import shutil
from pathlib import Path

from app.extensions import SUBTITLE_EXTS


def _companion_subtitles(source: Path) -> list[Path]:
    companions = []
    for ext in SUBTITLE_EXTS:
        candidate = source.with_suffix(ext)
        if candidate.exists():
            companions.append(candidate)
    return companions


def execute_move(library_root: Path, source_path: str, target_relpath: str) -> tuple[bool, str | None]:
    source = Path(source_path)
    target = library_root / target_relpath

    if not source.exists():
        return False, "Source file no longer exists"

    if target.exists() and target.resolve() != source.resolve():
        return False, "Target already exists (conflict)"

    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        shutil.move(str(source), str(target))
        for sub in _companion_subtitles(source):
            sub_target = target.with_suffix(sub.suffix)
            if not sub_target.exists():
                shutil.move(str(sub), str(sub_target))
    except OSError as exc:
        return False, str(exc)

    _prune_empty_dirs(source.parent, library_root)
    return True, None


def _prune_empty_dirs(start: Path, stop_at: Path) -> None:
    current = start
    stop_at = stop_at.resolve()
    while current.resolve() != stop_at and stop_at in current.resolve().parents:
        try:
            if any(current.iterdir()):
                break
            current.rmdir()
        except OSError:
            break
        current = current.parent
