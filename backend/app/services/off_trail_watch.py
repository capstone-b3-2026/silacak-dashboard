"""Peringatan dini "di luar jalur" (OFF_TRAIL): posisi TERAKHIR pendaki aktif keluar koridor perimeter.

Sinyal ini TAMBAHAN, bukan pengganti Auto-SOS (stagnant). Keduanya memakai perimeter yang sama
(`settings.stagnant_perimeter_m`), tetapi OFF_TRAIL berbunyi ketika pendaki MENYIMPANG dari jalur
(bukan ketika diam di tempat). OFF_TRAIL tidak pernah di-ACKNOWLEDGED manual: ia hilang OTOMATIS
(status RESOLVED) saat pendaki kembali masuk perimeter.

Dipicu dari NOTIFY `position_updates` (main.py) untuk SETIAP baris positions yang masuk - sama jalur
dengan sos_watch - supaya peringatan muncul dalam satu-dua paket (bukan menunggu scheduler 2 menit).
Debounce `DEBOUNCE_N` paket (lihat geo.is_off_trail) menapis lonjakan GPS satu paket.
"""
from __future__ import annotations

import json
import logging

from app.core import database
from app.core.config import settings
from app.repositories import alert_repo, position_repo
from app.services import geo
from app.services.notifier import notifier

log = logging.getLogger("silacak.offtrail")

DEBOUNCE_N = 3  # paket terbaru yang harus semuanya di luar perimeter (ASUMSI, belum dikalibrasi)


async def handle_position(data: dict) -> None:
    code = data.get("hiker_code")
    session_id = data.get("session_id")
    if database.pool is None or session_id is None or not code:
        return
    async with database.pool.acquire() as conn:
        trail = await position_repo.get_active_site_trail(conn)
        if not trail or len(trail) < 2:
            return  # tanpa acuan koridor jangan menebak (sama seperti stagnant)
        trail_pts = [(p[0], p[1]) for p in trail]

        rows = await position_repo.get_recent_fixes_for_session(conn, session_id, DEBOUNCE_N)
        recent_points = [(r["lat"], r["lon"]) for r in rows]  # terbaru -> terlama

        off = geo.is_off_trail(recent_points, trail_pts, settings.stagnant_perimeter_m, DEBOUNCE_N)

        if off:
            if await alert_repo.get_active_alert(conn, session_id, "OFF_TRAIL"):
                return  # sudah ada alarm OFF_TRAIL aktif untuk sesi ini (dedupe)
            hiker_id = await conn.fetchval("SELECT id FROM hikers WHERE hiker_code = $1", code)
            if hiker_id is None:
                return
            dist = geo.dist_point_to_trail_m(recent_points[0], trail_pts)
            alert = await alert_repo.create_alert(
                conn, hiker_id, session_id, "OFF_TRAIL",
                meta={"perimeter_m": settings.stagnant_perimeter_m, "dist_to_trail_m": round(dist, 1)},
            )
            await notifier.broadcast(json.dumps({"type": "alert", "data": alert}, default=str))
            log.warning("OFF_TRAIL %s (sesi %s): %.1f m dari jalur", code, session_id, dist)
        else:
            resolved = await alert_repo.resolve_off_trail(conn, session_id)
            if resolved:
                await notifier.broadcast(json.dumps(
                    {"type": "alert_resolved",
                     "data": {"id": resolved["id"], "session_id": resolved["session_id"],
                              "alert_type": "OFF_TRAIL"}},
                    default=str,
                ))
                log.info("OFF_TRAIL %s (sesi %s) selesai: kembali masuk perimeter", code, session_id)
