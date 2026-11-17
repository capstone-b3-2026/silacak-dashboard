from fastapi import APIRouter, Depends, Query

from app.core.config import settings
from app.core.database import get_db
from app.services import retention

router = APIRouter(prefix="/retention", tags=["retention"])


@router.get("/preview")
async def preview(days: int | None = Query(None, ge=1, le=3650), conn=Depends(get_db)):
    """Pratinjau: berapa baris yang AKAN dihapus bila batas `days` hari (bawaan: nilai pengaturan saat ini) diterapkan. Tidak menghapus apa pun."""
    d = days if days is not None else int(settings.data_retention_days)
    if d <= 0:
        return {"enabled": False, "days": 0, "would_delete": None}
    return {"enabled": int(settings.data_retention_days) > 0, "days": d, "would_delete": await retention.preview(conn, d)}
