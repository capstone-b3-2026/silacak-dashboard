from fastapi import APIRouter, Depends, Query

from app.core.database import get_db
from app.repositories import position_repo
from app.services.geo import thin_track

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("/latest")
async def latest_positions(conn=Depends(get_db)):
    """Posisi terakhir semua pendaki - dipanggil frontend sekali saat
    dashboard pertama kali dibuka, update selanjutnya lewat SSE (/stream)."""
    return await position_repo.get_latest_positions(conn)


@router.get("/{hiker_code}/track")
async def hiker_track(
    hiker_code: str,
    max_points: int = Query(1500, ge=0, le=100000, description="Jarangkan jejak untuk TAMPILAN (0 = semua titik). Data di DB & GPX tetap penuh."),
    conn=Depends(get_db),
):
    return thin_track(await position_repo.get_track_points(conn, hiker_code), max_points)
