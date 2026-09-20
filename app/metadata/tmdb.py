import httpx

BASE_URL = "https://api.themoviedb.org/3"


class TmdbClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = httpx.Client(base_url=BASE_URL, timeout=10.0)

    def close(self):
        self._client.close()

    def _get(self, path: str, **params) -> dict:
        params["api_key"] = self.api_key
        resp = self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    def search_movie(self, title: str, year: int | None = None) -> dict | None:
        params = {"query": title, "include_adult": "false"}
        if year:
            params["year"] = year
        data = self._get("/search/movie", **params)
        results = data.get("results") or []
        if not results and year:
            data = self._get("/search/movie", query=title, include_adult="false")
            results = data.get("results") or []
        if not results:
            return None
        best = results[0]
        release_date = best.get("release_date") or ""
        return {
            "title": best.get("title") or title,
            "year": int(release_date[:4]) if release_date[:4].isdigit() else year,
        }

    def search_tv(self, title: str) -> dict | None:
        data = self._get("/search/tv", query=title, include_adult="false")
        results = data.get("results") or []
        if not results:
            return None
        best = results[0]
        first_air = best.get("first_air_date") or ""
        return {
            "id": best.get("id"),
            "name": best.get("name") or title,
            "year": int(first_air[:4]) if first_air[:4].isdigit() else None,
        }

    def get_episode_title(self, tv_id: int, season: int, episode: int) -> str | None:
        try:
            data = self._get(f"/tv/{tv_id}/season/{season}/episode/{episode}")
        except httpx.HTTPStatusError:
            return None
        return data.get("name")
