"""Analisis PENUMPUKAN paket (radio base -> baca serial) dari LOG MENTAH sesi yang sudah lewat, tanpa perangkat keras.

Backend menulis tiap baris serial ke data/raw/YYYY-MM-DD.log dengan format  <jam laptop ISO, mikrodetik>,<baris CSV_DATA>.
Baris itu membawa base_received_uptime_ms (jam base saat paket diterima radio), jadi selisih antarpaket di jam base vs jam
baca laptop menunjukkan paket yang sempat tertahan. Aturan dan batasnya sama dengan app/services/serial_timing.py.

Lokasi log mode portabel : %LOCALAPPDATA%\\SiLacak\\data\\raw        (di Git Bash: ~/AppData/Local/SiLacak/data/raw)
Lokasi log Docker        : volume data backend, folder raw/

    python scripts/analyze_raw_log.py ~/AppData/Local/SiLacak/data/raw
    python scripts/analyze_raw_log.py raw/2026-11-02.log --window 300 --csv hasil.csv

Log dipotong per jendela (bawaan 600 paket) karena jam kristal base dan laptop bergeser puluhan ppm; jendela yang lebih panjang
menumpuk pergeseran itu menjadi penundaan semu. Jam laptop yang mundur lebih dari 1 dtk (koreksi NTP/ubah jam manual)
memulai jendela baru. Jendela di bawah 20 paket dilewati.
"""
import argparse
import csv
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from app.services import base_protocol as bp  # noqa: E402
from app.services.serial_timing import MIN_PACKETS, TimingBuffer  # noqa: E402


def iter_packets(paths):
    """Hasilkan (jam_baca_epoch_detik, base_ms, nama_berkas) untuk tiap baris CSV_DATA yang bisa dibaca, urut berkas."""
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                ts, _, rest = line.rstrip("\n").partition(",")
                if not rest.startswith("CSV_DATA,"):
                    continue
                row = bp.parse_csv_data(rest)
                if not row:
                    continue
                try:
                    t = datetime.fromisoformat(ts)
                    if t.tzinfo is None:
                        t = t.replace(tzinfo=timezone.utc)
                    base_ms = int(row["base_received_uptime_ms"])
                except (ValueError, KeyError):
                    continue
                yield t.timestamp(), base_ms, os.path.basename(path)


def analyze(paths, window=600):
    """Daftar hasil per jendela: {berkas, mulai, n, verdict, tunda_p95_s, tunda_max_s, terkumpul, base_resets}."""
    out, buf, first_t, last_t, cur_file = [], None, None, None, None

    def flush():
        if buf is None or buf.stats().get("n", 0) == 0:
            return
        s = buf.stats()
        out.append({"berkas": cur_file, "mulai": datetime.fromtimestamp(first_t, timezone.utc).isoformat(timespec="seconds"),
                    "n": s["n"], "verdict": s["verdict"],
                    "tunda_p95_s": (s.get("tunda_ekstra_s") or {}).get("p95"), "tunda_max_s": (s.get("tunda_ekstra_s") or {}).get("max"),
                    "terkumpul": (s.get("terkumpul") or {}).get("kejadian"), "base_resets": s["base_resets"]})

    n = 0
    for t, base_ms, fname in iter_packets(paths):
        if buf is not None and (n >= window or (last_t is not None and t < last_t - 1.0)):
            flush()
            buf, n = None, 0
        if buf is None:
            buf, first_t, cur_file = TimingBuffer(maxlen=window + 5), t, fname
        buf.add(t, base_ms, None, None)
        last_t, n = t, n + 1
    flush()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="folder raw/ atau satu berkas .log")
    ap.add_argument("--window", type=int, default=600, help="paket per jendela (bawaan 600 = sekitar 50 menit pada 5 dtk/paket)")
    ap.add_argument("--csv", help="tulis hasil per jendela ke berkas CSV")
    a = ap.parse_args(argv)
    paths = [a.path] if os.path.isfile(a.path) else sorted(os.path.join(a.path, f) for f in os.listdir(a.path) if f.endswith(".log"))
    if not paths:
        raise SystemExit("Tidak ada berkas .log di sana.")
    res = analyze(paths, a.window)
    usable = [r for r in res if r["verdict"] != "belum_cukup_data"]
    print(f"{len(paths)} berkas, {sum(r['n'] for r in res)} paket CSV_DATA, {len(res)} jendela ({len(usable)} cukup data, min {MIN_PACKETS} paket)")
    if not usable:
        print("Tidak ada jendela yang cukup data. Pastikan log memuat baris CSV_DATA dengan base_received_uptime_ms.")
        return 0
    by = {}
    for r in usable:
        by[r["verdict"]] = by.get(r["verdict"], 0) + 1
    for v, c in sorted(by.items(), key=lambda kv: -kv[1]):
        print(f"  {v}: {c} jendela")
    print("Jendela terburuk (penundaan ekstra maksimum):")
    for r in sorted(usable, key=lambda r: -(r["tunda_max_s"] or 0))[:5]:
        print(f"  {r['berkas']} mulai {r['mulai']}  n={r['n']}  maks={r['tunda_max_s']} dtk  p95={r['tunda_p95_s']} dtk  "
              f"terkumpul={r['terkumpul']}x  -> {r['verdict']}")
    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(res[0].keys()))
            w.writeheader()
            w.writerows(res)
        print(f"Tertulis: {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
