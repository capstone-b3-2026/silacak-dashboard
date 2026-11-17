"""Ingest base station (USB serial) -> Postgres, tertanam di proses backend.

Menggantikan keharusan menjalankan reference-for-hardware-team/serial_to_postgres_bridge.py
secara manual. Ciri:
- port ditemukan otomatis (ESP32 USB-UART); kalau ada >1 kandidat TIDAK menebak, tunggu dipilih lewat API
- auto-reconnect kalau kabel dicabut / kesenggol, status terbaca lewat GET /api/v1/base/status
- SETIAP baris CSV_DATA ditulis dulu ke log mentah append-only (data_dir/raw/YYYY-MM-DD.log), baru ke DB:
  kalau DB bermasalah, data lapangan tidak hilang
- downlink konfigurasi (device_commands) seperti bridge referensi
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone

from app.core import database
from app.core.config import settings
from app.repositories import alert_repo, relay_repo
from app.services import base_protocol as bp
from app.services.serial_timing import TimingBuffer
from app.services.notifier import notifier

log = logging.getLogger("silacak.serial")

try:  # pyserial opsional di import-time supaya backend tetap bisa start tanpa dia
    import serial
    from serial.tools import list_ports
except ImportError:  # pragma: no cover
    serial = None
    list_ports = None

DOWNLINK_POLL_S = 2.0
# Alarm MANUAL_SOS TIDAK dibuat di sini lagi: dibuat oleh app/services/sos_watch.py dari NOTIFY `position_updates`,
# supaya jalur bridge (proses luar, Docker) dan jalur ingest bawaan memakai satu logika yang sama.
_CACHE_TTL_S = 10.0


def _friendly(exc: Exception, port: str | None = None) -> str:
    msg = str(exc)
    low = msg.lower()
    if port and "://" in port:  # URL pyserial (socket://, rfc2217://): bukan soal kabel/driver
        return f"Tidak bisa tersambung ke {port} (programnya sudah berjalan?)."
    if "access is denied" in low or "permission" in low or "busy" in low or "in use" in low:
        return "Port sedang dipakai program lain (tutup Serial Monitor / PlatformIO / Arduino IDE) lalu tunggu beberapa detik."
    if "could not open" in low or "no such file" in low or "filenotfound" in low:
        return "Port tidak bisa dibuka (kabel baru dicabut atau driver belum terpasang)."
    return msg


class SerialIngest:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._reconnect = threading.Event()
        self._ser = None
        self._downlink_task: asyncio.Task | None = None

        self._requested = settings.serial_port
        self._fail_count = 0           # percobaan gagal berturut-turut (untuk jeda bertahap)
        self._last_logged: str | None = None  # pesan error terakhir yang dicatat ke log (anti-banjir)
        self._state = "off"
        self._port: str | None = None
        self._candidates: list[dict] = []
        self._last_error: str | None = None
        self._packets = 0
        self._rejected = 0
        self._relay_reports = 0       # CSV_RELAY_BATTERY yang berhasil disimpan
        self._last_relay_at: datetime | None = None
        self._last_packet_at: datetime | None = None
        self._duplicates = 0          # paket ganda yang ditolak indeks uq_positions_packet (tidak disimpan ulang)
        self._timing = TimingBuffer()  # ukur penumpukan base -> baca serial (lihat services/serial_timing.py)
        self._cache: dict[int, tuple[float, int | None, str | None]] = {}  # node_id -> (exp, hiker_id, role)

        self._raw_fh = None
        self._raw_day: str | None = None

    # ── penyimpanan pilihan port ──────────────────────────────────────────────
    @property
    def _pref_path(self) -> str:
        return os.path.join(settings.data_dir, "base_link.json")

    def _load_pref(self) -> None:
        try:
            with open(self._pref_path, encoding="utf-8") as f:
                port = json.load(f).get("port")
            if port:
                self._requested = port
        except (OSError, ValueError):
            pass

    def _save_pref(self) -> None:
        try:
            os.makedirs(settings.data_dir, exist_ok=True)
            with open(self._pref_path, "w", encoding="utf-8") as f:
                json.dump({"port": self._requested}, f)
        except OSError as exc:
            log.warning("Gagal menyimpan pilihan port: %s", exc)

    # ── API publik ────────────────────────────────────────────────────────────
    @property
    def enabled(self) -> bool:
        return settings.serial_port.lower() != "off"

    def ports(self) -> list[dict]:
        if list_ports is None:
            return []
        out = []
        for p in list_ports.comports():
            out.append({
                "device": p.device, "description": p.description or "", "vid": p.vid, "pid": p.pid,
                "candidate": p.vid in bp.ESP_USB_VIDS,
            })
        return out

    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "state": self._state,  # off | unavailable | searching | ambiguous | connected | reconnecting
            "port": self._port,
            "requested": self._requested,
            "baud": settings.serial_baud,
            "candidates": [{"device": c["device"], "description": c["description"]} for c in self._candidates],
            "packets_received": self._packets,
            "packets_rejected": self._rejected,
            "packets_duplicate": self._duplicates,
            "last_packet_at": self._last_packet_at.isoformat() if self._last_packet_at else None,
            "last_error": self._last_error,
            "raw_log": settings.raw_log,
            "cfg_downlink": settings.firmware_supports_cfg,  # False = push konfigurasi dimatikan (firmware belum mendukung)
            "relay_reports": self._relay_reports,
            "last_relay_at": self._last_relay_at.isoformat() if self._last_relay_at else None,
        }

    def timing_stats(self) -> dict:
        """Analisis penumpukan paket antara penerimaan radio di base dan pembacaan serial (GET /diagnostics/serial-timing)."""
        return self._timing.stats()

    def set_port(self, port: str) -> None:
        """Pilih port ('COM5') atau kembali ke deteksi otomatis ('auto'); disimpan untuk start berikutnya."""
        self._requested = port.strip() or "auto"
        self._last_error = None
        self._save_pref()
        self._reconnect.set()
        self._wake.set()

    async def start(self) -> None:
        if not self.enabled:
            self._state = "off"
            return
        if serial is None:
            self._state = "unavailable"
            self._last_error = "pyserial belum terpasang (pip install pyserial)."
            log.warning(self._last_error)
            return
        self._load_pref()
        self._loop = asyncio.get_running_loop()
        self._stop.clear()
        self._state = "searching"
        self._thread = threading.Thread(target=self._run, name="serial-ingest", daemon=True)
        self._thread.start()
        self._downlink_task = asyncio.create_task(self._downlink_loop())

    async def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._downlink_task:
            self._downlink_task.cancel()
        if self._thread:
            await asyncio.to_thread(self._thread.join, 3.0)
        if self._raw_fh:
            self._raw_fh.close()
            self._raw_fh = None

    # ── thread pembaca serial ─────────────────────────────────────────────────
    def _wait(self, seconds: float) -> None:
        self._wake.wait(seconds)
        self._wake.clear()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                port, cands = bp.select_port(self.ports(), self._requested)
                self._candidates = cands
                if port is None:
                    self._port = None
                    self._last_error = None  # tidak ada alat = bukan error; jangan tampilkan sisa error port lama
                    self._state = "ambiguous" if len(cands) > 1 else "searching"
                    self._wait(2.0)
                    continue
                self._read_port(port)
            except Exception as exc:  # noqa: BLE001 - thread tidak boleh mati
                self._last_error = _friendly(exc)
                self._state = "reconnecting"
                if self._last_error != self._last_logged:  # pesan yang sama tidak dicatat berulang tiap percobaan
                    log.warning("Serial: %s", self._last_error)
                    self._last_logged = self._last_error
                self._fail_count += 1
                self._wait(min(10.0, 2.0 * 2 ** min(self._fail_count - 1, 3)))  # 2, 4, 8, 10 dtk; set_port membangunkan seketika

    def _read_port(self, port: str) -> None:
        # serial_for_url: nama biasa ('COM4') -> Serial; URL ('socket://127.0.0.1:7777') -> base PALSU untuk tes tanpa alat
        ser = serial.serial_for_url(port, do_not_open=True)
        ser.baudrate, ser.timeout = settings.serial_baud, 1
        ser.dtr = False  # best effort: jangan memicu auto-reset ESP32 saat port dibuka
        ser.rts = False
        try:
            ser.open()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(_friendly(exc, port)) from exc
        self._fail_count, self._last_logged = 0, None
        self._reconnect.clear()
        self._ser, self._port, self._state, self._last_error = ser, port, "connected", None
        log.info("Serial terhubung: %s @ %s", port, settings.serial_baud)
        try:
            while not self._stop.is_set() and not self._reconnect.is_set():
                raw = ser.readline().decode("utf-8", errors="replace").strip()
                # Catat SEGERA setelah baris terbaca (sebelum parse/DB), supaya waktu ini = saat laptop menerima baris.
                read_mono, read_wall = time.monotonic(), datetime.now(timezone.utc)
                if raw:
                    try:
                        backlog = int(ser.in_waiting)  # byte yang masih menunggu di buffer serial: >0 = laptop tertinggal
                    except Exception:  # noqa: BLE001 - tidak semua driver/URL handler punya in_waiting
                        backlog = None
                    self._on_raw(raw, read_mono, read_wall, backlog)
        finally:
            self._ser = None
            try:
                ser.close()
            except Exception:  # noqa: BLE001
                pass
            if not self._stop.is_set():
                self._state = "reconnecting"

    def _write_raw(self, raw: str) -> None:
        now = datetime.now(timezone.utc)
        day = now.strftime("%Y-%m-%d")
        if self._raw_day != day:
            if self._raw_fh:
                self._raw_fh.close()
            folder = os.path.join(settings.data_dir, "raw")
            os.makedirs(folder, exist_ok=True)
            self._raw_fh = open(os.path.join(folder, f"{day}.log"), "a", encoding="utf-8")
            self._raw_day = day
        self._raw_fh.write(f"{now.isoformat()},{raw}\n")
        self._raw_fh.flush()

    def _on_raw(self, raw: str, read_mono: float | None = None, read_wall: datetime | None = None,
                backlog: int | None = None) -> None:
        if raw.startswith("CFG_ACK,"):
            self._submit(self._handle_ack(raw))
            return
        if raw.startswith("CSV_TIMING,"):  # laporan RTT dari pendaki (base_real.cpp handleTimingPacket)
            if settings.raw_log:
                try:
                    self._write_raw(raw)
                except OSError as exc:
                    log.warning("Gagal menulis log mentah: %s", exc)
            self._submit(self._handle_timing(raw))
            return
        if raw.startswith(("CSV_RELAY_BATTERY,", "CSV_LINK,", "CSV_BOOT,")):  # baris pendukung dari base_real.cpp
            if settings.raw_log:
                try:
                    self._write_raw(raw)
                except OSError as exc:
                    log.warning("Gagal menulis log mentah: %s", exc)
            self._submit(self._handle_aux(raw))
            return
        if not raw.startswith("CSV_DATA,"):
            return
        if settings.raw_log:
            try:
                self._write_raw(raw)
            except OSError as exc:
                log.warning("Gagal menulis log mentah: %s", exc)
        self._submit(self._handle_line(raw, read_mono, read_wall, backlog), wait=True)

    def _submit(self, coro, wait: bool = False) -> None:
        if self._loop is None or self._loop.is_closed():
            coro.close()
            return
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        if wait:  # tunggu: urutan terjaga & DB lambat jadi back-pressure, bukan antrean tak terbatas
            try:
                fut.result(timeout=15)
            except Exception as exc:  # noqa: BLE001
                log.warning("Gagal memproses paket: %s", exc)

    # ── sisi async: tulis ke DB ───────────────────────────────────────────────
    async def _handle_line(self, raw: str, read_mono: float | None = None, read_wall: datetime | None = None,
                           backlog: int | None = None) -> None:
        t0 = read_mono if read_mono is not None else time.monotonic()
        row = bp.parse_csv_data(raw)
        rec = bp.to_record(row) if row else None
        if rec is None:
            self._rejected += 1
            return
        await self._store(rec, read_wall)
        try:  # jam base saat paket diterima radio (firmware: base_received_uptime_ms); tidak ada = firmware lama
            base_ms = int(row.get("base_received_uptime_ms", ""))
        except (TypeError, ValueError):
            base_ms = None
        self._timing.add(t0, base_ms, backlog, (time.monotonic() - t0) * 1000.0)

    async def _handle_aux(self, raw: str) -> None:
        """Baterai relay / RSSI per hop / reboot pendaki. Gagal di sini TIDAK boleh mengganggu aliran CSV_DATA."""
        pool = database.pool
        if pool is None:
            return
        try:
            if raw.startswith("CSV_RELAY_BATTERY,"):
                rec = bp.parse_relay_battery(raw)
                if rec is None:
                    self._rejected += 1
                    return
                async with pool.acquire() as conn:
                    await relay_repo.insert_relay_status(conn, rec)
                self._relay_reports += 1
                self._last_relay_at = datetime.now(timezone.utc)
            elif raw.startswith("CSV_LINK,"):
                rec = bp.parse_csv_link(raw)
                if rec is not None:
                    async with pool.acquire() as conn:
                        await relay_repo.insert_link_hops(conn, rec)
            elif raw.startswith("CSV_BOOT,"):
                rec = bp.parse_csv_boot(raw)
                if rec is not None:
                    log.info("Pendaki node %s reboot (boot_id=%s)", rec["node_id"], rec["boot_id"])
                    async with pool.acquire() as conn:
                        await relay_repo.insert_node_boot(conn, rec)
        except Exception as exc:  # noqa: BLE001
            log.warning("Gagal menyimpan baris pendukung (%s): %s", raw.split(",", 1)[0], exc)

    async def _handle_timing(self, raw: str) -> None:
        """CSV_TIMING tiba SESUDAH CSV_DATA paket yang sama (urutan serial terjaga) -> isi rtt_ms barisnya.
        Dibatasi 2 menit terakhir + rtt_ms IS NULL: sequence bisa dipakai ulang setelah pendaki restart."""
        t = bp.parse_csv_timing(raw)
        if t is None or database.pool is None:
            return
        async with database.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE positions p SET rtt_ms = $3
                FROM hikers h
                WHERE h.id = p.hiker_id AND h.hiker_code = $1 AND p.sequence = $2
                  AND p.rtt_ms IS NULL AND p.received_at > now() - interval '2 minutes'
                """,
                f"H{t['node_id']:02d}", t["sequence"], t["rtt_ms"],
            )

    async def _store(self, rec: bp.PositionRecord, read_wall: datetime | None = None) -> None:
        pool = database.pool
        if pool is None:
            return
        async with pool.acquire() as conn:
            now = time.monotonic()
            hit = self._cache.get(rec.node_id)
            if hit is None or hit[0] < now:
                role = await conn.fetchval("SELECT role FROM devices WHERE node_id = $1", rec.node_id)
                hiker_id = None
                if role not in ("relay", "base"):
                    hiker_id = await conn.fetchval(
                        "INSERT INTO hikers (hiker_code) VALUES ($1) "
                        "ON CONFLICT (hiker_code) DO UPDATE SET hiker_code = EXCLUDED.hiker_code RETURNING id",
                        rec.hiker_code,
                    )
                hit = (now + _CACHE_TTL_S, hiker_id, role)
                self._cache[rec.node_id] = hit
            _, hiker_id, role = hit
            if role in ("relay", "base") or hiker_id is None:
                return  # relay/base bukan pendaki: jangan jadi jejak/sesi/alarm SOS
            status = await conn.execute(
                """
                INSERT INTO positions
                    (hiker_id, location, elevation, hop_count, route_path, sequence, rssi_dbm, satellites, hdop,
                     missing_since_previous, total_missing, recorded_at, gps_valid, gps_flags, time_from_gps, speed_kph, battery_pct, sos,
                     serial_read_at)
                VALUES
                    ($1, CASE WHEN $2::float8 IS NULL OR $3::float8 IS NULL THEN NULL
                              ELSE point($2::float8, $3::float8) END,
                     $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)
                ON CONFLICT DO NOTHING  -- paket ganda (uq_positions_packet) tidak disimpan ulang & tidak memicu NOTIFY/SSE
                """,
                hiker_id, rec.lon, rec.lat, rec.elevation, rec.hop_count, rec.route_path, rec.sequence,
                rec.rssi_dbm, rec.satellites, rec.hdop, rec.missing_since_previous, rec.total_missing,
                rec.recorded_at, rec.gps_valid, rec.gps_flags, rec.time_from_gps, rec.speed_kph,
                rec.battery_pct, rec.sos, read_wall,
            )
        if isinstance(status, str) and status.endswith(" 0"):  # "INSERT 0 0" = ditolak sebagai paket ganda
            self._duplicates += 1
            return
        self._packets += 1
        self._last_packet_at = datetime.now(timezone.utc)

    # ── downlink konfigurasi (dashboard -> alat) ──────────────────────────────
    async def _mark_command(self, cmd_id: int, status: str, error: str | None = None) -> None:
        async with database.pool.acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE device_commands SET status=$2, error=$3, updated_at=now() WHERE id=$1 RETURNING device_id, payload",
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

    async def _downlink_loop(self) -> None:
        while True:
            await asyncio.sleep(DOWNLINK_POLL_S)
            if not settings.firmware_supports_cfg and database.pool is not None:
                # Firmware belum membaca serial masuk: gagalkan perintah tertunda dengan alasan jelas, jangan dibiarkan 'sent' selamanya.
                try:
                    async with database.pool.acquire() as conn:
                        await conn.execute(
                            "UPDATE device_commands SET status='failed', error=$1, updated_at=now() WHERE status='pending'",
                            "Firmware base belum mendukung konfigurasi dari dashboard (FIRMWARE_SUPPORTS_CFG=false).",
                        )
                except Exception as exc:  # noqa: BLE001
                    log.warning("Downlink: gagal menandai perintah: %s", exc)
                continue
            ser = self._ser
            if ser is None or database.pool is None:
                continue
            try:
                async with database.pool.acquire() as conn:
                    rows = await conn.fetch("SELECT id, payload FROM device_commands WHERE status='pending' ORDER BY id")
                for r in rows:
                    payload = r["payload"]
                    if isinstance(payload, str):
                        payload = json.loads(payload)
                    try:
                        line = bp.build_cfg_line(payload).encode("utf-8")
                        await asyncio.to_thread(lambda: (ser.write(line), ser.flush()))
                    except Exception as exc:  # noqa: BLE001
                        await self._mark_command(r["id"], "failed", f"gagal tulis serial: {exc}")
                        continue
                    await self._mark_command(r["id"], "acked" if settings.serial_no_ack else "sent")
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.warning("Downlink gagal: %s", exc)

    async def _handle_ack(self, raw: str) -> None:
        parts = raw.split(",")
        if len(parts) < 3 or database.pool is None:
            return
        try:
            node_id, version = int(parts[1]), int(parts[2])
        except ValueError:
            return
        async with database.pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT c.id FROM device_commands c JOIN devices d ON d.id = c.device_id
                   WHERE d.node_id=$1 AND c.status='sent' AND (c.payload->>'version')::int = $2
                   ORDER BY c.id DESC LIMIT 1""",
                node_id, version,
            )
        if row:
            await self._mark_command(row["id"], "acked")


serial_ingest = SerialIngest()