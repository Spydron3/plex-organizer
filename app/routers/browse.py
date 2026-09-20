import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/browse", tags=["browse"])


@router.get("")
def browse(path: str | None = None):
    target = Path(path).expanduser() if path else Path.home()
    if not target.is_absolute():
        raise HTTPException(400, "Path must be absolute")
    if not target.exists() or not target.is_dir():
        target = Path.home() if Path.home().exists() else Path("/")

    target = target.resolve()

    dirs = []
    try:
        for entry in sorted(target.iterdir(), key=lambda p: p.name.lower()):
            if entry.name.startswith("."):
                continue
            try:
                if entry.is_dir():
                    dirs.append(entry.name)
            except OSError:
                continue
    except PermissionError:
        raise HTTPException(403, f"Permission denied: {target}")

    parent = str(target.parent) if target != target.parent else None
    return {"path": str(target), "parent": parent, "dirs": dirs}
