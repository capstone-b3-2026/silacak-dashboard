import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from app.services.clock_check import assess  # noqa: E402


class Clock(unittest.TestCase):
    def test_selaras(self):
        r = assess([1.2, 1.8, 2.5, 1.1, 3.0, 2.2])
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["offset_perkiraan_s"], 0.0)

    def test_laptop_tertinggal_terdeteksi_dan_offset_diperkirakan(self):
        r = assess([-12.0, -10.5, -9.0, -11.2, -8.7, -10.0])   # jam laptop ~12 dtk di belakang
        self.assertEqual(r["status"], "jam_laptop_tertinggal")
        self.assertEqual(r["offset_perkiraan_s"], 12.0)
        self.assertEqual(r["negatif_persen"], 100.0)

    def test_noise_kecil_di_bawah_nol_bukan_masalah(self):
        self.assertEqual(assess([-0.3, 0.4, 1.0, 0.8, 1.5])["status"], "ok")

    def test_satu_paket_negatif_di_antara_normal_tetap_dilaporkan(self):
        self.assertEqual(assess([2.0, 2.4, -3.0, 2.2, 2.6, 2.1])["status"], "jam_laptop_tertinggal")

    def test_curiga_jam_maju(self):
        self.assertEqual(assess([75.0, 80.0, 90.0, 76.0, 79.0])["status"], "curiga_jam_maju")

    def test_data_kurang_dan_none_diabaikan(self):
        self.assertEqual(assess([1.0, 2.0])["status"], "belum_cukup_data")
        self.assertEqual(assess([None, None, None, None, None, 1.0])["status"], "belum_cukup_data")


if __name__ == "__main__":
    unittest.main()
