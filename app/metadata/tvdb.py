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

    def _translated_name(self, kind: str, tvdb_id: int, language: str) -> str | None:
        try:
            data = self._get(f"/{kind}/{tvdb_id}/translations/{language}")
        except httpx.HTTPStatusError:
            return None
        return (data.get("data") or {}).get("name")

    def _best_translation(self, kind: str, tvdb_id: int, languages: list[str]) -> tuple[str, str] | None:
        """Try each preferred language in order; return (name, language) of the first hit."""
        for lang in languages:
            name = self._translated_name(kind, tvdb_id, lang)
            if name:
                return name, lang
        return None

    def search_movie_candidates(
        self, title: str, year: int | None = None, limit: int = 5, languages: list[str] | None = None
    ) -> list[dict]:
        params = {"query": title, "type": "movie", "limit": limit}
        if year:
            params["year"] = year
        data = self._get("/search", **params)
        results = data.get("data") or []
        if not results and year:
            data = self._get("/search", query=title, type="movie", limit=limit)
            results = data.get("data") or []
        candidates = []
        for r in results[:limit]:
            tvdb_id = r.get("tvdb_id")
            if not tvdb_id or not str(tvdb_id).isdigit():
                continue
            tvdb_id_int = int(tvdb_id)
            name = r.get("name") or title
            record_language = r.get("primary_language")
            # A record's `name` is always its primary-language title, even
            # when a translation exists in a preferred language - fetch it
            # explicitly rather than only ever showing the original title.
            wanted = [lang for lang in (languages or []) if lang != record_language]
            if wanted:
                hit = self._best_translation("movies", tvdb_id_int, wanted)
                if hit:
                    name, record_language = hit
            candidates.append(
                {
                    "id": tvdb_id_int,
                    "title": name,
                    "year": self._year_int(r.get("year")) or year,
                    "language": record_language,
                }
            )
        return candidates

    def search_tv_candidates(
        self, title: str, limit: int = 5, languages: list[str] | None = None
    ) -> list[dict]:
        data = self._get("/search", query=title, type="series", limit=limit)
        results = data.get("data") or []
        candidates = []
        for r in results[:limit]:
            tvdb_id = r.get("tvdb_id")
            if not tvdb_id or not str(tvdb_id).isdigit():
                continue
            tvdb_id_int = int(tvdb_id)
            name = r.get("name") or title
            record_language = r.get("primary_language")
            wanted = [lang for lang in (languages or []) if lang != record_language]
            if wanted:
                hit = self._best_translation("series", tvdb_id_int, wanted)
                if hit:
                    name, record_language = hit
            candidates.append(
                {
                    "id": tvdb_id_int,
                    "name": name,
                    "year": self._year_int(r.get("year")),
                    "language": record_language,
                }
            )
        return candidates

    def list_languages(self) -> list[dict]:
        data = self._get("/languages")
        return [{"id": lang["id"], "name": lang["name"]} for lang in (data.get("data") or [])]

    def get_episode_title(
        self, series_id: int, season: int, episode: int, languages: list[str] | None = None
    ) -> str | None:
        for lang in languages or []:
            try:
                data = self._get(
                    f"/series/{series_id}/episodes/default/{lang}",
                    page=0,
                    season=season,
                    episodeNumber=episode,
                )
            except httpx.HTTPStatusError:
                continue
            episodes = (data.get("data") or {}).get("episodes") or []
            for ep in episodes:
                if ep.get("seasonNumber") == season and ep.get("number") == episode:
                    return ep.get("name")

        try:
            data = self._get(f"/series/{series_id}/episodes/default", page=0, season=season, episodeNumber=episode)
        except httpx.HTTPStatusError:
            return None
        episodes = (data.get("data") or {}).get("episodes") or []
        for ep in episodes:
            if ep.get("seasonNumber") == season and ep.get("number") == episode:
                return ep.get("name")
        return episodes[0].get("name") if episodes else None
