-- =========================================================
-- SiLacak - Init Schema
-- Dijalankan otomatis oleh image timescaledb-ha saat container
-- db pertama kali dibuat (lewat /docker-entrypoint-initdb.d/).
-- =========================================================

CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS postgis;

-- ---------------------------------------------------------
-- Data operasional (relasional biasa)
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS hikers (
    id              SERIAL PRIMARY KEY,
    hiker_code      TEXT UNIQUE NOT NULL,   -- contoh: "H01" -- harus match ID yang dikirim node LoRa
    full_name       TEXT,
    phone_number    TEXT,
    emergency_contact TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
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
    alert_type      TEXT NOT NULL,          -- STAGNANT | MANUAL_SOS | LOW_BATTERY
    status          TEXT NOT NULL DEFAULT 'ACTIVE', -- ACTIVE | ACKNOWLEDGED | RESOLVED
    triggered_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at     TIMESTAMPTZ,
    meta            JSONB
);

CREATE INDEX IF NOT EXISTS idx_alerts_hiker_status ON alerts (hiker_id, status);

-- ---------------------------------------------------------
-- Data time-series (hypertable TimescaleDB)
-- ---------------------------------------------------------

CREATE TABLE IF NOT EXISTS positions (
    hiker_id                INTEGER NOT NULL REFERENCES hikers(id),
    session_id              INTEGER REFERENCES hiking_sessions(id),
    location                GEOGRAPHY(Point, 4326),  -- NULL = paket tanpa GPS fix
    elevation               DOUBLE PRECISION,

    -- field mesh/radio - persis sesuai baris CSV_DATA dari base_real.cpp /
    -- base_optimized.cpp (lihat protocol.h & tools/serial_logger.py punya
    -- tim hardware). hop_count = routeLength, route_path = jalur human-
    -- readable ("R2>R5" / "LANGSUNG").
    hop_count               INTEGER,
    route_path              TEXT,
    sequence                BIGINT,
    rssi_dbm                SMALLINT,
    missing_since_previous  INTEGER,
    total_missing           INTEGER,

    -- kualitas fix GPS - dikirim langsung oleh node, bukan diukur di sisi
    -- dashboard. Dipakai buat fitur Node Diagnostics nanti.
    satellites               SMALLINT,
    hdop                     DOUBLE PRECISION,

    -- CATATAN: firmware saat ini TIDAK mengirim data baterai sama sekali
    -- (tidak ada sensor di DataPacket). Kolom ini sengaja dibiarkan nullable
    -- buat jaga-jaga kalau revisi hardware berikutnya nambahin sensor itu -
    -- selama itu belum ada, kolom ini akan selalu NULL, itu wajar.
    battery_pct              DOUBLE PRECISION,

    recorded_at              TIMESTAMPTZ NOT NULL,  -- dari GPS (gps_utc) node, BUKAN dari millis() uptime
    received_at              TIMESTAMPTZ NOT NULL DEFAULT now()  -- waktu masuk DB (buat hitung latency mesh)
);

SELECT create_hypertable('positions', 'recorded_at', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_positions_hiker_time ON positions (hiker_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_positions_geo ON positions USING GIST (location);

-- ---------------------------------------------------------
-- Trigger: broadcast posisi baru via pg_notify (dipakai backend
-- buat push live update ke dashboard lewat SSE, tanpa polling).
-- ---------------------------------------------------------

CREATE OR REPLACE FUNCTION notify_position_insert() RETURNS trigger AS $$
DECLARE
    v_hiker_code TEXT;
BEGIN
    SELECT hiker_code INTO v_hiker_code FROM hikers WHERE id = NEW.hiker_id;

    PERFORM pg_notify(
        'position_updates',
        json_build_object(
            'hiker_code', v_hiker_code,
            'lat', ST_Y(NEW.location::geometry),
            'lon', ST_X(NEW.location::geometry),
            'elevation', NEW.elevation,
            'battery_pct', NEW.battery_pct,
            'hop_count', NEW.hop_count,
            'route_path', NEW.route_path,
            'rssi_dbm', NEW.rssi_dbm,
            'satellites', NEW.satellites,
            'hdop', NEW.hdop,
            'recorded_at', NEW.recorded_at
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_notify_position ON positions;
CREATE TRIGGER trg_notify_position
    AFTER INSERT ON positions
    FOR EACH ROW EXECUTE FUNCTION notify_position_insert();

-- ---------------------------------------------------------
-- Seed data awal buat development (boleh dihapus di production)
-- ---------------------------------------------------------

INSERT INTO hikers (hiker_code, full_name)
VALUES ('H01', 'Pendaki Satu'), ('H02', 'Pendaki Dua'), ('H03', 'Pendaki Tiga (uji SOS)')
ON CONFLICT (hiker_code) DO NOTHING;
