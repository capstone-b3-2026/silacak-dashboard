"""Konfigurasi perangkat LoRa (tracker / relay / base) + tombol "push ke hardware".

Alurnya sengaja lewat antrean (device_commands): dashboard TIDAK bicara serial
langsung (backend jalan di Docker, port COM ada di host). Dashboard menulis
perintah `pending`, bridge serial di host (reference-for-hardware-team) mengambilnya,
menulis ke alat, lalu melapor balik lewat POST /devices/commands/{id}/result.
"""
import json

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.database import get_db

router = APIRouter(prefix="/devices", tags=["devices"])

ROLES = ("tracker", "relay", "base")
# Nilai awal yang masuk akal; sesuaikan dengan apa yang benar-benar didukung firmware.
DEFAULT_CONFIG = {"report_interval_s": 30, "tx_power_dbm": 17, "sf": 9}


def _j(v):
    return json.loads(v) if isinstance(v, str) else v


class DeviceIn(BaseModel):
    node_id: int = Field(ge=1, le=254)
    name: str = Field(min_length=1, max_length=40)
    role: str = "tracker"
    config: dict = {}


def _out(r, last_cmd=None) -> dict:
    return {
        "id": r["id"], "node_id": r["node_id"], "name": r["name"], "role": r["role"],
        "hiker_code": f"H{r['node_id']:02d}" if r["role"] == "tracker" else None,
        "plan_slot": r["plan_slot"],
        "config": {**DEFAULT_CONFIG, **(_j(r["config"]) or {})},
        "config_version": r["config_version"], "pushed_version": r["pushed_version"],
        "in_sync": r["config_version"] == r["pushed_version"],
        "last_command": dict(last_cmd) if last_cmd else None,
    }


def _check(body: DeviceIn) -> None:
    if body.role not in ROLES:
        raise HTTPException(422, f"role harus salah satu dari {ROLES}")
    c = body.config
    if "report_interval_s" in c and not (5 <= int(c["report_interval_s"]) <= 3600):
        raise HTTPException(422, "report_interval_s harus 5..3600 detik")
    if "tx_power_dbm" in c and not (2 <= int(c["tx_power_dbm"]) <= 20):
        raise HTTPException(422, "tx_power_dbm harus 2..20")
    if "sf" in c and not (5 <= int(c["sf"]) <= 11):  # LLCC68 (E220-900T22D) tidak mendukung SF12
        raise HTTPException(422, "sf harus 5..11 (batas chip LLCC68)")


async def _list(conn):
    rows = await conn.fetch("SELECT * FROM devices ORDER BY node_id")
    cmds = await conn.fetch(
        """SELECT DISTINCT ON (device_id) id, device_id, status, error, created_at, updated_at
           FROM device_commands ORDER BY device_id, id DESC"""
    )
    by_dev = {c["device_id"]: {**dict(c), "created_at": c["created_at"].isoformat(),
                               "updated_at": c["updated_at"].isoformat()} for c in cmds}
    return [_out(r, by_dev.get(r["id"])) for r in rows]


@router.get("")
async def list_devices(conn=Depends(get_db)):
    return await _list(conn)


@router.post("")
async def create_device(body: DeviceIn, conn=Depends(get_db)):
    _check(body)
    if await conn.fetchval("SELECT 1 FROM devices WHERE node_id=$1", body.node_id):
        raise HTTPException(409, f"node_id {body.node_id} sudah terdaftar.")
    await conn.execute(
        "INSERT INTO devices (node_id, name, role, config) VALUES ($1,$2,$3,$4)",
        body.node_id, body.name.strip(), body.role, json.dumps(body.config),
    )
    return await _list(conn)


# ── untuk bridge serial (harus didaftarkan SEBELUM rute /{device_id}) ──
@router.get("/commands")
async def pending_commands(status: str = "pending", conn=Depends(get_db)):
    rows = await conn.fetch(
        "SELECT id, device_id, payload FROM device_commands WHERE status=$1 ORDER BY id", status
    )
    return [{"id": r["id"], "device_id": r["device_id"], "payload": _j(r["payload"])} for r in rows]


class CommandResult(BaseModel):
    status: str  # sent | acked | failed
    error: str | None = None


@router.post("/commands/{command_id}/result")
async def command_result(command_id: int, body: CommandResult, conn=Depends(get_db)):
    if body.status not in ("sent", "acked", "failed"):
        raise HTTPException(422, "status harus sent | acked | failed")
    row = await conn.fetchrow(
        "UPDATE device_commands SET status=$2, error=$3, updated_at=now() WHERE id=$1 RETURNING device_id, payload",
        command_id, body.status, body.error,
    )
    if not row:
        raise HTTPException(404, "Perintah tidak ditemukan.")
    # "acked" = alat mengonfirmasi. "sent" = bridge sudah menulis ke serial tapi alat belum
    # membalas; untuk firmware yang tidak punya ACK, bridge boleh langsung lapor "acked".
    if body.status == "acked":
        v = _j(row["payload"]).get("version", 0)
        await conn.execute(
            "UPDATE devices SET pushed_version = GREATEST(pushed_version, $2) WHERE id=$1",
            row["device_id"], v,
        )
    return {"ok": True}


@router.put("/{device_id}")
async def update_device(device_id: int, body: DeviceIn, conn=Depends(get_db)):
    _check(body)
    dup = await conn.fetchval("SELECT 1 FROM devices WHERE node_id=$1 AND id<>$2", body.node_id, device_id)
    if dup:
        raise HTTPException(409, f"node_id {body.node_id} sudah dipakai perangkat lain.")
    r = await conn.fetchrow(
        """UPDATE devices SET node_id=$2, name=$3, role=$4, config=$5, config_version=config_version+1,
                  plan_slot = CASE WHEN $4 = 'relay' THEN plan_slot ELSE NULL END
           WHERE id=$1 RETURNING id""",
        device_id, body.node_id, body.name.strip(), body.role, json.dumps(body.config),
    )
    if not r:
        raise HTTPException(404, "Perangkat tidak ditemukan.")
    return await _list(conn)


class PlanSlotIn(BaseModel):
    plan_slot: int | None = Field(default=None, ge=1, le=64)


@router.put("/{device_id}/plan-slot")
async def set_plan_slot(device_id: int, body: PlanSlotIn, conn=Depends(get_db)):
    """Petakan relay ke posisi R<n> pada rencana lokasi (null = lepas). Sengaja TIDAK lewat PUT /{id}: pemetaan ini
    data dashboard, tidak boleh menaikkan config_version (yang berarti 'belum disinkronkan ke alat')."""
    dev = await conn.fetchrow("SELECT id, role FROM devices WHERE id=$1", device_id)
    if not dev:
        raise HTTPException(404, "Perangkat tidak ditemukan.")
    if body.plan_slot is not None and dev["role"] != "relay":
        raise HTTPException(422, "Hanya perangkat berperan relay yang bisa dipetakan ke posisi relay.")
    try:
        await conn.execute("UPDATE devices SET plan_slot=$2 WHERE id=$1", device_id, body.plan_slot)
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, f"Posisi R{body.plan_slot} sudah dipakai relay lain.") from None
    return await _list(conn)


@router.delete("/{device_id}")
async def delete_device(device_id: int, conn=Depends(get_db)):
    await conn.execute("DELETE FROM devices WHERE id=$1", device_id)
    return await _list(conn)


@router.post("/{device_id}/push")
async def push_device(device_id: int, conn=Depends(get_db)):
    r = await conn.fetchrow("SELECT * FROM devices WHERE id=$1", device_id)
    if not r:
        raise HTTPException(404, "Perangkat tidak ditemukan.")
    # perintah lama yang belum terkirim untuk alat yang sama dibatalkan, biar nggak numpuk
    await conn.execute(
        "UPDATE device_commands SET status='failed', error='digantikan perintah baru', updated_at=now() "
        "WHERE device_id=$1 AND status='pending'", device_id,
    )
    payload = {
        "node_id": r["node_id"], "name": r["name"], "role": r["role"],
        "config": {**DEFAULT_CONFIG, **(_j(r["config"]) or {})}, "version": r["config_version"],
    }
    await conn.execute(
        "INSERT INTO device_commands (device_id, payload) VALUES ($1,$2)", device_id, json.dumps(payload)
    )
    return await _list(conn)