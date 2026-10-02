"""Tabel yang dibuat saat backend start (idempotent). init.sql cuma jalan di
DB baru, jadi tabel fitur Setup dibuat di sini biar DB lama tetap kebagian."""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sites (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'processing',   -- processing | ready | error
    message     TEXT,
    is_active   BOOLEAN NOT NULL DEFAULT FALSE,
    dem_info    JSONB,                                 -- bounds, elevasi, resolusi, zoom tile
    base        JSONB,                                 -- {"lat":..,"lon":..}
    trail       JSONB NOT NULL DEFAULT '[]'::jsonb,    -- [[lat,lon],...]
    params      JSONB NOT NULL DEFAULT '{}'::jsonb,
    plan        JSONB,                                 -- hasil hitung relay terakhir
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS devices (
    id              SERIAL PRIMARY KEY,
    node_id         INTEGER UNIQUE NOT NULL,              -- node_id di firmware (1,2,3..) = H01,H02,..
    name            TEXT NOT NULL,                        -- node_name
    role            TEXT NOT NULL DEFAULT 'tracker',      -- tracker | relay | base
    config          JSONB NOT NULL DEFAULT '{}'::jsonb,   -- parameter radio/laporan
    config_version  INTEGER NOT NULL DEFAULT 1,           -- naik tiap config disimpan
    pushed_version  INTEGER NOT NULL DEFAULT 0,           -- versi terakhir yang dikonfirmasi sampai ke alat
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Antrean perintah ke hardware. Dashboard cuma MENULIS ke sini; yang benar-benar
-- ngirim ke alat adalah bridge serial (lihat reference-for-hardware-team).
CREATE TABLE IF NOT EXISTS device_commands (
    id          SERIAL PRIMARY KEY,
    device_id   INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    payload     JSONB NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',          -- pending | sent | acked | failed
    error       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_device_commands_status ON device_commands (status, id);

-- ══════════════════════════════════════════════════════════════
-- SESI PENDAKIAN. Alat (H01, H02, ..) permanen; yang berganti adalah sesinya:
-- satu sesi = satu perjalanan satu pendaki. Jejak, GPX, dan deteksi SOS dihitung
-- per sesi, jadi alat yang dipinjamkan lagi mulai dari jejak kosong.
-- ══════════════════════════════════════════════════════════════
ALTER TABLE hiking_sessions ADD COLUMN IF NOT EXISTS full_name TEXT;
ALTER TABLE hiking_sessions ADD COLUMN IF NOT EXISTS phone_number TEXT;
ALTER TABLE hiking_sessions ADD COLUMN IF NOT EXISTS emergency_contact TEXT;
-- TRUE = sesi dibuka otomatis karena alat mengirim data padahal belum di-check-in
ALTER TABLE hiking_sessions ADD COLUMN IF NOT EXISTS auto_opened BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS session_id INTEGER REFERENCES hiking_sessions(id);

-- Sebelum indeks unik dibuat: kalau ada >1 sesi 'active' per alat (data lama), sisakan yang terbaru.
UPDATE hiking_sessions SET status = 'completed', checked_out_at = COALESCE(checked_out_at, now())
WHERE status = 'active'
  AND id NOT IN (SELECT MAX(id) FROM hiking_sessions WHERE status = 'active' GROUP BY hiker_id);

-- satu alat hanya boleh punya satu sesi aktif
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_session_per_hiker ON hiking_sessions (hiker_id) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_positions_session_time ON positions (session_id, recorded_at DESC);

-- Migrasi data lama (sebelum ada sesi): tiap alat yang punya posisi tanpa sesi dibungkus jadi satu sesi.
-- Kalau alatnya masih hidup (data < 15 menit lalu) sesinya dibiarkan AKTIF supaya pendaki yang
-- sedang di gunung saat upgrade tidak kehilangan jejaknya di dashboard.
DO $$
DECLARE r RECORD; sid INTEGER;
BEGIN
    FOR r IN
        SELECT hiker_id, MIN(recorded_at) AS t0, MAX(recorded_at) AS t1
        FROM positions WHERE session_id IS NULL GROUP BY hiker_id
    LOOP
        IF r.t1 > now() - interval '15 minutes'
           AND NOT EXISTS (SELECT 1 FROM hiking_sessions WHERE hiker_id = r.hiker_id AND status = 'active') THEN
            INSERT INTO hiking_sessions (hiker_id, trail_name, checked_in_at, status, auto_opened)
            VALUES (r.hiker_id, 'Dilanjutkan dari data sebelum fitur sesi', r.t0, 'active', TRUE)
            RETURNING id INTO sid;
        ELSE
            INSERT INTO hiking_sessions (hiker_id, trail_name, checked_in_at, checked_out_at, status, full_name)
            VALUES (r.hiker_id, 'Riwayat sebelum fitur sesi', r.t0, r.t1, 'completed',
                    (SELECT full_name FROM hikers WHERE id = r.hiker_id))
            RETURNING id INTO sid;
        END IF;
        UPDATE positions SET session_id = sid WHERE hiker_id = r.hiker_id AND session_id IS NULL;
        UPDATE alerts SET session_id = sid WHERE hiker_id = r.hiker_id AND session_id IS NULL;
    END LOOP;
END $$;

-- Setiap posisi baru OTOMATIS ditempel ke sesi aktif alatnya, apa pun jalur masuknya
-- (bridge serial, seed, impor CSV). Kalau belum ada sesi aktif, sesi dibuka otomatis dan
-- ditandai "belum check-in": data tidak pernah dibuang dan pendaki tidak pernah tersembunyi.
CREATE OR REPLACE FUNCTION assign_position_session() RETURNS trigger AS $$
DECLARE sid INTEGER;
BEGIN
    IF NEW.session_id IS NOT NULL THEN RETURN NEW; END IF;
    SELECT id INTO sid FROM hiking_sessions WHERE hiker_id = NEW.hiker_id AND status = 'active' LIMIT 1;
    IF sid IS NULL THEN
        INSERT INTO hiking_sessions (hiker_id, checked_in_at, status, auto_opened)
        VALUES (NEW.hiker_id, now(), 'active', TRUE)
        ON CONFLICT (hiker_id) WHERE status = 'active' DO NOTHING
        RETURNING id INTO sid;
        IF sid IS NULL THEN  -- keduluan insert lain di saat yang sama
            SELECT id INTO sid FROM hiking_sessions WHERE hiker_id = NEW.hiker_id AND status = 'active' LIMIT 1;
        END IF;
    END IF;
    NEW.session_id := sid;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_assign_session ON positions;
CREATE TRIGGER trg_assign_session BEFORE INSERT ON positions
    FOR EACH ROW EXECUTE FUNCTION assign_position_session();

-- Paket TANPA GPS fix tetap disimpan (bahan PDR & indikator "GPS invalid / lokasi terakhir").
ALTER TABLE positions ALTER COLUMN location DROP NOT NULL;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS gps_valid BOOLEAN;        -- NULL = data lama (anggap valid kalau ada lokasi)
ALTER TABLE positions ADD COLUMN IF NOT EXISTS gps_flags TEXT;           -- mentah dari firmware, buat diselidiki
ALTER TABLE positions ADD COLUMN IF NOT EXISTS time_from_gps BOOLEAN NOT NULL DEFAULT FALSE;  -- recorded_at asli dari GPS? (syarat hitung latency)

-- sama dengan versi di init.sql + session_id (dipakai dashboard buat tahu kalau sesi berganti)
CREATE OR REPLACE FUNCTION notify_position_insert() RETURNS trigger AS $$
DECLARE
    v_hiker_code TEXT;
BEGIN
    SELECT hiker_code INTO v_hiker_code FROM hikers WHERE id = NEW.hiker_id;
    PERFORM pg_notify(
        'position_updates',
        json_build_object(
            'hiker_code', v_hiker_code,
            'session_id', NEW.session_id,
            'lat', ST_Y(NEW.location::geometry),
            'lon', ST_X(NEW.location::geometry),
            'elevation', NEW.elevation,
            'battery_pct', NEW.battery_pct,
            'hop_count', NEW.hop_count,
            'route_path', NEW.route_path,
            'rssi_dbm', NEW.rssi_dbm,
            'satellites', NEW.satellites,
            'hdop', NEW.hdop,
            'gps_valid', NEW.gps_valid,
            'recorded_at', NEW.recorded_at,
            'received_at', NEW.received_at
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


async def ensure_schema(conn) -> None:
    await conn.execute(SCHEMA_SQL)