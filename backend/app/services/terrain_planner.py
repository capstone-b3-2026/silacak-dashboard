"""
Perencanaan penempatan relay LoRa berbasis analisis Line-of-Sight (LOS) &
Fresnel zone dari data elevasi (DEM).

Ide dasarnya (lihat juga TODO lama di api/v1/terrain.py):
- Radio link idealnya bebas halangan bukan cuma di garis lurus antar 2
  antena, tapi di sekitar "first Fresnel zone"-nya juga.
- Kalau ground/terrain nembus ke dalam zona itu di suatu titik sepanjang
  link, sinyalnya makin lemah (walau LOS "keliatan" sekalipun).
- Kita jalan (greedy) dari base station sepanjang jalur pendakian, cari
  titik paling jauh yang masih clear, begitu ketutup baru cari kandidat
  relay terdekat yang paling jauh "melihat" ke depan.

INI CUMA MODEL TERRAIN (tanah/batu dari DEM) - BUKAN model vegetasi/pohon.
Hasilnya kandidat kuat, bukan keputusan final - tetep wajib divalidasi di
lapangan (lihat catatan di README/chat).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

EARTH_RADIUS_KM = 6371.0
K_FACTOR = 4 / 3  # faktor refraksi atmosfer standar buat koreksi kelengkungan bumi
FRESNEL_CLEARANCE_FRACTION = 0.6  # aturan umum: 60% dari radius Fresnel pertama cukup


# ───────────────────────── sumber elevasi ─────────────────────────


class ElevationSource:
    """Interface umum - biar algoritma di bawah gak peduli datanya dari
    DEM asli atau dari fungsi sintetis buat testing."""

    def elevation_at(self, lat: float, lon: float) -> float:
        raise NotImplementedError


class RasterElevationSource(ElevationSource):
    """DEM asli (GeoTIFF, misal hasil clip DEMNAS) - dipakai buat lokasi
    sungguhan (Bukit Klangon). Butuh package `rasterio`.

    DEMNAS kadang didistribusikan dalam proyeksi UTM (meter), bukan
    geografis (lat/lon derajat) - jadi di sini kita cek CRS raster-nya
    dulu dan transform otomatis kalau perlu, daripada nebak/asumsi salah
    satu format doang."""

    def __init__(self, path: str):
        import rasterio  # import di sini biar rasterio gak wajib ada kalau cuma mau pakai mode sintetis
        from rasterio.crs import CRS
        from rasterio.warp import transform as warp_transform

        self._src = rasterio.open(path)
        crs = self._src.crs
        if crs is None:
            # DEM hasil clip/proses ulang kadang kehilangan metadata CRS. Aturannya disamain
            # dengan dem_ingest.normalize_dem: kalau koordinatnya masuk akal sbg derajat
            # lat/lon -> EPSG:4326; kalau nggak, tolak dengan pesan jelas (jangan nebak UTM).
            b = self._src.bounds
            if -180 <= b.left < b.right <= 180 and -90 <= b.bottom < b.top <= 90:
                crs = CRS.from_epsg(4326)
            else:
                self._src.close()
                raise ValueError(
                    "File DEM tidak punya CRS dan koordinatnya bukan derajat lat/lon. "
                    "Set CRS-nya dulu (mis. gdal_edit.py -a_srs EPSG:32749 file.tif)."
                )
        self._crs = crs
        self._band = self._src.read(1)
        self._is_geographic = crs.is_geographic
        self._warp_transform = warp_transform

    def elevation_at(self, lat: float, lon: float) -> float:
        if self._is_geographic:
            x, y = lon, lat
        else:
            xs, ys = self._warp_transform("EPSG:4326", self._crs, [lon], [lat])
            x, y = xs[0], ys[0]
        row, col = self._src.index(x, y)
        h, w = self._band.shape
        # Cek eksplisit: indeks negatif TIDAK melempar IndexError di numpy (wrap ke sisi
        # seberang), jadi titik di barat/utara DEM bisa diam-diam dapat elevasi yang salah.
        if not (0 <= row < h and 0 <= col < w):
            raise ValueError(
                f"Titik ({lat}, {lon}) di luar cakupan file DEM ini. "
                "Cek lagi apa tile DEMNAS yang di-download beneran nutupin area ini."
            )
        return float(self._band[row, col])

    def close(self) -> None:
        self._src.close()


class SyntheticElevationSource(ElevationSource):
    """Elevasi hasil rumus matematis simpel, buat testing MEKANIK
    algoritma di area datar (misal sekitaran FT UGM) tanpa perlu DEM
    asli. FT UGM aslinya relatif datar (~113-114 mdpl, dataran rendah
    Yogyakarta) - DEM ASLI di sana gak bakal nunjukkin obstruksi apa pun.

    Tapi obstruksi paling nyata di situ justru BUKAN dari terrain - itu
    gedung landmark 11 lantai yang bikin node portable sering kehalang.
    Jadi di sini elevasi 'gedung' itu dimodelin sebagai plateau (atap
    rata) dengan tepi curam - beda dari bukit alami yang landai - biar
    lebih ngena ke kondisi obstruksi yang beneran dialamin, meski tetep
    murni alat bantu tes kode (bukan DEM asli).
    """

    def __init__(
        self,
        base_elev_m: float = 113.0,
        building_center: tuple[float, float] | None = None,
        building_height_m: float = 40.0,  # ~11 lantai x ~3.6 m/lantai, sesuaikan kalau tau tinggi pastinya
        building_radius_km: float = 0.035,  # radius footprint gedung (~35 m)
        edge_km: float = 0.01,  # transisi tajam di tepi (tembok, bukan lereng)
    ):
        self.base_elev_m = base_elev_m
        self.building_center = building_center
        self.building_height_m = building_height_m
        self.building_radius_km = building_radius_km
        self.edge_km = edge_km

    def elevation_at(self, lat: float, lon: float) -> float:
        elev = self.base_elev_m
        if self.building_center is not None:
            d = haversine_km((lat, lon), self.building_center)
            if d <= self.building_radius_km:
                elev += self.building_height_m  # di dalam footprint = tinggi penuh (atap rata)
            elif d <= self.building_radius_km + self.edge_km:
                frac = 1 - (d - self.building_radius_km) / self.edge_km
                elev += self.building_height_m * frac  # tembok/tepi gedung
        return elev


# ───────────────────────── geometri & radio ─────────────────────────


def haversine_km(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    lat1, lon1 = math.radians(p1[0]), math.radians(p1[1])
    lat2, lon2 = math.radians(p2[0]), math.radians(p2[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def fresnel_radius_m(d1_km: float, d2_km: float, freq_mhz: float) -> float:
    """Radius Fresnel zone pertama (meter) di suatu titik sepanjang link,
    d1/d2 = jarak titik itu ke tiap ujung link (km)."""
    freq_ghz = freq_mhz / 1000
    total = d1_km + d2_km
    if total <= 0 or freq_ghz <= 0:
        return 0.0
    return 17.32 * math.sqrt((d1_km * d2_km) / (freq_ghz * total))


def earth_curvature_bulge_m(d1_km: float, d2_km: float) -> float:
    """Seberapa 'naik' efeknya permukaan bumi di suatu titik akibat
    kelengkungan bumi (meter) - kecil di jarak pendek, tapi disertakan
    biar perhitungannya tetap benar secara fisik."""
    return 1000 * (d1_km * d2_km) / (2 * K_FACTOR * EARTH_RADIUS_KM)


@dataclass
class LosSample:
    t: float  # posisi sepanjang link, 0..1
    distance_km: float
    ground_elev_m: float
    sightline_elev_m: float
    fresnel_radius_m: float
    required_clear_elev_m: float
    blocked: bool


@dataclass
class LosResult:
    clear: bool
    samples: list[LosSample] = field(default_factory=list)
    worst_margin_m: float = 0.0  # margin negatif = seberapa parah ketutupnya


def los_profile(
    elev_src: ElevationSource,
    p1: tuple[float, float],
    p2: tuple[float, float],
    antenna_h1_m: float = 2.0,
    antenna_h2_m: float = 2.0,
    freq_mhz: float = 915.0,
    n_samples: int = 40,
) -> LosResult:
    """Cek apakah link p1<->p2 clear (LOS + toleransi Fresnel zone),
    dengan nyoba n_samples titik di sepanjang garis lurus antara
    keduanya."""
    total_km = haversine_km(p1, p2)
    elev1 = elev_src.elevation_at(*p1) + antenna_h1_m
    elev2 = elev_src.elevation_at(*p2) + antenna_h2_m

    samples: list[LosSample] = []
    worst_margin = float("inf")
    clear = True

    # titik ujung (t=0, t=1) dilewatin karena jarak salah satu sisi = 0
    # bikin Fresnel radius selalu 0 di situ (gak informatif) - fokus ke
    # titik-titik di antaranya.
    for i in range(1, n_samples):
        t = i / n_samples
        lat = p1[0] + (p2[0] - p1[0]) * t
        lon = p1[1] + (p2[1] - p1[1]) * t
        d1 = total_km * t
        d2 = total_km * (1 - t)

        ground = elev_src.elevation_at(lat, lon)
        sightline = elev1 + (elev2 - elev1) * t
        fresnel_r = fresnel_radius_m(d1, d2, freq_mhz)
        curve = earth_curvature_bulge_m(d1, d2)
        required_clear = ground + curve + FRESNEL_CLEARANCE_FRACTION * fresnel_r
        margin = sightline - required_clear
        blocked = margin < 0

        samples.append(
            LosSample(t, d1, ground, sightline, fresnel_r, required_clear, blocked)
        )
        worst_margin = min(worst_margin, margin)
        if blocked:
            clear = False

    return LosResult(clear=clear, samples=samples, worst_margin_m=worst_margin if samples else 0.0)


# ───────────────────────── algoritma penempatan relay ─────────────────────────


@dataclass
class RelaySuggestion:
    lat: float
    lon: float
    covers_trail_index: int  # index terjauh di trail_points yang ke-cover dari sini (selalu >= 0)
    worst_margin_m: float


@dataclass
class RelayPlan:
    """Hasil perencanaan: relay yang ditemukan + status JUJUR soal cakupan trail."""

    relays: list[RelaySuggestion]
    n_trail: int
    covered_through: int  # trail[0..covered_through] beneran ke-cover; -1 = belum ada satu pun
    stall_reason: str | None = None  # None = selesai | "no_candidate" | "max_relays"

    @property
    def complete(self) -> bool:
        return self.stall_reason is None

    @property
    def stalled_at(self) -> int | None:
        """Index titik trail PERTAMA yang tidak berhasil dijangkau (None kalau selesai)."""
        return None if self.complete else self.covered_through + 1

    @property
    def uncovered_points(self) -> int:
        return self.n_trail - 1 - self.covered_through


def _candidate_offsets(radius_km: float, step_km: float):
    """Grid kandidat kotak di sekitar (0,0) dalam km, buat dicoba jadi
    posisi relay - konversi ke lat/lon dilakukan pas dipakai."""
    n = int(radius_km / step_km)
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            dx, dy = i * step_km, j * step_km
            if math.hypot(dx, dy) <= radius_km:
                yield dx, dy


def _offset_point(origin: tuple[float, float], dx_km: float, dy_km: float) -> tuple[float, float]:
    lat, lon = origin
    dlat = dy_km / 111.32  # ~km per derajat lintang
    dlon = dx_km / (111.32 * math.cos(math.radians(lat)))
    return (lat + dlat, lon + dlon)


def suggest_relay_chain(
    elev_src: ElevationSource,
    base: tuple[float, float],
    trail_points: list[tuple[float, float]],
    max_hop_km: float = 2.0,
    antenna_h_m: float = 2.0,
    freq_mhz: float = 915.0,
    candidate_search_radius_km: float = 0.3,
    candidate_grid_step_km: float = 0.06,
    max_relays: int = 10,
) -> RelayPlan:
    """Greedy: dari `base`, jalan sejauh mungkin sepanjang trail_points
    selama link masih clear & di bawah max_hop_km. Begitu ketutup, cari
    kandidat relay di sekitar titik terakhir yang masih ke-cover, pilih
    yang paling jauh 'melihat' ke depan sekaligus clear ke belakang.

    Aturan penting: relay HANYA dipasang kalau dia beneran menambah cakupan
    (menjangkau minimal 1 titik trail baru dan tersambung ke node sebelumnya).
    Kalau tidak ada kandidat seperti itu, berhenti dan laporkan di titik mana
    macetnya (RelayPlan.stalled_at) - tidak ada relay "pemanis" yang dipaksakan.
    """

    def link_ok(a, b) -> LosResult | None:
        if haversine_km(a, b) > max_hop_km:
            return None
        res = los_profile(elev_src, a, b, antenna_h_m, antenna_h_m, freq_mhz)
        return res if res.clear else None

    def reach_from(node, first: int) -> int:
        """Index terjauh yang terjangkau node secara berurutan mulai dari `first`
        (first - 1 kalau titik `first` pun tidak terjangkau)."""
        j = first
        while j < n and link_ok(node, trail_points[j]) is not None:
            j += 1
        return j - 1

    relays: list[RelaySuggestion] = []
    origin = base
    n = len(trail_points)
    covered = -1  # trail[0..covered] sudah ke-cover oleh base/relay sebelumnya
    reason: str | None = None

    while True:
        start = covered + 1
        covered = reach_from(origin, start)  # perluas cakupan dari node saat ini
        if covered >= n - 1:
            break  # trail abis, semuanya ke-cover
        if len(relays) >= max_relays:
            reason = "max_relays"
            break

        anchor = trail_points[covered] if covered >= start else trail_points[start]
        best = None  # (kandidat, reach, margin)
        for dx, dy in _candidate_offsets(candidate_search_radius_km, candidate_grid_step_km):
            cand = _offset_point(anchor, dx, dy)
            try:
                back = link_ok(origin, cand)
                if back is None:
                    continue
                reach = reach_from(cand, covered + 1)
            except ValueError:  # kandidat jatuh di luar cakupan DEM -> bukan kandidat
                continue
            if reach <= covered:
                continue  # relay ini tidak menolong sama sekali -> bukan kandidat
            # reach sama -> pilih yang link ke belakangnya paling lega (margin Fresnel terbesar),
            # bukan sekadar kandidat yang kebetulan dicoba duluan.
            if best is None or reach > best[1] or (reach == best[1] and back.worst_margin_m > best[2]):
                best = (cand, reach, back.worst_margin_m)

        if best is None:
            # Tidak ada posisi relay yang tersambung ke belakang DAN menjangkau titik
            # baru. Berhenti jujur: butuh radius cari/hop lebih besar atau geser waypoint.
            reason = "no_candidate"
            break

        cand, covered, margin = best
        relays.append(RelaySuggestion(cand[0], cand[1], covered, margin))
        origin = cand

    return RelayPlan(relays=relays, n_trail=n, covered_through=covered, stall_reason=reason)


@dataclass
class RelayEval:
    lat: float
    lon: float
    hop_km: float  # jarak ke node sebelumnya (base atau relay sebelumnya)
    margin_m: float  # margin Fresnel terburuk di link ke node sebelumnya (negatif = ketutup)
    link_ok: bool  # link ke belakang clear, di bawah hop maks, DAN node sebelumnya sendiri tersambung
    covers_trail_index: int  # index trail terjauh yang terjangkau sampai node ini


def evaluate_relay_chain(
    elev_src: ElevationSource,
    base: tuple[float, float],
    relay_points: list[tuple[float, float]],
    trail_points: list[tuple[float, float]],
    max_hop_km: float = 2.0,
    antenna_h_m: float = 2.0,
    freq_mhz: float = 915.0,
) -> tuple[list[RelayEval], int]:
    """Nilai rantai base -> R1 -> R2 -> ... dengan posisi relay yang SUDAH ditentukan (mis. digeser
    manual sesuai kondisi lapangan). Aturan sama dengan suggest_relay_chain: relay hanya menambah
    cakupan kalau link ke node sebelumnya clear; satu link putus = relay sesudahnya ikut tidak
    tersambung (rantai diurutkan, bukan jaring). Return (hasil_per_relay, covered_through)."""
    n = len(trail_points)

    def link(a, b):
        return haversine_km(a, b), los_profile(elev_src, a, b, antenna_h_m, antenna_h_m, freq_mhz)

    def reach_from(node, first: int) -> int:
        j = first
        while j < n:
            d, res = link(node, trail_points[j])
            if d > max_hop_km or not res.clear:
                break
            j += 1
        return j - 1

    covered = reach_from(base, 0)
    origin, connected = base, True
    out: list[RelayEval] = []
    for rp in relay_points:
        d, res = link(origin, rp)
        ok = connected and d <= max_hop_km and res.clear
        if ok:
            covered = reach_from(rp, covered + 1)
        connected = ok
        out.append(RelayEval(rp[0], rp[1], d, res.worst_margin_m, ok, covered))
        origin = rp
    return out, covered
