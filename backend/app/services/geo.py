"""Geometri murni (tanpa dependensi): jarak Haversine & penjarangan jejak.

Penjarangan HANYA untuk tampilan (peta/riwayat). Data mentah di DB dan export GPX
tetap resolusi penuh.
"""
from __future__ import annotations

import math

EARTH_R_M = 6371008.8  # harus sama dengan fungsi SQL geo_dist_m di core/schema.py


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_M * math.asin(min(1.0, math.sqrt(a)))


def _project(coords):
    """lat/lon -> meter datar lokal (cukup akurat untuk jejak gunung berskala km)."""
    lat0 = sum(c[0] for c in coords) / len(coords)
    kx = math.cos(math.radians(lat0)) * 111320.0
    return [(c[1] * kx, c[0] * 110540.0) for c in coords]


def _perp_dist(p, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0 and dy == 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def dist_point_to_trail_m(point, trail) -> float:
    """Jarak terpendek (meter) dari sebuah titik ke garis jalur (polyline).

    Konvensi KETAT: semua koordinat LAT DULU, (lat, lon) — sama dengan kolom
    `trail` di tabel sites. JANGAN menukar lat/lon (bug historis #1 proyek ini).

    - `point`  = (lat, lon)
    - `trail`  = [(lat, lon), ...]

    Dipakai ulang _project (lat/lon -> meter datar lokal) + _perp_dist (titik ke
    segmen di bidang meter), tidak ada rumus jarak baru. Proyeksi memakai lat0 dari
    gabungan titik + trail supaya titik dan segmen berada di bidang meter yang sama.

    Kasus batas:
    - trail kosong -> float('inf') (artinya "tidak ada jalur", pemanggil melewati).
    - trail 1 titik -> jarak ke titik itu.
    """
    if not trail:
        return float("inf")
    proj = _project([point] + list(trail))
    p = proj[0]
    pts = proj[1:]
    if len(pts) == 1:
        return math.hypot(p[0] - pts[0][0], p[1] - pts[0][1])
    best = float("inf")
    for a, b in zip(pts, pts[1:]):
        d = _perp_dist(p, a, b)
        if d < best:
            best = d
    return best


def choose_window_minutes(dist_m: float, perimeter_m: float, inside_min: int, outside_min: int) -> int:
    """Pilih window stagnan: di dalam koridor (jarak <= perimeter) -> inside_min (panjang),
    di luar -> outside_min (pendek). Murni biar bisa diuji unit."""
    return inside_min if dist_m <= perimeter_m else outside_min


def is_off_trail(recent_points, trail, perimeter_m: float, debounce_n: int = 3) -> bool:
    """Apakah sebuah sesi dianggap "di luar jalur" (keluar koridor perimeter).

    MENGAPA debounce: fix GPS di bawah kanopi bisa melonjak 10-30 m untuk SATU paket.
    Satu paket di luar perimeter belum tentu pendaki benar-benar menyimpang; bisa sekadar
    lonjakan. Maka peringatan baru dinyalakan bila `debounce_n` paket (dengan fix) TERBARU
    SEMUA di luar koridor. Paket ~5 detik sekali (firmware), jadi 3 paket ~15 detik:
    cukup menapis lonjakan tanpa menunda peringatan dini terlalu lama.

    Sinyal ini TAMBAHAN, bukan pengganti deteksi stagnan (Auto-SOS). Memakai ulang
    `dist_point_to_trail_m` (tidak ada rumus jarak baru) dan perimeter yang sama.

    Argumen:
    - `recent_points`: daftar titik `(lat, lon)` TERURUT dari TERBARU ke TERLAMA
      (indeks 0 = paling baru). Hanya titik yang punya fix (pemanggil menyaring None).
    - `trail`: `[(lat, lon), ...]` (LAT DULU; sama konvensi dengan `dist_point_to_trail_m`).
      JANGAN tukar lat/lon (bug historis #1 proyek ini).
    - `perimeter_m`: lebar koridor (meter). Jarak > perimeter dianggap "di luar".
    - `debounce_n`: berapa paket terbaru yang harus semuanya di luar.

    Kembalikan boolean SUNGGUHAN (bukan nilai falsy kebetulan).
    Kasus batas:
    - trail < 2 titik -> False (tidak ada acuan koridor; pemanggil juga melewati lebih awal).
    - jumlah titik < debounce_n -> False (belum cukup bukti).
    - daftar kosong -> False.
    """
    if trail is None or len(trail) < 2:
        return False
    if debounce_n < 1 or len(recent_points) < debounce_n:
        return False
    for pt in recent_points[:debounce_n]:
        if dist_point_to_trail_m(pt, trail) <= perimeter_m:
            return False
    return True


def _rdp(xy, eps: float) -> list[int]:
    """Ramer-Douglas-Peucker iteratif. Return indeks yang dipertahankan (terurut)."""
    n = len(xy)
    keep = [False] * n
    keep[0] = keep[n - 1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        dmax, idx = 0.0, -1
        for k in range(i + 1, j):
            d = _perp_dist(xy[k], xy[i], xy[j])
            if d > dmax:
                dmax, idx = d, k
        if dmax > eps:
            keep[idx] = True
            stack.append((i, idx))
            stack.append((idx, j))
    return [k for k, v in enumerate(keep) if v]


_PRE_LIMIT = 6000


def thin_indices(coords: list[tuple[float, float]], max_points: int) -> list[int]:
    """Indeks titik yang dipertahankan (<= max_points), titik pertama & terakhir selalu ikut,
    bentuk jejak dijaga (belokan tidak hilang). coords = [(lat, lon), ...] urut waktu."""
    n = len(coords)
    if max_points < 2:
        max_points = 2
    if n <= max_points:
        return list(range(n))

    # prafilter kasar supaya RDP tidak lambat di sesi yang sangat panjang
    base = list(range(n))
    if n > _PRE_LIMIT:
        stride = math.ceil(n / _PRE_LIMIT)
        base = list(range(0, n, stride))
        if base[-1] != n - 1:
            base.append(n - 1)
    xy = _project([coords[i] for i in base])
    if len(base) <= max_points:
        return base

    # cari toleransi terkecil yang menghasilkan <= max_points titik (bisection)
    xs, ys = [p[0] for p in xy], [p[1] for p in xy]
    lo, hi = 0.0, math.hypot(max(xs) - min(xs), max(ys) - min(ys)) + 1.0
    best = _rdp(xy, hi)
    for _ in range(14):
        mid = (lo + hi) / 2
        kept = _rdp(xy, mid)
        if len(kept) <= max_points:
            best, hi = kept, mid
        else:
            lo = mid
    return [base[k] for k in best]


def thin_track(rows: list[dict], max_points: int | None) -> list[dict]:
    """Jarangkan list baris {lat, lon, ...}. max_points None/0 = tanpa penjarangan."""
    if not max_points or len(rows) <= max_points:
        return rows
    idx = thin_indices([(r["lat"], r["lon"]) for r in rows], max_points)
    return [rows[i] for i in idx]
