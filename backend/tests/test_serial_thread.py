"""Tes loop thread serial (konek -> baca -> putus -> konek ulang) dengan pyserial PALSU, dan tes base palsu
(scripts/fake_base.py) lewat soket sungguhan. Tanpa hardware, tanpa Postgres.
Tidak teruji di sini: pyserial asli (termasuk handler socket://), USB, driver."""
import asyncio
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest

from tests import test_serial_ingest as base_tests  # noqa: F401  (menyiapkan stub asyncpg/pydantic_settings bila perlu)
from tests.test_serial_ingest import FIX, NOFIX, FakePool  # noqa: E402

from app.core import database  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.services import base_protocol as bp  # noqa: E402
from app.services import serial_ingest as si  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakeSerialException(Exception):
    pass


class FakeSerial:
    """Satu 'sambungan': keluarkan baris-baris skrip, lalu putus (raise) atau menggantung (menunggu stop)."""
    script_queue: list = []

    def __init__(self, port):
        self.port, self.is_open = port, False
        self.baudrate = self.timeout = self.dtr = self.rts = None
        self.lines, self.ending = FakeSerial.script_queue.pop(0)

    def open(self):
        self.is_open = True

    def readline(self):
        if self.lines:
            return (self.lines.pop(0) + "\n").encode()
        if self.ending == "raise":
            raise FakeSerialException("device disconnected")
        time.sleep(0.02)
        return b""

    def close(self):
        self.is_open = False


def fake_serial_module(ports):
    ns = types.SimpleNamespace(serial_for_url=lambda url, **kw: FakeSerial(url))
    lp = types.SimpleNamespace(comports=lambda: ports)
    return ns, lp


class FailingOpen:
    """Port yang selalu gagal dibuka (mis. base palsu tidak berjalan)."""
    attempts = 0

    def __init__(self, port):
        FailingOpen.attempts += 1
        self.port, self.baudrate, self.timeout, self.dtr, self.rts = port, None, None, None, None

    def open(self):
        raise OSError(f"Could not open port {self.port}: [WinError 10061] connection refused")

    def close(self):
        pass


class Port:
    def __init__(self, device, vid):
        self.device, self.description, self.vid, self.pid = device, "CH340", vid, 0x7523


class ThreadLoop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        settings.data_dir, settings.raw_log, settings.serial_port = self.tmp.name, False, "auto"
        self.pool = FakePool()
        database.pool = self.pool
        self.loop = asyncio.new_event_loop()
        self.t_loop = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.t_loop.start()
        self._orig = (si.serial, si.list_ports)
        self.ing = si.SerialIngest()
        self.ing._loop = self.loop
        self.ing._wait = lambda s: time.sleep(0.05)  # jangan menunggu 2 detik asli

    def tearDown(self):
        self.ing._stop.set()
        if getattr(self, "th", None):
            self.th.join(3)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.t_loop.join(2)
        self.loop.close()
        si.serial, si.list_ports = self._orig
        database.pool = None
        self.tmp.cleanup()

    def start(self, ports, scripts):
        si.serial, si.list_ports = fake_serial_module(ports)
        FakeSerial.script_queue = scripts
        self.th = threading.Thread(target=self.ing._run, daemon=True)
        self.th.start()

    def wait_for(self, cond, timeout=5):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if cond():
                return True
            time.sleep(0.02)
        return False

    def inserts(self):
        return [e for e in self.pool.log if e[0] == "execute" and "INSERT INTO positions" in e[1]]

    def test_putus_lalu_konek_ulang_tanpa_kehilangan_paket(self):
        self.start([Port("COM4", 0x1A86)], [([FIX, FIX, NOFIX], "raise"), ([FIX, FIX], "hang")])
        self.assertTrue(self.wait_for(lambda: self.ing.status()["packets_received"] == 5), self.ing.status())
        st = self.ing.status()
        self.assertEqual((st["state"], st["port"], st["last_error"]), ("connected", "COM4", None))  # error lama terhapus

    def test_paket_tanpa_fix_tersimpan_dengan_lokasi_null(self):
        self.start([Port("COM4", 0x1A86)], [([NOFIX], "hang")])
        self.assertTrue(self.wait_for(lambda: len(self.inserts()) == 1))
        a = self.inserts()[0][2]
        self.assertIsNone(a[1])
        self.assertIsNone(a[2])

    def test_baris_non_csv_diabaikan(self):
        self.start([Port("COM4", 0x1A86)], [(["[INFO] boot", "ets Jun  8 2016", FIX], "hang")])
        self.assertTrue(self.wait_for(lambda: self.ing.status()["packets_received"] == 1))
        self.assertEqual(self.ing.status()["packets_rejected"], 0)

    def test_gagal_buka_url_pesan_tepat_log_tidak_membanjir_jeda_bertahap(self):
        FailingOpen.attempts = 0
        waits = []
        self.ing._wait = lambda s: (waits.append(s), time.sleep(0.01))[1]
        self.ing._requested = "socket://127.0.0.1:7777"
        si.serial = types.SimpleNamespace(serial_for_url=lambda url, **kw: FailingOpen(url))
        si.list_ports = types.SimpleNamespace(comports=lambda: [])
        with self.assertLogs("silacak.serial", level="WARNING") as cm:
            self.th = threading.Thread(target=self.ing._run, daemon=True)
            self.th.start()
            self.assertTrue(self.wait_for(lambda: FailingOpen.attempts >= 6))
            self.ing._stop.set()
            self.th.join(3)
        st = self.ing.status()
        self.assertIn("socket://127.0.0.1:7777", st["last_error"])
        self.assertNotIn("kabel", st["last_error"])          # bukan soal kabel/driver
        self.assertEqual(len(cm.output), 1, cm.output)       # 6+ percobaan, SATU baris log
        self.assertEqual(waits[:5], [2.0, 4.0, 8.0, 10.0, 10.0])

    def test_tidak_ada_alat_status_searching_dan_error_bersih(self):
        self.ing._last_error = "sisa error lama"
        self.start([], [])
        self.assertTrue(self.wait_for(lambda: self.ing.status()["state"] == "searching"))
        self.assertTrue(self.wait_for(lambda: self.ing.status()["last_error"] is None))

    def test_dua_kandidat_tidak_menebak(self):
        self.start([Port("COM4", 0x1A86), Port("COM6", 0x10C4)], [])
        self.assertTrue(self.wait_for(lambda: self.ing.status()["state"] == "ambiguous"))
        self.assertEqual({c["device"] for c in self.ing.status()["candidates"]}, {"COM4", "COM6"})
        self.assertIsNone(self.ing.status()["port"])


class FakeBase(unittest.TestCase):
    """scripts/fake_base.py dijalankan sungguhan (proses terpisah) dan dibaca lewat soket."""

    @staticmethod
    def free_port():
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def spawn(self, *extra):
        port = self.free_port()
        p = subprocess.Popen([sys.executable, os.path.join(ROOT, "scripts", "fake_base.py"), "--port", str(port),
                              "--interval", "0.01", *extra], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: (p.kill(), p.wait()))
        for _ in range(100):
            try:
                sock = socket.create_connection(("127.0.0.1", port), timeout=3)
                self.addCleanup(sock.close)
                return port, sock
            except OSError:
                time.sleep(0.05)
        self.fail("fake_base tidak mau listen")

    @staticmethod
    def read_lines(sock, n):
        buf, out = b"", []
        while len(out) < n:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf and len(out) < n:
                ln, buf = buf.split(b"\n", 1)
                out.append(ln.decode())
        return out

    def test_format_diterima_parser_asli(self):
        _, s = self.spawn()
        lines = [x for x in self.read_lines(s, 60) if x.startswith("CSV_DATA,")]
        recs = [bp.to_record(bp.parse_csv_data(x)) for x in lines]
        self.assertEqual(len(recs), len(lines))  # tak satu pun ditolak parser
        self.assertEqual({r.hiker_code for r in recs}, {"H11", "H12"})
        nofix = [r for r in recs if r.lat is None]
        fix = [r for r in recs if r.lat is not None]
        self.assertTrue(nofix and fix)             # skenario tanpa-fix memang muncul
        self.assertTrue(all(r.gps_valid for r in fix))
        self.assertFalse(any(r.gps_valid for r in nofix))
        self.assertTrue(all(-7.60 < r.lat < -7.57 and 110.44 < r.lon < 110.46 for r in fix))  # di area Bukit Klangon

    def test_rute_lewat_relay_diterima_parser_asli(self):
        _, s = self.spawn("--relay-route", "5,6", "--routed-nodes", "12")
        recs = [bp.to_record(bp.parse_csv_data(x)) for x in self.read_lines(s, 40) if x.startswith("CSV_DATA,")]
        h12 = [r for r in recs if r.hiker_code == "H12"]
        h11 = [r for r in recs if r.hiker_code == "H11"]
        self.assertTrue(h12 and h11)
        self.assertTrue(all(r.route_path == "R5>R6" and r.hop_count == 2 for r in h12))
        self.assertTrue(all(r.route_path == "LANGSUNG" and r.hop_count == 0 for r in h11))

    def test_nomor_urut_meloncat_dan_missing_terhitung(self):
        _, s = self.spawn("--nodes", "11")
        recs = [bp.to_record(bp.parse_csv_data(x)) for x in self.read_lines(s, 80) if x.startswith("CSV_DATA,")]
        seqs = [r.sequence for r in recs]
        self.assertTrue(any(b - a > 1 for a, b in zip(seqs, seqs[1:])))
        self.assertTrue(any((r.missing_since_previous or 0) > 0 for r in recs))

    def test_drop_after_memutus_lalu_menerima_koneksi_baru(self):
        port, s = self.spawn("--drop-after", "5")
        self.assertLessEqual(len([x for x in self.read_lines(s, 50) if x.startswith("CSV_DATA,")]), 5)
        s.close()
        for _ in range(100):  # server harus menerima koneksi berikutnya (uji auto-reconnect backend)
            try:
                s2 = socket.create_connection(("127.0.0.1", port), timeout=3)
                self.addCleanup(s2.close)
                break
            except OSError:
                time.sleep(0.05)
        else:
            self.fail("server tidak menerima koneksi ulang")
        self.assertTrue(any(x.startswith("CSV_DATA,") for x in self.read_lines(s2, 5)))


if __name__ == "__main__":
    unittest.main()
