"""Ekspor data (CSV / cadangan ZIP) + info folder data. SEMUA endpoint di sini hanya MEMBACA data;
tidak ada yang mengubah atau menghapus isi basis data. File baru: tidak mengubah logic yang sudah ada."""
import csv
import io
import os
import tempfile
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from starlette.background import BackgroundTask

from app.api.v1.diagnostics import _base_xy
from app.core.config import settings
from app.core.database import get_db

router = APIRouter(prefix="/export", tags=["export"])

BOM = "\ufeff"  # supaya Excel membaca UTF-8 dengan benar

POSITION_HEADER = [
    "sesi_id", "kode_alat", "nama_pendaki", "waktu_gps", "waktu_terima", "sequence", "lat", "lon", "elevasi_m",
    "rssi_dbm", "hop", "rute", "satelit", "hdop", "gps_valid", "paket_hilang_sebelumnya", "total_hilang",
    "baterai_pct", "jarak_ke_base_m", "latency_s", "kecepatan_kph", "rtt_ms",
]

POSITION_SQL = """
    SELECT s.id AS session_id, h.hiker_code, s.full_name, p.recorded_at, p.received_at, p.sequence,
           (p.location)[1] AS lat, (p.location)[0] AS lon, p.elevation, p.rssi_dbm, p.hop_count, p.route_path,
           p.satellites, p.hdop, COALESCE(p.gps_valid, p.location IS NOT NULL) AS gps_valid,
           p.missing_since_previous, p.total_missing, p.battery_pct,
           CASE WHEN $1::float8 IS NULL OR p.location IS NULL THEN NULL
                ELSE geo_dist_m(p.location, point($2::float8, $1::float8)) END AS dist_m,
           CASE WHEN p.time_from_gps THEN EXTRACT(EPOCH FROM p.received_at - p.recorded_at) END AS latency_s,
           p.speed_kph, p.rtt_ms
    FROM positions p
    JOIN hiking_sessions s ON s.id = p.session_id
    JOIN hikers h ON h.id = s.hiker_id
    WHERE ($3::int IS NULL OR s.id = $3)
      AND ($4::timestamptz IS NULL OR p.recorded_at >= $4)
      AND ($5::timestamptz IS NULL OR p.recorded_at <= $5)
    ORDER BY s.id, p.recorded_at
"""


def _dt(v: str | None, name: str) -> datetime | None:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(422, f"Format waktu '{name}' tidak valid.")
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, float):
        return round(v, 6)
    return v


def _position_row(r) -> list:
    return [
        r["session_id"], r["hiker_code"], r["full_name"] or "", _cell(r["recorded_at"]), _cell(r["received_at"]),
        _cell(r["sequence"]), _cell(r["lat"]), _cell(r["lon"]), _cell(r["elevation"]), _cell(r["rssi_dbm"]),
        _cell(r["hop_count"]), r["route_path"] or "", _cell(r["satellites"]), _cell(r["hdop"]),
        "" if r["gps_valid"] is None else int(bool(r["gps_valid"])), _cell(r["missing_since_previous"]),
        _cell(r["total_missing"]), _cell(r["battery_pct"]),
        "" if r["dist_m"] is None else round(r["dist_m"]),
        "" if r["latency_s"] is None else round(float(r["latency_s"]), 2),
        _cell(r["speed_kph"]), _cell(r["rtt_ms"]),
    ]


async def _positions_csv(conn, session_id, t_from, t_to) -> str:
    blat, blon = await _base_xy(conn)
    rows = await conn.fetch(POSITION_SQL, blat, blon, session_id, t_from, t_to)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(POSITION_HEADER)
    for r in rows:
        w.writerow(_position_row(r))
    return BOM + buf.getvalue()


def _csv_response(text: str, filename: str) -> Response:
    return Response(
        content=text.encode("utf-8"), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/session/{session_id}.csv")
async def export_session_csv(
    session_id: int,
    time_from: str | None = Query(None, alias="from"),
    time_to: str | None = Query(None, alias="to"),
    conn=Depends(get_db),
):
    """Semua paket satu sesi (aktif maupun riwayat), opsional dibatasi rentang waktu GPS."""
    if not await conn.fetchval("SELECT 1 FROM hiking_sessions WHERE id = $1", session_id):
        raise HTTPException(404, "Sesi tidak ditemukan.")
    text = await _positions_csv(conn, session_id, _dt(time_from, "from"), _dt(time_to, "to"))
    return _csv_response(text, f"silacak_sesi_{session_id}.csv")


@router.get("/positions.csv")
async def export_range_csv(
    time_from: str | None = Query(None, alias="from"),
    time_to: str | None = Query(None, alias="to"),
    conn=Depends(get_db),
):
    """Semua paket dari semua sesi dalam rentang waktu GPS (kosong = semua)."""
    text = await _positions_csv(conn, None, _dt(time_from, "from"), _dt(time_to, "to"))
    return _csv_response(text, f"silacak_data_{datetime.now().strftime('%Y%m%d_%H%M')}.csv")


# tabel kecil yang diekspor apa adanya ke ZIP cadangan (positions diekspor lewat POSITION_SQL di atas)
_BACKUP_TABLES = {
    "hikers.csv": "SELECT * FROM hikers ORDER BY id",
    "sesi.csv": "SELECT * FROM hiking_sessions ORDER BY id",
    "alarm.csv": "SELECT * FROM alerts ORDER BY id",
}


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


@router.get("/backup.zip")
async def export_backup(conn=Depends(get_db)):
    """Cadangan data operasional (CSV: pendaki, sesi, alarm, seluruh paket posisi) + log mentah serial (data/raw).
    BUKAN dump basis data penuh (tanpa DEM/rencana relay); itu tetap disimpan di folder data / pg_dump."""
    fd, path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    try:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for name, sql in _BACKUP_TABLES.items():
                rows = await conn.fetch(sql)
                buf = io.StringIO()
                w = csv.writer(buf)
                if rows:
                    w.writerow(list(rows[0].keys()))
                    for r in rows:
                        w.writerow([_cell(v) if not isinstance(v, (dict, list)) else str(v) for v in r.values()])
                z.writestr(name, BOM + buf.getvalue())
            z.writestr("paket_posisi.csv", await _positions_csv(conn, None, None, None))
            raw = os.path.join(settings.data_dir, "raw")
            if os.path.isdir(raw):
                for fn in sorted(os.listdir(raw)):
                    fp = os.path.join(raw, fn)
                    if os.path.isfile(fp):
                        z.write(fp, f"raw/{fn}")
    except Exception:
        _remove(path)
        raise
    name = f"silacak_cadangan_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
    return FileResponse(path, media_type="application/zip", filename=name, background=BackgroundTask(_remove, path))


def _is_local(request: Request) -> bool:
    return bool(request.client) and request.client.host in ("127.0.0.1", "::1", "localhost")


@router.get("/data-info")
async def data_info(request: Request):
    """Lokasi folder data. Tombol 'Buka folder' hanya aktif kalau dashboard dibuka di komputer yang sama dengan backend (Windows)."""
    return {"data_dir": settings.data_dir, "can_open": os.name == "nt" and _is_local(request) and os.path.isdir(settings.data_dir)}


@router.post("/open-data-folder")
async def open_data_folder(request: Request):
    if os.name != "nt" or not _is_local(request):
        raise HTTPException(409, "Hanya bisa dibuka dari komputer yang menjalankan backend (Windows). Folder: " + settings.data_dir)
    if not os.path.isdir(settings.data_dir):
        raise HTTPException(404, "Folder data belum ada.")
    os.startfile(settings.data_dir)  # noqa: S606 - hanya folder data milik aplikasi, tanpa input pengguna
    return {"status": "ok", "data_dir": settings.data_dir}