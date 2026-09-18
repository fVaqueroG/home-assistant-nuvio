"""TheTVDB v4 remote-id resolver for streaming-provider deep links."""

from __future__ import annotations

import time
from typing import Any

from aiohttp import ClientError, ClientSession

from .providers import streaming_provider_key


TVDB_API_BASE = "https://api4.thetvdb.com/v4"


class TvdbApiError(Exception):
    """Raised when TheTVDB metadata cannot be loaded."""


class TvdbApi:
    """Resolve exact movie/episode provider URLs from TheTVDB remote IDs."""

    def __init__(
        self,
        session: ClientSession,
        api_key: str,
        subscriber_pin: str | None = None,
    ) -> None:
        self._session = session
        self._api_key = str(api_key or "").strip()
        self._pin = str(subscriber_pin or "").strip()
        self._token = ""
        self._token_expires = 0.0
        self._source_types: dict[int, dict[str, Any]] | None = None
        self._cache: dict[tuple[Any, ...], tuple[float, Any]] = {}
        self._ttl = 86400.0

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def _cached(self, key: tuple[Any, ...]) -> Any | None:
        item = self._cache.get(key)
        if item is None:
            return None
        expires, value = item
        if expires <= time.monotonic():
            self._cache.pop(key, None)
            return None
        return value

    def _store(self, key: tuple[Any, ...], value: Any) -> Any:
        self._cache[key] = (time.monotonic() + self._ttl, value)
        return value

    async def _login(self) -> str:
        if not self._api_key:
            raise TvdbApiError("TheTVDB API key is not configured")
        if self._token and self._token_expires > time.monotonic():
            return self._token

        payload: dict[str, str] = {"apikey": self._api_key}
        if self._pin:
            payload["pin"] = self._pin
        try:
            async with self._session.post(
                f"{TVDB_API_BASE}/login",
                json=payload,
                headers={"accept": "application/json"},
                timeout=15,
            ) as response:
                if response.status in {401, 403}:
                    raise TvdbApiError("TheTVDB rejected the API key or PIN")
                if response.status >= 400:
                    raise TvdbApiError(f"TheTVDB login returned HTTP {response.status}")
                body = await response.json(content_type=None)
        except TvdbApiError:
            raise
        except (ClientError, TimeoutError, ValueError) as err:
            raise TvdbApiError("Could not connect to TheTVDB") from err

        data = body.get("data") if isinstance(body, dict) else None
        token = data.get("token") if isinstance(data, dict) else None
        if not isinstance(token, str) or not token:
            raise TvdbApiError("TheTVDB did not return an authentication token")
        self._token = token
        # TheTVDB documents one-month tokens; refresh a little early.
        self._token_expires = time.monotonic() + (27 * 86400)
        return token

    async def _get_json(self, path: str) -> dict[str, Any]:
        token = await self._login()
        try:
            async with self._session.get(
                f"{TVDB_API_BASE}/{path.lstrip('/')}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "accept": "application/json",
                },
                timeout=15,
            ) as response:
                if response.status in {401, 403}:
                    self._token = ""
                    self._token_expires = 0.0
                    raise TvdbApiError("TheTVDB authorization expired or was rejected")
                if response.status == 404:
                    return {"data": None}
                if response.status >= 400:
                    raise TvdbApiError(f"TheTVDB returned HTTP {response.status}")
                body = await response.json(content_type=None)
        except TvdbApiError:
            raise
        except (ClientError, TimeoutError, ValueError) as err:
            raise TvdbApiError("Could not connect to TheTVDB") from err
        if not isinstance(body, dict):
            raise TvdbApiError("TheTVDB returned an invalid response")
        return body

    async def async_validate(self) -> None:
        """Validate the key/PIN combination."""
        await self._login()

    async def _async_source_types(self) -> dict[int, dict[str, Any]]:
        if self._source_types is not None:
            return self._source_types
        body = await self._get_json("sources/types")
        raw = body.get("data")
        result: dict[int, dict[str, Any]] = {}
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    continue
                try:
                    source_id = int(item.get("id"))
                except (TypeError, ValueError):
                    continue
                result[source_id] = item
        self._source_types = result
        return result

    @staticmethod
    def _extract_data(body: dict[str, Any]) -> dict[str, Any] | None:
        data = body.get("data")
        return data if isinstance(data, dict) else None

    async def async_movie_id_by_remote(self, remote_id: str) -> int | None:
        """Resolve an IMDb/remote id to a TheTVDB movie id."""
        remote_id = str(remote_id or "").strip()
        if not remote_id:
            return None
        key = ("movie-search", remote_id.casefold())
        cached = self._cached(key)
        if cached is not None:
            return cached or None

        body = await self._get_json(f"search/remoteid/{remote_id}")
        raw = body.get("data")
        items = raw if isinstance(raw, list) else [raw] if isinstance(raw, dict) else []
        movie_id: int | None = None
        for item in items:
            if not isinstance(item, dict):
                continue
            candidate = item.get("movie")
            if not isinstance(candidate, dict):
                # Some API versions return the entity directly.
                candidate = item if item.get("type") == "movie" else None
            if not isinstance(candidate, dict):
                continue
            try:
                movie_id = int(candidate.get("id") or candidate.get("tvdb_id"))
            except (TypeError, ValueError):
                continue
            break
        self._store(key, movie_id or 0)
        return movie_id

    async def _async_remote_links(
        self,
        entity_type: str,
        entity_id: int,
    ) -> list[dict[str, Any]]:
        key = ("links", entity_type, int(entity_id))
        cached = self._cached(key)
        if cached is not None:
            return cached

        body = await self._get_json(f"{entity_type}/{int(entity_id)}/extended")
        data = self._extract_data(body)
        if data is None:
            return self._store(key, [])

        source_types = await self._async_source_types()
        remote_ids = data.get("remoteIds")
        if not isinstance(remote_ids, list):
            remote_ids = data.get("remote_ids")
        if not isinstance(remote_ids, list):
            return self._store(key, [])

        links: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for remote in remote_ids:
            if not isinstance(remote, dict):
                continue
            remote_id = str(remote.get("id") or "").strip()
            source_name = str(
                remote.get("sourceName")
                or remote.get("source_name")
                or ""
            ).strip()
            try:
                source_type_id = int(remote.get("type"))
            except (TypeError, ValueError):
                source_type_id = -1
            source_type = source_types.get(source_type_id, {})
            if not source_name:
                source_name = str(source_type.get("name") or "").strip()
            provider_key = streaming_provider_key(source_name)
            if not provider_key or not remote_id:
                continue

            prefix = str(source_type.get("prefix") or "")
            postfix = str(source_type.get("postfix") or "")
            url = f"{prefix}{remote_id}{postfix}" if prefix else ""
            if url and not url.lower().startswith(("http://", "https://")):
                url = ""

            signature = (provider_key, url or remote_id)
            if signature in seen:
                continue
            seen.add(signature)
            links.append(
                {
                    "provider_key": provider_key,
                    "provider_name": source_name,
                    "remote_id": remote_id,
                    "source_type_id": source_type_id,
                    "source_slug": source_type.get("slug"),
                    "url": url or None,
                }
            )
        return self._store(key, links)

    async def async_episode_links(self, tvdb_episode_id: int) -> list[dict[str, Any]]:
        """Return provider remote links for an exact TV episode."""
        return await self._async_remote_links("episodes", int(tvdb_episode_id))

    async def async_series_links(self, tvdb_series_id: int) -> list[dict[str, Any]]:
        """Return provider remote links for a TV series."""
        return await self._async_remote_links("series", int(tvdb_series_id))

    async def async_movie_links(
        self,
        *,
        tvdb_movie_id: int | None = None,
        imdb_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return provider remote links for a movie."""
        movie_id = tvdb_movie_id
        if movie_id is None and imdb_id:
            movie_id = await self.async_movie_id_by_remote(imdb_id)
        if movie_id is None:
            return []
        return await self._async_remote_links("movies", int(movie_id))
