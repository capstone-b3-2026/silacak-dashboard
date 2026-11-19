import contextlib
import io
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import analyze_raw_log as arl  # noqa: E402

T0 = datetime(2026, 11, 2, 1, 0, 0, tzinfo=timezone.utc)


def row(seq, host_s, base_ms):
    ts = (T0 + timedelta(seconds=host_s)).isoformat()
    utc = (T0 + timedelta(seconds=host_s - 3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{ts},CSV_DATA,{seq},1,H01,LANGSUNG,0,{seq * 5000},{base_ms},31,{utc},-7.5912,110.4001,1450.2,1.2,9,0.95,-97,0,0\n"


class Raw(unittest.TestCase):
    def make_log(self):
        d = tempfile.mkdtemp()
        lines = []
        for i in range(60):                                   # jendela 1: normal, 5 dtk per paket
            lines.append(row(i, 100 + i * 5.0, 10_000 + i * 5000))
        for i in range(60, 120):                              # jendela 2: paket 90..94 tertahan 25 dtk lalu dilepas sekaligus
            host = 100 + i * 5.0
            if 90 <= i <= 94:
                host = 100 + 94 * 5.0 + (i - 90) * 0.01
            lines.append(row(i, host, 10_000 + i * 5000))
        lines.insert(3, "2026-11-02T01:00:20+00:00,CSV_TIMING,1,2,3\n")     # baris lain dilewati
        lines.insert(5, "baris rusak tanpa koma\n")
        p = os.path.join(d, "2026-11-02.log")
        with open(p, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return d, p

    def test_jendela_normal_vs_tertahan(self):
        d, p = self.make_log()
        res = arl.analyze([p], window=60)
        self.assertEqual([r["verdict"] for r in res], ["tidak_ada_penumpukan", "tertahan_sebelum_dibaca"])
        self.assertLess(res[0]["tunda_max_s"], 0.01)
        self.assertGreater(res[1]["tunda_max_s"], 15)
        self.assertGreaterEqual(res[1]["terkumpul"], 4)

    def test_cli_ringkasan_dan_csv(self):
        d, p = self.make_log()
        out_csv = os.path.join(d, "hasil.csv")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            arl.main([d, "--window", "60", "--csv", out_csv])
        txt = buf.getvalue()
        self.assertIn("tertahan_sebelum_dibaca: 1 jendela", txt)
        self.assertIn("2026-11-02.log", txt)
        with open(out_csv, encoding="utf-8") as f:
            self.assertEqual(len(f.read().strip().splitlines()), 3)   # header + 2 jendela

    def test_jam_laptop_mundur_memulai_jendela_baru(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "a.log")
        ls = [row(i, 100 + i * 5.0, 10_000 + i * 5000) for i in range(30)]
        ls += [row(i, 50 + i * 5.0, 10_000 + i * 5000) for i in range(30)]    # jam laptop dikoreksi mundur ~100 dtk
        with open(p, "w", encoding="utf-8") as f:
            f.writelines(ls)
        res = arl.analyze([p], window=600)
        self.assertEqual(len(res), 2)                                         # tidak menghasilkan "penundaan" semu


if __name__ == "__main__":
    unittest.main()
