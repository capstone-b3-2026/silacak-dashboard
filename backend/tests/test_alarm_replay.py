import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from app.services import alarm_replay as ar  # noqa: E402

LAT0, LON0 = -7.6, 110.4
M_LAT = 1 / 110540.0
M_LON = 1 / (111320.0 * math.cos(math.radians(LAT0)))
TRAIL = [(LAT0 + k * 100 * M_LAT, LON0) for k in range(0, 31)]   # lurus ke utara 3 km


def at(north_m, east_m=0.0):
    return (LAT0 + north_m * M_LAT, LON0 + east_m * M_LON)


def walk(rng, noise_m, segments, step_s=5.0):
    """segments: [(durasi_dtk, utara_awal_m, utara_akhir_m, timur_m)] -> daftar fix (t, lat, lon) dengan galat GPS acak."""
    fixes, t = [], 0.0
    for dur, n0, n1, east in segments:
        steps = max(int(dur / step_s), 1)
        for i in range(steps):
            n = n0 + (n1 - n0) * i / steps
            lat, lon = at(n + rng.gauss(0, noise_m), east + rng.gauss(0, noise_m))
            fixes.append((t, lat, lon))
            t += step_s
    return fixes


class Replay(unittest.TestCase):
    def test_episodes_dan_score_dasar(self):
        st = [(0, False), (5, True), (10, True), (15, False), (20, True)]
        self.assertEqual(ar.episodes(st), [(5, 10), (20, 20)])
        s = ar.score([(5, 10), (20, 20)], truth=[(4, 12)])
        self.assertEqual((s["false_alarms"], s["detected"], s["missed"], s["delay_s"]), (1, 1, 0, [1]))
        self.assertEqual(ar.score([(5, 10)], truth=[(100, 200)])["missed"], 1)
        self.assertEqual(ar.score([(5, 10)])["false_alarms"], 1)                  # tanpa truth: alarm = palsu

    def test_off_trail_koridor_sempit_memicu_alarm_palsu_koridor_lebar_tidak(self):
        rng = random.Random(7)
        fixes = walk(rng, 6.0, [(1200, 0, 1000, 0.0)])                           # jalan normal di jalur, galat GPS ~6 m
        for per, expect_false in ((3, True), (60, False)):
            eps = ar.episodes(ar.replay_off_trail(fixes, TRAIL, per, 3))
            self.assertEqual(ar.score(eps)["false_alarms"] > 0, expect_false, per)

    def test_debounce_menapis_lonjakan_satu_paket(self):
        rng = random.Random(1)
        fixes = walk(rng, 1.0, [(600, 0, 500, 0.0)])
        t, lat, lon = fixes[40]
        fixes[40] = (t, *at(200, 90))                                              # SATU paket melonjak 90 m ke samping
        self.assertGreater(len(ar.episodes(ar.replay_off_trail(fixes, TRAIL, 50, 1))), 0)
        self.assertEqual(ar.episodes(ar.replay_off_trail(fixes, TRAIL, 50, 3)), [])

    def test_keluar_jalur_sungguhan_terdeteksi_dengan_tunda_sekitar_debounce(self):
        rng = random.Random(3)
        fixes = walk(rng, 2.0, [(300, 0, 300, 0.0), (300, 300, 330, 120.0), (300, 330, 360, 120.0)])
        truth = [(300.0, 900.0)]                                                   # mulai menyimpang 120 m pada t=300
        sc = ar.score(ar.episodes(ar.replay_off_trail(fixes, TRAIL, 50, 3)), truth)
        self.assertEqual((sc["detected"], sc["missed"], sc["false_alarms"]), (1, 0, 0))
        self.assertLess(sc["delay_s"][0], 60.0)

    def test_istirahat_di_koridor_alarm_palsu_bergantung_jendela_dalam(self):
        rng = random.Random(5)
        # jalan 10 menit, ISTIRAHAT 30 menit di jalur (galat GPS 4 m), lalu jalan lagi
        fixes = walk(rng, 4.0, [(600, 0, 200, 0.0), (1800, 200, 200, 0.0), (600, 200, 400, 0.0)])
        short = ar.episodes(ar.replay_stagnant(fixes, TRAIL, 50, 30, inside_min=15, outside_min=10))
        long_ = ar.episodes(ar.replay_stagnant(fixes, TRAIL, 50, 30, inside_min=60, outside_min=10))
        self.assertGreater(ar.score(short)["false_alarms"], 0)                    # jendela dalam 15 mnt < istirahat 30 mnt
        self.assertEqual(ar.score(long_)["false_alarms"], 0)

    def test_diam_di_luar_koridor_terdeteksi_dengan_jendela_luar_pendek(self):
        rng = random.Random(9)
        fixes = walk(rng, 3.0, [(300, 0, 300, 0.0), (300, 300, 300, 150.0), (3600, 300, 300, 150.0)])
        truth = [(900.0, 4200.0)]   # celaka di 150 m dari jalur: diam penuh sejak ~600 dtk
        sc = ar.score(ar.episodes(ar.replay_stagnant(fixes, TRAIL, 50, 30, inside_min=240, outside_min=20)), truth)
        self.assertEqual((sc["detected"], sc["false_alarms"]), (1, 0))

    def test_stagnant_at_syarat_window_penuh(self):
        fixes = [(t, *at(0, 0)) for t in range(0, 1200, 30)]                       # diam 20 menit
        self.assertTrue(ar.stagnant_at(fixes, 1170, 15, 30))
        self.assertFalse(ar.stagnant_at(fixes, 1170, 30, 30))                      # window 30 mnt belum terisi penuh
        self.assertFalse(ar.stagnant_at([], 100, 5, 30))


if __name__ == "__main__":
    unittest.main()
