"""Tes logika murni (stdlib unittest, tanpa DB/FastAPI):
    cd backend && python -m unittest discover -s tests -v
Yang TIDAK tercakup di sini: query SQL & koneksi Postgres (perlu DB sungguhan)."""
import math
import random
import unittest
from datetime import datetime, timezone

from app.services import base_protocol as bp
from app.services.geo import haversine_m, thin_indices, thin_track
from app.services.liveness import FALLBACK_S, MAX_S, MIN_S, observed_interval_s, stale_threshold_s

FIX = "CSV_DATA,123,1,H01,LANGSUNG,0,45000,45010,31,2026-07-01T03:04:05Z,-7.5912345,110.4001234,1450.20,1.20,9,0.95,-97,2,5"
NOFIX = "CSV_DATA,124,1,H01,LANGSUNG,0,50000,50020,0,-,0.0000000,0.0000000,0.00,0.00,0,0.00,-101,0,5"


class Haversine(unittest.TestCase):
    def test_nol(self):
        self.assertEqual(haversine_m(-7.5, 110.4, -7.5, 110.4), 0.0)

    def test_satu_derajat_lintang(self):
        self.assertAlmostEqual(haversine_m(0, 0, 1, 0), 111195, delta=100)  # ~111.2 km

    def test_simetris_dan_antipoda_tidak_nan(self):
        self.assertAlmostEqual(haversine_m(10, 20, 11, 22), haversine_m(11, 22, 10, 20), places=6)
        self.assertFalse(math.isnan(haversine_m(0, 0, 0, 180)))

    def test_selisih_vs_spheroid_kecil(self):
        # Pembanding: ~1 km di Indonesia (lintang ~-7.6). Spheroid WGS84 1 derajat bujur di lintang itu = 110.4 km.
        d = haversine_m(-7.6, 110.4, -7.6, 110.40905)
        self.assertAlmostEqual(d, 1000, delta=8)  # galat < 0.8%


class Parser(unittest.TestCase):
    def test_paket_dengan_fix(self):
        r = bp.to_record(bp.parse_csv_data(FIX))
        self.assertEqual((r.hiker_code, r.sequence, r.rssi_dbm), ("H01", 123, -97))
        self.assertAlmostEqual(r.lat, -7.5912345)
        self.assertTrue(r.gps_valid and r.time_from_gps)
        self.assertEqual(r.recorded_at, datetime(2026, 7, 1, 3, 4, 5, tzinfo=timezone.utc))

    def test_REGRESI_tanpa_fix_bukan_titik_nol(self):
        """Firmware mencetak 0.0000000,0.0000000 saat tidak ada fix. Harus jadi NULL, bukan (0,0)."""
        r = bp.to_record(bp.parse_csv_data(NOFIX), now=datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assertIsNone(r.lat)
        self.assertIsNone(r.lon)
        self.assertFalse(r.gps_valid)
        self.assertFalse(r.time_from_gps)  # gps_utc "-" -> pakai waktu terima

    def test_flags_kosong_koordinat_nol_tetap_dianggap_tanpa_fix(self):
        row = bp.parse_csv_data(NOFIX)
        row["gps_flags"] = ""
        self.assertIsNone(bp.to_record(row).lat)

    def test_fix_tapi_satelit_sedikit_tidak_valid(self):
        row = bp.parse_csv_data(FIX)
        row["satellites"] = "3"
        r = bp.to_record(row)
        self.assertIsNotNone(r.lat)       # lokasi tetap disimpan
        self.assertFalse(r.gps_valid)     # tapi ditandai tidak valid (C-251 4.1.3)

    def test_tahun_2000_bukan_waktu_gps(self):
        row = bp.parse_csv_data(FIX)
        row["gps_utc"] = "2000-01-01T00:00:00Z"
        self.assertFalse(bp.to_record(row).time_from_gps)

    def test_baris_bukan_data_atau_kurang_field(self):
        self.assertIsNone(bp.parse_csv_data("[INFO] base siap"))
        self.assertIsNone(bp.parse_csv_data("CSV_DATA,1,2,3"))
        self.assertIsNone(bp.parse_csv_data("CFG_ACK,1,2"))

    def test_field_tambahan_diabaikan(self):
        self.assertIsNotNone(bp.parse_csv_data(FIX + ",SOS,1"))


class PilihPort(unittest.TestCase):
    CP210X = {"device": "COM5", "description": "Silicon Labs CP210x", "vid": 0x10C4, "pid": 0xEA60}
    CH340 = {"device": "COM7", "description": "USB-SERIAL CH340", "vid": 0x1A86, "pid": 0x7523}
    BT = {"device": "COM3", "description": "Standard Serial over Bluetooth", "vid": None, "pid": None}

    def test_satu_kandidat_dipilih_otomatis(self):
        self.assertEqual(bp.select_port([self.BT, self.CP210X], "auto")[0], "COM5")

    def test_dua_kandidat_tidak_menebak(self):
        port, cands = bp.select_port([self.CP210X, self.CH340], "auto")
        self.assertIsNone(port)
        self.assertEqual(len(cands), 2)

    def test_pilihan_eksplisit_menang(self):
        self.assertEqual(bp.select_port([self.CP210X, self.CH340], "COM7")[0], "COM7")

    def test_tidak_ada_port(self):
        self.assertEqual(bp.select_port([], "auto"), (None, []))


class NodeBasi(unittest.TestCase):
    @staticmethod
    def ts(gaps, now=1000.0):
        out, t = [now], now
        for g in gaps:
            t -= g
            out.append(t)
        return out

    def test_mode_real_5_detik(self):
        self.assertAlmostEqual(stale_threshold_s(self.ts([5, 4.2, 5.8, 5, 6, 4.5, 5.1])), 20.0, delta=1.5)

    def test_mode_optimized_dijepit_batas_bawah(self):
        self.assertEqual(stale_threshold_s(self.ts([0.5] * 10)), MIN_S)

    def test_kebal_blackout_dan_coba_ulang_cepat(self):
        self.assertAlmostEqual(stale_threshold_s(self.ts([5, 5, 300, 5, 1.5, 5, 5, 5])), 20.0, delta=1.0)

    def test_sinyal_lemah_ambang_menyesuaikan(self):
        self.assertAlmostEqual(stale_threshold_s(self.ts([10, 12, 9, 11, 10])), 40.0, delta=4)

    def test_data_kurang_pakai_konfigurasi_lalu_fallback(self):
        self.assertEqual(stale_threshold_s(self.ts([5]), configured_interval_s=30), 120.0)
        self.assertEqual(stale_threshold_s(None, None), FALLBACK_S)
        self.assertIsNone(observed_interval_s([1000.0, 990.0]))

    def test_batas_atas(self):
        self.assertEqual(stale_threshold_s(self.ts([1000] * 5)), MAX_S)


class PenjarangJejak(unittest.TestCase):
    @staticmethod
    def jejak(n, seed=1):
        rnd = random.Random(seed)
        lat, lon, pts = -7.6, 110.4, []
        for i in range(n):
            lat += 0.00002 + rnd.uniform(-0.000005, 0.000005)
            lon += 0.00003 * math.sin(i / 150) + rnd.uniform(-0.000004, 0.000004)
            pts.append({"lat": lat, "lon": lon, "i": i})
        return pts

    def test_tidak_diubah_kalau_sudah_sedikit(self):
        p = self.jejak(100)
        self.assertIs(thin_track(p, 500), p)
        self.assertIs(thin_track(p, None), p)

    def test_batas_titik_dan_ujung_terjaga(self):
        p = self.jejak(8000)
        t = thin_track(p, 800)
        self.assertLessEqual(len(t), 800)
        self.assertGreater(len(t), 100)
        self.assertEqual((t[0]["i"], t[-1]["i"]), (0, 7999))
        self.assertEqual([x["i"] for x in t], sorted(x["i"] for x in t))  # urutan waktu terjaga

    def test_bentuk_terjaga_lebih_baik_dari_stride_biasa(self):
        p = self.jejak(4000)
        coords = [(r["lat"], r["lon"]) for r in p]
        keep = thin_indices(coords, 300)

        def max_dev(idx):
            worst = 0.0
            for a, b in zip(idx, idx[1:]):
                for k in range(a + 1, b):
                    # jarak titik ke garis a-b, aproksimasi meter datar
                    ax, ay = coords[a][1] * 110000, coords[a][0] * 110540
                    bx, by = coords[b][1] * 110000, coords[b][0] * 110540
                    px, py = coords[k][1] * 110000, coords[k][0] * 110540
                    dx, dy = bx - ax, by - ay
                    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy or 1)))
                    worst = max(worst, math.hypot(px - ax - t * dx, py - ay - t * dy))
            return worst

        stride = list(range(0, 4000, 4000 // 300))
        if stride[-1] != 3999:
            stride.append(3999)
        self.assertLessEqual(max_dev(keep), max_dev(stride))

    def test_sesi_sangat_panjang_tetap_cepat_dan_valid(self):
        import time
        p = self.jejak(60000)
        t0 = time.time()
        t = thin_track(p, 1500)
        self.assertLess(time.time() - t0, 8)
        self.assertLessEqual(len(t), 1500)
        self.assertEqual(t[-1]["i"], 59999)


class TrailProfil3D(unittest.TestCase):
    """Tes trail_profile_3d: PROFIL penuh sepanjang segmen, bukan dua-ujung.

    Sumber elevasi tiruan: fungsi elevasi dari posisi + opsi 'di luar DEM' (NaN) untuk lat tertentu.
    Tidak menyentuh rasterio/DB — murni logika."""

    class FlatElev:
        """Medan datar: semua titik di dalam cakupan punya elevasi konstan."""
        def __init__(self, elev_m=100.0):
            self.elev_m = elev_m

        def elevation_many(self, lats, lons):
            import numpy as np
            return np.full(np.shape(lats), self.elev_m, dtype=float)

    class RampElev:
        """Elevasi naik linear terhadap lintang (per derajat), untuk menguji 3D > horizontal."""
        def __init__(self, slope_m_per_deg):
            self.slope = slope_m_per_deg

        def elevation_many(self, lats, lons):
            import numpy as np
            return np.asarray(lats, dtype=float) * self.slope

    class HoleElev:
        """Datar, tetapi titik dengan lon >= hole_lon dianggap di luar DEM (NaN)."""
        def __init__(self, hole_lon, elev_m=100.0):
            self.hole_lon = hole_lon
            self.elev_m = elev_m

        def elevation_many(self, lats, lons):
            import numpy as np
            lons = np.asarray(lons, dtype=float)
            out = np.full(lons.shape, self.elev_m, dtype=float)
            out[lons >= self.hole_lon] = np.nan
            return out

    def setUp(self):
        from app.services.terrain_planner import trail_profile_3d
        self.fn = trail_profile_3d

    def test_3d_tidak_pernah_kurang_dari_horizontal(self):
        res = self.fn(self.RampElev(2000.0), {"lat": -7.60, "lon": 110.40},
                      [(-7.59, 110.40), (-7.58, 110.41)])
        self.assertIsNotNone(res["total_3d_m"])
        self.assertGreaterEqual(res["total_3d_m"], res["total_horizontal_m"])

    def test_medan_datar_3d_mendekati_horizontal(self):
        res = self.fn(self.FlatElev(), {"lat": -7.60, "lon": 110.40},
                      [(-7.59, 110.40), (-7.59, 110.41)])
        self.assertIsNotNone(res["total_3d_m"])
        self.assertAlmostEqual(res["total_3d_m"], res["total_horizontal_m"], delta=0.01)

    def test_segmen_datar_satu_km_sekitar_1000_m(self):
        # ~1 km ke utara di lintang -7.6 (0.008993 derajat lintang ~ 1000 m), medan datar.
        res = self.fn(self.FlatElev(), {"lat": -7.60, "lon": 110.40}, [(-7.591007, 110.40)])
        self.assertEqual(len(res["segments"]), 1)
        self.assertAlmostEqual(res["segments"][0]["dist_3d_m"], 1000, delta=5)
        self.assertAlmostEqual(res["total_horizontal_m"], 1000, delta=5)

    def test_segmen_di_luar_dem_jadi_none_dan_total_tidak_lengkap(self):
        # Segmen kedua masuk ke lon >= 110.405 -> ada sub-titik di luar DEM.
        res = self.fn(self.HoleElev(hole_lon=110.405), {"lat": -7.60, "lon": 110.40},
                      [(-7.59, 110.40), (-7.59, 110.41)])
        self.assertEqual(len(res["segments"]), 2)
        self.assertIsNotNone(res["segments"][0]["dist_3d_m"])  # segmen dalam DEM tetap terhitung
        self.assertIsNone(res["segments"][1]["dist_3d_m"])  # segmen keluar DEM -> None
        self.assertTrue(res["incomplete"])
        self.assertIsNone(res["total_3d_m"])
        # Horizontal harus tetap lengkap walau 3D tidak.
        self.assertGreater(res["total_horizontal_m"], 0)

    def test_tanpa_base_mulai_dari_titik_pertama(self):
        res = self.fn(self.FlatElev(), None, [(-7.60, 110.40), (-7.59, 110.40)])
        self.assertEqual(len(res["segments"]), 1)
        self.assertEqual(res["segments"][0]["from"], "Titik 1")
        self.assertEqual(res["segments"][0]["to"], "Titik 2")

    def test_kurang_dari_dua_titik_tidak_ada_segmen(self):
        res = self.fn(self.FlatElev(), None, [(-7.60, 110.40)])
        self.assertEqual(res["segments"], [])
        self.assertEqual(res["total_horizontal_m"], 0.0)
        self.assertEqual(res["total_3d_m"], 0.0)
        self.assertFalse(res["incomplete"])

    def test_profil_penuh_bukan_dua_ujung(self):
        # Medan berbentuk lembah di tengah: dua-ujung (elev sama) akan menghitung 3D ~= horizontal,
        # tetapi PROFIL penuh harus lebih panjang karena turun lalu naik di tengah segmen.
        import numpy as np

        class ValleyElev:
            def elevation_many(self, lats, lons):
                lats = np.asarray(lats, dtype=float)
                # Lembah dalam & lebar: turun 1500 m di tengah lintasan lintang, kembali ke 100 m di ujung.
                mid = (-7.60 + -7.55) / 2
                return 100.0 - 1500.0 * np.exp(-((lats - mid) / 0.012) ** 2)

        res = self.fn(ValleyElev(), {"lat": -7.60, "lon": 110.40}, [(-7.55, 110.40)])
        # Dua ujung punya elevasi hampir sama (100 m), jadi pendekatan "dua-ujung" akan menghitung
        # 3D ~= horizontal. Profil penuh melewati lembah -1500 m lalu naik lagi -> jauh lebih panjang,
        # membuktikan perhitungan memakai SEMUA sub-titik, bukan sekadar dua ujung segmen.
        self.assertGreater(res["segments"][0]["dist_3d_m"], res["total_horizontal_m"] + 300)


if __name__ == "__main__":
    unittest.main()
