from datetime import datetime


async def insert_position(
    conn,
    hiker_id: int,
    lat: float,
    lon: float,
    recorded_at: datetime,
    elevation: float | None = None,
    hop_count: int | None = None,
    route_path: str | None = None,
    sequence: int | None = None,
    rssi_dbm: int | None = None,
    satellites: int | None = None,
    hdop: float | None = None,
    missing_since_previous: int | None = None,
    total_missing: int | None = None,
    battery_pct: float | None = None,  # belum ada di firmware saat ini, tetap NULL
    session_id: int | None = None,
):
    await conn.execute(
        """
        INSERT INTO positions
            (hiker_id, session_id, location, elevation, hop_count, route_path,
             sequence, rssi_dbm, satellites, hdop, missing_since_previous,
             total_missing, battery_pct, recorded_at)
        VALUES
            ($1, $2, ST_SetSRID(ST_MakePoint($3, $4), 4326)::geography, $5, $6, $7,
             $8, $9, $10, $11, $12, $13, $14, $15)
        """,
        hiker_id,
        session_id,
        lon,
        lat,
        elevation,
        hop_count,
        route_path,
        sequence,
        rssi_dbm,
        satellites,
        hdop,
        missing_since_previous,
        total_missing,
        battery_pct,
        recorded_at,
    )


async def get_latest_positions(conn):
    """Posisi terakhir tiap SESI AKTIF - buat render marker awal di peta.
    Sesi yang sudah di-check-out tidak ikut (jejaknya ada di riwayat)."""
    rows = await conn.fetch(
        """
        -- field paket = paket TERBARU; koordinat = fix TERAKHIR (last known location) kalau paket terbaru tanpa fix
        SELECT DISTINCT ON (p.session_id)
            h.hiker_code,
            p.session_id,
            ST_Y(k.location::geometry) AS lat,
            ST_X(k.location::geometry) AS lon,
            k.elevation,
            p.battery_pct,
            p.hop_count,
            p.route_path,
            p.rssi_dbm,
            p.satellites,
            p.hdop,
            COALESCE(p.gps_valid, p.location IS NOT NULL) AS gps_valid,
            p.recorded_at,
            p.received_at
        FROM positions p
        JOIN hiking_sessions s ON s.id = p.session_id AND s.status = 'active'
        JOIN hikers h ON h.id = s.hiker_id
        LEFT JOIN LATERAL (
            SELECT q.location, q.elevation FROM positions q
            WHERE q.session_id = p.session_id AND q.location IS NOT NULL
            ORDER BY q.recorded_at DESC LIMIT 1
        ) k ON TRUE
        ORDER BY p.session_id, p.recorded_at DESC
        """
    )
    return [dict(r) for r in rows]


async def resolve_session_id(conn, hiker_code: str) -> int | None:
    """Sesi aktif milik alat ini; kalau tidak ada, sesi terakhirnya."""
    return await conn.fetchval(
        """
        SELECT s.id FROM hiking_sessions s JOIN hikers h ON h.id = s.hiker_id
        WHERE h.hiker_code = $1
        ORDER BY (s.status = 'active') DESC, s.id DESC
        LIMIT 1
        """,
        hiker_code,
    )


async def get_session_track(conn, session_id: int):
    """Semua titik jejak SATU sesi, urut waktu - dipakai buat peta & GPX export."""
    rows = await conn.fetch(
        """
        SELECT
            ST_Y(p.location::geometry) AS lat,
            ST_X(p.location::geometry) AS lon,
            p.elevation,
            p.recorded_at
        FROM positions p
        WHERE p.session_id = $1 AND p.location IS NOT NULL
        ORDER BY p.recorded_at ASC
        """,
        session_id,
    )
    return [dict(r) for r in rows]


async def get_track_points(conn, hiker_code: str):
    """Jejak sesi AKTIF alat ini (atau sesi terakhirnya) - BUKAN semua riwayat alat itu,
    supaya perjalanan pendaki sebelumnya tidak tercampur."""
    sid = await resolve_session_id(conn, hiker_code)
    return await get_session_track(conn, sid) if sid else []


async def find_stagnant_sessions(conn, window_minutes: int, radius_m: float):
    """
    Deteksi SESI AKTIF yang seluruh titiknya dalam `window_minutes` terakhir
    berada dalam radius `radius_m` dari posisi terbarunya (indikasi diam/stagnan).
    Dihitung per sesi: data dari sesi/perjalanan lain tidak pernah ikut terhitung.
    """
    rows = await conn.fetch(
        """
        SELECT s.id AS session_id, s.hiker_id
        FROM hiking_sessions s
        JOIN LATERAL (
            SELECT location FROM positions WHERE session_id = s.id AND location IS NOT NULL
            ORDER BY recorded_at DESC LIMIT 1
        ) last ON TRUE
        WHERE s.status = 'active'
        -- semua titik sesi ini dalam window HARUS dekat posisi terakhir
        AND NOT EXISTS (
            SELECT 1 FROM positions p3
            WHERE p3.session_id = s.id
              AND p3.location IS NOT NULL
              AND p3.recorded_at >= NOW() - make_interval(mins => $1)
              AND NOT ST_DWithin(p3.location, last.location, $2)
        )
        -- pastikan window-nya beneran penuh terisi: harus ada titik di 10 menit PERTAMA window
        AND EXISTS (
            SELECT 1 FROM positions p4
            WHERE p4.session_id = s.id
              AND p4.recorded_at >= NOW() - make_interval(mins => $1)
              AND p4.recorded_at <= NOW() - make_interval(mins => $1) + interval '10 minutes'
        )
        """,
        window_minutes,
        radius_m,
    )
    return [dict(r) for r in rows]
