import asyncio
import json
import logging
import mimetypes
import os

import asyncpg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import alerts, app_config, base, devices, diagnostics, export, gpx, hikers, positions, relays, sites, stream, terrain, sessions, retention
from app.core import database
from app.core.schema import ensure_schema
from app.core.config import settings
from app.core.scheduler import scheduler, start_scheduler
from app.services import app_settings, sos_watch, off_trail_watch
from app.services.notifier import notifier
from app.services.serial_ingest import serial_ingest

log = logging.getLogger("silacak")

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
app.include_router(base.router, prefix="/api/v1")
app.include_router(relays.router, prefix="/api/v1")
app.include_router(app_config.router, prefix="/api/v1")
app.include_router(retention.router, prefix="/api/v1")
app.include_router(export.router, prefix="/api/v1")

# Tile elevasi hasil upload DEM disajikan langsung dari folder data/sites
os.makedirs(sites.SITES_DIR, exist_ok=True)
app.mount("/api/v1/site-files", StaticFiles(directory=sites.SITES_DIR), name="site-files")

_listener_conn: asyncpg.Connection | None = None


def _on_position_notify(connection, pid, channel, payload: str) -> None:
    """Callback asyncpg LISTEN - dipanggil tiap ada INSERT baru ke table
    positions (lewat trigger pg_notify di init.sql). Forward langsung ke
    semua client SSE, jadi backend nggak perlu polling DB tiap detik."""
    data = json.loads(payload)
    asyncio.create_task(notifier.broadcast(json.dumps({"type": "position", "data": data})))
    asyncio.create_task(sos_watch.handle_position(data))  # tombol SOS pendaki -> alarm MANUAL_SOS (jalur apa pun)
    asyncio.create_task(off_trail_watch.handle_position(data))  # keluar perimeter -> peringatan OFF_TRAIL (amber)


@app.on_event("startup")
async def on_startup() -> None:
    global _listener_conn
    await database.connect_db()
    async with database.pool.acquire() as conn:
        has_timescale = await ensure_schema(conn)
        log.info("Skema siap (TimescaleDB: %s)", "aktif" if has_timescale else "tidak dipakai")
        # Proses DEM yang sedang jalan waktu backend mati tidak akan pernah selesai -> tandai error,
        # biar tidak "memproses" selamanya di UI.
        await conn.execute(
            "UPDATE sites SET status='error', message='Proses terputus karena backend restart. Upload ulang.' "
            "WHERE status='processing'"
        )

    _listener_conn = await asyncpg.connect(dsn=settings.database_url)
    await _listener_conn.add_listener("position_updates", _on_position_notify)

    app_settings.load_saved_into(settings, settings.data_dir)  # pilihan operator dari wizard, sebelum scheduler
    start_scheduler()
    await serial_ingest.start()  # no-op kalau SERIAL_PORT=off
    asyncio.create_task(sites.backfill_topo())  # peta topo offline utk lokasi yang dibuat sebelum fitur ini ada


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await serial_ingest.stop()
    if scheduler.running:
        scheduler.shutdown()
    if _listener_conn is not None:
        await _listener_conn.close()
    await database.disconnect_db()


_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
_WIZARD = os.path.join(_STATIC_DIR, "wizard.html")
_WIZARD_LOGO = os.path.join(_STATIC_DIR, "LOGO.png")


@app.get("/awal", include_in_schema=False)
@app.get("/pengaturan", include_in_schema=False)
async def wizard_page():
    """Halaman pengaturan awal (HTML mandiri, tidak butuh build frontend). Harus di atas catch-all SPA."""
    return FileResponse(_WIZARD, headers={"Cache-Control": "no-cache"})


@app.get("/awal-logo.png", include_in_schema=False)
async def wizard_logo():
    """Logo untuk halaman wizard. Disajikan dari backend/app/static supaya tetap tampil
    pada first run meski dashboard hasil build (FRONTEND_DIR) belum di-mount."""
    return FileResponse(_WIZARD_LOGO, headers={"Cache-Control": "no-cache"})


@app.get("/health")
async def health():
    return {"status": "ok"}


def _mount_frontend() -> None:
    """Sajikan dashboard hasil build (FRONTEND_DIR) langsung dari backend: tanpa nginx/Node.
    Harus dipanggil PALING AKHIR supaya catch-all tidak menimpa route API."""
    root = settings.frontend_dir
    if not root:
        return
    index = os.path.join(root, "index.html")
    if not os.path.isfile(index):
        log.warning("FRONTEND_DIR=%s tidak berisi index.html; dashboard tidak disajikan.", root)
        return
    # Windows: mimetypes membaca registri dan sering salah ('.js' -> text/plain) sehingga browser menolak
    # menjalankan module script (halaman kosong). Tetapkan eksplisit.
    for mime, ext in (("application/javascript", ".js"), ("application/javascript", ".mjs"),
                      ("text/css", ".css"), ("image/svg+xml", ".svg"), ("application/wasm", ".wasm")):
        mimetypes.add_type(mime, ext)
    assets = os.path.join(root, "assets")
    if os.path.isdir(assets):
        app.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")
    root_real = os.path.realpath(root)

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path == "api" or path.startswith("api/") or path.startswith("assets/"):
            raise HTTPException(404)  # aset yang hilang harus 404, jangan dijawab index.html (menyamarkan error)
        candidate = os.path.realpath(os.path.join(root_real, path))
        if path and candidate.startswith(root_real + os.sep) and os.path.isfile(candidate):  # cegah ../ keluar folder
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})  # SPA fallback


_mount_frontend()
