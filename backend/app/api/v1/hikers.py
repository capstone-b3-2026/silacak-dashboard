from fastapi import APIRouter, Depends

from app.core.database import get_db
from app.repositories import hiker_repo
from app.schemas.hiker import HikerCreate, HikerOut

router = APIRouter(prefix="/hikers", tags=["hikers"])


@router.get("", response_model=list[HikerOut])
async def list_hikers(conn=Depends(get_db)):
    return await hiker_repo.get_all_hikers(conn)


@router.post("", response_model=HikerOut)
async def register_hiker(payload: HikerCreate, conn=Depends(get_db)):
    return await hiker_repo.create_hiker(
        conn, payload.hiker_code, payload.full_name, payload.phone_number
    )
