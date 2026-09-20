import os
from pathlib import Path
from typing import Callable, Iterator

from guessit import guessit
from mutagen import File as MutagenFile

from app import naming
from app.extensions import EXTS_BY_TYPE, SUBTITLE_EXTS
from app.metadata.musicbrainz import MusicBrainzClient
from app.metadata.tvdb import TvdbClient
from app.models import ItemStatus, MediaType


def iter_media_files(root: Path, media_type: MediaType) -> Iterator[Path]:
    exts = EXTS_BY_TYPE[media_type.value]
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            if name.startswith("."):
                continue
            ext = Path(name).suffix.lower()
            if ext in exts:
                yield Path(dirpath) / name


def _music_tags(path: Path) -> dict:
    try:
        audio = MutagenFile(path, easy=True)
    except Exception:
        audio = None
    tags = {"artist": None, "album": None, "title": None, "track": None}
    if audio and audio.tags:
        tags["artist"] = (audio.tags.get("artist") or [None])[0]
        tags["album"] = (audio.tags.get("album") or [None])[0]
        tags["title"] = (audio.tags.get("title") or [None])[0]
        track_raw = (audio.tags.get("tracknumber") or [None])[0]
        if track_raw:
            try:
                tags["track"] = int(str(track_raw).split("/")[0])
            except ValueError:
                tags["track"] = None
    return tags


class ScanResult:
    def __init__(
        self,
        source_path: str,
        target_relpath: str | None,
        media_type: MediaType,
        title=None,
        year=None,
        season=None,
        episode=None,
        artist=None,
        album=None,
        track=None,
        matched: bool = False,
        status: ItemStatus = ItemStatus.pending,
        error_message: str | None = None,
        candidates: list[dict] | None = None,
        search_query: str | None = None,
        language: str | None = None,
    ):
        self.source_path = source_path
        self.target_relpath = target_relpath
        self.media_type = media_type
        self.title = title
        self.year = year
        self.season = season
        self.episode = episode
        self.artist = artist
        self.album = album
        self.track = track
        self.matched = matched
        self.status = status
        self.error_message = error_message
        self.candidates = candidates
        self.search_query = search_query
        self.language = language


def scan_movie_library(
    root: Path,
    tvdb: TvdbClient | None,
    on_progress: Callable[[int, int], None] | None = None,
    languages: list[str] | None = None,
) -> list[ScanResult]:
    results = []
    files = list(iter_media_files(root, MediaType.movie))
    total = len(files)
    if on_progress:
        on_progress(0, total)
    for i, path in enumerate(files, start=1):
        guess = guessit(path.name)
        raw_title = str(guess.get("title") or path.stem)
        raw_year = guess.get("year")
        matched = False
        title, year, language_used = raw_title, raw_year, None
        candidates = []
        if tvdb:
            candidates = tvdb.search_movie_candidates(raw_title, raw_year, languages=languages)
            if candidates:
                best = candidates[0]
                title, year, language_used = best["title"], best["year"] or raw_year, best.get("language")
                matched = True
        relpath = naming.movie_relpath(title, year, path.suffix.lower())
        results.append(
            ScanResult(
                source_path=str(path),
                target_relpath=relpath,
                media_type=MediaType.movie,
                title=title,
                year=year,
                matched=matched,
                status=ItemStatus.pending if matched else ItemStatus.unmatched,
                candidates=candidates,
                search_query=raw_title,
                language=language_used,
            )
        )
        if on_progress:
            on_progress(i, total)
    return results


def scan_tv_library(
    root: Path,
    tvdb: TvdbClient | None,
    on_progress: Callable[[int, int], None] | None = None,
    languages: list[str] | None = None,
) -> list[ScanResult]:
    results = []
    show_cache: dict[str, list[dict]] = {}
    files = list(iter_media_files(root, MediaType.tv))
    total = len(files)
    if on_progress:
        on_progress(0, total)
    for i, path in enumerate(files, start=1):
        guess = guessit(path.name)
        raw_show = str(guess.get("title") or path.parent.name)
        season = guess.get("season")
        episode = guess.get("episode")
        if isinstance(season, list):
            season = season[0] if season else None
        if isinstance(episode, list):
            episode = episode[0] if episode else None

        show, year, tv_id, language_used, matched = raw_show, None, None, None, False
        candidates: list[dict] = []
        if tvdb:
            if raw_show not in show_cache:
                show_cache[raw_show] = tvdb.search_tv_candidates(raw_show, languages=languages)
            candidates = show_cache[raw_show]
            if candidates:
                best = candidates[0]
                show, year, tv_id, language_used, matched = (
                    best["name"],
                    best["year"],
                    best["id"],
                    best.get("language"),
                    True,
                )

        if season is None or episode is None:
            results.append(
                ScanResult(
                    source_path=str(path),
                    target_relpath=None,
                    media_type=MediaType.tv,
                    title=show,
                    matched=False,
                    status=ItemStatus.unmatched,
                    error_message="Could not determine season/episode from filename",
                    candidates=candidates,
                    search_query=raw_show,
                    language=language_used,
                )
            )
            if on_progress:
                on_progress(i, total)
            continue

        episode_title = None
        if tvdb and tv_id:
            episode_title = tvdb.get_episode_title(
                tv_id, season, episode, languages=[language_used] if language_used else None
            )

        relpath = naming.tv_relpath(show, season, episode, episode_title, path.suffix.lower(), year)
        results.append(
            ScanResult(
                source_path=str(path),
                target_relpath=relpath,
                media_type=MediaType.tv,
                title=show,
                year=year,
                season=season,
                episode=episode,
                matched=matched,
                status=ItemStatus.pending if matched else ItemStatus.unmatched,
                candidates=candidates,
                search_query=raw_show,
                language=language_used,
            )
        )
        if on_progress:
            on_progress(i, total)
    return results


def scan_music_library(
    root: Path,
    mb: MusicBrainzClient | None,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[ScanResult]:
    results = []
    files = list(iter_media_files(root, MediaType.music))
    total = len(files)
    if on_progress:
        on_progress(0, total)
    for i, path in enumerate(files, start=1):
        tags = _music_tags(path)
        artist, album, title, track = tags["artist"], tags["album"], tags["title"], tags["track"]
        matched = bool(artist and album and title)

        if not matched:
            guess = guessit(path.name)
            title = title or str(guess.get("title") or path.stem)
            artist = artist or str(guess.get("artist") or "Unknown Artist")
            if mb and (not album or not artist):
                hit = mb.search_recording(artist, title)
                if hit:
                    artist, album, title = hit["artist"], hit["album"], hit["title"]
                    matched = True
            album = album or "Unknown Album"

        relpath = naming.music_relpath(artist, album, title, track, path.suffix.lower())
        results.append(
            ScanResult(
                source_path=str(path),
                target_relpath=relpath,
                media_type=MediaType.music,
                title=title,
                artist=artist,
                album=album,
                track=track,
                matched=matched,
                status=ItemStatus.pending if matched else ItemStatus.unmatched,
            )
        )
        if on_progress:
            on_progress(i, total)
    return results
