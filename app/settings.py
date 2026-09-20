import os

from dotenv import load_dotenv
from sqlmodel import Session, select

from app.models import AppSetting

load_dotenv()

TMDB_API_KEY_SETTING = "tmdb_api_key"


def get_tmdb_api_key(session: Session) -> str | None:
    row = session.get(AppSetting, TMDB_API_KEY_SETTING)
    if row and row.value:
        return row.value
    return os.environ.get("TMDB_API_KEY") or None


def set_tmdb_api_key(session: Session, value: str) -> None:
    row = session.get(AppSetting, TMDB_API_KEY_SETTING)
    if row:
        row.value = value
    else:
        row = AppSetting(key=TMDB_API_KEY_SETTING, value=value)
    session.add(row)
    session.commit()
