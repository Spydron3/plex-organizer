import json
import os

from dotenv import load_dotenv
from sqlmodel import Session

from app.models import AppSetting

load_dotenv()

TVDB_API_KEY_SETTING = "tvdb_api_key"
TVDB_PIN_SETTING = "tvdb_pin"
PREFERRED_LANGUAGES_SETTING = "preferred_languages"


def _get_setting(session: Session, key: str, env_fallback: str | None = None) -> str | None:
    row = session.get(AppSetting, key)
    if row and row.value:
        return row.value
    return os.environ.get(env_fallback) if env_fallback else None


def _set_setting(session: Session, key: str, value: str) -> None:
    row = session.get(AppSetting, key)
    if row:
        row.value = value
    else:
        row = AppSetting(key=key, value=value)
    session.add(row)
    session.commit()


def get_tvdb_api_key(session: Session) -> str | None:
    return _get_setting(session, TVDB_API_KEY_SETTING, "TVDB_API_KEY")


def set_tvdb_api_key(session: Session, value: str) -> None:
    _set_setting(session, TVDB_API_KEY_SETTING, value)


def get_tvdb_pin(session: Session) -> str | None:
    return _get_setting(session, TVDB_PIN_SETTING, "TVDB_PIN")


def set_tvdb_pin(session: Session, value: str) -> None:
    _set_setting(session, TVDB_PIN_SETTING, value)


def get_preferred_languages(session: Session) -> list[str]:
    raw = _get_setting(session, PREFERRED_LANGUAGES_SETTING)
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


def set_preferred_languages(session: Session, values: list[str]) -> None:
    _set_setting(session, PREFERRED_LANGUAGES_SETTING, json.dumps(values))
