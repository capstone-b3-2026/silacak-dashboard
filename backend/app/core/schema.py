"""Seluruh skema dibuat/dimigrasi di sini saat backend start (idempotent), jadi
backend bisa jalan di PostgreSQL polos (mode portable tanpa Docker) maupun di
Docker Compose. Tidak ada extension wajib:

- PostGIS TIDAK dipakai. Posisi disimpan sebagai tipe bawaan `point` (x = lon, y = lat)
  dan jarak dihitung Haversine lewat fungsi SQL `geo_dist_m` (sesuai C-251 sec. 2.6.3).
  DB lama dengan kolom `geography` dimigrasi otomatis (butuh PostGIS yang masih terpasang).
- TimescaleDB OPSIONAL. Kalau extension-nya tersedia, `positions` dijadikan hypertable
  (profil server); kalau tidak, tabel biasa (profil basecamp). Lihat ensure_schema().
"""
import logging

log = logging.getLogger("silacak.schema")

BASE_SQL = """
CREATE TABLE IF NOT EXISTS hikers (
    id                SERIAL PRIMARY KEY,
    hiker_code        TEXT UNIQUE NOT NULL,   -- contoh: "H01" -- harus match ID yang dikirim node LoRa
    full_name         TEXT,
    phone_number      TEXT,
    emergency_contact TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS hiking_sessions (
    id              SERIAL PRIMARY KEY,
    hiker_id        INTEGER NOT NULL REFERENCES hikers(id),
    trail_name      TEXT,
    checked_in_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    checked_out_at  TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'active'  -- active | completed | emergency
);

CREATE TABLE IF NOT EXISTS alerts (
    id              SERIAL PRIMARY KEY,
    hiker_id        INTEGER NOT NULL REFERENCES hikers(id),
    alert_type      TEXT NOT NULL,                  -- STAGNANT | MANUAL_SOS | LOW_BATTERY
    status          TEXT NOT NULL DEFAULT 'ACTIVE', -- ACTIVE | ACKNOWLEDGED | RESOLVED
    triggered_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at     TIMESTAMPTZ,
    meta            JSONB
);
CREATE INDEX IF NOT EXISTS idx_alerts_hiker_status ON alerts (hiker_id, status);

-- Data time-series. location = point(lon, lat); NULL = paket tanpa GPS fix.
-- Kolom radio persis sesuai baris CSV_DATA dari base_real.cpp / base_optimized.cpp.
-- battery_pct: firmware saat ini TIDAK mengirim baterai -> selalu NULL (wajar).
CREATE TABLE IF NOT EXISTS positions (
    hiker_id                INTEGER NOT NULL REFERENCES hikers(id),
    session_id              INTEGER REFERENCES hiking_sessions(id),
    location                POINT,
    elevation               DOUBLE PRECISION,
    hop_count               INTEGER,
    route_path              TEXT,
    sequence                BIGINT,
    rssi_dbm                SMALLINT,
    missing_since_previous  INTEGER,
    total_missing           INTEGER,
    satellites              SMALLINT,
    hdop                    DOUBLE PRECISION,
    battery_pct             DOUBLE PRECISION,
    recorded_at             TIMESTAMPTZ NOT NULL,                -- jam GPS node (bukan millis())
    received_at             TIMESTAMPTZ NOT NULL DEFAULT now()   -- waktu masuk DB
);
CREATE INDEX IF NOT EXISTS idx_positions_hiker_time ON positions (hiker_id, recorded_at DESC);

-- Jarak dua titik (meter), rumus Haversine, bola bumi radius rata-rata 6371008.8 m.
-- Selisih terhadap jarak spheroid WGS84 (ex-PostGIS) < ~0.5%, kira-kira beberapa meter per km.
CREATE OR REPLACE FUNCTION geo_dist_m(p1 point, p2 point) RETURNS float8 AS $$
    SELECT CASE WHEN p1 IS NULL OR p2 IS NULL THEN NULL ELSE
        2 * 6371008.8 * asin(least(1.0, sqrt(
            power(sin(radians((p2)[1] - (p1)[1]) / 2), 2) +
            cos(radians((p1)[1])) * cos(radians((p2)[1])) *
            power(sin(radians((p2)[0] - (p1)[0]) / 2), 2)
        )))
    END
$$ LANGUAGE sql IMMUTABLE;
"""

# DB lama (sebelum PostGIS dibuang): kolom geography -> point. Idempotent: no-op kalau sudah point.
MIGRATE_GEOGRAPHY_SQL = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = current_schema() AND table_name = 'positions'
                 AND column_name = 'location' AND udt_name = 'geography') THEN
        DROP INDEX IF EXISTS idx_positions_geo;
        ALTER TABLE positions ALTER COLUMN location TYPE point
            USING (CASE WHEN location IS NULL THEN NULL
                        ELSE point(ST_X(location::geometry), ST_Y(location::geometry)) END);
    END IF;
END $$;
"""

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

-- Relay: dipasang di posisi R<n> pada rencana lokasi (plan.relays[].n). Data DASHBOARD saja (tidak dikirim ke alat),
-- dipakai untuk menggambar rute paket di peta: firmware menulis rute sebagai ID node relay mentah ("R5>R6").
ALTER TABLE devices ADD COLUMN IF NOT EXISTS plan_slot INTEGER;
CREATE UNIQUE INDEX IF NOT EXISTS uq_devices_plan_slot ON devices (plan_slot) WHERE plan_slot IS NOT NULL;

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
ALTER TABLE positions ADD COLUMN IF NOT EXISTS speed_kph REAL;           -- speed_kph dari CSV_DATA (NULL = bit SpeedValid tidak di-set)
ALTER TABLE positions ADD COLUMN IF NOT EXISTS rtt_ms INTEGER;           -- RTT diukur pendaki, dari baris CSV_TIMING (NULL = laporan tidak sampai)
ALTER TABLE positions ADD COLUMN IF NOT EXISTS sos BOOLEAN NOT NULL DEFAULT FALSE;  -- tombol SOS pendaki aktif saat paket ini dikirim (field ke-20 CSV_DATA)
ALTER TABLE positions ADD COLUMN IF NOT EXISTS serial_read_at TIMESTAMPTZ;  -- saat baris serial DIBACA laptop (received_at = saat masuk DB); NULL = data lama

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
            'lat', (NEW.location)[1],
            'lon', (NEW.location)[0],
            'elevation', NEW.elevation,
            'battery_pct', NEW.battery_pct,
            'hop_count', NEW.hop_count,
            'route_path', NEW.route_path,
            'rssi_dbm', NEW.rssi_dbm,
            'satellites', NEW.satellites,
            'hdop', NEW.hdop,
            'gps_valid', NEW.gps_valid,
            'sos', NEW.sos,
            'recorded_at', NEW.recorded_at,
            'time_from_gps', NEW.time_from_gps,
            'serial_read_at', NEW.serial_read_at,
            'received_at', NEW.received_at
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_notify_position ON positions;
CREATE TRIGGER trg_notify_position
    AFTER INSERT ON positions
    FOR EACH ROW EXECUTE FUNCTION notify_position_insert();

-- Satu paket radio = satu baris. Kunci: (pendaki, nomor urut firmware, jam GPS, status SOS). Paket ganda (relay + jalur
-- langsung, tulis ulang serial, dsb.) ditolak lewat ON CONFLICT DO NOTHING di kode simpan, jadi tidak ikut terhitung
-- sebagai "diterima" di PDR dan tidak memicu NOTIFY/SSE dua kali. `sos` ikut kunci supaya pergantian status SOS pada
-- nomor urut + jam yang sama tidak hilang. recorded_at ada di kunci (syarat hypertable TimescaleDB).
-- NULL sequence / paket tanpa jam GPS (recorded_at = waktu terima) tidak bisa dideduplikasi dan tetap tersimpan.
-- Bila DB lama sudah berisi paket ganda, indeks TIDAK dibuat (tidak ada data yang dihapus otomatis): jalankan
-- scripts/dedupe_positions.py lalu mulai ulang backend.
DO $$
BEGIN
    CREATE UNIQUE INDEX IF NOT EXISTS uq_positions_packet ON positions (hiker_id, sequence, recorded_at, sos);
EXCEPTION WHEN unique_violation THEN
    RAISE WARNING 'uq_positions_packet belum dibuat: ada paket ganda lama';
END $$;
"""


# Data pendukung dari base (bukan posisi pendaki): baterai relay, RSSI per hop, riwayat reboot pendaki.
RELAY_STATUS_SQL = """
CREATE TABLE IF NOT EXISTS relay_status (
    id             BIGSERIAL PRIMARY KEY,
    relay_id       INTEGER NOT NULL,              -- RELAY_ID di firmware (mis. 101)
    boot_id        BIGINT,
    sequence       BIGINT,
    battery_pct    SMALLINT,                      -- NULL = sensor tidak OK (lihat gauge_state)
    volts          DOUBLE PRECISION,
    gauge_state    TEXT NOT NULL,                 -- OK | NO_DEVICE | IO_ERROR | INVALID | STALE | WARMING_UP | UNKNOWN
    sample_age_ms  BIGINT,
    route_path     TEXT,
    hop_count      INTEGER,
    rssi_dbm       INTEGER,
    received_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_relay_status_relay_time ON relay_status (relay_id, received_at DESC);

CREATE TABLE IF NOT EXISTS link_hops (
    id           BIGSERIAL PRIMARY KEY,
    node_id      INTEGER NOT NULL,                -- pendaki
    boot_id      BIGINT,
    sequence     BIGINT,
    hops         JSONB NOT NULL,                  -- [{"relay_id":101,"rssi_dbm":-87}, ...] urutan pendaki -> base
    received_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_link_hops_node_time ON link_hops (node_id, received_at DESC);

CREATE TABLE IF NOT EXISTS node_boots (
    id           BIGSERIAL PRIMARY KEY,
    node_id      INTEGER NOT NULL,
    boot_id      BIGINT NOT NULL,
    received_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_node_boots_node_time ON node_boots (node_id, received_at DESC);
"""


async def _try_timescale(conn) -> bool:
    """Opsional: jadikan positions hypertable kalau TimescaleDB tersedia. Tidak pernah fatal."""
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb'"):
            return False
        await conn.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
        await conn.execute(
            "SELECT create_hypertable('positions', 'recorded_at', if_not_exists => TRUE, migrate_data => TRUE)"
        )
        return True
    except Exception as exc:  # noqa: BLE001 - extension bukan syarat; lanjut sebagai tabel biasa
        log.warning("TimescaleDB tersedia tapi gagal dipakai (%s); lanjut tanpa hypertable.", exc)
        return False


async def ensure_schema(conn) -> bool:
    """Buat/migrasi skema. Return True kalau positions berjalan sebagai hypertable TimescaleDB."""
    await conn.execute(BASE_SQL)
    await conn.execute(MIGRATE_GEOGRAPHY_SQL)
    await conn.execute(SCHEMA_SQL)
    await conn.execute(RELAY_STATUS_SQL)
    if not await conn.fetchval("SELECT 1 FROM pg_indexes WHERE indexname = 'uq_positions_packet'"):
        log.warning("Indeks anti-paket-ganda (uq_positions_packet) belum ada karena data lama berisi paket ganda. "
                    "Paket baru tetap diterima apa adanya. Jalankan: python scripts/dedupe_positions.py --apply, lalu mulai ulang.")
    return await _try_timescale(conn)