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
ALTITUDE_VALID = 0x08  # GpsFlags::AltitudeValid -- tanpa bit ini firmware mencetak altitude_m = 0.00 (BUKAN 0 m sungguhan)
SPEED_VALID = 0x10     # GpsFlags::SpeedValid   -- tanpa bit ini firmware mencetak speed_kph = 0.00

# Field OPSIONAL di BELAKANG baris CSV_DATA (firmware baru): field ke-19 = baterai 0..100 (%), ke-20 = flag SOS (1 = aktif).
# Firmware lama hanya 18 field -> kedua kunci ini tidak ada di dict, dan to_record() memperlakukannya sebagai kosong.
OPTIONAL_FIELDNAMES = ["battery_pct", "sos"]

# Baris `CSV_TIMING,<seq>,<node_id>,<node_name>,<rtt_ms>,<one_way_ms>` dari handleTimingPacket() base_real.cpp
TIMING_FIELDNAMES = ["sequence", "node_id", "node_name", "rtt_ms", "one_way_ms"]

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
    row = dict(zip(FIELDNAMES, parts[1:19]))
    row.update(zip(OPTIONAL_FIELDNAMES, parts[19:21]))
    return row


def parse_csv_timing(raw: str) -> dict[str, int] | None:
    """`CSV_TIMING,...` -> {sequence, node_id, rtt_ms}, atau None kalau bukan CSV_TIMING / rusak."""
    if not raw.startswith("CSV_TIMING,"):
        return None
    try:
        parts = next(csv.reader([raw]))
    except (csv.Error, StopIteration):
        return None
    if len(parts) < 6:
        return None
    d = dict(zip(TIMING_FIELDNAMES, parts[1:6]))
    seq, node, rtt = to_int(d["sequence"]), to_int(d["node_id"]), to_int(d["rtt_ms"])
    if seq is None or node is None or rtt is None or rtt < 0:
        return None
    return {"sequence": seq, "node_id": node, "rtt_ms": rtt}


# ── Baris pendukung dari base_real.cpp (bukan CSV_DATA) ─────────────────────────────────────────
# CSV_RELAY_BATTERY,<relay_id>,<boot>,<seq>,<relay_uptime_ms>,<base_rx_ms>,<pct|->,<volt|->,<state>,<umur_sampel_ms|->,<rute>,<hop>,<rssi|->
#   (formatRelayBattery di include/real_serial.h; dikirim base tiap relay melapor, ~30 dtk)
RELAY_BATTERY_FIELDS = [
    "relay_id", "boot_id", "sequence", "relay_uptime_ms", "base_received_ms", "battery_pct",
    "volts", "gauge_state", "sample_age_ms", "route", "hops", "rssi_dbm",
]
GAUGE_STATES = {"OK", "NO_DEVICE", "IO_ERROR", "INVALID", "STALE", "WARMING_UP", "UNKNOWN"}


def parse_relay_battery(raw: str) -> dict | None:
    """`CSV_RELAY_BATTERY,...` -> dict siap simpan, atau None kalau bukan baris itu / rusak.
    Tanda `,` setelah nama sengaja ikut dicek supaya `CSV_RELAY_BATTERY_STATS,...` tidak ikut terbaca."""
    if not raw.startswith("CSV_RELAY_BATTERY,"):
        return None
    try:
        parts = next(csv.reader([raw]))
    except (csv.Error, StopIteration):
        return None
    if len(parts) < 13:
        return None
    d = dict(zip(RELAY_BATTERY_FIELDS, parts[1:13]))
    relay_id, boot_id, seq = to_int(d["relay_id"]), to_int(d["boot_id"]), to_int(d["sequence"])
    if relay_id is None or boot_id is None or seq is None:
        return None
    state = d["gauge_state"].strip().upper()
    if state not in GAUGE_STATES:
        state = "UNKNOWN"
    pct, volts = parse_battery(d["battery_pct"]), to_float(d["volts"])
    if state != "OK" or (volts is not None and not 2.5 <= volts <= 4.5):
        pct = volts = None  # firmware mencetak "-" kalau sensor tidak OK; jangan simpan angka yang tidak dipercaya
    return {
        "relay_id": relay_id, "boot_id": boot_id, "sequence": seq, "battery_pct": pct, "volts": volts,
        "gauge_state": state, "sample_age_ms": to_int(d["sample_age_ms"]), "route_path": d["route"] or None,
        "hop_count": to_int(d["hops"]), "rssi_dbm": to_int(d["rssi_dbm"]),
    }


def parse_csv_link(raw: str) -> dict | None:
    """`CSV_LINK,<node>,<boot>,<seq>[,R<id>:<rssi|->]...` -> {node_id, boot_id, sequence, hops:[{relay_id, rssi_dbm}]}.
    Paket langsung (tanpa relay) menghasilkan hops kosong. RSSI "-" = tidak diketahui (None)."""
    if not raw.startswith("CSV_LINK,"):
        return None
    parts = raw.split(",")
    if len(parts) < 4:
        return None
    node, boot, seq = to_int(parts[1]), to_int(parts[2]), to_int(parts[3])
    if node is None or boot is None or seq is None:
        return None
    hops = []
    for tok in parts[4:]:
        tag, _, rssi = tok.strip().partition(":")
        rid = to_int(tag[1:]) if tag.startswith("R") else None
        if rid is None:
            return None
        hops.append({"relay_id": rid, "rssi_dbm": to_int(rssi)})
    return {"node_id": node, "boot_id": boot, "sequence": seq, "hops": hops}


def parse_csv_boot(raw: str) -> dict | None:
    """`CSV_BOOT,<node>,<boot>` -> pendaki reboot (boot ID naik). Dipakai untuk menjelaskan penghitung paket yang di-reset."""
    if not raw.startswith("CSV_BOOT,"):
        return None
    parts = raw.split(",")
    if len(parts) < 3:
        return None
    node, boot = to_int(parts[1]), to_int(parts[2])
    return None if node is None or boot is None else {"node_id": node, "boot_id": boot}


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
    speed_kph: float | None = None
    battery_pct: float | None = None
    sos: bool = False

def parse_battery(value: str) -> float | None:
    v = (value or "").strip().rstrip("%").strip()
    if v in ("", "-"):
        return None
    try:
        x = round(float(v))
    except ValueError:
        return None
    return float(x) if 0 <= x <= 100 else None

def parse_sos(value: str) -> bool:
    # Kontrak firmware: field ke-20 hanya "0" atau "1" (valid() di real_protocol.h menolak sos > 1).
    # Sama persis dengan bridge referensi (`== "1"`): nilai lain = bukan SOS, supaya tidak ada alarm palsu.
    return (value or "").strip() == "1"

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
    # Firmware mencetak 0.00 untuk altitude/speed yang TIDAK valid. Tanpa cek bit flag-nya, "0 m" tersimpan
    # dan tampil di dashboard + <ele>0</ele> di GPX. flags kosong/rusak (None) = data lama: nilai dipakai apa adanya.
    elevation, speed = to_float(row["altitude_m"]), to_float(row["speed_kph"])
    if flags is not None and not (flags & ALTITUDE_VALID):
        elevation = None
    if flags is not None and not (flags & SPEED_VALID):
        speed = None
    # Baterai: hanya 0..100 yang dipercaya (firmware boleh mengirim 255/-1/"-" = tidak terbaca -> NULL, bukan 255%).
    battery = parse_battery(row.get("battery_pct", ""))
    sos = parse_sos(row.get("sos", ""))
    # kriteria validitas C-251 4.1.3: Nsat >= 4 dan HDOP <= 5
    gps_valid = lat is not None and (sats is None or sats >= 4) and (hdop is None or hdop <= 5.0)
    recorded_at, from_gps = parse_recorded_at(row, now)
    return PositionRecord(
        node_id=node_id, hiker_code=f"H{node_id:02d}", lat=lat, lon=lon,
        elevation=elevation, hop_count=to_int(row["relay_hops"]),
        route_path=row["route"] or None, sequence=to_int(row["sequence"]),
        rssi_dbm=to_int(row["rssi_dbm"]), satellites=sats, hdop=hdop,
        missing_since_previous=to_int(row["missing_since_previous"]),
        total_missing=to_int(row["total_missing"]), recorded_at=recorded_at,
        gps_valid=gps_valid, gps_flags=row["gps_flags"] or None, time_from_gps=from_gps, speed_kph=speed,
        battery_pct=None if battery is None else float(battery), sos=sos,
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