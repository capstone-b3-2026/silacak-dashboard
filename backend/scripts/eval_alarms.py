"""Evaluasi alarm palsu & keterlambatan OFF_TRAIL / STAGNANT dari REKAMAN JALAN, sambil menyapu ambang.

Bahan:
  --fixes   CSV rekaman. Dua format diterima:
              (a) ekspor aplikasi (Ekspor > CSV): kolom kode_alat, waktu_gps, lat, lon
              (b) umum: kolom time (ISO 8601), lat, lon, opsional hiker
  --trail   jalur acuan: GPX (.gpx) atau CSV dengan kolom lat,lon
  --truth   (opsional) CSV kebenaran dasar: kind,start,end  (kind = off_trail | stagnant; waktu ISO 8601)
            = selang saat alarm jenis itu SEHARUSNYA menyala. Tanpa berkas ini rekaman dianggap jalan NORMAL
            dan setiap alarm dihitung sebagai alarm PALSU.

Contoh:
  python scripts/eval_alarms.py --fixes jalan1.csv --trail jalur.gpx
  python scripts/eval_alarms.py --fixes jalan1.csv --trail jalur.gpx --truth truth.csv \\
         --grid "perimeter=20,50,100;debounce=1,3,5;inside=60,240,480"

Parameter yang bisa disapu (--grid, dipisah titik koma) dan bawaannya (sama dengan bawaan aplikasi):
  perimeter=50  radius=50  inside=480  outside=240  interval=2  debounce=3
CATATAN: satu rekaman tidak cukup untuk menyimpulkan ambang. Lihat batas di app/services/alarm_replay.py.
"""
import argparse
import csv
import itertools
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from app.services import alarm_replay as ar  # noqa: E402

DEFAULTS = {"perimeter": 50.0, "radius": 50.0, "inside": 480, "outside": 240, "interval": 2.0, "debounce": 3}


def parse_time(s: str) -> float:
    d = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def read_fixes(path: str, hiker: str | None) -> dict[str, list]:
    by: dict[str, list] = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            tcol = "waktu_gps" if "waktu_gps" in r else "time"
            if not r.get(tcol) or not r.get("lat") or not r.get("lon"):
                continue
            code = r.get("kode_alat") or r.get("hiker") or "-"
            if hiker and code != hiker:
                continue
            gv = (r.get("gps_valid") or "").strip().lower()
            if gv in ("false", "f", "0"):
                continue                                   # fix tanpa GPS valid tidak ikut (sama seperti detektor)
            by.setdefault(code, []).append((parse_time(r[tcol]), float(r["lat"]), float(r["lon"])))
    return {k: sorted(v) for k, v in by.items()}


def read_trail(path: str) -> list[tuple]:
    if path.lower().endswith(".gpx"):
        import gpxpy
        with open(path, encoding="utf-8") as f:
            g = gpxpy.parse(f)
        pts = [(p.latitude, p.longitude) for t in g.tracks for s in t.segments for p in s.points]
        pts += [(p.latitude, p.longitude) for r in g.routes for p in r.points]
    else:
        with open(path, newline="", encoding="utf-8-sig") as f:
            pts = [(float(r["lat"]), float(r["lon"])) for r in csv.DictReader(f)]
    if len(pts) < 2:
        raise SystemExit("Jalur butuh minimal 2 titik.")
    return pts


def read_truth(path: str | None) -> dict[str, list]:
    out = {"off_trail": [], "stagnant": []}
    if path:
        with open(path, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                out[r["kind"].strip()].append((parse_time(r["start"]), parse_time(r["end"])))
    return out


def parse_grid(text: str | None) -> dict[str, list]:
    grid = {k: [v] for k, v in DEFAULTS.items()}
    for part in filter(None, (text or "").split(";")):
        k, vals = part.split("=")
        k = k.strip()
        if k not in DEFAULTS:
            raise SystemExit(f"Parameter '{k}' tidak dikenal. Pilihan: {', '.join(DEFAULTS)}")
        grid[k] = [type(DEFAULTS[k])(float(v)) if isinstance(DEFAULTS[k], int) else float(v) for v in vals.split(",")]
    return grid


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fixes", required=True)
    ap.add_argument("--trail", required=True)
    ap.add_argument("--truth")
    ap.add_argument("--grid")
    ap.add_argument("--hiker", help="hanya alat ini (bawaan: semua alat di berkas)")
    ap.add_argument("--grace", type=float, default=0.0, help="toleransi detik di tepi selang truth")
    a = ap.parse_args(argv)

    walks = read_fixes(a.fixes, a.hiker)
    if not walks:
        raise SystemExit("Tidak ada fix valid di berkas.")
    trail = read_trail(a.trail)
    truth = read_truth(a.truth)
    grid = parse_grid(a.grid)
    keys = list(DEFAULTS)
    print(f"{sum(len(v) for v in walks.values())} fix dari {len(walks)} alat; jalur {len(trail)} titik; "
          f"{'dengan' if a.truth else 'TANPA'} kebenaran dasar" + ("" if a.truth else " (semua alarm dihitung PALSU)"))
    print("perimeter,radius,inside,outside,interval,debounce,alat,off_episode,off_palsu,off_terdeteksi,off_terlewat,off_tunda_p50_s,"
          "diam_episode,diam_palsu,diam_terdeteksi,diam_terlewat,diam_tunda_p50_s")
    for combo in itertools.product(*(grid[k] for k in keys)):
        p = dict(zip(keys, combo))
        for code, fixes in sorted(walks.items()):
            off = ar.score(ar.episodes(ar.replay_off_trail(fixes, trail, p["perimeter"], int(p["debounce"]))), truth["off_trail"], a.grace)
            dm = ar.score(ar.episodes(ar.replay_stagnant(fixes, trail, p["perimeter"], p["radius"], int(p["inside"]), int(p["outside"]), p["interval"])),
                          truth["stagnant"], a.grace)
            med = lambda d: "" if not d["delay_s"] else f'{d["delay_s"][len(d["delay_s"]) // 2]:.0f}'  # noqa: E731
            print(",".join(str(x) for x in [p["perimeter"], p["radius"], p["inside"], p["outside"], p["interval"], p["debounce"], code,
                                            off["episodes"], off["false_alarms"], off["detected"], off["missed"], med(off),
                                            dm["episodes"], dm["false_alarms"], dm["detected"], dm["missed"], med(dm)]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
