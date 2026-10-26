"""Status baterai relay (dari baris CSV_RELAY_BATTERY yang dicetak base)."""
from fastapi import APIRouter, Depends, Query

from app.core.database import get_db
from app.repositories import relay_repo

router = APIRouter(prefix="/relays", tags=["relays"])


@router.get("/status")
async def relays_status(conn=Depends(get_db)):
    """Laporan terbaru tiap relay. `stale` = tidak ada laporan > 120 dtk. `battery_pct`/`volts` null bila sensor tidak OK."""
    return await relay_repo.latest_relay_status(conn)


@router.get("/{relay_id}/history")
async def relay_history(relay_id: int, hours: int = Query(24, ge=1, le=720), limit: int = Query(500, ge=1, le=5000),
                        conn=Depends(get_db)):
    return await relay_repo.relay_history(conn, relay_id, hours, limit)
