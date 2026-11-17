import contextlib
import csv
import io
import math
import os
import random
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import eval_alarms  # noqa: E402


class Cli(unittest.TestCase):
    def test_sapuan_ambang_di_rekaman_sintetis(self):
        d = tempfile.mkdtemp()
        rng = random.Random(2)
        lat0, lon0 = -7.6, 110.4
        ml, mo = 1 / 110540.0, 1 / (111320 * math.cos(math.radians(lat0)))
        t0 = datetime(2026, 11, 16, 1, 0, 0, tzinfo=timezone.utc)
        with open(f"{d}/trail.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["lat", "lon"])
            for k in range(31):
                w.writerow([lat0 + k * 100 * ml, lon0])
        rows, t = [], 0.0
        for dur, n0, n1, e in [(600, 0, 200, 0), (1800, 200, 200, 0), (600, 200, 400, 0)]:   # jalan, istirahat 30 mnt, jalan
            for i in range(int(dur / 5)):
                n = n0 + (n1 - n0) * i / (dur / 5)
                rows.append([(t0 + timedelta(seconds=t)).isoformat(), lat0 + (n + rng.gauss(0, 4)) * ml, lon0 + rng.gauss(0, 4) * mo, "H01"])
                t += 5
        with open(f"{d}/walk.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["time", "lat", "lon", "hiker"])
            w.writerows(rows)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            eval_alarms.main(["--fixes", f"{d}/walk.csv", "--trail", f"{d}/trail.csv", "--grid", "perimeter=5,50;inside=15,480"])
        lines = [ln for ln in buf.getvalue().splitlines() if ln and ln[0].isdigit() and ln.count(",") >= 10]  # baris data saja
        header = next(ln for ln in buf.getvalue().splitlines() if ln.startswith("perimeter,"))
        cols = header.split(",")
        res = {(r[0], r[2]): dict(zip(cols, r)) for r in (ln.split(",") for ln in lines)}
        # rekaman NORMAL tanpa truth: semua alarm = palsu
        self.assertGreater(int(res[("5.0", "15")]["off_palsu"]), 0)       # koridor 5 m < galat GPS 4 m x sebaran -> palsu
        self.assertEqual(int(res[("50.0", "15")]["off_palsu"]), 0)
        self.assertGreater(int(res[("50.0", "15")]["diam_palsu"]), 0)     # istirahat 30 mnt > jendela dalam 15 mnt
        self.assertEqual(int(res[("50.0", "480")]["diam_palsu"]), 0)


if __name__ == "__main__":
    unittest.main()
