import re

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MULTI_SPACE = re.compile(r"\s+")


def sanitize(name: str) -> str:
    name = _INVALID.sub("", name)
    name = _MULTI_SPACE.sub(" ", name).strip()
    name = name.rstrip(". ")
    return name or "Unknown"


def movie_relpath(title: str, year: int | None, ext: str) -> str:
    label = f"{sanitize(title)} ({year})" if year else sanitize(title)
    return f"{label}/{label}{ext}"


def tv_relpath(
    show: str,
    season: int,
    episode: int,
    episode_title: str | None,
    ext: str,
    year: int | None = None,
) -> str:
    show_label = f"{sanitize(show)} ({year})" if year else sanitize(show)
    season_dir = f"Season {season:02d}"
    file_label = f"{sanitize(show)} - s{season:02d}e{episode:02d}"
    if episode_title:
        file_label += f" - {sanitize(episode_title)}"
    return f"{show_label}/{season_dir}/{file_label}{ext}"


def music_relpath(
    artist: str,
    album: str,
    title: str,
    track: int | None,
    ext: str,
) -> str:
    artist_label = sanitize(artist)
    album_label = sanitize(album)
    if track:
        file_label = f"{track:02d} - {sanitize(title)}"
    else:
        file_label = sanitize(title)
    return f"{artist_label}/{album_label}/{file_label}{ext}"
