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
from app.services import dem_ingest, link_calibration
from app.services.terrain_planner import (
    LinkParams, evaluate_relay_chain, haversine_km, make_link_params, predict_links,
    suggest_relay_chain, trail_profile_3d,
)

router = APIRouter(prefix="/sites", tags=["sites"])

DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
SITES_DIR = os.path.join(DATA_DIR, "sites")
DEFAULT_PARAMS = {
    # freq_mhz: pita legal Indonesia 920–923 MHz (AS923, Permenkominfo 1/2019; C-251 §b/§c/§d).
    # 922 = default patuh (915 = pita AS, non-patuh). Ini parameter MODEL planner (FSPL/Fresnel),
    # BUKAN nilai yang dikirim ke alat; firmware memakai LORA_CHANNEL 70 (MHz aktual dicetak saat boot).
    "freq_mhz": 922.0, "antenna_h_m": 2.0, "max_hop_km": 2.0,
    "search_radius_km": 0.3, "search_step_km": 0.06, "max_relays": 10,
    "relay_h_m": 2.0,  # tinggi antena relay & base (antena pendaki = antenna_h_m)
    "max_loss_db": 6.0,  # redaman difraksi maks yang masih dianggap link layak (lihat terrain_planner.py)
    "dem_error_m": 1.0,  # medan dianggap segini lebih tinggi (cadangan galat DEM); 0 = percaya DEM apa adanya
    # ── anggaran daya tautan (default = C-251 Tabel 10.2: rencana, BUKAN hasil ukur) ──
    "tx_dbm": 21.0, "gain_hiker_dbi": 5.0, "gain_relay_dbi": 5.0,
    "sensitivity_dbm": -137.0,  # SF9 menurut C-251; verifikasi ke datasheet & lapangan
    "fade_margin_db": 10.0,  # margin fading yang disyaratkan di atas sensitivitas
    "calib_offset_db": 0.0,  # redaman tambahan hasil kalibrasi RSSI lapangan (+ = lebih lemah dari model)
    "veg_scale": 1.0,  # pengali redaman vegetasi (0 = abaikan; < 1 bila DEM sudah memuat kanopi)
}
_NONNEG = {"dem_error_m", "veg_scale", "fade_margin_db"}  # boleh 0
_ANY_SIGN = {"tx_dbm", "gain_hiker_dbi", "gain_relay_dbi", "sensitivity_dbm", "calib_offset_db"}  # boleh negatif/0


def _j(v):
    return json.loads(v) if isinstance(v, str) else v


def _merge_params(extra) -> dict:
    """DEFAULT_PARAMS + nilai tersimpan/dikirim UI. Nilai yang bukan angka positif (kolom dikosongkan
    di form -> "" / null) diganti default-nya, supaya planner tidak meledak."""
    out = dict(DEFAULT_PARAMS)
    for k, v in (_j(extra) or {}).items():
        if k in DEFAULT_PARAMS:
            num = isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")
            ok = num and (k in _ANY_SIGN or v > 0 or (v == 0 and k in _NONNEG))
            out[k] = v if ok else DEFAULT_PARAMS[k]
        else:
            out[k] = v
    return out


def _planner_kw(params: dict) -> dict:
    """Parameter model tautan -> argumen kata kunci planner (satu tempat, dipakai plan, evaluasi, kalibrasi)."""
    keys = ("relay_h_m", "max_loss_db", "dem_error_m", "tx_dbm", "gain_hiker_dbi", "gain_relay_dbi",
            "sensitivity_dbm", "fade_margin_db", "calib_offset_db", "veg_scale")
    return {k: params[k] for k in keys}


def _canopy_info(site_id: int) -> dict | None:
    """Info kanopi yang diunggah untuk lokasi ini (sidecar JSON), atau None."""
    p = os.path.join(SITES_DIR, str(site_id), "canopy.json")
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _row(r) -> dict:
    return {
        "id": r["id"], "name": r["name"], "status": r["status"], "message": r["message"],
        "is_active": r["is_active"], "dem_info": _j(r["dem_info"]), "base": _j(r["base"]),
        "trail": _j(r["trail"]) or [], "params": _merge_params(r["params"]),
        "plan": _j(r["plan"]), "created_at": r["created_at"].isoformat(), "canopy": _canopy_info(r["id"]),
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
        json.dumps(_merge_params(body.params)),
    )
    # Posisi relay yang sudah digeser manual TIDAK dibuang saat base/trail/parameter berubah:
    # dinilai ulang di tempatnya. Untuk kembali ke rekomendasi otomatis: tombol "Hitung ulang".
    old_plan = _j(r["plan"])
    if old_plan and old_plan.get("manual") and body.base and body.trail and r["status"] == "ready":
        try:
            kept = await asyncio.to_thread(
                _evaluate_blocking, os.path.join(SITES_DIR, str(r["id"]), "dem.tif"), body.base, body.trail,
                _merge_params(body.params), [[x["lat"], x["lon"]] for x in old_plan["relays"]])
            await _set(r["id"], plan=kept)
        except (ValueError, OSError):
            pass  # DEM/titik bermasalah -> plan kosong, UI akan menawarkan hitung ulang
    return await _with_pending(conn, await conn.fetchrow("SELECT * FROM sites WHERE id=$1", r["id"]))


# ── hitung relay ──────────────────────────────────────────────────────
def _plan_blocking(dem_path: str, base: dict, trail: list, params: dict) -> dict:
    src = dem_ingest.GridElevation(dem_path)
    clutter = dem_ingest.load_clutter(os.path.dirname(dem_path))  # None = tanpa data vegetasi
    b = (base["lat"], base["lon"])
    pts = [(p[0], p[1]) for p in trail]
    result = suggest_relay_chain(
        src, b, pts, max_hop_km=params["max_hop_km"], antenna_h_m=params["antenna_h_m"],
        freq_mhz=params["freq_mhz"], candidate_search_radius_km=params["search_radius_km"],
        candidate_grid_step_km=params["search_step_km"], max_relays=int(params["max_relays"]),
        clutter=clutter, **_planner_kw(params),
    )
    out = []
    for i, r in enumerate(result.relays, 1):
        out.append({
            "n": i, "lat": r.lat, "lon": r.lon, "elev_m": round(src.elevation_at(r.lat, r.lon), 1),
            "parent": r.parent, "hop_km": round(r.hop_km, 3), "loss_db": round(r.loss_db, 1),
            "veg_db": round(r.veg_db, 1), "rssi_dbm": round(r.rssi_dbm, 1), "fade_margin_db": round(r.fade_margin_db, 1),
            "covers_index": r.covers_trail_index, "margin_m": round(r.worst_margin_m, 1),
            "cover_loss_db": round(r.cover_loss_db, 1), "cover_fade_db": round(r.cover_fade_db, 1),
            "access_km": round(r.access_km, 3), "slope_deg": round(r.slope_deg, 1),
        })
    # Status cakupan datang dari planner (bukan ditebak dari daftar relay): daftar relay
    # kosong BISA berarti "base sudah cukup" ATAU "macet total", dan keduanya beda.
    message = None
    if not result.complete:
        k = result.stalled_at
        if result.stall_reason == "max_relays":
            why = f"batas {int(params['max_relays'])} relay tercapai sebelum trail habis"
        else:
            why = ("tidak ada posisi relay (dalam radius cari dan lereng yang bisa dipasangi) yang tersambung "
                   "ke node sebelumnya sekaligus menjangkau jalur di sini — perbesar radius cari / hop maks / "
                   "redaman medan maks, kurangi margin fading, naikkan tinggi antena relay, atau geser titik trail")
        message = (f"Macet sebelum titik trail #{k + 1} dari {len(pts)} "
                   f"(jalur tercover {result.covered_km:.2f} dari {result.trail_km:.2f} km): {why}.")
    return {
        "relays": out, "covers_all": result.complete,
        "uncovered_points": result.uncovered_points,
        "covered_through": result.covered_through,
        "stalled_at": result.stalled_at, "stall_reason": result.stall_reason, "message": message,
        "base_elev_m": round(src.elevation_at(*b), 1),
        "algorithm": "optimal-v3",
        "uses_clutter": result.uses_clutter,
        "clutter_cover_pct": None if result.clutter_coverage_pct is None else round(result.clutter_coverage_pct, 1),
        "trail_km": round(result.trail_km, 3), "covered_km": round(result.covered_km, 3),
        "coverage_pct": None if result.coverage_pct is None else round(result.coverage_pct, 1),
        "n_candidates": result.n_candidates,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def _evaluate_blocking(dem_path: str, base: dict, trail: list, params: dict, relay_pts: list) -> dict:
    """Plan dari posisi relay MANUAL: sama bentuknya dengan hasil otomatis (+ manual=True, + link_ok per relay)."""
    src = dem_ingest.GridElevation(dem_path)
    clutter = dem_ingest.load_clutter(os.path.dirname(dem_path))
    b = (base["lat"], base["lon"])
    pts = [(p[0], p[1]) for p in trail]
    evals, covered = evaluate_relay_chain(
        src, b, [(p[0], p[1]) for p in relay_pts], pts, max_hop_km=params["max_hop_km"],
        antenna_h_m=params["antenna_h_m"], freq_mhz=params["freq_mhz"],
        clutter=clutter, **_planner_kw(params),
    )
    out = [{
        "n": i, "lat": e.lat, "lon": e.lon, "elev_m": round(src.elevation_at(e.lat, e.lon), 1),
        "parent": e.parent, "hop_km": round(e.hop_km, 3), "loss_db": round(e.loss_db, 1),
        "veg_db": round(e.veg_db, 1), "rssi_dbm": round(e.rssi_dbm, 1), "fade_margin_db": round(e.fade_margin_db, 1),
        "covers_index": e.covers_trail_index, "margin_m": round(e.margin_m, 1),
        "link_ok": e.link_ok, "manual": True,
    } for i, e in enumerate(evals, 1)]
    n = len(pts)
    broken = next((x for x in out if not x["link_ok"]), None)
    message, reason = None, None
    if broken:
        reason = "link_putus"
        if broken["hop_km"] > params["max_hop_km"]:
            why = "terlalu jauh"
        elif broken["loss_db"] > params["max_loss_db"]:
            why = "terhalang medan"
        else:
            why = "sinyal terlalu lemah (anggaran daya/vegetasi)"
        message = (f"Link ke R{broken['n']} putus ({why}; hop {broken['hop_km']} km, redaman medan {broken['loss_db']} dB, "
                   f"vegetasi {broken['veg_db']} dB, margin fading {broken['fade_margin_db']} dB, "
                   f"butuh {params['fade_margin_db']} dB). "
                   "Geser relay lebih dekat/lebih tinggi, atau tekan Hitung ulang untuk kembali ke rekomendasi.")
    elif covered < n - 1:
        reason = "belum_terjangkau"
        message = f"Titik trail #{covered + 2} dari {n} belum terjangkau dari rantai relay ini."
    return {
        "relays": out, "covers_all": covered >= n - 1, "uncovered_points": n - 1 - covered,
        "covered_through": covered, "stalled_at": None if covered >= n - 1 else covered + 1,
        "stall_reason": reason, "message": message, "manual": True,
        "base_elev_m": round(src.elevation_at(*b), 1), "algorithm": "optimal-v3",
        "uses_clutter": clutter is not None,
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
    params = _merge_params(r["params"])
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
    params = _merge_params(r["params"])
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


# ── jarak trail 3D (profil dari DEM): sekunder, horizontal tetap dihitung di frontend ──
def _trail_distance_blocking(dem_path: str, base: dict, trail: list) -> dict:
    """Panggil fungsi murni trail_profile_3d dengan DEM sungguhan. Segmen di luar DEM -> 3D None
    (tanpa menggagalkan respons); angka dibulatkan untuk UI."""
    src = dem_ingest.GridElevation(dem_path)
    res = trail_profile_3d(src, base, trail)
    return {
        "total_horizontal_m": round(res["total_horizontal_m"], 1),
        "total_3d_m": None if res["total_3d_m"] is None else round(res["total_3d_m"], 1),
        "incomplete": res["incomplete"],
        "segments": [
            {"from": s["from"], "to": s["to"], "horizontal_m": round(s["horizontal_m"], 1),
             "dist_3d_m": None if s["dist_3d_m"] is None else round(s["dist_3d_m"], 1)}
            for s in res["segments"]
        ],
    }


class TrailDistanceBody(BaseModel):
    base: dict | None = None
    trail: list[list[float]] = []


@router.post("/active/trail-distance")
async def trail_distance(body: TrailDistanceBody, conn=Depends(get_db)):
    """Jarak 3D (profil penuh dari DEM) sepanjang base -> trail. BONUS/sekunder: angka horizontal
    headline dihitung instan di frontend; ini hanya menambah profil 3D saat DEM sudah siap."""
    r = await _active(conn)
    if not r:
        raise HTTPException(404, "Belum ada lokasi. Upload DEM dulu.")
    if r["status"] != "ready":
        raise HTTPException(409, "DEM belum siap.")
    if not body.base or len(body.trail) < 2:
        raise HTTPException(400, "Isi titik base dan minimal 2 titik trail dulu.")
    dem_path = os.path.join(SITES_DIR, str(r["id"]), "dem.tif")
    return await asyncio.to_thread(_trail_distance_blocking, dem_path, body.base, body.trail)


# ── data vegetasi (opsional): raster tinggi kanopi ──────────────────────────
def _overlap_pct(a: list, b: list) -> float:
    """Persen luas kotak a=[w,s,e,n] yang tertutup kotak b."""
    w, s, e, n = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    if e <= w or n <= s:
        return 0.0
    return 100.0 * (e - w) * (n - s) / ((a[2] - a[0]) * (a[3] - a[1]))


@router.post("/active/canopy")
async def upload_canopy(file: UploadFile = File(...), conn=Depends(get_db)):
    """Unggah raster TINGGI KANOPI (GeoTIFF, meter) untuk lokasi aktif. Dipakai perencana untuk
    menghitung redaman vegetasi. Tanpa berkas ini, vegetasi dianggap tidak ada (hasil optimistis)."""
    r = await _active(conn)
    if not r or r["status"] != "ready":
        raise HTTPException(409, "DEM belum siap.")
    if not (file.filename or "").lower().endswith((".tif", ".tiff")):
        raise HTTPException(400, "File harus GeoTIFF (.tif / .tiff).")
    folder = os.path.join(SITES_DIR, str(r["id"]))
    raw = os.path.join(folder, "canopy_raw.tif")
    with open(raw, "wb") as f:  # streaming
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)
    try:
        info = await asyncio.to_thread(dem_ingest.normalize_canopy, raw, os.path.join(folder, "canopy.tif"))
        info["dem_overlap_pct"] = round(_overlap_pct(_j(r["dem_info"])["bounds"], info["bounds"]), 1)
        if info["dem_overlap_pct"] < 5:
            os.remove(os.path.join(folder, "canopy.tif"))
            raise HTTPException(422, "Raster kanopi tidak menutup area DEM (tumpang tindih < 5%). Cek lokasi/CRS-nya.")
        info["filename"] = file.filename
        info["uploaded_at"] = datetime.now(timezone.utc).isoformat()
        with open(os.path.join(folder, "canopy.json"), "w", encoding="utf-8") as f:
            json.dump(info, f)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except HTTPException:
        raise
    except Exception as e:  # berkas rusak / bukan raster
        raise HTTPException(422, "Gagal membaca raster kanopi (berkas rusak atau bukan GeoTIFF yang valid).")
    finally:
        try:
            os.remove(raw)
        except OSError:
            pass
    return info


@router.delete("/active/canopy")
async def delete_canopy(conn=Depends(get_db)):
    r = await _active(conn)
    if not r:
        raise HTTPException(404, "Belum ada lokasi.")
    for name in ("canopy.tif", "canopy.json"):
        try:
            os.remove(os.path.join(SITES_DIR, str(r["id"]), name))
        except OSError:
            pass
    return {"ok": True}


# ── kalibrasi model tautan dari RSSI lapangan ───────────────────────────────
def _calibrate_blocking(dem_path: str, base: dict, params: dict, rows: list, max_km: float | None) -> dict:
    src = dem_ingest.GridElevation(dem_path)
    clutter = dem_ingest.load_clutter(os.path.dirname(dem_path))
    p = make_link_params(max_hop_km=params["max_hop_km"], antenna_h_m=params["antenna_h_m"],
                         freq_mhz=params["freq_mhz"], **_planner_kw(params))
    pts = [(x["lat"], x["lon"]) for x in rows]
    pred = predict_links(src, clutter, p, (base["lat"], base["lon"]), pts)
    meas = [x["rssi_dbm"] for x in rows]
    keep = [i for i in range(len(rows)) if (max_km is None or pred["dist_km"][i] <= max_km)]
    n_outside = sum(1 for i in range(len(rows)) if pred["rssi_dbm"][i] != pred["rssi_dbm"][i])
    res = link_calibration.calibrate(
        [meas[i] for i in keep], [pred["rssi_dbm"][i] for i in keep], [pred["dist_km"][i] for i in keep],
        current_offset_db=params["calib_offset_db"])
    step = max(1, len(keep) // 200)  # titik untuk grafik (maks ~200)
    res["points"] = [{"dist_km": round(float(pred["dist_km"][i]), 3), "measured_dbm": meas[i],
                      "predicted_dbm": round(float(pred["rssi_dbm"][i]), 1)}
                     for i in keep[::step] if pred["rssi_dbm"][i] == pred["rssi_dbm"][i]]
    res.update({"n_outside_dem": n_outside, "uses_clutter": clutter is not None,
                "current_fade_margin_db": params["fade_margin_db"], "current_sensitivity_dbm": params["sensitivity_dbm"]})
    return res


@router.get("/active/calibration")
async def calibration(session_id: int | None = None, hours: int = 72, max_km: float | None = None, conn=Depends(get_db)):
    """Bandingkan RSSI TERUKUR (paket langsung 0 hop, GPS valid) dengan RSSI PREDIKSI model pada posisi
    yang sama, lalu sarankan `calib_offset_db` dan `fade_margin_db`. Pakai data lapangan, JANGAN data sintetis."""
    r = await _active(conn)
    if not r or r["status"] != "ready":
        raise HTTPException(409, "DEM belum siap.")
    base = _j(r["base"])
    if not base:
        raise HTTPException(400, "Titik base belum diset.")
    rows = await conn.fetch(
        """
        SELECT (p.location)[1] AS lat, (p.location)[0] AS lon, p.rssi_dbm
        FROM positions p
        WHERE p.hop_count = 0 AND p.rssi_dbm IS NOT NULL AND p.location IS NOT NULL
          AND COALESCE(p.gps_valid, TRUE)
          AND p.received_at >= now() - make_interval(hours => $1)
          AND ($2::int IS NULL OR p.session_id = $2)
        ORDER BY p.received_at DESC LIMIT 5000
        """,
        max(1, min(int(hours), 24 * 60)), session_id,
    )
    params = _merge_params(r["params"])
    dem_path = os.path.join(SITES_DIR, str(r["id"]), "dem.tif")
    res = await asyncio.to_thread(_calibrate_blocking, dem_path, base, params, [dict(x) for x in rows], max_km)
    res.update({"window_hours": hours, "session_id": session_id, "max_km": max_km})
    return res


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
            comment=f"hop {x['hop_km']} km, redaman {x.get('loss_db', '?')} dB, margin fading {x.get('fade_margin_db', '?')} dB"))
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