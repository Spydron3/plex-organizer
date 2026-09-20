from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db import get_session
from app.settings import get_tmdb_api_key, set_tmdb_api_key

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/tmdb-key")
def read_tmdb_key(session: Session = Depends(get_session)):
    key = get_tmdb_api_key(session)
    return {"configured": bool(key)}


@router.post("/tmdb-key")
def write_tmdb_key(payload: dict, session: Session = Depends(get_session)):
    value = (payload.get("value") or "").strip()
    set_tmdb_api_key(session, value)
    return {"configured": bool(value)}
