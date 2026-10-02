import json

from app.core import database
from app.core.config import settings
from app.repositories import alert_repo, position_repo
from app.services.notifier import notifier


async def check_stagnant_hikers() -> None:
    """Dijalankan berkala oleh scheduler (lihat core/scheduler.py).
    Cek siapa aja yang diam di radius yang sama selama window tertentu,
    lalu buat alert kalau belum ada alert STAGNANT yang masih aktif
    (biar nggak spam alert baru tiap kali job jalan)."""
    async with database.pool.acquire() as conn:
        stagnant = await position_repo.find_stagnant_sessions(
            conn,
            window_minutes=settings.stagnant_window_minutes,
            radius_m=settings.stagnant_radius_m,
        )

        for row in stagnant:
            existing = await alert_repo.get_active_alert(conn, row["session_id"], "STAGNANT")
            if existing:
                continue

            alert = await alert_repo.create_alert(
                conn,
                row["hiker_id"],
                row["session_id"],
                "STAGNANT",
                meta={
                    "radius_m": settings.stagnant_radius_m,
                    "window_minutes": settings.stagnant_window_minutes,
                },
            )
            await notifier.broadcast(
                json.dumps({"type": "alert", "data": alert}, default=str)
            )
