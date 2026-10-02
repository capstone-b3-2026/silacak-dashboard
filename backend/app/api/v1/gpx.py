from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.core.database import get_db
from app.repositories import position_repo
from app.services.gpx_exporter import build_session_gpx

router = APIRouter(prefix="/gpx", tags=["gpx"])


def _response(result) -> Response:
    if result is None:
        raise HTTPException(404, "Sesi tidak ditemukan.")
    gpx_bytes, filename = result
    return Response(
        content=gpx_bytes,
        media_type="application/gpx+xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/session/{session_id}")
async def export_session_gpx(session_id: int, conn=Depends(get_db)):
    """GPX satu sesi pendakian (aktif maupun riwayat)."""
    return _response(await build_session_gpx(conn, session_id))


@router.get("/{hiker_code}")
async def export_gpx(hiker_code: str, conn=Depends(get_db)):
    """GPX sesi AKTIF alat ini (kalau tidak ada yang aktif: sesi terakhirnya).
    Sengaja tidak lagi menggabung semua riwayat alat itu jadi satu jejak."""
    sid = await position_repo.resolve_session_id(conn, hiker_code)
    if sid is None:
        raise HTTPException(404, f"Belum ada sesi untuk {hiker_code}.")
    return _response(await build_session_gpx(conn, sid))
