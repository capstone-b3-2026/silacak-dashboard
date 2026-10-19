import functools
import json
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator

from app.core.database import get_db
from app.repositories import position_repo
from app.services.geo import thin_track
from app.services.notifier import notifier

router = APIRouter(prefix="/sessions", tags=["sessions"])
log = logging.getLogger("silacak.sessions")


def _diagnosable(fn):
    """Error tak terduga: tulis traceback ke log backend DAN kirim jenis error-nya ke UI,
    supaya yang tampil bukan sekadar 'Error 500'. (Dashboard lokal, bukan layanan publik.)"""

    @functools.wraps(fn)
    async def wrapper(*a, **kw):
        try:
            return await fn(*a, **kw)
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            log.exception("sessions: %s gagal", fn.__name__)
            raise HTTPException(500, f"{type(e).__name__}: {e}") from e

    return wrapper

CODE_RE = re.compile(r"^[A-Z0-9_-]{1,20}$")

SESSION_SELECT = """
    SELECT s.id, h.hiker_code, s.full_name, s.phone_number, s.emergency_contact,
           s.trail_name, s.status, s.auto_opened, s.checked_in_at, s.checked_out_at,
           (SELECT MAX(p.recorded_at) FROM positions p WHERE p.session_id = s.id) AS last_seen,
           (SELECT COUNT(*) FROM alerts a WHERE a.session_id = s.id AND a.status = 'ACTIVE') AS active_alerts
    FROM hiking_sessions s
    JOIN hikers h ON h.id = s.hiker_id
"""


class CheckIn(BaseModel):
    hiker_code: str  # kode alat, mis. "H01" (harus sama dengan node_id di firmware)
    full_name: str
    phone_number: str | None = None
    emergency_contact: str | None = None
    trail_name: str | None = None

    @field_validator("hiker_code")
    @classmethod
    def _code(cls, v: str) -> str:
        v = v.strip().upper()
        if not CODE_RE.match(v):
            raise ValueError("Kode alat hanya boleh huruf/angka/-/_ (maks 20 karakter).")
        return v

    @field_validator("full_name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Nama pendaki wajib diisi.")
        return v


def _clean(v: str | None) -> str | None:
    v = (v or "").strip()
    return v or None


async def _get(conn, session_id: int):
    row = await conn.fetchrow(SESSION_SELECT + " WHERE s.id = $1", session_id)
    return dict(row) if row else None


async def _announce(event: str, session: dict) -> None:
    await notifier.broadcast(json.dumps({"type": "session", "event": event, "data": session}, default=str))


@router.get("")
async def list_sessions(status: str = Query("active", pattern="^(active|completed|all)$"), limit: int = 100, conn=Depends(get_db)):
    where = "" if status == "all" else f" WHERE s.status = '{status}'"
    order = " ORDER BY s.checked_in_at DESC" if status != "active" else " ORDER BY s.checked_in_at ASC"
    rows = await conn.fetch(SESSION_SELECT + where + order + " LIMIT $1", max(1, min(limit, 500)))
    return [dict(r) for r in rows]


@router.post("")
@_diagnosable
async def check_in(body: CheckIn, conn=Depends(get_db)):
    """Mulai sesi untuk satu alat. Kalau alat itu sudah mengirim data tanpa check-in
    (sesi dibuka otomatis), sesi itu DIAMBIL ALIH: identitas pendaki ditempel ke sesi yang
    sama, jadi jejak yang sudah terkumpul tidak terpotong. Kalau sudah ada sesi aktif yang
    memang sudah punya pendaki -> 409 (check-out dulu)."""
    async with conn.transaction():
        hiker_id = await conn.fetchval("SELECT id FROM hikers WHERE hiker_code = $1", body.hiker_code)
        if hiker_id is None:
            hiker_id = await conn.fetchval(
                "INSERT INTO hikers (hiker_code) VALUES ($1) ON CONFLICT (hiker_code) DO UPDATE "
                "SET hiker_code = EXCLUDED.hiker_code RETURNING id",
                body.hiker_code,
            )
        active = await conn.fetchrow(
            "SELECT id, auto_opened, full_name FROM hiking_sessions "
            "WHERE hiker_id = $1 AND status = 'active' FOR UPDATE",
            hiker_id,
        )
        if active and not active["auto_opened"]:
            who = active["full_name"] or "pendaki lain"
            raise HTTPException(409, f"Alat {body.hiker_code} masih dipakai {who}. Check-out dulu.")
        if active:
            sid = active["id"]
            await conn.execute(
                "UPDATE hiking_sessions SET full_name=$2, phone_number=$3, emergency_contact=$4, "
                "trail_name=$5, auto_opened=FALSE WHERE id=$1",
                sid, body.full_name, _clean(body.phone_number), _clean(body.emergency_contact), _clean(body.trail_name),
            )
        else:
            sid = await conn.fetchval(
                "INSERT INTO hiking_sessions (hiker_id, full_name, phone_number, emergency_contact, trail_name, status) "
                "VALUES ($1,$2,$3,$4,$5,'active') RETURNING id",
                hiker_id, body.full_name, _clean(body.phone_number), _clean(body.emergency_contact), _clean(body.trail_name),
            )
    session = await _get(conn, sid)
    await _announce("opened", session)
    return session


@router.post("/{session_id}/checkout")
@_diagnosable
async def check_out(session_id: int, conn=Depends(get_db)):
    """Tutup sesi: alarm yang masih aktif ikut diselesaikan, jejak pindah ke riwayat."""
    async with conn.transaction():
        row = await conn.fetchrow(
            "SELECT id, status FROM hiking_sessions WHERE id = $1 FOR UPDATE", session_id
        )
        if not row:
            raise HTTPException(404, "Sesi tidak ditemukan.")
        if row["status"] != "active":
            raise HTTPException(409, "Sesi ini sudah di-check-out.")
        await conn.execute(
            "UPDATE hiking_sessions SET status='completed', checked_out_at=now() WHERE id=$1", session_id
        )
        await conn.execute(
            "UPDATE alerts SET status='RESOLVED', resolved_at=now() WHERE session_id=$1 AND status <> 'RESOLVED'",
            session_id,
        )
    session = await _get(conn, session_id)
    await _announce("closed", session)
    return session


@router.get("/{session_id}/track")
async def session_track(
    session_id: int,
    max_points: int = Query(1500, ge=0, le=100000, description="Jarangkan untuk tampilan (0 = semua titik)."),
    conn=Depends(get_db),
):
    if not await _get(conn, session_id):
        raise HTTPException(404, "Sesi tidak ditemukan.")
    return thin_track(await position_repo.get_session_track(conn, session_id), max_points)
