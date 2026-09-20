from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db import get_session
from app.settings import get_tvdb_api_key, get_tvdb_pin, set_tvdb_api_key, set_tvdb_pin

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/tvdb-key")
def read_tvdb_key(session: Session = Depends(get_session)):
    key = get_tvdb_api_key(session)
    return {"configured": bool(key)}


@router.post("/tvdb-key")
def write_tvdb_key(payload: dict, session: Session = Depends(get_session)):
    value = (payload.get("value") or "").strip()
    set_tvdb_api_key(session, value)
    return {"configured": bool(value)}


@router.post("/tvdb-pin")
def write_tvdb_pin(payload: dict, session: Session = Depends(get_session)):
    value = (payload.get("value") or "").strip()
    set_tvdb_pin(session, value)
    return {"configured": bool(value)}
