import os
from pathlib import Path

from sqlalchemy import text
from sqlmodel import SQLModel, Session, create_engine

_override = os.environ.get("PLEX_ORGANIZER_DB")
if _override:
    DB_PATH = Path(_override)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
else:
    DATA_DIR = Path(__file__).resolve().parent.parent / "data"
    DATA_DIR.mkdir(exist_ok=True)
    DB_PATH = DATA_DIR / "plex_organizer.db"

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

# Minimal ad-hoc migration: add columns introduced after the table already
# existed on disk. SQLModel.metadata.create_all only creates missing tables.
_COLUMN_MIGRATIONS = {
    "planitem": {"candidates": "TEXT", "search_query": "TEXT", "language": "TEXT"},
}


def _run_migrations() -> None:
    with engine.connect() as conn:
        for table, columns in _COLUMN_MIGRATIONS.items():
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            for column, col_type in columns.items():
                if column not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
        conn.commit()


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)
    _run_migrations()


def get_session():
    with Session(engine) as session:
        yield session
