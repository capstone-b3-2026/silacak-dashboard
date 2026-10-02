from pydantic import BaseModel


class HikerCreate(BaseModel):
    hiker_code: str
    full_name: str | None = None
    phone_number: str | None = None


class HikerOut(BaseModel):
    id: int
    hiker_code: str
    full_name: str | None = None
    phone_number: str | None = None
