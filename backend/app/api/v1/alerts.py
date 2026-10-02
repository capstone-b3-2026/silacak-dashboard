from fastapi import APIRouter, Depends

from app.core.database import get_db
from app.repositories import alert_repo

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("")
async def list_alerts(conn=Depends(get_db)):
    return await alert_repo.list_active_alerts(conn)


@router.post("/{alert_id}/acknowledge")
async def acknowledge(alert_id: int, conn=Depends(get_db)):
    await alert_repo.acknowledge_alert(conn, alert_id)
    return {"status": "ok"}
