#!/usr/bin/env python3
"""
CATATAN: fungsi script ini sekarang SUDAH tertanam di backend (app/services/serial_ingest.py,
dijalankan otomatis kalau SERIAL_PORT diatur). Script ini dipertahankan sebagai referensi/alat
debug mandiri; JANGAN jalankan bersamaan dengan ingest bawaan pada port yang sama.

REFERENSI - bukan bagian resmi dari dashboard SiLacak.

Ini contoh cara nyambungin base station (via USB serial) ke database
`silacak` (PostgreSQL+TimescaleDB+PostGIS). Diadaptasi langsung dari
`tools/serial_logger.py` yang sudah ada di repo hardware - parsing baris
`CSV_DATA,...`-nya PERSIS SAMA (field & urutan sudah diverifikasi cocok
dengan base_real.cpp maupun base_optimized.cpp, dua-duanya pakai format
CSV yang identik).

Bedanya cuma satu: alih-alih (atau selain) nulis ke file CSV, tiap baris
yang berhasil di-parse langsung di-INSERT ke table `positions` di
Postgres lewat asyncpg. Begitu ke-INSERT, trigger `pg_notify` yang sudah
ada di init.sql otomatis nyala dan push ke dashboard lewat SSE - jadi
nggak perlu kode tambahan apa pun di sisi dashboard.

Silakan pakai langsung, modifikasi bebas, atau abaikan total kalau tim
hardware/ingestion mau pakai pendekatan lain (misal lewat MQTT broker
di tengah). Yang penting cuma satu: baris yang akhirnya masuk ke table
`positions` kolom & tipe datanya sama kayak yang didefinisikan di
`infra/postgres/init.sql`.

Cara pakai (mirip persis serial_logger.py):
    pip install pyserial asyncpg
    python serial_to_postgres_bridge.py --port COMy
    python serial_to_postgres_bridge.py --port COMy --also-csv   # dual-write, tetap simpan CSV juga

Environment variable DATABASE_URL bisa dipakai buat override koneksi
default (lihat DEFAULT_DATABASE_URL di bawah).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import time

try:
    import asyncpg
    import serial
    from serial.tools import list_ports
except ImportError:
    print(
        "Butuh pyserial & asyncpg. Jalankan: pip install pyserial asyncpg",
        file=sys.stderr,
    )
    raise SystemExit(1)


DEFAULT_DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://silacak:silacak@localhost:5432/silacak"
)

# Field CSV_DATA sesuai emitCsvData() di base_real.cpp / base_optimized.cpp
# (parts[0] literal "CSV_DATA", 18 value setelahnya). JANGAN diubah urutannya
# kecuali format printf di firmware juga ikut berubah.
FIELDNAMES = [
    "sequence",
    "node_id",
    "node_name",
    "route",
    "relay_hops",
    "tracker_uptime_ms",
    "base_received_uptime_ms",
    "gps_flags",
    "gps_utc",
    "latitude",
    "longitude",
    "altitude_m",
    "speed_kph",
    "satellites",
    "hdop",
    "rssi_dbm",
    "missing_since_previous",
    "total_missing",
]


_warned_extra = False


def parse_data(parts: list[str]) -> dict[str, str] | None:
    """Sama persis dengan parse_data() di tools/serial_logger.py."""
    # >=19: kalau firmware menambah field di BELAKANG (SOS, baterai, ...), 18 field pertama tetap terbaca
    # dan baris tidak lagi dibuang diam-diam. Field tambahan baru dipakai setelah FIELDNAMES diperbarui.
    global _warned_extra
    if len(parts) < 19:
        return None
    if len(parts) > 19 and not _warned_extra:
        _warned_extra = True
        print(f"[PERINGATAN] CSV_DATA punya {len(parts) - 1} field (>18): field tambahan diabaikan. "
              "Perbarui FIELDNAMES + INSERT kalau mau dipakai.", file=sys.stderr)
    return dict(zip(FIELDNAMES, parts[1:19]))


def select_port(requested: str | None) -> str:
    if requested:
        return requested
    ports = list(list_ports.comports())
    if len(ports) == 1:
        print(f"Port otomatis: {ports[0].device} ({ports[0].description})")
        return ports[0].device
    if not ports:
        raise SystemExit("Tidak ada port serial. Sambungkan ESP32 base lewat USB.")
    choices = "\n".join(f"  {p.device}: {p.description}" for p in ports)
    raise SystemExit("Ada lebih dari satu port serial. Pilih dengan --port.\n" + choices)


async def get_or_create_hiker_id(conn: asyncpg.Connection, hiker_code: str) -> int:
    """node_id di firmware itu integer (1,2,3...) - kita samakan konvensinya
    ke hiker_code 'H01','H02',... yang sudah dipakai di seed data
    (infra/postgres/init.sql). Kalau kodenya belum ada di table hikers,
    otomatis dibikinin barunya."""
    row = await conn.fetchrow("SELECT id FROM hikers WHERE hiker_code = $1", hiker_code)
    if row:
        return row["id"]
    row = await conn.fetchrow(
        "INSERT INTO hikers (hiker_code) VALUES ($1) RETURNING id", hiker_code
    )
    return row["id"]


def parse_recorded_at(row: dict[str, str]) -> tuple[datetime, bool]:
    """PENTING: trackerUptimeMs / base_received_uptime_ms itu millis() sejak
    boot ESP32 - BUKAN timestamp absolut, jangan dipakai buat recorded_at.
    Sumber waktu yang benar adalah gps_utc (waktu asli dari GPS module di
    node), yang cuma valid kalau GPS sudah dapat fix tanggal+jam. Kalau
    belum, fallback ke waktu bridge ini menerima baris (mendekati waktu
    asli, tapi bukan waktu on-node - beda ini penting buat fitur Node
    Diagnostics nanti)."""
    gps_utc = row.get("gps_utc", "")
    if gps_utc:
        try:
            t = datetime.fromisoformat(gps_utc.replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            if t.year >= 2024:  # GPS belum dapat tanggal sering melapor 2000-01-01 -> bukan waktu asli
                return t, True
        except ValueError:
            pass
    return datetime.now(timezone.utc), False  # latency TIDAK dihitung untuk paket ini


def to_int(value: str) -> int | None:
    return int(value) if value not in ("", "-") else None


def to_float(value: str) -> float | None:
    return float(value) if value not in ("", "-") else None


async def write_to_postgres(pool: asyncpg.Pool, row: dict[str, str]) -> None:
    node_id = int(row["node_id"])
    hiker_code = f"H{node_id:02d}"

    lat = to_float(row["latitude"])
    lon = to_float(row["longitude"])
    sats = to_int(row["satellites"])
    hdop = to_float(row["hdop"])
    flags = to_int(row["gps_flags"])
    # Firmware mencetak 0.0000000,0.0000000 (bukan kosong) saat tidak ada fix; bit LocationValid (1) tidak di-set.
    if (flags is not None and not (flags & 1)) or (lat == 0.0 and lon == 0.0):
        lat = lon = None
    if lat is None or lon is None:
        lat = lon = None  # paket tanpa fix TETAP disimpan (hitung PDR, status GPS invalid, lokasi terakhir)
    # Kriteria validitas dari plan C-251 (4.1.3): Nsat >= 4 dan HDOP <= 5
    gps_valid = lat is not None and (sats is None or sats >= 4) and (hdop is None or hdop <= 5.0)
    recorded_at, time_from_gps = parse_recorded_at(row)

    async with pool.acquire() as conn:
        # Node yang di Setup didaftarkan sebagai relay/base BUKAN pendaki: kalau firmware-nya suatu
        # saat ikut mengirim posisi sendiri, jangan dijadikan "pendaki" (jejak, GPX, sesi, alarm SOS).
        try:
            role = await conn.fetchval("SELECT role FROM devices WHERE node_id = $1", node_id)
        except asyncpg.UndefinedTableError:  # backend belum pernah start -> tabel devices belum ada
            role = None
        if role in ("relay", "base"):
            return
        hiker_id = await get_or_create_hiker_id(conn, hiker_code)
        await conn.execute(
            """
            INSERT INTO positions
                (hiker_id, location, elevation, hop_count, route_path,
                 sequence, rssi_dbm, satellites, hdop, missing_since_previous,
                 total_missing, recorded_at, gps_valid, gps_flags, time_from_gps)
            VALUES
                ($1, CASE WHEN $2::float8 IS NULL OR $3::float8 IS NULL THEN NULL
                          ELSE point($2::float8, $3::float8) END,
                 $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
            """,
            hiker_id,
            lon,
            lat,
            to_float(row["altitude_m"]),
            to_int(row["relay_hops"]),
            row["route"] or None,
            to_int(row["sequence"]),
            to_int(row["rssi_dbm"]),
            sats,
            hdop,
            to_int(row["missing_since_previous"]),
            to_int(row["total_missing"]),
            recorded_at,
            gps_valid,
            row["gps_flags"] or None,
            time_from_gps,
        )


# ── DOWNLINK: push konfigurasi dari dashboard ke alat ────────────────────
# Dashboard menaruh perintah di table device_commands (status 'pending'). Bridge ini
# mengambilnya, menulis SATU baris ke serial base, lalu melapor balik. Format baris
# di bawah adalah USULAN - firmware base harus dibuat mengerti format ini (atau
# sesuaikan build_cfg_line() dengan format perintah yang sudah ada di firmware).
#
#   CFG,<node_id>,<name>,<role>,<report_interval_s>,<tx_power_dbm>,<sf>,<version>
#
# Kalau firmware membalas "CFG_ACK,<node_id>,<version>" -> status 'acked'.
# Kalau firmware belum punya ACK, jalankan dengan --no-ack: begitu baris ditulis,
# langsung dianggap 'acked' (dashboard tidak bisa membuktikan alatnya benar-benar menerima).
DOWNLINK_POLL_SECONDS = 2.0


def build_cfg_line(p: dict) -> str:
    c = p["config"]
    name = str(p["name"]).replace(",", " ")
    return (
        f"CFG,{p['node_id']},{name},{p['role']},{c['report_interval_s']},"
        f"{c['tx_power_dbm']},{c['sf']},{p['version']}\n"
    )


async def mark_command(pool: asyncpg.Pool, cmd_id: int, status: str, error: str | None = None) -> None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE device_commands SET status=$2, error=$3, updated_at=now() "
            "WHERE id=$1 RETURNING device_id, payload",
            cmd_id, status, error,
        )
        if row and status == "acked":
            payload = row["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            await conn.execute(
                "UPDATE devices SET pushed_version = GREATEST(pushed_version, $2) WHERE id=$1",
                row["device_id"], payload.get("version", 0),
            )


async def flush_commands(pool: asyncpg.Pool, device: "serial.Serial", no_ack: bool) -> None:
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, payload FROM device_commands WHERE status='pending' ORDER BY id")
    for r in rows:
        payload = r["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        try:
            device.write(build_cfg_line(payload).encode("utf-8"))
            device.flush()
        except Exception as exc:  # noqa: BLE001
            await mark_command(pool, r["id"], "failed", f"gagal tulis serial: {exc}")
            continue
        await mark_command(pool, r["id"], "acked" if no_ack else "sent")
        print(f"[CFG] node {payload['node_id']} v{payload['version']} -> {'acked (tanpa ACK)' if no_ack else 'terkirim'}")


async def handle_ack(pool: asyncpg.Pool, raw: str) -> None:
    """Baris 'CFG_ACK,<node_id>,<version>' dari firmware -> tandai perintah terakhir yang 'sent' jadi 'acked'."""
    parts = raw.split(",")
    if len(parts) < 3:
        return
    node_id, version = int(parts[1]), int(parts[2])
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT c.id FROM device_commands c JOIN devices d ON d.id = c.device_id
               WHERE d.node_id=$1 AND c.status='sent' AND (c.payload->>'version')::int = $2
               ORDER BY c.id DESC LIMIT 1""",
            node_id, version,
        )
    if row:
        await mark_command(pool, row["id"], "acked")
        print(f"[CFG_ACK] node {node_id} v{version}")


async def main_async(args: argparse.Namespace) -> None:
    port = select_port(args.port)
    print(f"Membuka {port} @ {args.baud} baud")
    print(f"Nulis ke Postgres: {args.database_url}")

    pool = await asyncpg.create_pool(dsn=args.database_url, min_size=1, max_size=4)

    csv_writer = None
    csv_file = None
    if args.also_csv:
        output_path = Path("data") / datetime.now().strftime("lora_log_%Y%m%d_%H%M%S.csv")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        csv_file = output_path.open("a", newline="", encoding="utf-8")
        csv_writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        if csv_file.tell() == 0:
            csv_writer.writeheader()
        print(f"Dual-write CSV ke: {output_path.resolve()}")

    print("Tekan Ctrl+C buat berhenti.\n")

    try:
        with serial.Serial(port, args.baud, timeout=1) as device:
            last_poll = 0.0
            while True:
                # cek antrean konfigurasi dari dashboard tiap beberapa detik
                if time.monotonic() - last_poll >= DOWNLINK_POLL_SECONDS:
                    last_poll = time.monotonic()
                    try:
                        await flush_commands(pool, device, args.no_ack)
                    except Exception as exc:  # noqa: BLE001
                        print(f"[GAGAL downlink] {exc}", file=sys.stderr)

                raw = device.readline().decode("utf-8", errors="replace").strip()
                if raw.startswith("CFG_ACK,"):
                    try:
                        await handle_ack(pool, raw)
                    except Exception as exc:  # noqa: BLE001
                        print(f"[GAGAL ack] {exc}", file=sys.stderr)
                    continue
                if not raw.startswith("CSV_DATA,"):
                    continue

                row = parse_data(next(csv.reader([raw])))
                if row is None:
                    continue

                try:
                    await write_to_postgres(pool, row)
                    print(
                        f"[OK] node {row['node_id']} #{row['sequence']} "
                        f"-> {row['latitude'] or 'TANPA FIX'}, {row['longitude']} "
                        f"(RSSI {row['rssi_dbm']} dBm, {row['satellites']} sat)"
                    )
                except Exception as exc:  # noqa: BLE001 - sengaja luas, jangan sampai bridge mati gara-gara satu baris rusak
                    print(f"[GAGAL insert] {exc}", file=sys.stderr)

                if csv_writer is not None:
                    csv_writer.writerow(row)
                    csv_file.flush()
    except KeyboardInterrupt:
        print("\nBerhenti.")
    finally:
        if csv_file is not None:
            csv_file.close()
        await pool.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="Contoh: COM5. Otomatis kalau cuma ada satu port.")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--database-url", default=DEFAULT_DATABASE_URL)
    parser.add_argument(
        "--also-csv",
        action="store_true",
        help="Tetap simpan file CSV juga (backup lapangan), selain nulis ke Postgres.",
    )
    parser.add_argument(
        "--no-ack",
        action="store_true",
        help="Firmware belum membalas CFG_ACK: anggap konfigurasi 'acked' begitu baris CFG ditulis ke serial.",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())