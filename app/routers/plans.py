import json
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app import naming, progress
from app.db import engine, get_session
from app.executor import execute_move
from app.metadata.musicbrainz import MusicBrainzClient
from app.metadata.tvdb import TvdbClient
from app.models import ItemStatus, LibraryPath, MediaType, PlanItem, PlanItemUpdate, PlanStatus, ScanPlan
from app.scanner import scan_movie_library, scan_music_library, scan_tv_library
from app.settings import get_preferred_languages, get_tvdb_api_key, get_tvdb_pin

router = APIRouter(prefix="/api", tags=["plans"])


def _run_scan(library_id: int, library_path: str, library_type: MediaType) -> None:
    root = Path(library_path)
    with Session(engine) as session:
        try:
            tvdb_key = get_tvdb_api_key(session)
            tvdb_pin = get_tvdb_pin(session)
            languages = get_preferred_languages(session)

            def on_progress(processed: int, total: int) -> None:
                progress.set_total(library_id, total)
                progress.tick(library_id, processed)

            if library_type == MediaType.movie:
                tvdb = TvdbClient(tvdb_key, tvdb_pin) if tvdb_key else None
                try:
                    results = scan_movie_library(root, tvdb, on_progress, languages)
                finally:
                    if tvdb:
                        tvdb.close()
            elif library_type == MediaType.tv:
                tvdb = TvdbClient(tvdb_key, tvdb_pin) if tvdb_key else None
                try:
                    results = scan_tv_library(root, tvdb, on_progress, languages)
                finally:
                    if tvdb:
                        tvdb.close()
            else:
                mb = MusicBrainzClient()
                try:
                    results = scan_music_library(root, mb, on_progress)
                finally:
                    mb.close()

            plan = ScanPlan(library_id=library_id, status=PlanStatus.pending)
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
                    candidates=json.dumps(r.candidates) if r.candidates else None,
                    search_query=r.search_query,
                    language=r.language,
                )
                session.add(item)

            plan.skipped_up_to_date = up_to_date
            session.add(plan)
            session.commit()
            progress.finish(library_id, plan.id)
        except Exception as exc:  # noqa: BLE001 - surface any scan failure to the UI
            progress.fail(library_id, str(exc))


@router.post("/libraries/{library_id}/scan")
def scan_library(library_id: int, session: Session = Depends(get_session)):
    library = session.get(LibraryPath, library_id)
    if not library:
        raise HTTPException(404, "Library not found")

    root = Path(library.path)
    if not root.exists():
        raise HTTPException(400, f"Library path no longer exists: {root}")

    existing = progress.get(library_id)
    if existing and existing["status"] == "scanning":
        raise HTTPException(409, "A scan is already running for this library")

    progress.start(library_id)
    thread = threading.Thread(
        target=_run_scan, args=(library_id, library.path, library.type), daemon=True
    )
    thread.start()
    return {"library_id": library_id, "status": "scanning"}


@router.get("/libraries/{library_id}/scan-progress")
def scan_progress(library_id: int):
    state = progress.get(library_id)
    if not state:
        raise HTTPException(404, "No scan found for this library")
    return state


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


def _apply_candidate(item: PlanItem, candidate: dict, session: Session) -> None:
    ext = Path(item.source_path).suffix.lower()

    if item.media_type == MediaType.movie:
        item.title = candidate["title"]
        item.year = candidate["year"]
        item.target_path = naming.movie_relpath(item.title, item.year, ext)
    elif item.media_type == MediaType.tv:
        if item.season is None or item.episode is None:
            raise HTTPException(400, "Season/episode unknown; cannot rename this item")
        episode_title = None
        tvdb_key = get_tvdb_api_key(session)
        if tvdb_key:
            client = TvdbClient(tvdb_key, get_tvdb_pin(session))
            try:
                candidate_language = candidate.get("language")
                episode_title = client.get_episode_title(
                    candidate["id"],
                    item.season,
                    item.episode,
                    languages=[candidate_language] if candidate_language else None,
                )
            finally:
                client.close()
        item.title = candidate["name"]
        item.year = candidate["year"]
        item.target_path = naming.tv_relpath(
            item.title, item.season, item.episode, episode_title, ext, item.year
        )
    else:
        raise HTTPException(400, "Candidate selection is not supported for this media type")

    item.language = candidate.get("language")
    item.matched = True
    item.status = ItemStatus.pending
    item.error_message = None


def _require_pending_item(plan_id: int, item_id: int, session: Session) -> tuple[PlanItem, ScanPlan]:
    item = session.get(PlanItem, item_id)
    if not item or item.plan_id != plan_id:
        raise HTTPException(404, "Plan item not found")
    plan = session.get(ScanPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    if plan.status != PlanStatus.pending:
        raise HTTPException(400, f"Plan is {plan.status.value}, not pending")
    return item, plan


@router.post("/plans/{plan_id}/items/{item_id}/select", response_model=PlanItem)
def select_candidate(
    plan_id: int, item_id: int, payload: dict, session: Session = Depends(get_session)
):
    item, _ = _require_pending_item(plan_id, item_id, session)
    if not item.candidates:
        raise HTTPException(400, "No alternate matches available for this item")

    candidates = json.loads(item.candidates)
    index = payload.get("candidate_index")
    if not isinstance(index, int) or not (0 <= index < len(candidates)):
        raise HTTPException(400, "Invalid candidate index")

    _apply_candidate(item, candidates[index], session)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.post("/plans/{plan_id}/items/{item_id}/research", response_model=PlanItem)
def research_item(
    plan_id: int, item_id: int, payload: dict, session: Session = Depends(get_session)
):
    item, _ = _require_pending_item(plan_id, item_id, session)
    if item.media_type not in (MediaType.movie, MediaType.tv):
        raise HTTPException(400, "Re-searching is only supported for movie and TV items")

    query = (payload.get("query") or "").strip()
    if not query:
        raise HTTPException(400, "Query must not be empty")
    language = (payload.get("language") or "").strip() or None
    languages = [language] if language else None

    tvdb_key = get_tvdb_api_key(session)
    if not tvdb_key:
        raise HTTPException(400, "No TheTVDB API key configured")

    client = TvdbClient(tvdb_key, get_tvdb_pin(session))
    try:
        if item.media_type == MediaType.movie:
            candidates = client.search_movie_candidates(query, languages=languages)
        else:
            candidates = client.search_tv_candidates(query, languages=languages)
    finally:
        client.close()

    item.search_query = query
    item.candidates = json.dumps(candidates) if candidates else None

    if candidates:
        _apply_candidate(item, candidates[0], session)
    else:
        item.matched = False
        item.status = ItemStatus.unmatched
        item.target_path = ""
        item.error_message = "No matches found for this search"

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


@router.delete("/plans/{plan_id}")
def delete_plan(plan_id: int, session: Session = Depends(get_session)):
    plan = session.get(ScanPlan, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    items = session.exec(select(PlanItem).where(PlanItem.plan_id == plan_id)).all()
    for item in items:
        session.delete(item)
    session.delete(plan)
    session.commit()
    return {"ok": True}
