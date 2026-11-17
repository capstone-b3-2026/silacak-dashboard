"""Pengukur penumpukan base -> baca serial (services/serial_timing.py) dan jalur paket ganda di serial_ingest."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from app.services.serial_timing import TimingBuffer  # noqa: E402


def feed(buf, n, step_s=5.0, base0=10_000, host0=1000.0, backlog=0, proc_ms=20.0, jitter=None):
    for i in range(n):
        j = jitter(i) if jitter else 0.0
        buf.add(host0 + i * step_s + j, base0 + int(i * step_s * 1000), backlog, proc_ms)


class Timing(unittest.TestCase):
    def test_normal_tidak_ada_penumpukan(self):
        b = TimingBuffer()
        feed(b, 60)
        s = b.stats()
        self.assertEqual(s["verdict"], "tidak_ada_penumpukan")
        self.assertLess(s["tunda_ekstra_s"]["max"], 0.01)
        self.assertEqual(s["terkumpul"]["kejadian"], 0)

    def test_belum_cukup_data(self):
        b = TimingBuffer()
        feed(b, 5)
        self.assertEqual(b.stats()["verdict"], "belum_cukup_data")
        self.assertEqual(TimingBuffer().stats()["verdict"], "belum_cukup_data")

    def test_paket_tertahan_lalu_dilepas_sekaligus_terdeteksi_sebelum_pembacaan(self):
        # base menerima tiap 5 dtk; laptop baru menerima paket ke-20..24 SEKALIGUS pada waktu paket ke-24 (tertahan sebelum dibaca)
        b = TimingBuffer()
        for i in range(60):
            base_ms = 10_000 + i * 5000
            host = 1000.0 + i * 5.0
            if 20 <= i <= 24:
                host = 1000.0 + 24 * 5.0 + (i - 20) * 0.01   # dilepas bersamaan
            b.add(host, base_ms, 0, 20.0)
        s = b.stats()
        self.assertEqual(s["verdict"], "tertahan_sebelum_dibaca")
        self.assertGreater(s["tunda_ekstra_s"]["max"], 15.0)           # paket ke-20 tertahan ~20 dtk
        self.assertGreaterEqual(s["terkumpul"]["kejadian"], 4)

    def test_host_lambat_dibedakan_dari_penahan_sebelum_baca(self):
        b = TimingBuffer()
        for i in range(60):
            base_ms = 10_000 + i * 5000
            host = 1000.0 + i * 5.0 + (8.0 if 30 <= i < 34 else 0.0)  # laptop tersendat 8 dtk, bergerombol sesudahnya
            if 34 <= i <= 37:
                host = 1000.0 + 34 * 5.0 + 8.0 + (i - 34) * 0.01
            b.add(host, base_ms, 600 if 30 <= i <= 37 else 0, 3000.0 if 30 <= i <= 37 else 20.0)
        s = b.stats()
        self.assertEqual(s["verdict"], "host_tertinggal")
        self.assertGreaterEqual(s["backlog_byte"]["max"], 600)

    def test_base_reboot_memulai_referensi_baru_tanpa_artefak(self):
        b = TimingBuffer()
        feed(b, 40, base0=3_000_000)
        feed(b, 40, base0=2_000, host0=1000.0 + 40 * 5.0)  # base_ms mundur drastis = reboot
        s = b.stats()
        self.assertEqual(b.resets, 1)
        self.assertEqual(s["n_epoch"], 40)
        self.assertEqual(s["verdict"], "tidak_ada_penumpukan")
        self.assertLess(s["tunda_ekstra_s"]["max"], 0.01)

    def test_tanpa_jam_base_dilewati(self):
        b = TimingBuffer()
        b.add(1.0, None, 0, 1.0)
        self.assertEqual(b.stats()["n"], 0)

    def test_jitter_kecil_normal_tidak_dianggap_penumpukan(self):
        b = TimingBuffer()
        feed(b, 80, jitter=lambda i: 0.05 * ((i * 7) % 5 - 2) / 2)  # +-50 ms
        self.assertEqual(b.stats()["verdict"], "tidak_ada_penumpukan")

    def test_jendela_terbatas(self):
        b = TimingBuffer(maxlen=50)
        feed(b, 200)
        self.assertEqual(b.stats()["n"], 50)


if __name__ == "__main__":
    unittest.main()
