import threading

_lock = threading.Lock()
_progress: dict[int, dict] = {}


def start(library_id: int) -> None:
    with _lock:
        _progress[library_id] = {
            "status": "scanning",
            "total": 0,
            "processed": 0,
            "plan_id": None,
            "error": None,
        }


def set_total(library_id: int, total: int) -> None:
    with _lock:
        if library_id in _progress:
            _progress[library_id]["total"] = total


def tick(library_id: int, processed: int) -> None:
    with _lock:
        if library_id in _progress:
            _progress[library_id]["processed"] = processed


def finish(library_id: int, plan_id: int) -> None:
    with _lock:
        _progress[library_id]["status"] = "done"
        _progress[library_id]["plan_id"] = plan_id


def fail(library_id: int, error: str) -> None:
    with _lock:
        _progress[library_id]["status"] = "error"
        _progress[library_id]["error"] = error


def get(library_id: int) -> dict | None:
    with _lock:
        state = _progress.get(library_id)
        return dict(state) if state else None
