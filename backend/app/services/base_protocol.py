"""Protokol serial base station -> dashboard (murni, tanpa dependensi).

Format baris `CSV_DATA,...` PERSIS sama dengan emitCsvData() di base_real.cpp / base_optimized.cpp
(parts[0] literal "CSV_DATA" + 18 nilai). JANGAN ubah urutan kecuali firmware berubah.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone

FIELDNAMES = [
    "sequence", "node_id", "node_name", "route", "relay_hops", "tracker_uptime_ms",
    "base_received_uptime_ms", "gps_flags", "gps_utc", "latitude", "longitude", "altitude_m",
    "speed_kph", "satellites", "hdop", "rssi_dbm", "missing_since_previous", "total_missing",
]

# USB-UART yang lazim di board ESP32: Silicon Labs CP210x, WCH CH340/CH341, FTDI, Espressif USB native
LOCATION_VALID = 0x01  # GpsFlags::LocationValid di protocol.h firmware

ESP_USB_VIDS = {0x10C4, 0x1A86, 0x0403, 0x303A}


def parse_csv_data(raw: str) -> dict[str, str] | None:
    """Baris mentah -> dict field, atau None kalau bukan CSV_DATA / kurang field.
    Field tambahan di belakang (>18) diabaikan supaya firmware yang ditambah field tidak membuat baris terbuang."""
    if not raw.startswith("CSV_DATA,"):
        return None
    try:
        parts = next(csv.reader([raw]))
    except (csv.Error, StopIteration):
        return None
    if len(parts) < 19:
        return None
    return dict(zip(FIELDNAMES, parts[1:19]))


def to_int(v: str) -> int | None:
    try:
        return int(v) if v not in ("", "-") else None
    except ValueError:
        return None


def to_float(v: str) -> float | None:
    try:
        return float(v) if v not in ("", "-") else None
    except ValueError:
        return None


def parse_recorded_at(row: dict[str, str], now: datetime | None = None) -> tuple[datetime, bool]:
    """(waktu, dari_gps). gps_utc dipakai kalau valid; kalau GPS belum dapat tanggal (sering 2000-01-01)
    pakai waktu terima, dan latency TIDAK dihitung untuk paket itu."""
    gps_utc = row.get("gps_utc", "")
    if gps_utc:
        try:
            t = datetime.fromisoformat(gps_utc.replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            if t.year >= 2024:
                return t, True
        except ValueError:
            pass
    return (now or datetime.now(timezone.utc)), False


@dataclass
class PositionRecord:
    node_id: int
    hiker_code: str
    lat: float | None
    lon: float | None
    elevation: float | None
    hop_count: int | None
    route_path: str | None
    sequence: int | None
    rssi_dbm: int | None
    satellites: int | None
    hdop: float | None
    missing_since_previous: int | None
    total_missing: int | None
    recorded_at: datetime
    gps_valid: bool
    gps_flags: str | None
    time_from_gps: bool


def to_record(row: dict[str, str], now: datetime | None = None) -> PositionRecord | None:
    node_id = to_int(row["node_id"])
    if node_id is None:
        return None
    lat, lon = to_float(row["latitude"]), to_float(row["longitude"])
    # Firmware TIDAK mengosongkan koordinat saat tidak ada fix: ia mencetak 0.0000000,0.0000000 dan
    # bit LocationValid (gps_flags & 1) tidak di-set. Tanpa pengecekan ini marker pendaki lompat ke (0,0).
    flags = to_int(row["gps_flags"])
    if flags is not None and not (flags & LOCATION_VALID):
        lat = lon = None
    elif lat == 0.0 and lon == 0.0:  # jaring pengaman kalau kolom flags kosong/rusak
        lat = lon = None
    if lat is None or lon is None:
        lat = lon = None  # paket tanpa fix TETAP disimpan (PDR, status GPS invalid, lokasi terakhir)
    sats, hdop = to_int(row["satellites"]), to_float(row["hdop"])
    # kriteria validitas C-251 4.1.3: Nsat >= 4 dan HDOP <= 5
    gps_valid = lat is not None and (sats is None or sats >= 4) and (hdop is None or hdop <= 5.0)
    recorded_at, from_gps = parse_recorded_at(row, now)
    return PositionRecord(
        node_id=node_id, hiker_code=f"H{node_id:02d}", lat=lat, lon=lon,
        elevation=to_float(row["altitude_m"]), hop_count=to_int(row["relay_hops"]),
        route_path=row["route"] or None, sequence=to_int(row["sequence"]),
        rssi_dbm=to_int(row["rssi_dbm"]), satellites=sats, hdop=hdop,
        missing_since_previous=to_int(row["missing_since_previous"]),
        total_missing=to_int(row["total_missing"]), recorded_at=recorded_at,
        gps_valid=gps_valid, gps_flags=row["gps_flags"] or None, time_from_gps=from_gps,
    )


def select_port(ports: list[dict], requested: str | None) -> tuple[str | None, list[dict]]:
    """Pilih port serial base.

    ports: [{device, description, vid, pid}]. requested: 'COM5' | 'auto' | None.
    Return (port_terpilih | None, kandidat). Kalau kandidat > 1 TIDAK menebak (membuka port papan
    lain bisa me-reset-nya): kembalikan None dan biarkan pengguna memilih."""
    if requested and requested.lower() not in ("auto", ""):
        return requested, []
    cands = [p for p in ports if p.get("vid") in ESP_USB_VIDS]
    if not cands and len(ports) == 1:
        cands = ports
    return (cands[0]["device"] if len(cands) == 1 else None), cands


def build_cfg_line(p: dict) -> str:
    """Usulan format downlink (firmware BELUM mengerti; lihat catatan di reference bridge)."""
    c = p["config"]
    name = str(p["name"]).replace(",", " ")
    return f"CFG,{p['node_id']},{name},{p['role']},{c['report_interval_s']},{c['tx_power_dbm']},{c['sf']},{p['version']}\n"
