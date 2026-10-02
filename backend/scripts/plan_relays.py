"""
Jalanin analisis LOS/Fresnel + algoritma greedy buat nyaranin lokasi
relay LoRa. Dua preset:

    python scripts/plan_relays.py ft_ugm         # tes cepat, DEM sintetis
    python scripts/plan_relays.py bukit_klangon   # DEM asli (hasil unggah di Setup, atau set DEM_PATH)

Lihat catatan di terrain_planner.py soal kenapa FT UGM pakai elevasi
sintetis (bukan buat validasi propagasi asli, cuma buat mbuktiin kode-nya
jalan bener sebelum dipakai ke data sungguhan).
"""

import math
import os
import sys

# Cari folder backend/ relatif ke LOKASI FILE INI SENDIRI (bukan folder
# kerja terminal) - jadi script ini tetep nemu `app.services...` gak
# peduli kamu jalaninnya dari mana (root project, dalam backend/, lewat
# docker exec, dll).
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND_DIR)

from app.services.terrain_planner import (
    RasterElevationSource,
    SyntheticElevationSource,
    haversine_km,
    los_profile,
    suggest_relay_chain,
)

# ───────────────────────── preset: FT UGM (tes cepat) ─────────────────────────
# Koordinat perkiraan area Bulaksumur utara (klaster FT UGM / Fak. Geografi),
# BUKAN hasil survei presisi - gampang banget diganti sendiri karena kamu
# lagi di lokasi (klik-kanan titik di Google Maps buat ambil koordinat pasti).
#
# Jalurnya dibikin LOOP ngelilingin gedung landmark 11 lantai di
# tengah-tengah, persis pola jalan portable node kalian yang sering
# kehalang pas lurus motong deket gedung itu. Base ditaruh di satu titik
# di ring, trail-nya titik-titik lain di sekeliling ring itu.
FT_UGM_BUILDING_CENTER = (-7.7645, 110.3755)
FT_UGM_RING_RADIUS_KM = 0.07  # ~70 m dari gedung - sesuaikan sama lebar jalan/plaza di sekitarnya


def _ring_points(center: tuple[float, float], radius_km: float, n: int) -> list[tuple[float, float]]:
    pts = []
    for i in range(n):
        angle = 2 * math.pi * i / n
        dx = radius_km * math.cos(angle)
        dy = radius_km * math.sin(angle)
        dlat = dy / 111.32
        dlon = dx / (111.32 * math.cos(math.radians(center[0])))
        pts.append((center[0] + dlat, center[1] + dlon))
    return pts


_ft_ugm_ring = _ring_points(FT_UGM_BUILDING_CENTER, FT_UGM_RING_RADIUS_KM, n=10)
FT_UGM_BASE = _ft_ugm_ring[0]
FT_UGM_TRAIL = _ft_ugm_ring[1:] + [_ft_ugm_ring[0]]  # muter penuh, balik lagi deket base


# ───────────────────────── preset: Bukit Klangon (data asli) ─────────────────────────
# Sama persis kayak TRAIL_WAYPOINTS di scripts/seed_synthetic_data.py.
BUKIT_KLANGON_BASE = (-7.5850, 110.4500)
BUKIT_KLANGON_TRAIL = [
    (-7.5825, 110.4515),
    (-7.5805, 110.4525),
    (-7.5788, 110.4535),
    (-7.5779, 110.4541),
    (-7.5772, 110.4546),
]
# Path DEM untuk preset bukit_klangon. Bawaan: DEM hasil unggah di halaman Setup
# (lokasi #1, path di dalam container). Ganti lewat variabel lingkungan DEM_PATH, mis.
#   docker compose exec -e DEM_PATH=/app/data/sites/2/dem.tif backend python scripts/plan_relays.py bukit_klangon
BUKIT_KLANGON_DEM_PATH = os.environ.get("DEM_PATH", "/app/data/sites/1/dem.tif")


def run(name: str, base, trail, elev_src, max_hop_km: float, search_radius_km: float = 0.3, search_step_km: float = 0.06):
    print(f"\n=== {name} ===")
    print(f"base: {base}")
    print(f"jumlah titik trail: {len(trail)}")
    plan = suggest_relay_chain(
        elev_src,
        base,
        trail,
        max_hop_km=max_hop_km,
        candidate_search_radius_km=search_radius_km,
        candidate_grid_step_km=search_step_km,
    )
    relays = plan.relays

    if not relays and plan.complete:
        print("Gak butuh relay sama sekali - base bisa langsung nge-cover semua trail. (Kalau ini preset FT_UGM dan hasilnya begini, cek dulu FT_UGM_BUMP_CENTER-nya beneran ada di antara base & trail.)")
        return

    origin = base
    for i, r in enumerate(relays, start=1):
        d = haversine_km(origin, (r.lat, r.lon))
        print(
            f"Relay #{i}: ({r.lat:.6f}, {r.lon:.6f})"
            f"  jarak dari hop sebelumnya: {d:.3f} km"
            f"  cover trail sampai index {r.covers_trail_index}"
            f"  margin Fresnel: {r.worst_margin_m:+.1f} m"
        )
        origin = (r.lat, r.lon)

    if not plan.complete:
        reason = {
            "no_candidate": "tidak ada posisi relay yang tersambung ke node sebelumnya sekaligus menjangkau titik baru",
            "max_relays": "batas jumlah relay tercapai",
        }[plan.stall_reason]
        print(
            f"PERINGATAN: MACET di titik trail index {plan.stalled_at} ({reason}). "
            f"Ke-cover sampai index {plan.covered_through}; {plan.uncovered_points} titik di ujung belum ke-cover. "
            "Coba perbesar candidate_search_radius_km/max_hop_km, atau geser titik trail itu."
        )
    else:
        print(f"Selesai - {len(relays)} relay cukup buat nge-cover seluruh trail.")


def run_rooftop_test(elev_src, building_center, building_height_m, mast_height_m, base, ring_points, max_hop_km, freq_mhz=915.0):
    """Bandingan: 1 relay dipasang DI ATAS gedung (bukan muter di
    sekitarnya) - antena relay-nya jadi setinggi gedung + tiang mast di
    atasnya. Cek apa dia bisa langsung nyambung ke base + semua titik
    ring sekaligus, dari SATU titik doang.

    max_hop_km sengaja DISAMAIN kayak tes ring (bukan dilonggarin) biar
    perbandingannya adil - ini murni ngetes efek TINGGI antena, bukan
    nyampur sama asumsi jarak jangkau yang beda."""
    relay_h = building_height_m + mast_height_m
    print(f"\n=== FT UGM - relay di ATAS gedung (tinggi antena {relay_h:.1f} m) ===")
    all_points = [("base", base)] + [(f"ring[{i}]", p) for i, p in enumerate(ring_points)]
    covered = 0
    for label, p in all_points:
        d = haversine_km(building_center, p)
        if d > max_hop_km:
            print(f"{label}: jarak {d:.3f} km > max_hop_km ({max_hop_km} km) - di luar jangkauan")
            continue
        res = los_profile(elev_src, building_center, p, antenna_h1_m=relay_h, antenna_h2_m=2.0, freq_mhz=freq_mhz)
        status = "CLEAR" if res.clear else "TERHALANG"
        print(f"{label}: {status}  (margin Fresnel {res.worst_margin_m:+.1f} m, jarak {d:.3f} km)")
        if res.clear:
            covered += 1
    print(f"\nHasil: {covered}/{len(all_points)} titik ke-cover LANGSUNG dari 1 relay di atap gedung.")


if __name__ == "__main__":
    preset = sys.argv[1] if len(sys.argv) > 1 else "ft_ugm"

    if preset == "ft_ugm":
        # Gedung 11 lantai di tengah ring - default 40m/35m footprint.
        # Naikin building_height_m atau perbesar radius kalau mau coba
        # lihat perilaku pas algoritma GAGAL nemu kandidat (harusnya
        # keluar peringatan, bukan crash atau ngasih hasil yang salah).
        src = SyntheticElevationSource(building_center=FT_UGM_BUILDING_CENTER)
        run(
            "FT UGM (sintetis, gedung 11 lantai di tengah ring) - 3 relay muter",
            FT_UGM_BASE,
            FT_UGM_TRAIL,
            src,
            max_hop_km=0.12,
            search_radius_km=0.05,
            search_step_km=0.01,
        )
        run_rooftop_test(
            src,
            FT_UGM_BUILDING_CENTER,
            building_height_m=40.0,
            mast_height_m=3.0,
            base=FT_UGM_BASE,
            ring_points=FT_UGM_TRAIL,
            max_hop_km=0.12,
        )

    elif preset == "bukit_klangon":
        try:
            src = RasterElevationSource(BUKIT_KLANGON_DEM_PATH)
        except Exception as e:
            print(f"Gagal buka DEM di {BUKIT_KLANGON_DEM_PATH}: {e}")
            print("Unggah DEM lewat halaman Setup (hasilnya di data/sites/<id>/dem.tif), atau set DEM_PATH ke berkas GeoTIFF.")
            sys.exit(1)
        run("Bukit Klangon (DEM asli)", BUKIT_KLANGON_BASE, BUKIT_KLANGON_TRAIL, src, max_hop_km=2.0)
        src.close()

    else:
        print(f"Preset gak dikenal: {preset!r}. Pilihannya: ft_ugm, bukit_klangon")
        sys.exit(1)