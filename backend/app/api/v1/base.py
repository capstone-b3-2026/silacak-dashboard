"""Status & pemilihan port base station (USB serial)."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.serial_ingest import serial_ingest

router = APIRouter(prefix="/base", tags=["base"])


class PortBody(BaseModel):
    port: str = Field(min_length=1, max_length=120, description="'auto' atau nama port, mis. COM5")


@router.get("/status")
async def base_status():
    return serial_ingest.status()


@router.get("/ports")
async def base_ports():
    return serial_ingest.ports()


@router.post("/port")
async def base_select_port(body: PortBody):
    if not serial_ingest.enabled:
        raise HTTPException(409, "Ingest serial dimatikan (SERIAL_PORT=off).")
    serial_ingest.set_port(body.port)
    return serial_ingest.status()
