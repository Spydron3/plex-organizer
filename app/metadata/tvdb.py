import httpx

BASE_URL = "https://api4.thetvdb.com/v4"


class TvdbClient:
    def __init__(self, api_key: str, pin: str | None = None):
        self.api_key = api_key
        self.pin = pin
        self._client = httpx.Client(base_url=BASE_URL, timeout=15.0)
        self._token: str | None = None

    def close(self):
        self._client.close()

    def _ensure_token(self):
        if self._token:
            return
        body = {"apikey": self.api_key}
        if self.pin:
            body["pin"] = self.pin
        resp = self._client.post("/login", json=body)
        resp.raise_for_status()
        self._token = resp.json()["data"]["token"]
        self._client.headers["Authorization"] = f"Bearer {self._token}"

    def _get(self, path: str, **params) -> dict:
        self._ensure_token()
        resp = self._client.get(path, params=params)
        if resp.status_code == 401:
            self._token = None
            self._ensure_token()
            resp = self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _year_int(value) -> int | None:
        if value and str(value).isdigit():
            return int(value)
        return None

    def search_movie(self, title: str, year: int | None = None) -> dict | None:
        params = {"query": title, "type": "movie"}
        if year:
            params["year"] = year
        data = self._get("/search", **params)
        results = data.get("data") or []
        if not results and year:
            data = self._get("/search", query=title, type="movie")
            results = data.get("data") or []
        if not results:
            return None
        best = results[0]
        return {
            "title": best.get("name") or title,
            "year": self._year_int(best.get("year")) or year,
        }

    def search_tv(self, title: str) -> dict | None:
        data = self._get("/search", query=title, type="series")
        results = data.get("data") or []
        if not results:
            return None
        best = results[0]
        tvdb_id = best.get("tvdb_id")
        return {
            "id": int(tvdb_id) if tvdb_id and str(tvdb_id).isdigit() else None,
            "name": best.get("name") or title,
            "year": self._year_int(best.get("year")),
        }

    def get_episode_title(self, series_id: int, season: int, episode: int) -> str | None:
        try:
            data = self._get(
                f"/series/{series_id}/episodes/default",
                page=0,
                season=season,
                episodeNumber=episode,
            )
        except httpx.HTTPStatusError:
            return None
        episodes = (data.get("data") or {}).get("episodes") or []
        for ep in episodes:
            if ep.get("seasonNumber") == season and ep.get("number") == episode:
                return ep.get("name")
        return episodes[0].get("name") if episodes else None
