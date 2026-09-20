from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.db import get_session
from app.models import LibraryPath, LibraryPathCreate

router = APIRouter(prefix="/api/libraries", tags=["libraries"])


@router.get("", response_model=list[LibraryPath])
def list_libraries(session: Session = Depends(get_session)):
    return session.exec(select(LibraryPath)).all()


@router.post("", response_model=LibraryPath)
def add_library(payload: LibraryPathCreate, session: Session = Depends(get_session)):
    path = Path(payload.path).expanduser()
    if not path.is_absolute():
        raise HTTPException(400, "Path must be absolute")
    if not path.exists() or not path.is_dir():
        raise HTTPException(400, f"Path does not exist or is not a directory: {path}")

    existing = session.exec(
        select(LibraryPath).where(LibraryPath.path == str(path))
    ).first()
    if existing:
        raise HTTPException(400, "This path is already registered")

    library = LibraryPath(path=str(path), type=payload.type)
    session.add(library)
    session.commit()
    session.refresh(library)
    return library


@router.delete("/{library_id}")
def remove_library(library_id: int, session: Session = Depends(get_session)):
    library = session.get(LibraryPath, library_id)
    if not library:
        raise HTTPException(404, "Library not found")
    session.delete(library)
    session.commit()
    return {"ok": True}
