import threading
import time

import httpx

BASE_URL = "https://musicbrainz.org/ws/2"
USER_AGENT = "plex-organizer/0.1 (local tool; no contact configured)"

_last_call = 0.0
_lock = threading.Lock()


def _rate_limit():
    global _last_call
    with _lock:
        elapsed = time.monotonic() - _last_call
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)
        _last_call = time.monotonic()


class MusicBrainzClient:
    def __init__(self):
        self._client = httpx.Client(
            base_url=BASE_URL,
            timeout=10.0,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )

    def close(self):
        self._client.close()

    def search_recording(self, artist_hint: str, title_hint: str) -> dict | None:
        """Best-effort lookup used only when local file tags are missing."""
        query = f'recording:"{title_hint}" AND artist:"{artist_hint}"'
        _rate_limit()
        try:
            resp = self._client.get("/recording", params={"query": query, "fmt": "json", "limit": 1})
            resp.raise_for_status()
        except httpx.HTTPError:
            return None
        data = resp.json()
        recordings = data.get("recordings") or []
        if not recordings:
            return None
        best = recordings[0]
        artist_credit = best.get("artist-credit") or []
        artist = artist_credit[0]["name"] if artist_credit else artist_hint
        releases = best.get("releases") or []
        album = releases[0]["title"] if releases else "Unknown Album"
        return {"artist": artist, "album": album, "title": best.get("title") or title_hint}
