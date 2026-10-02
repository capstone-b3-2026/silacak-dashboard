"""Diagnostik link & kualitas data per sesi aktif: PDR, latency, node basi, jarak ke base, packet log.

Definisi (catat di laporan, ini yang membedakan dari model simulasi C-251):
- PDR sesi   = diterima / (diterima + hilang). 'hilang' = jumlah missing_since_previous dari paket kedua dst
               (paket pertama jadi jangkar, supaya jeda sebelum check-in tidak dihitung hilang).
- Latency    = received_at (masuk DB) - recorded_at (jam GPS node). Hanya paket yang waktunya benar-benar dari GPS;
               validitasnya bergantung jam laptop sinkron (NTP). Nilai negatif = jam laptop tidak sinkron.
- Basi       = tidak ada paket baru > STALE_AFTER_S detik.
"""
import json

from fastapi import APIRouter, Depends, Query

from app.core.database import get_db
from app.repositories import position_repo

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])

STALE_AFTER_S = 120  # 4x interval lapor default (30 dtk); sesuaikan kalau interval diubah


async def _base_xy(conn):
    raw = await conn.fetchval("SELECT base FROM sites WHERE is_active ORDER BY id DESC LIMIT 1")
    b = json.loads(raw) if isinstance(raw, str) else raw
    return (b["lat"], b["lon"]) if b and b.get("lat") is not None else (None, None)


def _f(v, nd=2):
    return None if v is None else round(float(v), nd)


@router.get("")
async def session_diagnostics(conn=Depends(get_db)):
    blat, blon = await _base_xy(conn)
    latest = await conn.fetch(
        """
        SELECT DISTINCT ON (p.session_id)
            p.session_id, h.hiker_code, p.sequence, p.rssi_dbm, p.hop_count, p.route_path,
            p.satellites, p.hdop, p.received_at,
            COALESCE(p.gps_valid, p.location IS NOT NULL) AS gps_valid,
            k.recorded_at AS last_fix_at,
            CASE WHEN $1::float8 IS NULL OR k.location IS NULL THEN NULL
                 ELSE ST_Distance(k.location, ST_SetSRID(ST_MakePoint($2::float8, $1::float8), 4326)::geography) END AS dist_m,
            EXTRACT(EPOCH FROM now() - p.received_at) AS silent_s
        FROM positions p
        JOIN hiking_sessions s ON s.id = p.session_id AND s.status = 'active'
        JOIN hikers h ON h.id = s.hiker_id
        LEFT JOIN LATERAL (
            SELECT q.location, q.recorded_at FROM positions q
            WHERE q.session_id = p.session_id AND q.location IS NOT NULL
            ORDER BY q.recorded_at DESC LIMIT 1
        ) k ON TRUE
        ORDER BY p.session_id, p.recorded_at DESC
        """, blat, blon)
    stats = await conn.fetch(
        """
        WITH r AS (
            SELECT p.*, ROW_NUMBER() OVER (PARTITION BY p.session_id ORDER BY p.recorded_at) AS rn
            FROM positions p JOIN hiking_sessions s ON s.id = p.session_id AND s.status = 'active'
        )
        SELECT session_id,
               COUNT(*) AS received,
               COALESCE(SUM(GREATEST(missing_since_previous, 0)) FILTER (WHERE rn > 1), 0) AS missing,
               percentile_cont(0.5)  WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM received_at - recorded_at)) FILTER (WHERE time_from_gps) AS lat_p50,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM received_at - recorded_at)) FILTER (WHERE time_from_gps) AS lat_p95,
               COUNT(*) FILTER (WHERE location IS NULL OR gps_valid IS FALSE) AS gps_bad
        FROM r GROUP BY session_id
        """)
    st = {r["session_id"]: r for r in stats}
    out = []
    for r in latest:
        s = st.get(r["session_id"])
        rec, miss = (s["received"], int(s["missing"])) if s else (0, 0)
        denom = (rec - 1) + miss
        out.append({
            "hiker_code": r["hiker_code"], "session_id": r["session_id"],
            "received": rec, "missing": miss,
            "pdr": _f(100.0 * (rec - 1) / denom, 1) if denom > 0 else None,
            "latency_p50_s": _f(s["lat_p50"]) if s else None,
            "latency_p95_s": _f(s["lat_p95"]) if s else None,
            "gps_bad_packets": s["gps_bad"] if s else 0,
            "sequence": r["sequence"], "rssi_dbm": r["rssi_dbm"], "hop_count": r["hop_count"],
            "route_path": r["route_path"], "satellites": r["satellites"], "hdop": r["hdop"],
            "gps_valid": r["gps_valid"],
            "last_heard_at": r["received_at"].isoformat(),
            "last_fix_at": r["last_fix_at"].isoformat() if r["last_fix_at"] else None,
            "dist_to_base_m": _f(r["dist_m"], 0),
            "silent_s": _f(r["silent_s"], 0),
            "stale": float(r["silent_s"]) > STALE_AFTER_S,
        })
    return {"stale_after_s": STALE_AFTER_S, "base_set": blat is not None, "sessions": out}


@router.get("/{hiker_code}/packets")
async def packet_log(hiker_code: str, limit: int = Query(60, ge=1, le=500), conn=Depends(get_db)):
    """Packet log sesi aktif (atau terakhir) alat ini, terbaru dulu. Jarak + RSSI per paket = bahan kalibrasi propagasi."""
    sid = await position_repo.resolve_session_id(conn, hiker_code)
    if not sid:
        return []
    blat, blon = await _base_xy(conn)
    rows = await conn.fetch(
        """
        SELECT p.sequence, p.recorded_at, p.received_at, p.rssi_dbm, p.hop_count, p.route_path,
               p.satellites, p.hdop, p.missing_since_previous,
               COALESCE(p.gps_valid, p.location IS NOT NULL) AS gps_valid,
               CASE WHEN p.time_from_gps THEN EXTRACT(EPOCH FROM p.received_at - p.recorded_at) END AS latency_s,
               CASE WHEN $2::float8 IS NULL OR p.location IS NULL THEN NULL
                    ELSE ST_Distance(p.location, ST_SetSRID(ST_MakePoint($3::float8, $2::float8), 4326)::geography) END AS dist_m
        FROM positions p WHERE p.session_id = $1
        ORDER BY p.recorded_at DESC LIMIT $4
        """, sid, blat, blon, limit)
    return [{
        "sequence": r["sequence"], "recorded_at": r["recorded_at"].isoformat(), "received_at": r["received_at"].isoformat(),
        "rssi_dbm": r["rssi_dbm"], "hop_count": r["hop_count"], "route_path": r["route_path"],
        "satellites": r["satellites"], "hdop": r["hdop"], "missing_since_previous": r["missing_since_previous"],
        "gps_valid": r["gps_valid"], "latency_s": _f(r["latency_s"]), "dist_to_base_m": _f(r["dist_m"], 0),
    } for r in rows]
