"""Pengaturan operator (wizard awal & halaman /pengaturan)."""
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.core.scheduler import reschedule_stagnant
from app.services import app_settings

router = APIRouter(prefix="/app-config", tags=["app-config"])


class ConfigBody(BaseModel):
    mode: Literal["default", "custom"]
    values: dict[str, Any] = {}


@router.get("")
async def read_config():
    return app_settings.get_state(settings, settings.data_dir)


@router.put("")
async def write_config(body: ConfigBody):
    try:
        state = app_settings.put_state(settings, settings.data_dir, body.mode, body.values)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(500, f"Gagal menyimpan pengaturan: {exc}") from exc
    reschedule_stagnant(settings.stagnant_check_interval_minutes)  # interval baru langsung berlaku
    return state
