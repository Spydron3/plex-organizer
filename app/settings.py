import os

from dotenv import load_dotenv
from sqlmodel import Session, select

from app.models import AppSetting

load_dotenv()

TVDB_API_KEY_SETTING = "tvdb_api_key"
TVDB_PIN_SETTING = "tvdb_pin"


def get_tvdb_api_key(session: Session) -> str | None:
    row = session.get(AppSetting, TVDB_API_KEY_SETTING)
    if row and row.value:
        return row.value
    return os.environ.get("TVDB_API_KEY") or None


def set_tvdb_api_key(session: Session, value: str) -> None:
    row = session.get(AppSetting, TVDB_API_KEY_SETTING)
    if row:
        row.value = value
    else:
        row = AppSetting(key=TVDB_API_KEY_SETTING, value=value)
    session.add(row)
    session.commit()


def get_tvdb_pin(session: Session) -> str | None:
    row = session.get(AppSetting, TVDB_PIN_SETTING)
    if row and row.value:
        return row.value
    return os.environ.get("TVDB_PIN") or None


def set_tvdb_pin(session: Session, value: str) -> None:
    row = session.get(AppSetting, TVDB_PIN_SETTING)
    if row:
        row.value = value
    else:
        row = AppSetting(key=TVDB_PIN_SETTING, value=value)
    session.add(row)
    session.commit()
