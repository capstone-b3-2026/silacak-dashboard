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
