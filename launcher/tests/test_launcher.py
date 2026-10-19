"""Tes logika launcher tanpa PostgreSQL sungguhan (proses di-fake):
    python -m unittest discover -s launcher/tests -v
TIDAK menguji: initdb/pg_ctl asli, Windows, PyInstaller."""
import json
import os
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pgmanager as pgm  # noqa: E402
import silacak_launcher as L  # noqa: E402


class FakeRunner:
    def __init__(self, results=None):
        self.calls, self.results = [], results or {}

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw))
        name = Path(cmd[0]).stem
        key = name if name != "pg_ctl" else f"pg_ctl:{cmd[-1]}"
        rc, err = self.results.get(key, (0, ""))
        return SimpleNamespace(returncode=rc, stdout="", stderr=err)


def make_pg(tmp, runner, **kw):
    return pgm.PgManager(Path(tmp) / "bin", Path(tmp) / "pgdata", Path(tmp) / "logs" / "pg.log", 54321, "pw/with:odd@chars", runner=runner, **kw)


class Config(unittest.TestCase):
    def test_dibuat_sekali_lalu_stabil(self):
        with tempfile.TemporaryDirectory() as d:
            a = L.load_or_create_config(Path(d))
            b = L.load_or_create_config(Path(d))
            self.assertEqual(a, b)
            self.assertGreaterEqual(len(a["pg_password"]), 24)
            self.assertEqual(a["serial_port"], "auto")

    def test_config_rusak_dibuat_ulang(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "config.json").write_text("{bukan json", encoding="utf-8")
            self.assertIn("pg_password", L.load_or_create_config(Path(d)))

    def test_pilihan_pengguna_dipertahankan(self):
        with tempfile.TemporaryDirectory() as d:
            c = L.load_or_create_config(Path(d))
            c["serial_port"] = "COM7"
            (Path(d) / "config.json").write_text(json.dumps(c), encoding="utf-8")
            self.assertEqual(L.load_or_create_config(Path(d))["serial_port"], "COM7")


class Frontend(unittest.TestCase):
    """Regresi: folder frontend/ (SOURCE, index.html memuat /src/main.js) tidak boleh disajikan."""
    SRC = '<script type="module" src="/src/main.js"></script>'
    BUILT = '<script type="module" src="/assets/index-abc123.js"></script>'

    def make(self, d, source=False, dist=False, flat_built=False):
        fe = Path(d) / "frontend"
        fe.mkdir()
        if source or flat_built:
            (fe / "index.html").write_text(self.BUILT if flat_built else self.SRC, encoding="utf-8")
        if dist:
            (fe / "dist").mkdir()
            (fe / "dist" / "index.html").write_text(self.BUILT, encoding="utf-8")

    def find(self, d):
        old, L.APP_DIR = L.APP_DIR, Path(d)
        try:
            return L.find_frontend()
        finally:
            L.APP_DIR = old

    def test_dist_dipilih_walau_source_ada(self):
        with tempfile.TemporaryDirectory() as d:
            self.make(d, source=True, dist=True)
            self.assertEqual(self.find(d), Path(d) / "frontend" / "dist")

    def test_hanya_source_ditolak(self):
        with tempfile.TemporaryDirectory() as d:
            self.make(d, source=True)
            self.assertIsNone(self.find(d))

    def test_layout_paket_rilis(self):
        with tempfile.TemporaryDirectory() as d:
            self.make(d, flat_built=True)
            self.assertEqual(self.find(d), Path(d) / "frontend")

    def test_tidak_ada_sama_sekali(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(self.find(d))


class Wizard(unittest.TestCase):
    def write(self, d, text):
        (Path(d) / "data").mkdir()
        (Path(d) / "data" / "app_settings.json").write_text(text, encoding="utf-8")

    def test_pertama_kali_tampil(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(L.needs_wizard(Path(d)))

    def test_setelah_dijawab_tidak_tampil_lagi(self):
        with tempfile.TemporaryDirectory() as d:
            self.write(d, '{"configured": true, "overrides": {}}')
            self.assertFalse(L.needs_wizard(Path(d)))

    def test_file_rusak_atau_belum_terkonfigurasi_tampil(self):
        for text in ("{rusak", "[]", '{"configured": false}'):
            with tempfile.TemporaryDirectory() as d:
                self.write(d, text)
                self.assertTrue(L.needs_wizard(Path(d)), text)


class Shutdown(unittest.TestCase):
    def test_stop_tanpa_tunggu_hanya_memulai_shutdown(self):
        with tempfile.TemporaryDirectory() as d:
            r = FakeRunner()
            make_pg(d, r).stop(wait=False)
            cmd = r.calls[-1][0]
            self.assertIn("-W", cmd)
            self.assertNotIn("-w", cmd)
            self.assertEqual(cmd[-1], "stop")
            self.assertTrue(r.calls[-1][1].get("quiet"))

    def test_stop_biasa_menunggu_selesai(self):
        with tempfile.TemporaryDirectory() as d:
            r = FakeRunner()
            make_pg(d, r).stop()
            self.assertIn("-w", r.calls[-1][0])
            self.assertNotIn("-W", r.calls[-1][0])

    def test_handler_penutupan_konsol_noop_di_selain_windows(self):
        if os.name != "nt":
            self.assertIsNone(L.install_console_close_handler(lambda: None))
            self.assertEqual(L._HANDLER_REFS, [])


class Port(unittest.TestCase):
    def test_port_terpakai_dihindari(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        busy = s.getsockname()[1]
        try:
            self.assertFalse(pgm.port_free(busy))
            self.assertNotEqual(pgm.pick_free_port(busy), busy)
        finally:
            s.close()


class PgManagerTest(unittest.TestCase):
    def test_dsn_meng_escape_password(self):
        with tempfile.TemporaryDirectory() as d:
            dsn = make_pg(d, FakeRunner()).dsn()
            self.assertIn("pw%2Fwith%3Aodd%40chars", dsn)
            self.assertTrue(dsn.endswith("@127.0.0.1:54321/silacak"))

    def test_initdb_pakai_auth_dan_password_tidak_bocor_ke_argumen(self):
        with tempfile.TemporaryDirectory() as d:
            r = FakeRunner()
            make_pg(d, r).init_cluster()
            cmd = r.calls[0][0]
            self.assertIn("--auth=scram-sha-256", cmd)
            self.assertTrue(any(a.startswith("--pwfile=") for a in cmd))
            self.assertFalse(any("pw/with" in a for a in cmd))  # password lewat file, bukan argumen
            pwfile = next(a for a in cmd if a.startswith("--pwfile="))[len("--pwfile="):]
            self.assertFalse(os.path.exists(pwfile))  # file sementara dihapus

    def test_start_hanya_loopback_dan_port_sendiri(self):
        with tempfile.TemporaryDirectory() as d:
            r = FakeRunner({"pg_ctl:status": (3, "")})  # 3 = tidak berjalan
            make_pg(d, r).start()
            start = r.calls[-1][0]
            opt = start[start.index("-o") + 1]
            self.assertIn("listen_addresses=127.0.0.1", opt)
            self.assertIn("-p 54321", opt)
            self.assertEqual(start[-1], "start")
            self.assertTrue(r.calls[-1][1].get("quiet"))  # tanpa pipa: cegah launcher menggantung di Windows

    def test_start_memakai_ulang_instance_yang_sudah_jalan(self):
        with tempfile.TemporaryDirectory() as d:
            r = FakeRunner({"pg_ctl:status": (0, "")})
            make_pg(d, r).start()
            self.assertEqual(len(r.calls), 1)  # hanya status, tidak start lagi

    def test_start_gagal_memunculkan_pgerror(self):
        with tempfile.TemporaryDirectory() as d:
            r = FakeRunner({"pg_ctl:status": (3, ""), "pg_ctl:start": (1, "port in use")})
            with self.assertRaises(pgm.PgError):
                make_pg(d, r).start()

    def test_createdb_sudah_ada_bukan_error(self):
        with tempfile.TemporaryDirectory() as d:
            make_pg(d, FakeRunner({"createdb": (1, 'database "silacak" already exists')})).ensure_database()

    def test_createdb_error_lain_dilaporkan(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(pgm.PgError):
                make_pg(d, FakeRunner({"createdb": (1, "password authentication failed")})).ensure_database()


if __name__ == "__main__":
    unittest.main()
