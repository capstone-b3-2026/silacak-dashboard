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

import numpy as np

EARTH_RADIUS_KM = 6371.0
K_FACTOR = 4 / 3  # faktor refraksi atmosfer standar buat koreksi kelengkungan bumi
FRESNEL_CLEARANCE_FRACTION = 0.6  # aturan umum: 60% dari radius Fresnel pertama cukup


# ───────────────────────── sumber elevasi ─────────────────────────


class ElevationSource:
    """Interface umum - biar algoritma di bawah gak peduli datanya dari
    DEM asli atau dari fungsi sintetis buat testing."""

    def elevation_at(self, lat: float, lon: float) -> float:
        raise NotImplementedError

    def elevation_many(self, lats, lons):
        """Versi massal (array). Titik di luar DEM -> NaN (bukan exception). Sumber yang bisa
        divektorkan (mis. GridElevation) sebaiknya meng-override ini; default-nya memanggil
        elevation_at satu per satu."""
        lats = np.asarray(lats, dtype=float)
        lons = np.asarray(lons, dtype=float)
        out = np.empty(lats.shape)
        flat = out.reshape(-1)
        for i, (la, lo) in enumerate(zip(lats.ravel(), lons.ravel())):
            try:
                flat[i] = self.elevation_at(float(la), float(lo))
            except ValueError:
                flat[i] = np.nan
        return out


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
    end_exclusion_m: float = 0.0,
) -> LosResult:
    """Cek apakah link p1<->p2 clear (LOS + toleransi Fresnel zone),
    dengan nyoba n_samples titik di sepanjang garis lurus antara
    keduanya. end_exclusion_m > 0: sampel yang lebih dekat dari itu ke salah satu ujung tidak
    dihitung (lihat catatan di perencana v2)."""
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
        excluded = end_exclusion_m > 0 and (d1 * 1000 < end_exclusion_m or d2 * 1000 < end_exclusion_m)
        blocked = margin < 0 and not excluded

        samples.append(
            LosSample(t, d1, ground, sightline, fresnel_r, required_clear, blocked)
        )
        if not excluded:
            worst_margin = min(worst_margin, margin)
        if blocked:
            clear = False

    if not samples:
        worst_margin = 0.0
    elif worst_margin == float("inf"):
        worst_margin = MARGIN_CAP_M  # semua sampel di zona ujung: terlalu pendek untuk dinilai
    return LosResult(clear=clear, samples=samples, worst_margin_m=worst_margin)


# ───────────────────────── algoritma penempatan relay ─────────────────────────


@dataclass
class RelaySuggestion:
    lat: float
    lon: float
    covers_trail_index: int  # index terjauh di trail_points yang ke-cover dari sini (selalu >= 0)
    worst_margin_m: float  # margin link ke node induk (backhaul)
    parent: int = 0  # 0 = base, k = relay ke-k (urutan hasil)
    hop_km: float = 0.0  # jarak ke node induk
    loss_db: float = 0.0  # redaman MEDAN (difraksi) link ke node induk
    veg_db: float = 0.0  # redaman vegetasi link ke node induk
    rssi_dbm: float = 0.0  # RSSI prediksi link ke node induk
    fade_margin_db: float = 0.0  # RSSI prediksi - sensitivitas (link ke node induk)
    cover_loss_db: float = 0.0  # redaman (medan+vegetasi) terburuk ke sampel jalur tanggungan relay ini
    cover_fade_db: float = 0.0  # margin fading terburuk ke sampel jalur tanggungan relay ini
    access_km: float = 0.0  # jarak relay ke jalur terdekat
    slope_deg: float = 0.0  # kemiringan medan di posisi relay


@dataclass
class RelayPlan:
    """Hasil perencanaan: relay yang ditemukan + status JUJUR soal cakupan trail."""

    relays: list[RelaySuggestion]
    n_trail: int
    covered_through: int  # trail[0..covered_through] beneran ke-cover; -1 = belum ada satu pun
    stall_reason: str | None = None  # None = selesai | "no_candidate" | "max_relays"
    coverage_pct: float | None = None  # % sampel jalur yang terjangkau (union, termasuk yang setelah celah)
    trail_km: float = 0.0
    covered_km: float = 0.0  # panjang jalur yang tercover berurutan dari awal
    n_candidates: int = 0
    step_used_km: float = 0.0
    uses_clutter: bool = False  # True kalau data kanopi dipakai
    clutter_coverage_pct: float | None = None  # % sampel jalur yang ada di dalam cakupan data kanopi

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


def suggest_relay_chain_greedy(
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
    """[DIGANTI oleh suggest_relay_chain v2; dipertahankan buat pembanding/benchmark]

    Greedy: dari `base`, jalan sejauh mungkin sepanjang trail_points
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
    parent: int = 0  # node yang dipakai sebagai induk: 0 = base, k = relay ke-k
    loss_db: float = 0.0  # redaman MEDAN (difraksi) link ke node induk
    veg_db: float = 0.0  # redaman vegetasi link ke node induk
    rssi_dbm: float = 0.0  # RSSI prediksi link ke node induk
    fade_margin_db: float = 0.0  # RSSI prediksi - sensitivitas


def evaluate_relay_chain_greedy(
    elev_src: ElevationSource,
    base: tuple[float, float],
    relay_points: list[tuple[float, float]],
    trail_points: list[tuple[float, float]],
    max_hop_km: float = 2.0,
    antenna_h_m: float = 2.0,
    freq_mhz: float = 915.0,
) -> tuple[list[RelayEval], int]:
    """[model lama; dipertahankan buat pembanding] Nilai rantai base -> R1 -> R2 -> ... dengan posisi relay yang SUDAH ditentukan (mis. digeser
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


# ═════════════════════════════════════════════════════════════════════════════
#  PERENCANA RELAY v3 — pencarian optimal + anggaran daya (link budget) + vegetasi
# ═════════════════════════════════════════════════════════════════════════════
#
# Masalah: pilih posisi (dan jumlah) relay supaya SELURUH jalur pendakian terjangkau dengan relay
# sesedikit mungkin, lalu yang paling andal.
#
# Model tautan (per link), semua dalam dB:
#   RSSI_prediksi = P_tx + G_a + G_b - FSPL(d, f) - L_medan - L_vegetasi - offset_kalibrasi
#   margin_fading = RSSI_prediksi - sensitivitas
#   link layak    = (L_medan <= max_loss_db)  DAN  (margin_fading >= fade_margin_db)  DAN  (d <= hop maks)
#     L_medan      redaman difraksi knife-edge (ITU-R P.526) pada rintangan terburuk, medan dinaikkan
#                  dem_error_m. `max_loss_db` = batas KEPERCAYAAN model difraksi (di atasnya model tidak
#                  dipercaya), bukan anggaran daya.
#     L_vegetasi   Weissberger (modifikasi, daun penuh) atas kedalaman jalur di dalam kanopi; butuh
#                  raster tinggi kanopi OPSIONAL (ClutterSource). Tanpa data -> 0 (hasil OPTIMISTIS).
#     offset       penyetelan dari RSSI lapangan (lihat link_calibration.py). 0 = model apa adanya.
# Default P_tx/G/sensitivitas mengikuti C-251 Tabel 10.2 (rencana, bukan hasil ukur): kalibrasi dulu
# sebelum percaya angka mutlaknya.
#
# Pencarian: DP berlapis menurut jumlah relay (jumlah minimum dijamin selama beam tidak terpotong),
# lalu di antara yang jumlahnya sama dipilih biaya terendah:
#   biaya relay = W_RELAY + W_BACKHAUL*pen(link ke induk) + W_COVER*pen(link terburuk ke jalur)
#               + W_ACCESS*(jarak ke jalur/radius) + W_SLOPE*(lereng/lereng maks)^2
#   pen(link)   = 0.7 * clip(1 - slack/max_loss_db, 0, 1) + 0.3 * jarak/hop_maks
#   slack       = min(max_loss_db - L_medan, margin_fading - fade_margin_db)   (>= 0 berarti layak)
# Polish: tiap relay digeser halus di sekitar posisi grid untuk menurunkan biaya.

W_RELAY = 100.0
W_BACKHAUL = 6.0
W_COVER = 4.0
W_ACCESS = 3.0
W_SLOPE = 2.0
MARGIN_CAP_M = 50.0  # margin geometris untuk link yang terlalu pendek untuk dinilai
LOSS_CAP_DB = 60.0
VEG_MAX_DEPTH_M = 400.0  # Weissberger berlaku sampai 400 m; di atasnya dijepit

MAX_SLOPE_DEG = 35.0
TRAIL_STEP_KM = 0.04
LINK_END_EXCLUSION_M = 30.0
LINK_SAMPLE_STEP_M = 15.0
MAX_CANDIDATES = 1200
BEAM_WIDTH = 150
POLISH_SWEEPS = 2
DEFAULT_MAX_LOSS_DB = 6.0
DEFAULT_DEM_ERROR_M = 1.0


@dataclass(frozen=True)
class LinkParams:
    """Semua parameter model tautan. Satu objek supaya perencana, evaluasi manual, dan kalibrasi
    memakai angka yang SAMA persis."""

    freq_mhz: float = 915.0
    h_hiker_m: float = 2.0  # tinggi antena pendaki
    h_relay_m: float = 2.0  # tinggi antena relay & base
    max_hop_km: float = 2.0
    max_loss_db: float = DEFAULT_MAX_LOSS_DB  # batas kepercayaan redaman medan (difraksi)
    dem_error_m: float = DEFAULT_DEM_ERROR_M
    end_exclusion_m: float = LINK_END_EXCLUSION_M
    tx_dbm: float = 21.0
    gain_hiker_dbi: float = 5.0  # gain BERSIH antena pendaki (sudah dikurangi rugi kabel/konektor)
    gain_relay_dbi: float = 5.0
    sensitivity_dbm: float = -137.0
    fade_margin_db: float = 10.0  # margin fading yang disyaratkan di atas sensitivitas
    calib_offset_db: float = 0.0  # redaman tambahan hasil kalibrasi lapangan (+ = lebih lemah dari model)
    veg_scale: float = 1.0  # pengali redaman vegetasi (0 = abaikan; <1 bila DEM sudah memuat kanopi)


class ClutterSource:
    """Tinggi kanopi/vegetasi (m) per titik. Kelas dasar = tidak ada data (selalu 0, tidak aktif).
    Titik di luar cakupan data boleh dikembalikan NaN (dianggap 0 = tidak ada vegetasi)."""

    active = False

    def canopy_many(self, lats, lons):
        return np.zeros(np.shape(lats), dtype=float)


def fspl_db(d_km, f_mhz: float):
    """Free-space path loss (dB): 32.44 + 20 log10(d_km) + 20 log10(f_MHz)."""
    return 32.44 + 20.0 * np.log10(np.maximum(d_km, 1e-3)) + 20.0 * math.log10(f_mhz)


def weissberger_db(depth_m, f_mhz: float):
    """Redaman vegetasi Weissberger modifikasi (daun penuh), f dalam GHz, kedalaman dalam m:
    0.45 f^0.284 d (d <= 14 m); 1.33 f^0.284 d^0.588 (14 < d <= 400 m). Kedalaman > 400 m dijepit."""
    d = np.minimum(np.maximum(np.asarray(depth_m, dtype=float), 0.0), VEG_MAX_DEPTH_M)
    f = (f_mhz / 1000.0) ** 0.284
    return np.where(d <= 14.0, 0.45 * f * d, 1.33 * f * np.power(np.maximum(d, 1e-9), 0.588))


def knife_edge_loss_db(nu):
    """Redaman difraksi satu rintangan (ITU-R P.526): J(v) = 6.9 + 20 log10(sqrt((v-0.1)^2+1) + v - 0.1)
    untuk v > -0.78, selain itu 0. v = tinggi rintangan di atas garis pandang * sqrt(2(d1+d2)/(lambda d1 d2))."""
    nu = np.asarray(nu, dtype=float)
    out = np.zeros_like(nu)
    m = nu > -0.78
    x = nu[m] - 0.1
    out[m] = 6.9 + 20.0 * np.log10(np.sqrt(x * x + 1.0) + x)
    return out


def _haversine_np(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = p2 - p1
    dlmb = np.radians(lon2) - np.radians(lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def _n_samples(max_hop_km: float) -> int:
    """Jumlah sampel per link: TETAP (ditentukan hop maks), bukan bergantung pada isi batch, supaya
    satu link yang sama selalu bernilai sama di perencana, polish, evaluasi manual, dan kalibrasi."""
    return int(np.clip(math.ceil(max_hop_km * 1000.0 / LINK_SAMPLE_STEP_M), 16, 200))


def _fin(x, lim: float = 99.0) -> float:
    """Angka yang aman di-JSON-kan (tanpa inf/nan)."""
    x = float(x)
    return -lim if math.isnan(x) else float(min(max(x, -lim), lim))


@dataclass
class LinkEval:
    """Hasil evaluasi link (semua array sepanjang jumlah target)."""

    terrain: np.ndarray  # redaman medan (dB)
    veg: np.ndarray  # redaman vegetasi (dB)
    margin_m: np.ndarray  # margin geometris di atas 60% Fresnel (m), hanya informasi
    dist_km: np.ndarray
    rssi: np.ndarray  # RSSI prediksi (dBm)
    fade: np.ndarray  # rssi - sensitivitas (dB)
    slack: np.ndarray  # >= 0 berarti link layak (-inf kalau di luar hop maks)


class _Model:
    """Evaluator link yang divektorkan: satu titik -> banyak titik."""

    def __init__(self, src: ElevationSource, clutter: ClutterSource | None, p: LinkParams):
        self.src, self.clutter, self.p = src, clutter, p
        self.S = _n_samples(p.max_hop_km)
        self.use_veg = clutter is not None and bool(getattr(clutter, "active", True)) and p.veg_scale > 0
        self.g_rr = 2.0 * p.gain_relay_dbi  # relay <-> relay / base
        self.g_rh = p.gain_relay_dbi + p.gain_hiker_dbi  # relay/base <-> pendaki
        self.lam = 299.792458 / p.freq_mhz

    def link(self, lat1, lon1, ground1, h1, lats2, lons2, grounds2, h2, g_sum, n_samples: int | None = None) -> LinkEval:
        p = self.p
        lats2 = np.asarray(lats2, dtype=float)
        lons2 = np.asarray(lons2, dtype=float)
        grounds2 = np.asarray(grounds2, dtype=float)
        K = lats2.shape[0]
        D = _haversine_np(lat1, lon1, lats2, lons2)  # km
        if K == 0:
            z = np.zeros(0)
            return LinkEval(z, z, z, D, z, z, z)
        S = n_samples or self.S
        t = np.arange(1, S) / S
        la = lat1 + (lats2[:, None] - lat1) * t[None, :]
        lo = lon1 + (lons2[:, None] - lon1) * t[None, :]
        ground = self.src.elevation_many(la.ravel(), lo.ravel()).reshape(K, S - 1)
        e1, e2 = ground1 + h1, grounds2 + h2
        sight = e1 + (e2 - e1)[:, None] * t[None, :]
        Dc = np.maximum(D, 1e-9)[:, None]
        d1, d2 = Dc * t[None, :], Dc * (1.0 - t[None, :])
        curve = 1000.0 * d1 * d2 / (2 * K_FACTOR * EARTH_RADIUS_KM)
        fres = 17.32 * np.sqrt(d1 * d2 / ((p.freq_mhz / 1000.0) * Dc))
        margin = sight - (ground + curve + FRESNEL_CLEARANCE_FRACTION * fres)
        obst = ground + curve + p.dem_error_m - sight  # tinggi rintangan di atas garis pandang (m)
        nu = obst * np.sqrt(2.0 * (d1 + d2) * 1000.0 / (self.lam * d1 * 1000.0 * d2 * 1000.0))
        nu = np.where(np.isnan(nu), np.inf, nu)
        margin = np.where(np.isnan(margin), -np.inf, margin)

        veg = np.zeros(K)
        if self.use_veg:
            canopy = np.nan_to_num(self.clutter.canopy_many(la.ravel(), lo.ravel()), nan=0.0).reshape(K, S - 1)
            inside = canopy > (sight - ground)  # garis pandang lewat DI DALAM kanopi
            step_m = D * 1000.0 / S
            depth = (inside * step_m[:, None]).sum(axis=1)
            c1 = float(np.nan_to_num(self.clutter.canopy_many([lat1], [lon1]), nan=0.0)[0])
            c2 = np.nan_to_num(self.clutter.canopy_many(lats2, lons2), nan=0.0)
            depth = depth + 0.5 * step_m * ((c1 > h1) * 1.0 + (c2 > h2) * 1.0)  # ujung link
            veg = weissberger_db(depth, p.freq_mhz) * p.veg_scale

        if p.end_exclusion_m > 0:  # difraksi: abaikan zona ujung (DEM tidak bisa menyelesaikannya)
            valid = (d1 * 1000.0 >= p.end_exclusion_m) & (d2 * 1000.0 >= p.end_exclusion_m)
            nu = np.where(valid, nu, -np.inf)
            margin = np.where(valid, margin, np.inf)
        nu_max = nu.max(axis=1)
        terrain = np.where(
            np.isposinf(nu_max), LOSS_CAP_DB,
            np.minimum(knife_edge_loss_db(np.where(np.isfinite(nu_max), nu_max, 0.0)), LOSS_CAP_DB))
        mw = margin.min(axis=1)
        mw = np.where(np.isposinf(mw), MARGIN_CAP_M, np.maximum(np.minimum(mw, MARGIN_CAP_M), -MARGIN_CAP_M))
        outside = np.isnan(grounds2)
        terrain = np.where(outside, LOSS_CAP_DB, terrain)
        mw = np.where(outside, -MARGIN_CAP_M, mw)

        rssi = p.tx_dbm + g_sum - fspl_db(D, p.freq_mhz) - terrain - veg - p.calib_offset_db
        fade = rssi - p.sensitivity_dbm
        slack = np.minimum(p.max_loss_db - terrain, fade - p.fade_margin_db)
        slack = np.where(D > p.max_hop_km, -np.inf, slack)
        return LinkEval(terrain, veg, mw, D, rssi, fade, slack)


def predict_links(
    elev_src: ElevationSource, clutter: ClutterSource | None, params: LinkParams,
    from_pt: tuple[float, float], to_pts: list[tuple[float, float]], to_is_hiker: bool = True,
) -> dict:
    """Prediksi link dari satu titik (mis. base) ke banyak titik (mis. posisi pendaki) dengan model
    yang SAMA dengan perencana. Dipakai kalibrasi RSSI. Return dict array: dist_km, terrain_db,
    veg_db, fspl_db, rssi_dbm. Titik di luar DEM -> rssi NaN."""
    m = _Model(elev_src, clutter, params)
    g0 = elev_src.elevation_at(*from_pt)
    lats = np.array([p[0] for p in to_pts], dtype=float)
    lons = np.array([p[1] for p in to_pts], dtype=float)
    grounds = elev_src.elevation_many(lats, lons)
    h_to = params.h_hiker_m if to_is_hiker else params.h_relay_m
    g_sum = m.g_rh if to_is_hiker else m.g_rr
    out = {k: np.full(len(lats), np.nan) for k in ("dist_km", "terrain_db", "veg_db", "fspl_db", "rssi_dbm")}
    for i in range(0, len(lats), 200):  # per potong biar memori kecil
        sl = slice(i, i + 200)
        ok = ~np.isnan(grounds[sl])
        if not ok.any():
            continue
        ev = m.link(from_pt[0], from_pt[1], g0, params.h_relay_m, lats[sl][ok], lons[sl][ok], grounds[sl][ok], h_to, g_sum)
        idx = np.flatnonzero(ok) + i
        out["dist_km"][idx] = ev.dist_km
        out["terrain_db"][idx] = ev.terrain
        out["veg_db"][idx] = ev.veg
        out["fspl_db"][idx] = fspl_db(ev.dist_km, params.freq_mhz)
        out["rssi_dbm"][idx] = ev.rssi
    return out


def _densify(points: list[tuple[float, float]], step_km: float):
    """Sisipkan sampel tiap <= step_km di tiap segmen. Titik asli SELALU ikut.
    Return (lat[], lon[], idx_titik_asli[])."""
    lats, lons, widx = [points[0][0]], [points[0][1]], [0]
    for a, b in zip(points, points[1:]):
        k = max(1, math.ceil(haversine_km(a, b) / step_km))
        for i in range(1, k + 1):
            lats.append(a[0] + (b[0] - a[0]) * i / k)
            lons.append(a[1] + (b[1] - a[1]) * i / k)
        widx.append(len(lats) - 1)
    return np.array(lats), np.array(lons), widx


@dataclass
class _St:
    node: int
    f: int  # frontier: sampel [0, f) sudah tercover, sampel f belum
    cost: float
    prev: "_St | None"
    parent: int  # node induk (0 = base)
    f0: int  # frontier sebelum relay ini (tanggungannya: sampel [f0, f))
    nodes: frozenset


class _Planner:
    """Satu masalah perencanaan: semua matriks cakupan dihitung sekali di sini."""

    def __init__(self, src, clutter, base, trail_points, p: LinkParams, *, radius_km, step_km, max_slope_deg, trail_step_km):
        self.src, self.base, self.p = src, base, p
        self.m = _Model(src, clutter, p)
        self.radius = max(radius_km, 1e-6)
        self.max_slope = max_slope_deg
        self.ref = max(p.max_loss_db, 1.0)  # skala penalti slack

        self.base_ground = src.elevation_at(*base)  # ValueError kalau base di luar DEM
        self.s_lat, self.s_lon, self.wp_idx = _densify(trail_points, trail_step_km)
        self.n = len(self.s_lat)
        self.s_ground = src.elevation_many(self.s_lat, self.s_lon)
        bad = np.flatnonzero(np.isnan(self.s_ground))
        if bad.size:
            src.elevation_at(float(self.s_lat[bad[0]]), float(self.s_lon[bad[0]]))  # ValueError berpesan jelas
            raise ValueError("Titik trail di luar cakupan DEM.")
        seg = _haversine_np(self.s_lat[:-1], self.s_lon[:-1], self.s_lat[1:], self.s_lon[1:])
        self.cum_km = np.concatenate([[0.0], np.cumsum(seg)])
        if self.m.use_veg:
            c = clutter.canopy_many(self.s_lat, self.s_lon)
            self.clutter_cover_pct = float(100.0 * np.mean(~np.isnan(c)))
        else:
            self.clutter_cover_pct = None

        self._build_candidates(step_km)
        self._build_coverage()
        self._bh_cache: dict[int, tuple[np.ndarray, np.ndarray]] = {}

    def to_hiker(self, lat, lon, ground, lats, lons, grounds):
        return self.m.link(lat, lon, ground, self.p.h_relay_m, lats, lons, grounds, self.p.h_hiker_m, self.m.g_rh)

    def to_node(self, lat, lon, ground, lats, lons, grounds):
        return self.m.link(lat, lon, ground, self.p.h_relay_m, lats, lons, grounds, self.p.h_relay_m, self.m.g_rr)

    # ── kandidat ──────────────────────────────────────────────────────────
    def _build_candidates(self, step_km: float) -> None:
        lat0 = float(np.mean(self.s_lat))
        kx, ky = 111.32 * math.cos(math.radians(lat0)), 111.32
        sx = (self.s_lon - self.base[1]) * kx
        sy = (self.s_lat - self.base[0]) * ky
        R = self.radius
        step = step_km
        while True:
            xs = np.arange(sx.min() - R, sx.max() + R + 1e-9, step)
            ys = np.arange(sy.min() - R, sy.max() + R + 1e-9, step)
            gx, gy = np.meshgrid(xs, ys)
            gx, gy = gx.ravel(), gy.ravel()
            dmin = np.empty(gx.shape[0])
            for i in range(0, gx.shape[0], 4000):  # per potong biar memori kecil
                dx = gx[i:i + 4000, None] - sx[None, :]
                dy = gy[i:i + 4000, None] - sy[None, :]
                dmin[i:i + 4000] = np.sqrt(dx * dx + dy * dy).min(axis=1)
            keep = dmin <= R
            if keep.sum() + self.n <= MAX_CANDIDATES or step > 5.0:
                break
            step *= 1.15  # terlalu banyak kandidat -> kasarkan grid (jaga waktu hitung)
        self.step_used = step
        gx, gy, dmin = gx[keep], gy[keep], dmin[keep]
        lat = np.concatenate([self.base[0] + gy / ky, self.s_lat])  # + titik di jalur itu sendiri
        lon = np.concatenate([self.base[1] + gx / kx, self.s_lon])
        acc = np.concatenate([dmin, np.zeros(self.n)])

        ground = self.src.elevation_many(lat, lon)
        # kemiringan lokal (selisih terpusat +-30 m) -> buang lereng yang tidak mungkin dipasangi
        dlat, dlon = 0.03 / 111.32, 0.03 / kx
        ge = self.src.elevation_many(lat, lon + dlon); gw = self.src.elevation_many(lat, lon - dlon)
        gn = self.src.elevation_many(lat + dlat, lon); gs = self.src.elevation_many(lat - dlat, lon)
        slope = np.degrees(np.arctan(np.hypot((ge - gw) / 60.0, (gn - gs) / 60.0)))
        ok = ~np.isnan(ground) & ~np.isnan(slope) & (slope <= self.max_slope)
        self.N = int(ok.sum())
        # node 0 = base, 1..N = kandidat
        self.n_lat = np.concatenate([[self.base[0]], lat[ok]])
        self.n_lon = np.concatenate([[self.base[1]], lon[ok]])
        self.n_ground = np.concatenate([[self.base_ground], ground[ok]])
        self.n_slope = np.concatenate([[0.0], slope[ok]])
        self.n_acc = np.concatenate([[0.0], acc[ok]])

    # ── cakupan node -> sampel jalur ─────────────────────────────────────────
    def _build_coverage(self) -> None:
        self.cs = np.empty((self.N + 1, self.n))  # slack node -> sampel (>= 0 layak)
        self.cd = np.empty((self.N + 1, self.n))  # jarak
        for u in range(self.N + 1):
            ev = self.to_hiker(self.n_lat[u], self.n_lon[u], self.n_ground[u], self.s_lat, self.s_lon, self.s_ground)
            self.cs[u], self.cd[u] = ev.slack, ev.dist_km
        ok = self.cs >= 0.0
        self.ng = np.empty((self.N + 1, self.n + 1), dtype=np.int32)  # ng[u,f] = sampel pertama >= f yang TIDAK tercover u
        grid = np.arange(self.n + 1)
        for u in range(self.N + 1):
            bad = np.append(np.flatnonzero(~ok[u]), self.n)
            self.ng[u] = bad[np.searchsorted(bad, grid)]

    # ── backhaul antar node (antena relay di kedua ujung) ───────────────────────
    def _bh(self, v: int):
        hit = self._bh_cache.get(v)
        if hit is None:
            d = _haversine_np(self.n_lat[v], self.n_lon[v], self.n_lat, self.n_lon)
            slack = np.full(self.N + 1, -np.inf)
            near = np.flatnonzero(d <= self.p.max_hop_km)  # hanya yang dalam jangkauan hop yang perlu dinilai
            if near.size:
                slack[near] = self.to_node(self.n_lat[v], self.n_lon[v], self.n_ground[v],
                                           self.n_lat[near], self.n_lon[near], self.n_ground[near]).slack
            slack[v] = -np.inf
            hit = self._bh_cache[v] = (slack, d)
        return hit

    def wp_covered(self, f: int) -> int:
        """Index titik klik terjauh yang seluruhnya ada di sampel [0, f)."""
        return max([w for w, i in enumerate(self.wp_idx) if i < f], default=-1)

    # ── biaya satu relay ────────────────────────────────────────────────────
    def _link_pen(self, slack, dist_km):
        s = 0.0 if not np.isfinite(slack) else float(slack)
        return 0.7 * min(max(1.0 - s / self.ref, 0.0), 1.0) + 0.3 * min(dist_km / self.p.max_hop_km, 1.0)

    def _relay_cost(self, u, bh_slack, bh_d, cov_slack, cov_d):
        return (W_RELAY + W_BACKHAUL * self._link_pen(bh_slack, bh_d) + W_COVER * self._link_pen(cov_slack, cov_d)
                + W_ACCESS * min(self.n_acc[u] / self.radius, 1.0)
                + W_SLOPE * (self.n_slope[u] / self.max_slope) ** 2)

    # ── DP berlapis menurut jumlah relay ───────────────────────────────────────
    def search(self, max_relays: int):
        f0 = int(self.ng[0, 0])
        root = _St(0, f0, 0.0, None, 0, 0, frozenset([0]))
        if f0 >= self.n:
            return root, None
        best_partial = root
        layer = [root]
        reason = "max_relays"  # kalau loop habis tanpa lengkap = batas relay tercapai
        s0, d0 = self._bh(0)
        for k in range(1, max_relays + 1):
            new: dict[tuple[int, int], _St] = {}
            for st in layer:
                v, f = st.node, st.f
                sv, dv = self._bh(v)
                use_v = sv >= s0  # induk = relay sebelumnya atau langsung base, mana yang slack-nya lebih besar
                bs = np.where(use_v, sv, s0)[1:]
                bd = np.where(use_v, dv, d0)[1:]
                valid = (self.ng[1:, f] > f) & (bs >= 0.0)
                for ui in np.flatnonzero(valid):
                    u = int(ui) + 1
                    if u in st.nodes:
                        continue
                    f2 = int(self.ng[u, f])
                    cost = st.cost + self._relay_cost(u, float(bs[ui]), float(bd[ui]),
                                                      float(self.cs[u, f:f2].min()), float(self.cd[u, f:f2].max()))
                    key = (u, f2)
                    cur = new.get(key)
                    if cur is None or cost < cur.cost:
                        new[key] = _St(u, f2, cost, st, v if use_v[u] else 0, f, st.nodes | {u})
            if not new:
                reason = "no_candidate"
                break
            done = [s for s in new.values() if s.f >= self.n]
            if done:
                return min(done, key=lambda s: s.cost), None
            top = max(new.values(), key=lambda s: (s.f, -s.cost))
            if top.f > best_partial.f:
                best_partial = top
            layer = self._prune(new)
        return best_partial, reason

    @staticmethod
    def _prune(new):
        by_node: dict[int, list[_St]] = {}
        for s in new.values():
            by_node.setdefault(s.node, []).append(s)
        kept = []
        for lst in by_node.values():  # dominasi: frontier >= dan biaya <=
            lst.sort(key=lambda s: (-s.f, s.cost))
            best = float("inf")
            for s in lst:
                if s.cost < best - 1e-9:
                    kept.append(s)
                    best = s.cost
        kept.sort(key=lambda s: (-s.f, s.cost))
        return kept[:BEAM_WIDTH]

    # ── polish: geser halus tiap relay di sekitar posisi grid ───────────────────
    def polish(self, relays: list[dict]) -> None:
        if not relays:
            return
        fine = self.step_used / 2.5
        kx = 111.32 * math.cos(math.radians(float(np.mean(self.s_lat))))
        for _ in range(POLISH_SWEEPS):
            moved = False
            for i, r in enumerate(relays):
                best = (self._local_cost(i, relays, r["lat"], r["lon"]), r["lat"], r["lon"])
                for a in range(-2, 3):
                    for b in range(-2, 3):
                        if a == 0 and b == 0:
                            continue
                        lat = r["lat"] + a * fine / 111.32
                        lon = r["lon"] + b * fine / kx
                        c = self._local_cost(i, relays, lat, lon)
                        if c is not None and (best[0] is None or c < best[0] - 1e-6):
                            best = (c, lat, lon)
                if (best[1], best[2]) != (r["lat"], r["lon"]):
                    r["lat"], r["lon"] = best[1], best[2]
                    moved = True
            if not moved:
                break

    def _local_cost(self, i: int, relays: list[dict], lat: float, lon: float):
        """Biaya lokal relay ke-i di (lat, lon); None kalau memutus link/cakupan yang diwajibkan."""
        try:
            g = self.src.elevation_at(lat, lon)
        except ValueError:
            return None
        r = relays[i]
        pl = self._parent_ll(r["parent_i"], relays)
        b = self.to_node(pl[0], pl[1], pl[2], [lat], [lon], [g])
        if b.slack[0] < 0:
            return None
        lo, hi = r["f0"], r["f"]
        c = self.to_hiker(lat, lon, g, self.s_lat[lo:hi], self.s_lon[lo:hi], self.s_ground[lo:hi])
        if c.slack.min() < 0:
            return None
        cost = 0.0
        for x in relays:  # anak yang bergantung pada relay ini
            if x["parent_i"] == i + 1:
                k = self.to_node(lat, lon, g, [x["lat"]], [x["lon"]], [self.src.elevation_at(x["lat"], x["lon"])])
                if k.slack[0] < 0:
                    return None
                cost += W_BACKHAUL * self._link_pen(float(k.slack[0]), float(k.dist_km[0]))
        slope = self._slope_at(lat, lon)
        if slope is None or slope > self.max_slope:
            return None
        acc = self._dist_to_trail_km(lat, lon)
        if acc > self.radius * 1.0001:
            return None
        return (cost + W_BACKHAUL * self._link_pen(float(b.slack[0]), float(b.dist_km[0]))
                + W_COVER * self._link_pen(float(c.slack.min()), float(c.dist_km.max()))
                + W_ACCESS * min(acc / self.radius, 1.0) + W_SLOPE * (slope / self.max_slope) ** 2)

    def _parent_ll(self, parent_i: int, relays: list[dict]):
        if parent_i == 0:
            return self.base[0], self.base[1], self.base_ground
        r = relays[parent_i - 1]
        return r["lat"], r["lon"], self.src.elevation_at(r["lat"], r["lon"])

    def _slope_at(self, lat: float, lon: float):
        kx = 111.32 * math.cos(math.radians(lat))
        dlat, dlon = 0.03 / 111.32, 0.03 / kx
        v = self.src.elevation_many([lat, lat, lat + dlat, lat - dlat], [lon + dlon, lon - dlon, lon, lon])
        if np.isnan(v).any():
            return None
        return float(np.degrees(np.arctan(math.hypot((v[0] - v[1]) / 60.0, (v[2] - v[3]) / 60.0))))

    def _dist_to_trail_km(self, lat: float, lon: float) -> float:
        return float(_haversine_np(lat, lon, self.s_lat, self.s_lon).min())


def make_link_params(
    max_hop_km: float = 2.0, antenna_h_m: float = 2.0, freq_mhz: float = 915.0, *, relay_h_m: float | None = None,
    max_loss_db: float = DEFAULT_MAX_LOSS_DB, dem_error_m: float = DEFAULT_DEM_ERROR_M,
    link_end_exclusion_m: float = LINK_END_EXCLUSION_M, tx_dbm: float = 21.0, gain_hiker_dbi: float = 5.0,
    gain_relay_dbi: float = 5.0, sensitivity_dbm: float = -137.0, fade_margin_db: float = 10.0,
    calib_offset_db: float = 0.0, veg_scale: float = 1.0,
) -> LinkParams:
    return LinkParams(
        freq_mhz=freq_mhz, h_hiker_m=antenna_h_m, h_relay_m=antenna_h_m if relay_h_m is None else relay_h_m,
        max_hop_km=max_hop_km, max_loss_db=max_loss_db, dem_error_m=dem_error_m,
        end_exclusion_m=link_end_exclusion_m, tx_dbm=tx_dbm, gain_hiker_dbi=gain_hiker_dbi,
        gain_relay_dbi=gain_relay_dbi, sensitivity_dbm=sensitivity_dbm, fade_margin_db=fade_margin_db,
        calib_offset_db=calib_offset_db, veg_scale=veg_scale)


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
    *,
    relay_h_m: float | None = None,
    max_loss_db: float = DEFAULT_MAX_LOSS_DB,
    dem_error_m: float = DEFAULT_DEM_ERROR_M,
    tx_dbm: float = 21.0,
    gain_hiker_dbi: float = 5.0,
    gain_relay_dbi: float = 5.0,
    sensitivity_dbm: float = -137.0,
    fade_margin_db: float = 10.0,
    calib_offset_db: float = 0.0,
    veg_scale: float = 1.0,
    clutter: ClutterSource | None = None,
    max_slope_deg: float = MAX_SLOPE_DEG,
    trail_step_km: float = TRAIL_STEP_KM,
    link_end_exclusion_m: float = LINK_END_EXCLUSION_M,
    polish: bool = True,
) -> RelayPlan:
    """Cari penempatan relay OPTIMAL: jumlah relay minimum yang menjangkau seluruh jalur, lalu (di
    antara yang jumlahnya sama) yang slack link-nya paling besar, paling dekat jalur, paling landai.
    Definisi model tautan dan biaya: lihat komentar di atas. `clutter` = data kanopi (opsional)."""
    n_wp = len(trail_points)
    if n_wp == 0:
        raise ValueError("Trail kosong.")
    p = make_link_params(max_hop_km, antenna_h_m, freq_mhz, relay_h_m=relay_h_m, max_loss_db=max_loss_db,
                         dem_error_m=dem_error_m, link_end_exclusion_m=link_end_exclusion_m, tx_dbm=tx_dbm,
                         gain_hiker_dbi=gain_hiker_dbi, gain_relay_dbi=gain_relay_dbi,
                         sensitivity_dbm=sensitivity_dbm, fade_margin_db=fade_margin_db,
                         calib_offset_db=calib_offset_db, veg_scale=veg_scale)
    P = _Planner(elev_src, clutter, base, trail_points, p, radius_km=candidate_search_radius_km,
                 step_km=candidate_grid_step_km, max_slope_deg=max_slope_deg, trail_step_km=trail_step_km)
    end, reason = P.search(int(max_relays))

    path: list[_St] = []
    s = end
    while s is not None and s.prev is not None:
        path.append(s)
        s = s.prev
    path.reverse()
    order = {st.node: i + 1 for i, st in enumerate(path)}
    relays_raw = [{"lat": float(P.n_lat[st.node]), "lon": float(P.n_lon[st.node]),
                   "parent_i": order.get(st.parent, 0), "f0": st.f0, "f": st.f} for st in path]
    if polish:
        P.polish(relays_raw)

    # metrik akhir dihitung ulang dari posisi final (setelah polish)
    suggestions: list[RelaySuggestion] = []
    nodes_ll = [(float(base[0]), float(base[1]), P.base_ground)]
    base_ev = P.to_hiker(base[0], base[1], P.base_ground, P.s_lat, P.s_lon, P.s_ground)
    union = base_ev.slack >= 0
    for r in relays_raw:
        g = elev_src.elevation_at(r["lat"], r["lon"])
        pl = nodes_ll[r["parent_i"]]
        b = P.to_node(pl[0], pl[1], pl[2], [r["lat"]], [r["lon"]], [g])
        c = P.to_hiker(r["lat"], r["lon"], g, P.s_lat, P.s_lon, P.s_ground)
        union = union | (c.slack >= 0)
        lo, hi = r["f0"], r["f"]
        seg_loss = (c.terrain + c.veg)[lo:hi]
        suggestions.append(RelaySuggestion(
            lat=r["lat"], lon=r["lon"], covers_trail_index=max(P.wp_covered(hi), 0),
            worst_margin_m=_fin(b.margin_m[0]), parent=r["parent_i"], hop_km=float(b.dist_km[0]),
            loss_db=_fin(b.terrain[0]), veg_db=_fin(b.veg[0]), rssi_dbm=_fin(b.rssi[0], 200.0),
            fade_margin_db=_fin(b.fade[0], 200.0),
            cover_loss_db=_fin(seg_loss.max()) if seg_loss.size else 0.0,
            cover_fade_db=_fin(c.fade[lo:hi].min(), 200.0) if hi > lo else 0.0,
            access_km=P._dist_to_trail_km(r["lat"], r["lon"]), slope_deg=P._slope_at(r["lat"], r["lon"]) or 0.0,
        ))
        nodes_ll.append((r["lat"], r["lon"], g))

    f_end = end.f
    return RelayPlan(
        relays=suggestions, n_trail=n_wp, covered_through=P.wp_covered(f_end),
        stall_reason=None if f_end >= P.n else (reason or "no_candidate"),
        coverage_pct=float(100.0 * union.mean()), trail_km=float(P.cum_km[-1]),
        covered_km=float(P.cum_km[-1] if f_end >= P.n else P.cum_km[max(f_end - 1, 0)]),
        n_candidates=P.N, step_used_km=float(P.step_used),
        uses_clutter=P.m.use_veg, clutter_coverage_pct=P.clutter_cover_pct,
    )


def evaluate_relay_chain(
    elev_src: ElevationSource,
    base: tuple[float, float],
    relay_points: list[tuple[float, float]],
    trail_points: list[tuple[float, float]],
    max_hop_km: float = 2.0,
    antenna_h_m: float = 2.0,
    freq_mhz: float = 915.0,
    *,
    relay_h_m: float | None = None,
    max_loss_db: float = DEFAULT_MAX_LOSS_DB,
    dem_error_m: float = DEFAULT_DEM_ERROR_M,
    tx_dbm: float = 21.0,
    gain_hiker_dbi: float = 5.0,
    gain_relay_dbi: float = 5.0,
    sensitivity_dbm: float = -137.0,
    fade_margin_db: float = 10.0,
    calib_offset_db: float = 0.0,
    veg_scale: float = 1.0,
    clutter: ClutterSource | None = None,
    trail_step_km: float = TRAIL_STEP_KM,
    link_end_exclusion_m: float = LINK_END_EXCLUSION_M,
) -> tuple[list[RelayEval], int]:
    """Nilai posisi relay yang SUDAH ditentukan (mis. digeser manual) dengan model tautan yang sama
    dengan perencana otomatis (slack >= 0 berarti link jalan).

    Relay tersambung kalau punya link yang jalan ke SALAH SATU node sebelumnya (base atau relay
    sebelumnya yang tersambung); dipilih yang slack-nya terbesar. Cakupan: sampel jalur (tiap ~40 m)
    dihitung berurutan dari awal, sama seperti perencana. Return (hasil_per_relay, covered_through)."""
    p = make_link_params(max_hop_km, antenna_h_m, freq_mhz, relay_h_m=relay_h_m, max_loss_db=max_loss_db,
                         dem_error_m=dem_error_m, link_end_exclusion_m=link_end_exclusion_m, tx_dbm=tx_dbm,
                         gain_hiker_dbi=gain_hiker_dbi, gain_relay_dbi=gain_relay_dbi,
                         sensitivity_dbm=sensitivity_dbm, fade_margin_db=fade_margin_db,
                         calib_offset_db=calib_offset_db, veg_scale=veg_scale)
    model = _Model(elev_src, clutter, p)
    s_lat, s_lon, wp_idx = _densify(trail_points, trail_step_km)
    s_ground = elev_src.elevation_many(s_lat, s_lon)
    if np.isnan(s_ground).any():
        k = int(np.flatnonzero(np.isnan(s_ground))[0])
        elev_src.elevation_at(float(s_lat[k]), float(s_lon[k]))
        raise ValueError("Titik trail di luar cakupan DEM.")
    n = len(s_lat)

    def cover(lat, lon, g):
        return model.link(lat, lon, g, p.h_relay_m, s_lat, s_lon, s_ground, p.h_hiker_m, model.g_rh).slack >= 0

    def frontier(ok, f):
        bad = np.flatnonzero(~ok[f:])
        return n if bad.size == 0 else f + int(bad[0])

    def wp(f):
        return max([w for w, i in enumerate(wp_idx) if i < f], default=-1)

    base_g = elev_src.elevation_at(*base)
    nodes = [(base[0], base[1], base_g)]
    connected = [True]
    f = frontier(cover(base[0], base[1], base_g), 0)
    out: list[RelayEval] = []
    for rp in relay_points:
        g = elev_src.elevation_at(rp[0], rp[1])
        ev = model.link(rp[0], rp[1], g, p.h_relay_m, [x[0] for x in nodes], [x[1] for x in nodes],
                        [x[2] for x in nodes], p.h_relay_m, model.g_rr)
        good = [i for i in range(len(nodes)) if connected[i] and ev.slack[i] >= 0]
        if good:
            q, ok = max(good, key=lambda i: (ev.slack[i], i)), True
        else:
            q, ok = len(nodes) - 1, False  # laporkan terhadap node sebelumnya
        if ok:
            f = frontier(cover(rp[0], rp[1], g) | (np.arange(n) < f), f)
        out.append(RelayEval(rp[0], rp[1], float(ev.dist_km[q]), _fin(ev.margin_m[q]), ok, wp(f), parent=q,
                             loss_db=_fin(ev.terrain[q]), veg_db=_fin(ev.veg[q]),
                             rssi_dbm=_fin(ev.rssi[q], 200.0), fade_margin_db=_fin(ev.fade[q], 200.0)))
        nodes.append((rp[0], rp[1], g))
        connected.append(ok)
    return out, wp(f)