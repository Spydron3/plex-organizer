from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.db import get_session
from app.executor import execute_move
from app.metadata.musicbrainz import MusicBrainzClient
from app.metadata.tvdb import TvdbClient
from app.models import ItemStatus, LibraryPath, MediaType, PlanItem, PlanItemUpdate, PlanStatus, ScanPlan
from app.scanner import scan_movie_library, scan_music_library, scan_tv_library
from app.settings import get_tvdb_api_key, get_tvdb_pin

router = APIRouter(prefix="/api", tags=["plans"])


@router.post("/libraries/{library_id}/scan", response_model=ScanPlan)
def scan_library(library_id: int, session: Session = Depends(get_session)):
    library = session.get(LibraryPath, library_id)
    if not library:
        raise HTTPException(404, "Library not found")

    root = Path(library.path)
    if not root.exists():
        raise HTTPException(400, f"Library path no longer exists: {root}")

    tvdb_key = get_tvdb_api_key(session)
    tvdb_pin = get_tvdb_pin(session)

    if library.type == MediaType.movie:
        tvdb = TvdbClient(tvdb_key, tvdb_pin) if tvdb_key else None
        try:
            results = scan_movie_library(root, tvdb)
        finally:
            if tvdb:
                tvdb.close()
    elif library.type == MediaType.tv:
        tvdb = TvdbClient(tvdb_key, tvdb_pin) if tvdb_key else None
        try:
            results = scan_tv_library(root, tvdb)
        finally:
            if tvdb:
                tvdb.close()
    else:
        mb = MusicBrainzClient()
        try:
            results = scan_music_library(root, mb)
        finally:
            mb.close()

    plan = ScanPlan(library_id=library.id, status=PlanStatus.pending)
    session.add(plan)
    session.commit()
    session.refresh(plan)

    up_to_date = 0
    for r in results:
        if r.target_relpath is not None:
            candidate_abs = str((root / r.target_relpath).resolve())
            if candidate_abs == str(Path(r.source_path).resolve()):
                up_to_date += 1
                continue
        item = PlanItem(
            plan_id=plan.id,
            source_path=r.source_path,
            target_path=r.target_relpath or "",
            media_type=r.media_type,
            title=r.title,
            year=r.year,
            season=r.season,
            episode=r.episode,
            artist=r.artist,
            album=r.album,
            track=r.track,
            matched=r.matched,
            status=r.status,
            error_message=r.error_message,
        )
        session.add(item)

    plan.skipped_up_to_date = up_to_date
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return plan


@router.get("/plans", response_model=list[ScanPlan])
def list_plans(session: Session = Depends(get_session)):
    return session.exec(select(ScanPlan).order_by(ScanPlan.id.desc())).all()


@router.get("/plans/{plan_id}")
def get_plan(plan_id: int, session: Session = Depends(get_session)):
    plan = session.get(ScanPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    items = session.exec(select(PlanItem).where(PlanItem.plan_id == plan_id)).all()
    library = session.get(LibraryPath, plan.library_id)
    return {"plan": plan, "library": library, "items": items}


@router.patch("/plans/{plan_id}/items/{item_id}", response_model=PlanItem)
def update_plan_item(
    plan_id: int, item_id: int, payload: PlanItemUpdate, session: Session = Depends(get_session)
):
    item = session.get(PlanItem, item_id)
    if not item or item.plan_id != plan_id:
        raise HTTPException(404, "Plan item not found")
    if payload.status is not None:
        item.status = payload.status
    if payload.target_path is not None:
        item.target_path = payload.target_path
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.post("/plans/{plan_id}/execute")
def execute_plan(plan_id: int, session: Session = Depends(get_session)):
    plan = session.get(ScanPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    if plan.status != PlanStatus.pending:
        raise HTTPException(400, f"Plan is {plan.status.value}, not pending")

    library = session.get(LibraryPath, plan.library_id)
    root = Path(library.path)
    items = session.exec(select(PlanItem).where(PlanItem.plan_id == plan_id)).all()

    done = skipped = failed = 0
    for item in items:
        if item.status in (ItemStatus.skip, ItemStatus.done):
            skipped += 1 if item.status == ItemStatus.skip else 0
            continue
        if not item.target_path:
            item.status = ItemStatus.error
            item.error_message = item.error_message or "No target path resolved"
            failed += 1
            session.add(item)
            continue
        ok, error = execute_move(root, item.source_path, item.target_path)
        if ok:
            item.status = ItemStatus.done
            done += 1
        else:
            item.status = ItemStatus.conflict if error and "conflict" in error.lower() else ItemStatus.error
            item.error_message = error
            failed += 1
        session.add(item)

    plan.status = PlanStatus.executed
    session.add(plan)
    session.commit()

    return {"done": done, "skipped": skipped, "failed": failed}


@router.post("/plans/{plan_id}/cancel", response_model=ScanPlan)
def cancel_plan(plan_id: int, session: Session = Depends(get_session)):
    plan = session.get(ScanPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    if plan.status == PlanStatus.executed:
        raise HTTPException(400, "Plan already executed")
    plan.status = PlanStatus.cancelled
    session.add(plan)
    session.commit()
    session.refresh(plan)
    return plan
