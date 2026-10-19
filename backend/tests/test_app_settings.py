"""Tes pengaturan operator (wizard): validasi, penyimpanan, penerapan, dan konsistensi dengan .env.example."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from tests import test_serial_ingest  # noqa: F401  (stub asyncpg/pydantic_settings bila belum terpasang)

from app.core.config import Settings, settings  # noqa: E402
from app.services import app_settings as aps  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


class S:  # pengganti Settings ringan
    stagnant_window_minutes = 180
    stagnant_radius_m = 50.0
    stagnant_check_interval_minutes = 2


class Validasi(unittest.TestCase):
    def test_angka_string_dikonversi_ke_tipe_benar(self):
        v = aps.validate({"stagnant_window_minutes": "120", "stagnant_radius_m": "75.5"})
        self.assertEqual(v, {"stagnant_window_minutes": 120, "stagnant_radius_m": 75.5})
        self.assertIsInstance(v["stagnant_window_minutes"], int)

    def test_ditolak(self):
        for bad in (
            {"stagnant_window_minutes": 5}, {"stagnant_window_minutes": 99999}, {"stagnant_radius_m": 0},
            {"stagnant_radius_m": "abc"}, {"stagnant_radius_m": None}, {"stagnant_radius_m": True},
            {"stagnant_radius_m": float("nan")}, {"stagnant_radius_m": float("inf")},
            {"stagnant_window_minutes": 90.5}, {"database_url": "postgresql://x"}, {"data_dir": "/etc"},
        ):
            with self.assertRaises(ValueError, msg=str(bad)):
                aps.validate(bad)

    def test_pesan_error_berbahasa_indonesia_dan_menyebut_batas(self):
        with self.assertRaises(ValueError) as cm:
            aps.validate({"stagnant_radius_m": 9999})
        self.assertIn("antara 5 dan 500", str(cm.exception))


class Konsistensi(unittest.TestCase):
    def test_semua_kunci_ada_di_settings_dan_punya_bawaan(self):
        for f in aps.FIELDS:
            self.assertIsNotNone(aps.default_of(Settings, f["key"]), f["key"])
            self.assertTrue(f["min"] <= aps.default_of(Settings, f["key"]) <= f["max"], f["key"])

    def test_env_example_sama_dengan_bawaan_kode(self):
        """Mencegah .env.example dan config.py saling menyimpang (dulu .env.example dianggap sumber bawaan)."""
        with open(os.path.join(HERE, "..", ".env.example"), encoding="utf-8") as fh:
            env = dict(re.findall(r"^([A-Z_]+)=(.+)$", fh.read(), re.M))
        for f in aps.FIELDS:
            self.assertEqual(float(env[f["key"].upper()]), float(aps.default_of(Settings, f["key"])), f["key"])


class Penyimpanan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.s = S()

    def tearDown(self):
        self.tmp.cleanup()

    def test_awalnya_belum_dikonfigurasi(self):
        self.assertFalse(aps.is_configured(self.d))
        self.assertFalse(aps.get_state(self.s, self.d)["configured"])

    def test_jawaban_tidak_tahu_memakai_bawaan_dan_menandai_terkonfigurasi(self):
        self.s.stagnant_radius_m = 999  # nilai sisa dari sebelumnya
        st = aps.put_state(self.s, self.d, "default", {})
        self.assertTrue(st["configured"])
        self.assertEqual(self.s.stagnant_radius_m, 50.0)  # kembali ke bawaan
        with open(os.path.join(self.d, "app_settings.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"configured": True, "overrides": {}})

    def test_pilihan_khusus_diterapkan_dan_bertahan_setelah_restart(self):
        aps.put_state(self.s, self.d, "custom", {"stagnant_radius_m": 80, "stagnant_window_minutes": 120})
        self.assertEqual((self.s.stagnant_radius_m, self.s.stagnant_window_minutes), (80.0, 120))
        baru = S()  # simulasi backend start ulang
        aps.load_saved_into(baru, self.d)
        self.assertEqual((baru.stagnant_radius_m, baru.stagnant_window_minutes, baru.stagnant_check_interval_minutes), (80.0, 120, 2))

    def test_nilai_salah_tidak_menyimpan_apa_pun(self):
        with self.assertRaises(ValueError):
            aps.put_state(self.s, self.d, "custom", {"stagnant_radius_m": -1})
        self.assertFalse(os.path.exists(os.path.join(self.d, "app_settings.json")))
        self.assertEqual(self.s.stagnant_radius_m, 50.0)

    def test_mode_tidak_dikenal(self):
        with self.assertRaises(ValueError):
            aps.put_state(self.s, self.d, "hapus-semua", {})

    def test_file_rusak_diabaikan_saat_start(self):
        with open(os.path.join(self.d, "app_settings.json"), "w", encoding="utf-8") as f:
            f.write("{bukan json")
        aps.load_saved_into(self.s, self.d)
        self.assertEqual(self.s.stagnant_radius_m, 50.0)
        self.assertFalse(aps.is_configured(self.d))

    def test_override_tersimpan_yang_tidak_valid_dilewati_tanpa_menggagalkan_start(self):
        with open(os.path.join(self.d, "app_settings.json"), "w", encoding="utf-8") as f:
            json.dump({"configured": True, "overrides": {"stagnant_radius_m": -5, "stagnant_window_minutes": 60, "asing": 1}}, f)
        aps.load_saved_into(self.s, self.d)
        self.assertEqual((self.s.stagnant_radius_m, self.s.stagnant_window_minutes), (50.0, 60))

    def test_tidak_ada_file_sementara_tersisa(self):
        aps.put_state(self.s, self.d, "default", {})
        self.assertEqual(os.listdir(self.d), ["app_settings.json"])

    def test_get_state_memuat_label_batas_dan_bawaan_untuk_form(self):
        st = aps.get_state(settings, self.d)
        self.assertEqual({f["key"] for f in st["fields"]}, {f["key"] for f in aps.FIELDS})
        for f in st["fields"]:
            self.assertTrue(all(k in f for k in ("label", "help", "unit", "min", "max", "default", "value")), f["key"])


class WizardJs(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node tidak terpasang; tes DOM wizard dilewati")
    def test_wizard_dom(self):
        r = subprocess.run(["node", os.path.join(HERE, "wizard_dom_test.js")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
