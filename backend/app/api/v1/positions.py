from fastapi import APIRouter, Depends

from app.core.database import get_db
from app.repositories import position_repo

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("/latest")
async def latest_positions(conn=Depends(get_db)):
    """Posisi terakhir semua pendaki - dipanggil frontend sekali saat
    dashboard pertama kali dibuka, update selanjutnya lewat SSE (/stream)."""
    return await position_repo.get_latest_positions(conn)


@router.get("/{hiker_code}/track")
async def hiker_track(hiker_code: str, conn=Depends(get_db)):
    return await position_repo.get_track_points(conn, hiker_code)
