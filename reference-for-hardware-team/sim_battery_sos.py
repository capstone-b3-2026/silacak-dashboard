#!/usr/bin/env python3
"""Simulator baterai & SOS TANPA hardware: menyuntik baris CSV_DATA (format persis firmware base_real, 20 field)
melalui kode bridge yang SAMA (parse_data + write_to_postgres) ke Postgres Docker.
Backend (Docker) lalu bereaksi seperti pada alat asli: NOTIFY -> SSE -> dashboard, dan alarm MANUAL_SOS.

Pakai:
  python reference-for-hardware-team/sim_battery_sos.py --scenario baterai
  python reference-for-hardware-team/sim_battery_sos.py --scenario sos
  python reference-for-hardware-team/sim_battery_sos.py --scenario semua --node 9 --interval 1

Perlu: pip install asyncpg   (sama dengan bridge). Docker harus jalan (port 5432 terbuka ke host).
Skenario memakai Node ID bebas (--node, bawaan 9 -> pendaki H09) supaya tidak mengotori pendaki nyata.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("bridge", HERE / "serial_to_postgres_bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

LAT0, LON0 = -7.5780, 110.4530  # sekitar titik awal peta dashboard


def line(seq: int, node: int, battery: str, sos: int, step: int) -> str:
    lat = LAT0 + step * 0.00012
    lon = LON0 + step * 0.00009
    label = f"Pendaki {chr(ord('A') + node - 1)}" if 1 <= node <= 26 else f"Node {node}"
    return (
        f"CSV_DATA,{seq},{node},{label},LANGSUNG,0,{seq * 5000},{seq * 5000 + 120},31,"
        f"2026-10-24T08:00:{seq % 60:02d}Z,{lat:.7f},{lon:.7f},{1200 + step:.2f},1.20,9,0.95,-97,0,0,{battery},{sos}"
    )


def scenario_baterai(node: int) -> list[tuple[str, str]]:
    out, seq = [], 1
    for pct in (90, 70, 50, 30, 19, 12, 5):
        out.append((f"baterai {pct}%" + ("  <-- di bawah 20%: peringatan baterai rendah" if pct < 20 else ""),
                    line(seq, node, str(pct), 0, seq)))
        seq += 1
    out.append(("baterai TIDAK DIKETAHUI ('-')", line(seq, node, "-", 0, seq)))
    return out


def scenario_sos(node: int, start_seq: int = 100) -> list[tuple[str, str]]:
    plan = [("normal", 0), ("normal", 0), ("SOS DITEKAN (alarm merah + bunyi harus muncul)", 1),
            ("SOS masih ditahan (TIDAK boleh ada alarm baru)", 1), ("SOS masih ditahan", 1),
            ("SOS dibatalkan di alat", 0), ("SOS ditekan LAGI (alarm baru harus muncul)", 1), ("SOS dibatalkan", 0)]
    return [(label, line(start_seq + i, node, str(60 - i), sos, i)) for i, (label, sos) in enumerate(plan)]


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", choices=["baterai", "sos", "semua"], default="semua")
    ap.add_argument("--node", type=int, default=9, help="Node ID pendaki simulasi (bawaan 9 -> H09)")
    ap.add_argument("--interval", type=float, default=2.0, help="jeda antar paket (detik)")
    ap.add_argument("--database-url", default="postgresql://silacak:silacak@localhost:5432/silacak")
    args = ap.parse_args()

    steps: list[tuple[str, str]] = []
    if args.scenario in ("baterai", "semua"):
        steps += scenario_baterai(args.node)
    if args.scenario in ("sos", "semua"):
        steps += scenario_sos(args.node)

    pool = await bridge.asyncpg.create_pool(args.database_url, min_size=1, max_size=2)
    print(f"Menyuntik {len(steps)} paket untuk node {args.node} (H{args.node:02d}), jeda {args.interval}s. Buka dashboard sekarang.\n")
    try:
        for i, (label, raw) in enumerate(steps, 1):
            row = bridge.parse_data(next(csv.reader([raw])))
            await bridge.write_to_postgres(pool, row)
            print(f"[{i:02d}/{len(steps)}] {label}\n        {raw}")
            await asyncio.sleep(args.interval)
    finally:
        await pool.close()
    print("\nSelesai. Hapus data simulasi bila perlu:\n"
          f"  docker compose exec db psql -U silacak -d silacak -c \"DELETE FROM alerts WHERE session_id IN (SELECT s.id FROM hiking_sessions s JOIN hikers h ON h.id=s.hiker_id WHERE h.hiker_code='H{args.node:02d}'); DELETE FROM positions WHERE hiker_id=(SELECT id FROM hikers WHERE hiker_code='H{args.node:02d}'); DELETE FROM hiking_sessions WHERE hiker_id=(SELECT id FROM hikers WHERE hiker_code='H{args.node:02d}');\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
