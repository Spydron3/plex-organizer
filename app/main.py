from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db import create_db_and_tables
from app.routers import browse, libraries, plans, settings

app = FastAPI(title="Plex Organizer")

app.include_router(libraries.router)
app.include_router(plans.router)
app.include_router(settings.router)
app.include_router(browse.router)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


@app.on_event("startup")
def on_startup():
    create_db_and_tables()
