"""Alarm MANUAL_SOS dari tombol SOS pendaki (satu logika untuk jalur bridge DAN ingest bawaan).

Dipicu dari NOTIFY `position_updates` (main.py), yang menyala untuk SETIAP baris positions yang masuk,
dari proses mana pun. Aturan:
- Sudah ada alarm MANUAL_SOS berstatus ACTIVE untuk sesi itu -> tidak membuat alarm baru.
- Tombol BARU ditekan (flag sos berubah 0 -> 1, atau backend baru start) -> alarm baru, walau alarm sebelumnya
  sudah "Sudah ditangani". Menekan SOS lagi adalah sinyal darurat baru.
- Flag sos MASIH menyala terus (tombol tidak dilepas) -> tidak ada alarm baru, kecuali alarm terakhir sudah lebih
  tua dari SOS_REALERT_S (pengingat), supaya operator tidak dibanjiri tiap paket.
"""
from __future__ import annotations

import asyncio
import json
import logging

from app.core import database
from app.repositories import alert_repo
from app.services.notifier import notifier

log = logging.getLogger("silacak.sos")

SOS_REALERT_S = 1800.0
_held: dict[str, bool] = {}  # kode alat -> flag SOS sudah terlihat menyala (belum pernah terlihat 0 sejak itu)
_lock = asyncio.Lock()


async def handle_position(data: dict) -> None:
    code = data.get("hiker_code")
    if not code:
        return
    if not data.get("sos"):
        _held.pop(code, None)
        return
    async with _lock:
        session_id = data.get("session_id")
        if database.pool is None or session_id is None:
            return
        new_press = not _held.get(code)
        async with database.pool.acquire() as conn:
            if await alert_repo.get_active_alert(conn, session_id, "MANUAL_SOS"):
                _held[code] = True
                return
            if not new_press:
                recent = await conn.fetchval(
                    """SELECT 1 FROM alerts WHERE session_id = $1 AND alert_type = 'MANUAL_SOS'
                       AND triggered_at > now() - make_interval(secs => $2)""",
                    session_id, SOS_REALERT_S,
                )
                if recent:
                    return
            hiker_id = await conn.fetchval("SELECT id FROM hikers WHERE hiker_code = $1", code)
            if hiker_id is None:
                return
            alert = await alert_repo.create_alert(
                conn, hiker_id, session_id, "MANUAL_SOS",
                meta={"lat": data.get("lat"), "lon": data.get("lon"), "rssi_dbm": data.get("rssi_dbm"),
                      "battery_pct": data.get("battery_pct"), "route_path": data.get("route_path")},
            )
            await notifier.broadcast(json.dumps({"type": "alert", "data": alert}, default=str))
            log.warning("SOS dari %s (sesi %s)", code, session_id)
        _held[code] = True
