from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db import get_session
from app.metadata.tvdb import TvdbClient
from app.settings import (
    get_preferred_languages,
    get_tvdb_api_key,
    get_tvdb_pin,
    set_preferred_languages,
    set_tvdb_api_key,
    set_tvdb_pin,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])

_language_cache: list[dict] | None = None


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


@router.get("/preferred-languages")
def read_preferred_languages(session: Session = Depends(get_session)):
    return {"languages": get_preferred_languages(session)}


@router.post("/preferred-languages")
def write_preferred_languages(payload: dict, session: Session = Depends(get_session)):
    values = [v.strip() for v in (payload.get("languages") or []) if isinstance(v, str) and v.strip()]
    set_preferred_languages(session, values)
    return {"languages": values}


@router.get("/languages")
def list_languages(session: Session = Depends(get_session)):
    global _language_cache
    if _language_cache is not None:
        return _language_cache

    tvdb_key = get_tvdb_api_key(session)
    if not tvdb_key:
        raise HTTPException(400, "No TheTVDB API key configured")

    client = TvdbClient(tvdb_key, get_tvdb_pin(session))
    try:
        languages = client.list_languages()
    finally:
        client.close()

    _language_cache = sorted(languages, key=lambda lang: lang["name"])
    return _language_cache
