"""Tes pemicu SiLacak.exe dengan layout paket palsu (Linux/macOS; dilewati di Windows)."""
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "stub"))
import run_silacak as stub  # noqa: E402


@unittest.skipIf(os.name == "nt", "layout palsu memakai skrip shell")
class Stub(unittest.TestCase):
    def layout(self, d, exit_code, record):
        (Path(d) / "python").mkdir()
        (Path(d) / "launcher").mkdir()
        (Path(d) / "launcher" / "silacak_launcher.py").write_text("# dummy", encoding="utf-8")
        py = Path(d) / "python" / "python"
        py.write_text(f'#!/bin/sh\necho "HOME=$PYTHONHOME PATHVAR=$PYTHONPATH CWD=$(pwd) ARG=$1" > "{record}"\nexit {exit_code}\n', encoding="utf-8")
        py.chmod(py.stat().st_mode | stat.S_IEXEC)

    def test_sukses_tanpa_jeda_dan_env_python_lain_dibuang(self):
        with tempfile.TemporaryDirectory() as d, mock.patch("builtins.input") as inp, \
                mock.patch.dict(os.environ, {"PYTHONHOME": "/lain", "PYTHONPATH": "/lain/lib"}):
            rec = Path(d) / "rec.txt"
            self.layout(d, 0, rec)
            self.assertEqual(stub.main(d), 0)
            inp.assert_not_called()
            out = rec.read_text()
            self.assertIn("HOME= PATHVAR=", out)  # dua-duanya kosong
            self.assertIn(f"CWD={os.path.realpath(d)}", out)
            self.assertIn("silacak_launcher.py", out)

    def test_gagal_menahan_jendela_dan_meneruskan_kode(self):
        with tempfile.TemporaryDirectory() as d, mock.patch("builtins.input") as inp:
            self.layout(d, 3, Path(d) / "rec.txt")
            self.assertEqual(stub.main(d), 3)
            inp.assert_called_once()

    def test_ctrl_c_tidak_membuat_pemicu_keluar_sebelum_anak_selesai(self):
        with tempfile.TemporaryDirectory() as d, mock.patch("builtins.input"), \
                mock.patch.object(stub.subprocess, "Popen") as popen:
            self.layout(d, 0, Path(d) / "rec.txt")
            popen.return_value.wait.side_effect = [KeyboardInterrupt, KeyboardInterrupt, 0]
            self.assertEqual(stub.main(d), 0)
            self.assertEqual(popen.return_value.wait.call_count, 3)  # terus menunggu sampai anak selesai

    def test_paket_tidak_lengkap_dilaporkan(self):
        with tempfile.TemporaryDirectory() as d, mock.patch("builtins.input") as inp:
            self.assertEqual(stub.main(d), 1)
            inp.assert_called_once()


if __name__ == "__main__":
    unittest.main()
