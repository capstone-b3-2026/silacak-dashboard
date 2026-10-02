"""
Generator data sintetis buat development dashboard SiLacak, dipakai
selama hardware LoRa masih dalam pengembangan.

Simulasi 3 pendaki:
- H01, H02 : bergerak pelan-pelan sepanjang jalur dummy
- H03      : SENGAJA dikunci diam di satu titik, buat nge-test
             apakah Auto-SOS "stagnan" beneran ke-trigger.

Cara pakai:
    cd backend
    pip install asyncpg   # kalau belum ada, atau tinggal jalanin di
                           # dalam container backend yang sudah py deps-nya
    python scripts/seed_synthetic_data.py

Otomatis ngikut lokasi aktif di dashboard (halaman Setup):
- jalur simulasi  = trail yang digambar di Setup (kalau belum ada: TRAIL_WAYPOINTS di bawah)
- elevasi         = dibaca dari DEM (TIF) lokasi aktif, jadi cocok sama peta 3D
Jadi ganti TIF / gambar trail baru nggak perlu edit file ini lagi.
"""

import asyncio
import json
import math
import os
import random
from datetime import datetime, timedelta, timezone

import asyncpg

# Kalau dijalankan lewat `docker compose exec backend ...`, DATABASE_URL
# sudah otomatis ke-inject dari backend/.env (host "db"). Fallback ke
# localhost cuma buat jaga-jaga kalau script ini dijalankan langsung di
# host (bukan di dalam container).
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://silacak:silacak@localhost:5432/silacak"
)

# Perkiraan kasar jalur Bukit Klangon (Kalitengah Lor, Glagaharjo,
# Cangkringan, Sleman) berdasarkan titik yang tersedia di direktori
# trail online - BUKAN hasil digitasi GPX asli, jarak & bentuknya cuma
# ilustrasi kasar.
#
# GANTI ini klo udh sempat jalan/naik ke lokasi bawa app GPS logger
# (Google Maps "record path", OsmAnd, atau Gaia GPS) - satu file .gpx
# hasil rekaman itu bisa dipake deh buat 3 hal sekaligus: (1) waypoint
# simulasi yang jauh lebih akurat di sini, (2) nentuin bounding box
# buat clip DEM & download tile basemap, (3) jadi ground-truth buat
# validasi akurasi GPS node asli nanti (fitur Node Diagnostics).
TRAIL_WAYPOINTS = [
    (-7.5850, 110.4500),  # perkiraan area parkir/start
    (-7.5825, 110.4515),
    (-7.5805, 110.4525),
    (-7.5788, 110.4535),
    (-7.5779, 110.4541),
    (-7.5772, 110.4546),  # titik viewpoint/puncak (AllTrails pin)
]

# Elevasi kasar tiap waypoint di atas (meter) - perkiraan garis naik
# landai khas jalur pendakian, BUKAN data DEM asli. Dipasangkan index-nya
# sama TRAIL_WAYPOINTS. Ganti begitu ada data GPX/DEM asli (lihat catatan
# di atas).
ELEVATION_WAYPOINTS = [1150, 1280, 1420, 1560, 1680, 1750]

HIKERS = [
    {"hiker_code": "H01", "full_name": "Pendaki Satu", "moving": True},
    {"hiker_code": "H02", "full_name": "Pendaki Dua", "moving": True},
    {"hiker_code": "H03", "full_name": "Pendaki Tiga (uji SOS)", "moving": False},
]

TICK_SECONDS = 5
PROGRESS_PER_TICK = 0.01  # kecepatan gerak simulasi sepanjang trail


async def ensure_hikers(conn) -> dict[str, int]:
    ids: dict[str, int] = {}
    for h in HIKERS:
        row = await conn.fetchrow(
            "SELECT id FROM hikers WHERE hiker_code = $1", h["hiker_code"]
        )
        if row is None:
            row = await conn.fetchrow(
                "INSERT INTO hikers (hiker_code, full_name) VALUES ($1, $2) RETURNING id",
                h["hiker_code"],
                h["full_name"],
            )
        ids[h["hiker_code"]] = row["id"]
    return ids


# ── konteks lokasi aktif (diisi di main) ─────────────────────────────
ROUTE: list[tuple[float, float]] = list(TRAIL_WAYPOINTS)
ROUTE_FALLBACK_ELEV: list[float] | None = list(ELEVATION_WAYPOINTS)
DEM = None  # DemSampler | None
_cum: list[float] = []  # jarak kumulatif sepanjang ROUTE (meter, pendekatan datar)


class DemSampler:
    """Elevasi bilinear dari dem.tif hasil upload (EPSG:4326, dinormalisasi backend)."""

    def __init__(self, path: str):
        import rasterio  # import di sini biar script tetap jalan (tanpa DEM) kalau rasterio nggak ada

        with rasterio.open(path) as src:
            self.a = src.read(1).astype("float64")
            self.left, self.top = src.bounds.left, src.bounds.top
            self.right, self.bottom = src.bounds.right, src.bounds.bottom
            self.rx, self.ry = src.res

    def inside(self, lat: float, lon: float) -> bool:
        return self.left <= lon <= self.right and self.bottom <= lat <= self.top

    def at(self, lat: float, lon: float) -> float:
        from scipy.ndimage import map_coordinates

        c = (lon - self.left) / self.rx - 0.5
        r = (self.top - lat) / self.ry - 0.5
        return float(map_coordinates(self.a, [[r], [c]], order=1, mode="nearest")[0])


def _seg_m(p1, p2) -> float:
    dy = (p2[0] - p1[0]) * 110574
    dx = (p2[1] - p1[1]) * 111320 * math.cos(math.radians((p1[0] + p2[0]) / 2))
    return math.hypot(dx, dy)


async def load_site_context(conn) -> None:
    """Ambil trail + DEM dari lokasi aktif. Semua opsional: kalau nggak ada, pakai nilai bawaan."""
    global ROUTE, ROUTE_FALLBACK_ELEV, DEM, _cum
    row = await conn.fetchrow(
        "SELECT id, name, trail FROM sites WHERE is_active AND status='ready' ORDER BY id DESC LIMIT 1"
    )
    if row is None:
        print("Belum ada lokasi aktif di dashboard -> pakai TRAIL_WAYPOINTS bawaan, elevasi perkiraan.")
    else:
        trail = row["trail"]
        trail = json.loads(trail) if isinstance(trail, str) else trail
        data_dir = os.environ.get("DATA_DIR", "/app/data")
        dem_path = os.path.join(data_dir, "sites", str(row["id"]), "dem.tif")
        try:
            DEM = DemSampler(dem_path)
            print(f"Lokasi aktif: {row['name']!r} - elevasi dibaca dari DEM.")
        except Exception as exc:  # noqa: BLE001
            print(f"DEM lokasi aktif nggak bisa dibuka ({exc}) -> elevasi perkiraan/kosong.")
        if len(trail) >= 2:
            ROUTE = [(float(a), float(b)) for a, b in trail]
            ROUTE_FALLBACK_ELEV = None
            print(f"Jalur simulasi = trail dari Setup ({len(ROUTE)} titik).")
        elif DEM and not all(DEM.inside(*p) for p in TRAIL_WAYPOINTS):
            print("PERINGATAN: jalur bawaan di luar cakupan DEM aktif. Gambar trail di Setup supaya simulasi ada di lokasi yang benar.")
    _cum = [0.0]
    for i in range(1, len(ROUTE)):
        _cum.append(_cum[-1] + _seg_m(ROUTE[i - 1], ROUTE[i]))


def interpolate(progress: float) -> tuple[float, float, float | None]:
    """(lat, lon, elevation) di titik `progress` (0..1) sepanjang jalur, rata per jarak
    (bukan per segmen), jadi kecepatan simulasi konstan walau jarak antar titik beda-beda."""
    total = _cum[-1] or 1.0
    d = min(max(progress, 0.0), 0.999) * total
    idx = max(i for i in range(len(_cum) - 1) if _cum[i] <= d) if len(_cum) > 1 else 0
    seg = (_cum[idx + 1] - _cum[idx]) or 1.0
    t = (d - _cum[idx]) / seg
    (lat1, lon1), (lat2, lon2) = ROUTE[idx], ROUTE[min(idx + 1, len(ROUTE) - 1)]
    lat = lat1 + (lat2 - lat1) * t
    lon = lon1 + (lon2 - lon1) * t

    elevation: float | None
    if DEM is not None and DEM.inside(lat, lon):
        elevation = DEM.at(lat, lon)
    elif ROUTE_FALLBACK_ELEV is not None:
        e1 = ROUTE_FALLBACK_ELEV[idx]
        e2 = ROUTE_FALLBACK_ELEV[min(idx + 1, len(ROUTE) - 1)]
        elevation = e1 + (e2 - e1) * t
    else:
        elevation = None

    # jitter kecil biar nggak persis satu garis lurus (mirip noise GPS asli)
    jitter = 0.00003
    return (
        lat + random.uniform(-jitter, jitter),
        lon + random.uniform(-jitter, jitter),
        round(elevation, 1) if elevation is not None else None,
    )


async def insert_position(
    conn,
    hiker_id: int,
    lat: float,
    lon: float,
    elevation: float | None,
    seq: int,
    rssi: int,
    hop: int,
    route: str,
    sats: int,
    hdop: float,
) -> None:
    now = datetime.now(timezone.utc)
    await conn.execute(
        """
        INSERT INTO positions
            (hiker_id, location, elevation, sequence, rssi_dbm, hop_count,
             route_path, satellites, hdop, recorded_at, received_at)
        VALUES
            ($1, ST_SetSRID(ST_MakePoint($2, $3), 4326)::geography,
             $4, $5, $6, $7, $8, $9, $10, $11, $12)
        """,
        hiker_id,
        lon,
        lat,
        elevation,
        seq,
        rssi,
        hop,
        route,
        sats,
        hdop,
        # recorded_at dibuat sedikit lebih lama dari received_at supaya
        # nanti latency (received_at - recorded_at) nggak selalu 0
        now - timedelta(milliseconds=random.randint(300, 2500)),
        now,
    )


async def main() -> None:
    conn = await asyncpg.connect(dsn=DATABASE_URL)
    hiker_ids = await ensure_hikers(conn)
    await load_site_context(conn)

    progress = {h["hiker_code"]: 0.0 for h in HIKERS}
    direction = {h["hiker_code"]: 1 for h in HIKERS}  # +1 naik, -1 turun
    seq = {h["hiker_code"]: 0 for h in HIKERS}

    # H03 dikunci di satu titik tetap dari awal (simulasi stagnan)
    frozen_progress = 0.3
    frozen_point = interpolate(frozen_progress)

    print(f"Generator jalan tiap {TICK_SECONDS} detik. Ctrl+C buat stop.")
    print(f"H03 dikunci di titik {frozen_point[:2]} buat uji Auto-SOS.\n")

    try:
        while True:
            for h in HIKERS:
                code = h["hiker_code"]

                if h["moving"]:
                    p = progress[code] + direction[code] * PROGRESS_PER_TICK
                    if p >= 1.0 or p <= 0.0:  # bolak-balik, jangan berhenti di ujung
                        direction[code] *= -1
                        p = max(0.0, min(1.0, p))
                    progress[code] = p
                    lat, lon, elevation = interpolate(p)
                else:
                    p = frozen_progress
                    lat, lon, elevation = frozen_point

                seq[code] += 1
                hop = 0 if p < 0.25 else (1 if p < 0.6 else 2)
                route = "LANGSUNG" if hop == 0 else ">".join(f"R{i + 1}" for i in range(hop))
                rssi = int(-65 - 45 * p + random.uniform(-4, 4))
                sats = random.randint(7, 12)
                hdop = round(random.uniform(0.8, 2.0), 1)

                await insert_position(
                    conn, hiker_ids[code], lat, lon, elevation,
                    seq[code], rssi, hop, route, sats, hdop,
                )
                print(f"{code}: {lat:.6f}, {lon:.6f}  alt={elevation}m  rssi={rssi}  hop={hop}")

            await asyncio.sleep(TICK_SECONDS)
    except KeyboardInterrupt:
        print("\nStop.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())