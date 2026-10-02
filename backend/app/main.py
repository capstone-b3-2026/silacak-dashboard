import asyncio
import json
import os

import asyncpg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1 import alerts, devices, diagnostics, gpx, hikers, positions, sites, stream, terrain, sessions
from app.core import database
from app.core.schema import ensure_schema
from app.core.config import settings
from app.core.scheduler import scheduler, start_scheduler
from app.services.notifier import notifier

app = FastAPI(title="SiLacak API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(hikers.router, prefix="/api/v1")
app.include_router(positions.router, prefix="/api/v1")
app.include_router(alerts.router, prefix="/api/v1")
app.include_router(gpx.router, prefix="/api/v1")
app.include_router(terrain.router, prefix="/api/v1")
app.include_router(sites.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(devices.router, prefix="/api/v1")
app.include_router(diagnostics.router, prefix="/api/v1")
app.include_router(stream.router, prefix="/api/v1")

# Tile elevasi hasil upload DEM disajikan langsung dari folder data/sites
os.makedirs(sites.SITES_DIR, exist_ok=True)
app.mount("/api/v1/site-files", StaticFiles(directory=sites.SITES_DIR), name="site-files")

_listener_conn: asyncpg.Connection | None = None


def _on_position_notify(connection, pid, channel, payload: str) -> None:
    """Callback asyncpg LISTEN - dipanggil tiap ada INSERT baru ke table
    positions (lewat trigger pg_notify di init.sql). Forward langsung ke
    semua client SSE, jadi backend nggak perlu polling DB tiap detik."""
    asyncio.create_task(
        notifier.broadcast(json.dumps({"type": "position", "data": json.loads(payload)}))
    )


@app.on_event("startup")
async def on_startup() -> None:
    global _listener_conn
    await database.connect_db()
    async with database.pool.acquire() as conn:
        await ensure_schema(conn)
        # Proses DEM yang sedang jalan waktu backend mati tidak akan pernah selesai -> tandai error,
        # biar tidak "memproses" selamanya di UI.
        await conn.execute(
            "UPDATE sites SET status='error', message='Proses terputus karena backend restart. Upload ulang.' "
            "WHERE status='processing'"
        )

    _listener_conn = await asyncpg.connect(dsn=settings.database_url)
    await _listener_conn.add_listener("position_updates", _on_position_notify)

    start_scheduler()
    asyncio.create_task(sites.backfill_topo())  # peta topo offline utk lokasi yang dibuat sebelum fitur ini ada


@app.on_event("shutdown")
async def on_shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown()
    if _listener_conn is not None:
        await _listener_conn.close()
    await database.disconnect_db()


@app.get("/health")
async def health():
    return {"status": "ok"}