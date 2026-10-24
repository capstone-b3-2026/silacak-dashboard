"""BASE STATION PALSU untuk tes tanpa hardware.

Mengirim baris `CSV_DATA,...` PERSIS format firmware (base_real.cpp / base_optimized.cpp) lewat soket TCP.
Backend membukanya seperti port serial biasa (pyserial mengerti URL `socket://`), jadi seluruh jalur
ingest ikut teruji: pembaca serial -> parser -> INSERT Postgres -> peta, termasuk auto-reconnect.
YANG TIDAK TERUJI: kabel USB, driver CH340/CP210x, dan radio LoRa.

Cara pakai (3 langkah, dari root repo):
  1) Jendela A (launcher sudah jalan):   python backend\\scripts\\fake_base.py
  2) Jendela B, arahkan backend ke sana:
       $cfg = Get-Content "$env:LOCALAPPDATA\\SiLacak\\config.json" | ConvertFrom-Json
       Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$($cfg.web_port)/api/v1/base/port" -ContentType "application/json" -Body '{"port":"socket://127.0.0.1:7777"}'
  3) Cek:  .../api/v1/base/status  -> state "connected", packets_received naik; pendaki H11/H12 muncul di peta.
  Kembali ke alat asli:  -Body '{"port":"auto"}'

Skenario bawaan: 2 pendaki (node 11, 12) naik di jalur Bukit Klangon; tiap ~12 paket ada 1 paket TANPA fix
(firmware mencetak 0.0000000,0.0000000 dan flags tanpa bit LocationValid; harus tersimpan dengan lokasi NULL,
bukan titik (0,0)); sesekali nomor urut loncat (paket hilang). Opsi --drop-after N memutus koneksi tiap N baris
untuk menguji auto-reconnect.

Rute lewat relay (firmware menulis ID node relay mentah, mis. "R5>R6"):
  python backend\\scripts\\fake_base.py --relay-route 5,6 --routed-nodes 12
membuat H12 selalu lewat relay node 5 lalu 6 (hop 2) sementara H11 tetap langsung. Daftarkan perangkat relay
ber-node_id 5 dan 6 di Setup > Perangkat, lalu pilih "dipasang di posisi R<n>" supaya rutenya tergambar di peta.
"""
import argparse
import socket
import time
from datetime import datetime, timezone

# (lat, lon, alt) jalur ilustrasi yang sama dengan seed_synthetic_data.py
WAYPOINTS = [(-7.5850, 110.4500, 900), (-7.5825, 110.4515, 940), (-7.5805, 110.4525, 985),
             (-7.5788, 110.4535, 1030), (-7.5779, 110.4541, 1070), (-7.5772, 110.4546, 1100)]


def interp(p: float):
    p = max(0.0, min(0.999999, p)) * (len(WAYPOINTS) - 1)
    i = int(p)
    f = p - i
    a, b = WAYPOINTS[i], WAYPOINTS[i + 1]
    return tuple(a[k] + (b[k] - a[k]) * f for k in range(3))


def line(node: int, seq: int, uptime_ms: int, progress: float, nofix: bool, missing: int, total_missing: int,
         route_ids: tuple = ()) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if nofix:  # persis perilaku firmware saat tidak ada fix
        flags, utc, lat, lon, alt, sats, hdop = 0, "-", 0.0, 0.0, 0.0, 0, 0.0
    else:
        lat, lon, alt = interp(progress)
        flags, utc, sats, hdop = 31, now, 9, 0.95
    route = ">".join(f"R{r}" for r in route_ids) or "LANGSUNG"  # persis formatRoute() di firmware
    return (f"CSV_DATA,{seq},{node},H{node:02d},{route},{len(route_ids)},{uptime_ms},{uptime_ms + 12},{flags},{utc},"
            f"{lat:.7f},{lon:.7f},{alt:.2f},1.20,{sats},{hdop:.2f},-97,{missing},{total_missing}\n")


def serve(args) -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.host, args.port))
    srv.listen(1)
    nodes = [int(n) for n in args.nodes.split(",")]
    relay_route = tuple(int(x) for x in args.relay_route.split(",") if x.strip())
    routed = {int(x) for x in args.routed_nodes.split(",") if x.strip()}
    seq = {n: 0 for n in nodes}
    total_missing = {n: 0 for n in nodes}
    progress = {n: 0.0 for n in nodes}
    print(f"Base palsu siap di socket://{args.host}:{args.port}  (node {nodes}). Ctrl+C untuk berhenti.")
    while True:
        conn, addr = srv.accept()
        print(f"Backend tersambung dari {addr}.")
        sent = 0
        t0 = time.monotonic()
        try:
            conn.sendall(b"[INFO] base palsu siap\n")
            while True:
                for n in nodes:
                    missing = 0
                    if seq[n] and seq[n] % 17 == 0:  # simulasi paket hilang
                        missing = 2
                        seq[n] += missing
                        total_missing[n] += missing
                    seq[n] += 1
                    progress[n] = (progress[n] + 0.01) % 1.0
                    nofix = seq[n] % 12 == 0
                    conn.sendall(line(n, seq[n], int((time.monotonic() - t0) * 1000), progress[n], nofix,
                                      missing, total_missing[n], relay_route if n in routed else ()).encode())
                    sent += 1
                    if args.drop_after and sent >= args.drop_after:
                        print(f"--drop-after {args.drop_after}: memutus koneksi (uji auto-reconnect).")
                        raise ConnectionAbortedError
                time.sleep(args.interval)
        except (ConnectionError, OSError):
            print("Koneksi putus; menunggu backend tersambung lagi...")
        finally:
            conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7777)
    ap.add_argument("--nodes", default="11,12", help="node id pendaki, dipisah koma (H11, H12)")
    ap.add_argument("--interval", type=float, default=1.0, help="detik antar putaran (firmware real: ~5)")
    ap.add_argument("--relay-route", default="", help="ID node relay yang dilewati, urut dari pendaki ke base, mis. 5,6")
    ap.add_argument("--routed-nodes", default="12", help="pendaki yang memakai --relay-route (bawaan: 12)")
    ap.add_argument("--drop-after", type=int, default=0, help="putus koneksi setelah N baris (0 = tidak)")
    try:
        serve(ap.parse_args())
    except KeyboardInterrupt:
        print("\nStop.")
