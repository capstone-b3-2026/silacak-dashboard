import asyncio
import json
import os
import shutil
from datetime import datetime, timezone

import gpxpy.gpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.core import database
from app.core.database import get_db
from app.services import dem_ingest
from app.services.terrain_planner import evaluate_relay_chain, haversine_km, suggest_relay_chain

router = APIRouter(prefix="/sites", tags=["sites"])

DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
SITES_DIR = os.path.join(DATA_DIR, "sites")
DEFAULT_PARAMS = {
    "freq_mhz": 915.0, "antenna_h_m": 2.0, "max_hop_km": 2.0,
    "search_radius_km": 0.3, "search_step_km": 0.06, "max_relays": 10,
}


def _j(v):
    return json.loads(v) if isinstance(v, str) else v


def _row(r) -> dict:
    return {
        "id": r["id"], "name": r["name"], "status": r["status"], "message": r["message"],
        "is_active": r["is_active"], "dem_info": _j(r["dem_info"]), "base": _j(r["base"]),
        "trail": _j(r["trail"]) or [], "params": {**DEFAULT_PARAMS, **(_j(r["params"]) or {})},
        "plan": _j(r["plan"]), "created_at": r["created_at"].isoformat(),
        "tiles_url": f"/api/v1/site-files/{r['id']}/tiles/{{z}}/{{x}}/{{y}}.png",
        "topo_url": f"/api/v1/site-files/{r['id']}/topo/{{z}}/{{x}}/{{y}}.webp",
    }


async def _active(conn):
    r = await conn.fetchrow("SELECT * FROM sites WHERE is_active ORDER BY id DESC LIMIT 1")
    if r:
        return r
    # belum ada yang aktif -> tampilkan yang lagi diproses/error terakhir biar user lihat statusnya
    return await conn.fetchrow("SELECT * FROM sites ORDER BY id DESC LIMIT 1")


async def _with_pending(conn, r) -> dict:
    """Lokasi aktif + (kalau ada) upload DEM pengganti yang lagi diproses / gagal.
    DEM lama tetap aktif sampai yang baru SELESAI, jadi UI butuh info ini buat
    nampilin progres & pesan error - kalau nggak, upload pengganti kelihatan 'diam'."""
    out = _row(r)
    p = await conn.fetchrow(
        "SELECT id, name, status, message FROM sites WHERE id > $1 AND status IN ('processing','error') "
        "ORDER BY id DESC LIMIT 1", r["id"],
    )
    out["pending"] = dict(p) if p and r["status"] == "ready" else None
    return out


@router.get("/active")
async def get_active(conn=Depends(get_db)):
    r = await _active(conn)
    return await _with_pending(conn, r) if r else None


@router.delete("/pending")
async def dismiss_failed(conn=Depends(get_db)):
    """Tutup pesan error upload (hapus baris + berkas yang gagal). Yang masih diproses tidak disentuh."""
    rows = await conn.fetch("DELETE FROM sites WHERE status='error' AND NOT is_active RETURNING id")
    for x in rows:
        shutil.rmtree(os.path.join(SITES_DIR, str(x["id"])), ignore_errors=True)
    return {"removed": len(rows)}


# ── upload DEM: satu file, sisanya otomatis ───────────────────────────
@router.post("/dem")
async def upload_dem(name: str = Form("Lokasi baru"), file: UploadFile = File(...), conn=Depends(get_db)):
    if not (file.filename or "").lower().endswith((".tif", ".tiff")):
        raise HTTPException(400, "File harus GeoTIFF (.tif / .tiff).")
    prev = await conn.fetchrow("SELECT * FROM sites WHERE is_active ORDER BY id DESC LIMIT 1")
    # Titik base/trail & parameter dari lokasi sebelumnya diwariskan, jadi ganti DEM
    # nggak perlu input ulang.
    site_id = await conn.fetchval(
        "INSERT INTO sites (name, base, trail, params) VALUES ($1, $2, $3, $4) RETURNING id",
        name.strip() or "Lokasi baru",
        json.dumps(_j(prev["base"])) if prev and prev["base"] else None,
        json.dumps(_j(prev["trail"]) if prev else []),
        json.dumps(_j(prev["params"]) if prev else {}),
    )
    folder = os.path.join(SITES_DIR, str(site_id))
    os.makedirs(folder, exist_ok=True)
    raw = os.path.join(folder, "raw.tif")
    with open(raw, "wb") as f:  # streaming, jangan baca seluruh file ke memori
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)
    asyncio.create_task(_process(site_id))
    return {"id": site_id, "status": "processing"}


async def _set(site_id: int, **cols):
    sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(cols))
    vals = [json.dumps(v) if isinstance(v, (dict, list)) else v for v in cols.values()]
    async with database.pool.acquire() as c:
        await c.execute(f"UPDATE sites SET {sets} WHERE id = $1", site_id, *vals)


async def _process(site_id: int) -> None:
    folder = os.path.join(SITES_DIR, str(site_id))
    try:
        await _set(site_id, message="Membaca & menormalkan DEM…")
        info = await asyncio.to_thread(dem_ingest.normalize_dem, os.path.join(folder, "raw.tif"), os.path.join(folder, "dem.tif"))
        await _set(site_id, message="Membuat tile 3D…")
        tiles = await asyncio.to_thread(dem_ingest.build_tiles, os.path.join(folder, "dem.tif"), os.path.join(folder, "tiles"))
        info.update(tiles)
        await _set(site_id, message="Membuat peta topo offline…")
        info["topo"] = await asyncio.to_thread(
            dem_ingest.build_topo_tiles, os.path.join(folder, "dem.tif"), os.path.join(folder, "topo"),
            tiles["min_zoom"], tiles["max_zoom"] + 1,
        )
        async with database.pool.acquire() as c:
            async with c.transaction():
                await c.execute("UPDATE sites SET is_active = FALSE WHERE is_active")
                await c.execute(
                    "UPDATE sites SET status='ready', message=$2, is_active=TRUE, dem_info=$3 WHERE id=$1",
                    site_id, "; ".join(info["notes"]) or None, json.dumps(info),
                )
            row = await c.fetchrow("SELECT * FROM sites WHERE id=$1", site_id)
        os.remove(os.path.join(folder, "raw.tif"))
        # DEM baru sudah aktif; kalau base & trail sudah ada, langsung hitung ulang relay.
        if row["base"] and _j(row["trail"]):
            await _run_plan(site_id)
        await _cleanup_old(site_id)
    except Exception as e:  # noqa: BLE001 - apa pun yang gagal harus kelihatan di UI
        msg = str(e)
        if "not recognized" in msg or "RasterioIOError" in type(e).__name__:
            msg = "File bukan GeoTIFF yang valid atau rusak (ikut terunggah tidak lengkap?)."
        await _set(site_id, status="error", message=msg[:400])


async def _cleanup_old(keep_id: int) -> None:
    """Hapus berkas lokasi lama (DEM + tile) - baris DB-nya tetap buat riwayat."""
    async with database.pool.acquire() as c:
        olds = await c.fetch("SELECT id FROM sites WHERE id <> $1", keep_id)
    for o in olds:
        shutil.rmtree(os.path.join(SITES_DIR, str(o["id"])), ignore_errors=True)


# ── titik base & trail ────────────────────────────────────────────────
class Inputs(BaseModel):
    base: dict | None = None
    trail: list[list[float]] = []
    params: dict = {}


@router.put("/active/inputs")
async def save_inputs(body: Inputs, conn=Depends(get_db)):
    r = await _active(conn)
    if not r:
        raise HTTPException(404, "Belum ada lokasi. Upload DEM dulu.")
    await conn.execute(
        "UPDATE sites SET base=$2, trail=$3, params=$4, plan=NULL WHERE id=$1",
        r["id"], json.dumps(body.base) if body.base else None, json.dumps(body.trail),
        json.dumps({**DEFAULT_PARAMS, **body.params}),
    )
    # Posisi relay yang sudah digeser manual TIDAK dibuang saat base/trail/parameter berubah:
    # dinilai ulang di tempatnya. Untuk kembali ke rekomendasi otomatis: tombol "Hitung ulang".
    old_plan = _j(r["plan"])
    if old_plan and old_plan.get("manual") and body.base and body.trail and r["status"] == "ready":
        try:
            kept = await asyncio.to_thread(
                _evaluate_blocking, os.path.join(SITES_DIR, str(r["id"]), "dem.tif"), body.base, body.trail,
                {**DEFAULT_PARAMS, **body.params}, [[x["lat"], x["lon"]] for x in old_plan["relays"]])
            await _set(r["id"], plan=kept)
        except (ValueError, OSError):
            pass  # DEM/titik bermasalah -> plan kosong, UI akan menawarkan hitung ulang
    return await _with_pending(conn, await conn.fetchrow("SELECT * FROM sites WHERE id=$1", r["id"]))


# ── hitung relay ──────────────────────────────────────────────────────
def _plan_blocking(dem_path: str, base: dict, trail: list, params: dict) -> dict:
    src = dem_ingest.GridElevation(dem_path)
    b = (base["lat"], base["lon"])
    pts = [(p[0], p[1]) for p in trail]
    result = suggest_relay_chain(
        src, b, pts, max_hop_km=params["max_hop_km"], antenna_h_m=params["antenna_h_m"],
        freq_mhz=params["freq_mhz"], candidate_search_radius_km=params["search_radius_km"],
        candidate_grid_step_km=params["search_step_km"], max_relays=int(params["max_relays"]),
    )
    out, origin = [], b
    for i, r in enumerate(result.relays, 1):
        out.append({
            "n": i, "lat": r.lat, "lon": r.lon, "elev_m": round(src.elevation_at(r.lat, r.lon), 1),
            "hop_km": round(haversine_km(origin, (r.lat, r.lon)), 3),
            "covers_index": r.covers_trail_index, "margin_m": round(r.worst_margin_m, 1),
        })
        origin = (r.lat, r.lon)
    # Status cakupan datang dari planner (bukan ditebak dari daftar relay): daftar relay
    # kosong BISA berarti "base sudah cukup" ATAU "macet total", dan keduanya beda.
    message = None
    if not result.complete:
        k = result.stalled_at
        if result.stall_reason == "max_relays":
            why = f"batas {int(params['max_relays'])} relay tercapai sebelum trail habis"
        else:
            why = ("tidak ada posisi relay (dalam radius cari) yang tersambung ke node sebelumnya "
                   "sekaligus menjangkau titik ini — perbesar radius cari / hop maks, atau geser titik trail")
        message = f"Macet di titik trail #{k + 1} dari {len(pts)}: {why}."
    return {
        "relays": out, "covers_all": result.complete,
        "uncovered_points": result.uncovered_points,
        "covered_through": result.covered_through,
        "stalled_at": result.stalled_at, "stall_reason": result.stall_reason, "message": message,
        "base_elev_m": round(src.elevation_at(*b), 1),
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def _evaluate_blocking(dem_path: str, base: dict, trail: list, params: dict, relay_pts: list) -> dict:
    """Plan dari posisi relay MANUAL: sama bentuknya dengan hasil otomatis (+ manual=True, + link_ok per relay)."""
    src = dem_ingest.GridElevation(dem_path)
    b = (base["lat"], base["lon"])
    pts = [(p[0], p[1]) for p in trail]
    evals, covered = evaluate_relay_chain(
        src, b, [(p[0], p[1]) for p in relay_pts], pts, max_hop_km=params["max_hop_km"],
        antenna_h_m=params["antenna_h_m"], freq_mhz=params["freq_mhz"],
    )
    out = [{
        "n": i, "lat": e.lat, "lon": e.lon, "elev_m": round(src.elevation_at(e.lat, e.lon), 1),
        "hop_km": round(e.hop_km, 3), "covers_index": e.covers_trail_index,
        "margin_m": round(e.margin_m, 1), "link_ok": e.link_ok, "manual": True,
    } for i, e in enumerate(evals, 1)]
    n = len(pts)
    broken = next((x for x in out if not x["link_ok"]), None)
    message, reason = None, None
    if broken:
        reason = "link_putus"
        why = "terlalu jauh" if broken["hop_km"] > params["max_hop_km"] else "terhalang medan"
        message = (f"Link ke R{broken['n']} putus ({why}; hop {broken['hop_km']} km, margin {broken['margin_m']} m). "
                   "Geser relay lebih dekat/lebih tinggi, atau tekan Hitung ulang untuk kembali ke rekomendasi.")
    elif covered < n - 1:
        reason = "belum_terjangkau"
        message = f"Titik trail #{covered + 2} dari {n} belum terjangkau dari rantai relay ini."
    return {
        "relays": out, "covers_all": covered >= n - 1, "uncovered_points": n - 1 - covered,
        "covered_through": covered, "stalled_at": None if covered >= n - 1 else covered + 1,
        "stall_reason": reason, "message": message, "manual": True,
        "base_elev_m": round(src.elevation_at(*b), 1),
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


class RelayMove(BaseModel):
    relays: list[list[float]]  # [[lat, lon], ...] urut sama dengan R1, R2, ...


@router.put("/active/relays")
async def move_relays(body: RelayMove, conn=Depends(get_db)):
    """Simpan posisi relay yang digeser manual (Setup aktif), lalu nilai ulang tiap link dari DEM."""
    r = await _active(conn)
    if not r or r["status"] != "ready":
        raise HTTPException(409, "DEM belum siap.")
    base, trail = _j(r["base"]), _j(r["trail"])
    if not base or not trail:
        raise HTTPException(400, "Isi titik base dan trail dulu.")
    old = _j(r["plan"])
    if not old or len(old.get("relays", [])) != len(body.relays):
        raise HTTPException(409, "Jumlah relay berubah. Hitung ulang dulu.")
    params = {**DEFAULT_PARAMS, **(_j(r["params"]) or {})}
    try:
        plan = await asyncio.to_thread(
            _evaluate_blocking, os.path.join(SITES_DIR, str(r["id"]), "dem.tif"), base, trail, params, body.relays)
    except ValueError as e:
        raise HTTPException(422, f"Posisi relay di luar cakupan DEM: {e}")
    await _set(r["id"], plan=plan)
    return plan


async def _run_plan(site_id: int) -> dict:
    async with database.pool.acquire() as c:
        r = await c.fetchrow("SELECT * FROM sites WHERE id=$1", site_id)
    base, trail = _j(r["base"]), _j(r["trail"])
    if not base or len(trail) < 1:
        raise HTTPException(400, "Isi titik base dan minimal 1 titik trail dulu.")
    params = {**DEFAULT_PARAMS, **(_j(r["params"]) or {})}
    dem_path = os.path.join(SITES_DIR, str(site_id), "dem.tif")
    try:
        plan = await asyncio.to_thread(_plan_blocking, dem_path, base, trail, params)
    except ValueError as e:
        raise HTTPException(422, str(e))
    await _set(site_id, plan=plan)
    return plan


@router.post("/active/plan")
async def compute_plan(conn=Depends(get_db)):
    r = await _active(conn)
    if not r or r["status"] != "ready":
        raise HTTPException(409, "DEM belum siap.")
    return await _run_plan(r["id"])


@router.get("/active/plan.gpx")
async def plan_gpx(conn=Depends(get_db)):
    r = await _active(conn)
    plan = _j(r["plan"]) if r else None
    if not plan:
        raise HTTPException(404, "Belum ada hasil rencana relay.")
    g = gpxpy.gpx.GPX()
    base = _j(r["base"])
    g.waypoints.append(gpxpy.gpx.GPXWaypoint(base["lat"], base["lon"], name="BASE", comment="Base station"))
    for x in plan["relays"]:
        g.waypoints.append(gpxpy.gpx.GPXWaypoint(
            x["lat"], x["lon"], elevation=x["elev_m"], name=f"RELAY-{x['n']}",
            comment=f"hop {x['hop_km']} km, margin Fresnel {x['margin_m']} m"))
    return Response(g.to_xml(), media_type="application/gpx+xml",
                    headers={"Content-Disposition": 'attachment; filename="relay_plan.gpx"'})



async def backfill_topo() -> None:
    """Lokasi yang diproses sebelum fitur peta topo ada: bikin tile topo-nya sekali, di latar belakang,
    dari dem.tif yang sudah tersimpan (nggak perlu upload ulang)."""
    try:
        async with database.pool.acquire() as c:
            r = await c.fetchrow("SELECT id, dem_info FROM sites WHERE is_active AND status='ready' ORDER BY id DESC LIMIT 1")
        if not r:
            return
        info = _j(r["dem_info"]) or {}
        folder = os.path.join(SITES_DIR, str(r["id"]))
        dem = os.path.join(folder, "dem.tif")
        if info.get("topo") or not os.path.exists(dem):
            return
        info["topo"] = await asyncio.to_thread(
            dem_ingest.build_topo_tiles, dem, os.path.join(folder, "topo"), info["min_zoom"], info["max_zoom"] + 1
        )
        await _set(r["id"], dem_info=info)
    except Exception as e:  # noqa: BLE001 - jangan sampai backend gagal start gara-gara ini
        print(f"[backfill_topo] dilewati: {e}")