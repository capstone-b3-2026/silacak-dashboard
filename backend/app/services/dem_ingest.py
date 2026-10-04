"""
Pipeline DEM otomatis: satu file GeoTIFF masuk -> siap dipakai dashboard.

  1. normalize_dem : apa pun kondisi TIF-nya (CRS kosong, UTM, nodata aneh)
                     dijadikan GeoTIFF EPSG:4326 float32 yang seragam.
  2. build_tiles   : bikin tile elevasi Terrarium (PNG) buat mode 3D MapLibre.
  3. build_topo_tiles : peta topo OFFLINE (warna ketinggian + bayangan + garis kontur)
                     dari DEM yang sama - jadi basemap tanpa internet, tanpa lisensi pihak ketiga.
  4. GridElevation : sumber elevasi cepat (numpy) buat planner relay.
"""
from __future__ import annotations

import math
import os

import numpy as np
import rasterio
from PIL import Image
from rasterio.crs import CRS
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject
from scipy.ndimage import gaussian_filter, map_coordinates

from app.services.terrain_planner import ClutterSource, ElevationSource

TILE = 256
MAX_TILES = 4000  # pengaman: DEM terlalu luas -> turunin zoom maksimum otomatis


def normalize_dem(src_path: str, dst_path: str) -> dict:
    notes: list[str] = []
    with rasterio.open(src_path) as src:
        crs = src.crs
        if crs is None:
            b = src.bounds
            if -180 <= b.left < b.right <= 180 and -90 <= b.bottom < b.top <= 90:
                crs = CRS.from_epsg(4326)
                notes.append("File tidak punya CRS; koordinatnya derajat, dianggap EPSG:4326.")
            else:
                raise ValueError(
                    "File tidak punya CRS dan koordinatnya bukan derajat lat/lon. "
                    "Set CRS-nya dulu (mis. gdal_edit.py -a_srs EPSG:32749 file.tif)."
                )
        data = src.read(1).astype("float32")
        if src.nodata is not None:
            data[data == src.nodata] = np.nan

        if crs.to_epsg() == 4326:
            transform = src.transform
            arr = data
        else:
            notes.append(f"CRS {crs.to_string()} direproyeksi ke EPSG:4326.")
            transform, w, h = calculate_default_transform(crs, "EPSG:4326", src.width, src.height, *src.bounds)
            arr = np.full((h, w), np.nan, dtype="float32")
            reproject(
                data, arr, src_transform=src.transform, src_crs=crs,
                dst_transform=transform, dst_crs="EPSG:4326",
                resampling=Resampling.bilinear, src_nodata=np.nan, dst_nodata=np.nan,
            )
        height, width = arr.shape
        left, top = transform.c, transform.f
        right = left + transform.a * width
        bottom = top + transform.e * height

    bad = np.isnan(arr)
    if bad.all():
        raise ValueError("Semua piksel DEM kosong (nodata).")
    if bad.any():
        notes.append(f"{bad.mean() * 100:.1f}% piksel kosong diisi elevasi minimum.")
        arr = np.where(bad, np.nanmin(arr), arr)
    emin, emax = float(arr.min()), float(arr.max())
    if emin < -500 or emax > 9000:
        raise ValueError(f"Rentang elevasi tidak masuk akal ({emin:.0f}..{emax:.0f} m). Bukan DEM meter?")

    with rasterio.open(
        dst_path, "w", driver="GTiff", height=height, width=width, count=1, dtype="float32",
        crs=CRS.from_epsg(4326), transform=from_bounds(left, bottom, right, top, width, height),
        compress="lzw", nodata=None,
    ) as dst:
        dst.write(arr, 1)

    res_m = abs(transform.a) * 111320 * math.cos(math.radians((top + bottom) / 2))
    return {
        "bounds": [left, bottom, right, top],  # west, south, east, north
        "elev_min": round(emin, 1), "elev_max": round(emax, 1),
        "res_m": round(res_m, 1), "width": width, "height": height, "notes": notes,
    }


def _tile_range(bounds, z):
    n = 2 ** z
    w, s, e, nn = bounds
    def lon2x(lon): return int((lon + 180) / 360 * n)
    def lat2y(lat): return int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return lon2x(w), lon2x(e), lat2y(nn), lat2y(s)


def build_tiles(dem_path: str, out_dir: str, on_progress=None) -> dict:
    with rasterio.open(dem_path) as s:
        dem = s.read(1).astype("float32")
        b, res = s.bounds, s.res
    bounds = [b.left, b.bottom, b.right, b.top]
    lat_mid = (b.top + b.bottom) / 2
    res_m = res[0] * 111320 * math.cos(math.radians(lat_mid))
    max_z = int(round(math.log2(156543.03 * math.cos(math.radians(lat_mid)) / max(res_m, 1e-3))))
    max_z = max(11, min(15, max_z))
    while max_z > 11:
        x0, x1, y0, y1 = _tile_range(bounds, max_z)
        if (x1 - x0 + 1) * (y1 - y0 + 1) <= MAX_TILES:
            break
        max_z -= 1
    min_z = max(7, max_z - 6)

    total = 0
    for z in range(min_z, max_z + 1):
        scale = 2 ** (max_z - z)
        src = gaussian_filter(dem, sigma=scale * 0.6) if scale > 1 else dem
        x0, x1, y0, y1 = _tile_range(bounds, z)
        n = 2 ** z
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                px = (x + (np.arange(TILE) + 0.5) / TILE) / n
                py = (y + (np.arange(TILE) + 0.5) / TILE) / n
                lon = px * 360 - 180
                lat = np.degrees(np.arctan(np.sinh(math.pi * (1 - 2 * py))))
                cols = (lon - b.left) / res[0] - 0.5
                rows = (b.top - lat) / res[1] - 0.5
                cc, rr = np.meshgrid(cols, rows)
                elev = map_coordinates(src, [rr, cc], order=1, mode="nearest")
                v = elev + 32768.0
                rgb = np.dstack([np.floor(v / 256.0), np.floor(v) % 256, np.floor((v - np.floor(v)) * 256.0)]).astype("uint8")
                d = os.path.join(out_dir, str(z), str(x))
                os.makedirs(d, exist_ok=True)
                Image.fromarray(rgb, "RGB").save(os.path.join(d, f"{y}.png"), optimize=True)
                total += 1
        if on_progress:
            on_progress(z, min_z, max_z)
    return {"min_zoom": min_z, "max_zoom": max_z, "tiles": total}


# ── peta topo offline ─────────────────────────────────────────────────
# Warna hipsometrik (elevasi absolut, meter) - sengaja absolut supaya tampilannya
# konsisten antar lokasi. Hijau dataran rendah -> kuning/krem -> cokelat -> abu-putih puncak.
_RAMP = [
    (0, (196, 220, 170)), (300, (170, 205, 140)), (700, (150, 190, 120)),
    (1100, (200, 205, 140)), (1500, (222, 200, 150)), (2000, (205, 170, 125)),
    (2500, (178, 140, 108)), (3000, (210, 205, 200)), (3500, (245, 245, 245)),
]


def _contour_steps(z: int) -> tuple[int, int]:
    """(interval kontur, interval kontur indeks/tebal) dalam meter, menurut zoom."""
    if z <= 10:
        return 200, 1000
    if z <= 12:
        return 100, 500
    if z == 13:
        return 50, 250
    return 25, 100


def _colorize(elev: np.ndarray) -> np.ndarray:
    xs = [r[0] for r in _RAMP]
    out = np.empty(elev.shape + (3,), dtype="float32")
    for c in range(3):
        out[..., c] = np.interp(elev, xs, [r[1][c] for r in _RAMP])
    return out


def _topo_tile(src, b, res, z, x, y, hs_exag=1.8):
    n = 2 ** z
    pad = 1  # 1 piksel sisa di tiap sisi supaya gradien & kontur nyambung antar tile
    t = TILE + 2 * pad
    px = (x + (np.arange(t) - pad + 0.5) / TILE) / n
    py = (y + (np.arange(t) - pad + 0.5) / TILE) / n
    lon = px * 360 - 180
    lat = np.degrees(np.arctan(np.sinh(math.pi * (1 - 2 * py))))
    cc, rr = np.meshgrid((lon - b.left) / res[0] - 0.5, (b.top - lat) / res[1] - 0.5)
    elev = map_coordinates(src, [rr, cc], order=1, mode="nearest")

    # ukuran piksel (meter) di tile ini, buat hitung kemiringan
    lat_c = float(lat[t // 2])
    pix_m = 156543.03 * math.cos(math.radians(lat_c)) / (2 ** z) * (256 / TILE)
    gy, gx = np.gradient(elev, pix_m)
    dzdx, dzdy = gx, -gy  # baris naik = ke selatan
    slope = np.arctan(np.hypot(dzdx, dzdy) * hs_exag)
    aspect = np.arctan2(dzdy, -dzdx)
    zen, azm = math.radians(45), math.radians((360 - 315 + 90) % 360)
    shade = math.cos(zen) * np.cos(slope) + math.sin(zen) * np.sin(slope) * np.cos(azm - aspect)

    rgb = _colorize(elev)
    rgb *= (0.55 + 0.75 * np.clip(shade, 0, 1))[..., None]

    interval, index = _contour_steps(z)
    lvl = np.floor(elev / interval)
    edge = np.zeros(elev.shape, dtype=bool)
    edge[:, :-1] |= lvl[:, :-1] != lvl[:, 1:]
    edge[:-1, :] |= lvl[:-1, :] != lvl[1:, :]
    ilvl = np.floor(elev / index)
    iedge = np.zeros(elev.shape, dtype=bool)
    iedge[:, :-1] |= ilvl[:, :-1] != ilvl[:, 1:]
    iedge[:-1, :] |= ilvl[:-1, :] != ilvl[1:, :]
    # kontur indeks ditebalkan 1 piksel
    thick = iedge.copy()
    thick[1:, :] |= iedge[:-1, :]
    thick[:, 1:] |= iedge[:, :-1]
    line = (110, 78, 50)
    rgb = np.where(edge[..., None], rgb * 0.45 + np.array(line, dtype="float32") * 0.55, rgb)
    rgb = np.where(thick[..., None], rgb * 0.25 + np.array((80, 52, 30), dtype="float32") * 0.75, rgb)

    # Di luar cakupan DEM -> transparan (bukan sapuan warna tepi), biar batas data kelihatan jujur.
    inside = (lon[None, :] >= b.left) & (lon[None, :] <= b.right) & (lat[:, None] >= b.bottom) & (lat[:, None] <= b.top)
    rgba = np.dstack([np.clip(rgb, 0, 255), inside * 255.0])[pad:-pad, pad:-pad]
    return Image.fromarray(rgba.astype("uint8"), "RGBA")


def build_topo_tiles(dem_path: str, out_dir: str, min_z: int, max_z: int) -> dict:
    """Tile peta topo WebP (dengan alpha di luar cakupan DEM) untuk zoom min_z..max_z. max_z biasanya max_zoom DEM + 1:
    satu level di atas resolusi asli masih enak dilihat karena kontur digambar dari DEM yang diinterpolasi."""
    with rasterio.open(dem_path) as s:
        dem = s.read(1).astype("float32")
        b, res = s.bounds, s.res
    bounds = [b.left, b.bottom, b.right, b.top]
    total = 0
    for z in range(min_z, max_z + 1):
        scale = 2 ** max(0, (max_z - 1) - z)  # DEM asli ~ zoom (max_z-1)
        src = gaussian_filter(dem, sigma=scale * 0.6) if scale > 1 else dem
        x0, x1, y0, y1 = _tile_range(bounds, z)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                d = os.path.join(out_dir, str(z), str(x))
                os.makedirs(d, exist_ok=True)
                _topo_tile(src, b, res, z, x, y).save(os.path.join(d, f"{y}.webp"), "WEBP", quality=82, method=4)
                total += 1
    return {"min_zoom": min_z, "max_zoom": max_z, "tiles": total}


class GridElevation(ElevationSource):
    """Elevasi bilinear dari DEM ter-normalisasi (EPSG:4326) di memori."""

    def __init__(self, path: str):
        with rasterio.open(path) as s:
            self._a = s.read(1).astype("float64")
            self._left, self._top = s.bounds.left, s.bounds.top
            self._rx, self._ry = s.res
        self.bounds = [self._left, s.bounds.bottom, s.bounds.right, self._top]

    def elevation_at(self, lat: float, lon: float) -> float:
        c = (lon - self._left) / self._rx - 0.5
        r = (self._top - lat) / self._ry - 0.5
        h, w = self._a.shape
        if r < 0 or c < 0 or r > h - 1 or c > w - 1:
            raise ValueError(f"Titik ({lat:.5f}, {lon:.5f}) di luar cakupan DEM.")
        return float(map_coordinates(self._a, [[r], [c]], order=1)[0])

    def elevation_many(self, lats, lons):
        """Bilinear untuk banyak titik sekaligus (divektorkan). Di luar DEM -> NaN."""
        lats = np.asarray(lats, dtype=float)
        lons = np.asarray(lons, dtype=float)
        c = (lons - self._left) / self._rx - 0.5
        r = (self._top - lats) / self._ry - 0.5
        h, w = self._a.shape
        ok = (r >= 0) & (c >= 0) & (r <= h - 1) & (c <= w - 1)
        out = np.full(lats.shape, np.nan)
        if ok.any():
            out[ok] = map_coordinates(self._a, [r[ok], c[ok]], order=1)
        return out


# ─────────────────────────── kanopi / vegetasi (opsional) ───────────────────────────
CANOPY_TARGET_RES_M = 10.0  # raster kanopi yang lebih halus dirata-ratakan ke ~10 m (batasi memori)
CANOPY_MAX_PLAUSIBLE_M = 150.0


def normalize_canopy(src_path: str, dst_path: str) -> dict:
    """Raster TINGGI KANOPI (meter) apa pun (CRS apa pun, resolusi apa pun) -> GeoTIFF EPSG:4326 float32.
    Piksel nodata di dalam raster dianggap 0 (tidak ada vegetasi); area di luar raster disimpan NaN
    (= tidak diketahui, dihitung sebagai 0 oleh perencana dan dilaporkan sebagai cakupan)."""
    notes: list[str] = []
    with rasterio.open(src_path) as src:
        crs = src.crs
        if crs is None:
            b = src.bounds
            if -180 <= b.left < b.right <= 180 and -90 <= b.bottom < b.top <= 90:
                crs = CRS.from_epsg(4326)
                notes.append("File tidak punya CRS; koordinatnya derajat, dianggap EPSG:4326.")
            else:
                raise ValueError("File tidak punya CRS dan koordinatnya bukan derajat lat/lon. Set CRS-nya dulu.")
        data = src.read(1).astype("float32")
        if src.nodata is not None:
            data[data == src.nodata] = np.nan
        data[~np.isfinite(data)] = np.nan
        valid = data[~np.isnan(data)]
        if valid.size == 0:
            raise ValueError("Semua piksel raster kanopi kosong (nodata).")
        if float(valid.min()) < -1 or float(valid.max()) > CANOPY_MAX_PLAUSIBLE_M:
            raise ValueError(
                f"Rentang nilai tidak masuk akal untuk tinggi kanopi dalam meter ({valid.min():.0f}..{valid.max():.0f}). "
                "Berkas ini mungkin DEM atau kelas tutupan lahan, bukan tinggi kanopi.")
        data = np.where(np.isnan(data), 0.0, np.clip(data, 0.0, None)).astype("float32")

        lat_mid = (src.bounds.top + src.bounds.bottom) / 2
        target_deg = CANOPY_TARGET_RES_M / (111320.0 * math.cos(math.radians(lat_mid)))
        if crs.to_epsg() != 4326:
            notes.append(f"CRS {crs.to_string()} direproyeksi ke EPSG:4326.")
        transform, w, h = calculate_default_transform(crs, "EPSG:4326", src.width, src.height, *src.bounds)
        if abs(transform.a) < target_deg:  # lebih halus dari ~10 m -> kasarkan
            scale = target_deg / abs(transform.a)
            transform, w, h = calculate_default_transform(
                crs, "EPSG:4326", src.width, src.height, *src.bounds, resolution=target_deg)
            notes.append(f"Resolusi dirata-ratakan ke ~{CANOPY_TARGET_RES_M:.0f} m (faktor {scale:.1f}).")
        arr = np.full((h, w), np.nan, dtype="float32")
        reproject(
            data, arr, src_transform=src.transform, src_crs=crs, dst_transform=transform, dst_crs="EPSG:4326",
            resampling=Resampling.average, src_nodata=None, dst_nodata=np.nan,
        )
    left, top = transform.c, transform.f
    right, bottom = left + transform.a * w, top + transform.e * h
    with rasterio.open(
        dst_path, "w", driver="GTiff", height=h, width=w, count=1, dtype="float32", crs=CRS.from_epsg(4326),
        transform=from_bounds(left, bottom, right, top, w, h), compress="lzw", nodata=float("nan"),
    ) as dst:
        dst.write(arr, 1)
    ok = ~np.isnan(arr)
    res_m = abs(transform.a) * 111320 * math.cos(math.radians((top + bottom) / 2))
    return {
        "bounds": [left, bottom, right, top], "res_m": round(res_m, 1), "width": w, "height": h,
        "max_height_m": round(float(np.nanmax(arr)), 1), "mean_height_m": round(float(np.nanmean(arr)), 1),
        "canopy_pct": round(float(100.0 * np.mean(arr[ok] >= 2.0)), 1), "notes": notes,
    }


class GridClutter(ClutterSource):
    """Tinggi kanopi (m) dari raster ter-normalisasi (EPSG:4326), nearest-neighbour. Di luar raster -> NaN."""

    active = True

    def __init__(self, path: str):
        with rasterio.open(path) as s:
            self._a = s.read(1).astype("float32")
            self._left, self._top = s.bounds.left, s.bounds.top
            self._rx, self._ry = s.res
        self.bounds = [self._left, self._top - self._a.shape[0] * self._ry, self._left + self._a.shape[1] * self._rx, self._top]

    def canopy_many(self, lats, lons):
        lats = np.asarray(lats, dtype=float)
        lons = np.asarray(lons, dtype=float)
        c = np.floor((lons - self._left) / self._rx)
        r = np.floor((self._top - lats) / self._ry)
        h, w = self._a.shape
        ok = np.isfinite(c) & np.isfinite(r) & (r >= 0) & (c >= 0) & (r < h) & (c < w)
        out = np.full(lats.shape, np.nan)
        if ok.any():
            out[ok] = self._a[r[ok].astype(int), c[ok].astype(int)]
        return out


def load_clutter(folder: str):
    """GridClutter dari <folder>/canopy.tif bila ada, selain itu None (tanpa data vegetasi)."""
    p = os.path.join(folder, "canopy.tif")
    return GridClutter(p) if os.path.exists(p) else None