"""TMDB/JustWatch availability client for Nuvio."""

from __future__ import annotations

import re
import time
from typing import Any

from aiohttp import ClientError, ClientSession


TMDB_API_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w92"


class TmdbApiError(Exception):
    """Raised when TMDB availability cannot be loaded."""


class TmdbWatchApi:
    """Fetch country-specific streaming availability from TMDB/JustWatch."""

    def __init__(self, session: ClientSession, access_token: str) -> None:
        self._session = session
        self._token = str(access_token or "").strip()
        self._cache: dict[tuple[Any, ...], tuple[float, Any]] = {}
        self._ttl = 3600.0

    @property
    def configured(self) -> bool:
        return bool(self._token)

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

    async def _get_json(
        self,
        path: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not self._token:
            raise TmdbApiError("TMDB API Read Access Token is not configured")
        try:
            async with self._session.get(
                f"{TMDB_API_BASE}/{path.lstrip('/')}",
                params=params,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "accept": "application/json",
                },
                timeout=15,
            ) as response:
                if response.status in {401, 403}:
                    raise TmdbApiError("TMDB API token was rejected")
                if response.status >= 400:
                    raise TmdbApiError(f"TMDB returned HTTP {response.status}")
                data = await response.json(content_type=None)
        except TmdbApiError:
            raise
        except (ClientError, TimeoutError, ValueError) as err:
            raise TmdbApiError("Could not connect to TMDB") from err
        if not isinstance(data, dict):
            raise TmdbApiError("TMDB returned an invalid response")
        return data

    async def async_validate(self) -> None:
        """Validate the configured TMDB read token."""
        await self._get_json("configuration")

    @staticmethod
    def _direct_tmdb_id(content_id: str) -> int | None:
        value = str(content_id or "").strip()
        if value.isdigit():
            return int(value)
        for pattern in (
            r"^tmdb:(\d+)$",
            r"^tmdb:(?:movie|tv|series):(\d+)$",
        ):
            match = re.fullmatch(pattern, value, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None

    async def async_tmdb_id(self, media_type: str, content_id: str) -> int | None:
        """Resolve an IMDb/Stremio/TMDB content id to a TMDB id."""
        direct = self._direct_tmdb_id(content_id)
        if direct is not None:
            return direct

        external_id = re.sub(r":\d+:\d+$", "", str(content_id or "").strip())
        if not re.fullmatch(r"tt\d+", external_id, re.IGNORECASE):
            return None

        key = ("find", media_type, external_id.casefold())
        cached = self._cached(key)
        if cached is not None:
            return cached or None

        data = await self._get_json(
            f"find/{external_id}",
            {"external_source": "imdb_id"},
        )
        result_key = "tv_results" if media_type == "series" else "movie_results"
        results = data.get(result_key)
        tmdb_id: int | None = None
        if isinstance(results, list):
            for item in results:
                if not isinstance(item, dict) or item.get("id") is None:
                    continue
                try:
                    tmdb_id = int(item["id"])
                except (TypeError, ValueError):
                    continue
                break
        self._store(key, tmdb_id or 0)
        return tmdb_id

    @staticmethod
    def _provider_rows(region_blob: dict[str, Any]) -> list[dict[str, Any]]:
        """Flatten subscription/free/ad-supported groups and dedupe providers."""
        merged: dict[int, dict[str, Any]] = {}
        for group_name, access_label in (
            ("flatrate", "Subscription"),
            ("free", "Free"),
            ("ads", "Free with ads"),
        ):
            providers = region_blob.get(group_name)
            if not isinstance(providers, list):
                continue
            for raw in providers:
                if not isinstance(raw, dict):
                    continue
                try:
                    provider_id = int(raw.get("provider_id"))
                except (TypeError, ValueError):
                    continue
                name = str(raw.get("provider_name") or "").strip()
                if not name:
                    continue
                row = merged.setdefault(
                    provider_id,
                    {
                        "provider_id": provider_id,
                        "name": name,
                        "logo_path": raw.get("logo_path"),
                        "display_priority": raw.get("display_priority"),
                        "access": [],
                    },
                )
                if access_label not in row["access"]:
                    row["access"].append(access_label)

        def sort_key(row: dict[str, Any]) -> tuple[int, str]:
            try:
                priority = int(row.get("display_priority"))
            except (TypeError, ValueError):
                priority = 9999
            return priority, str(row.get("name") or "").casefold()

        rows = sorted(merged.values(), key=sort_key)
        for row in rows:
            logo_path = row.pop("logo_path", None)
            row["logo_url"] = (
                f"{TMDB_IMAGE_BASE}{logo_path}"
                if isinstance(logo_path, str) and logo_path.startswith("/")
                else None
            )
        return rows

    async def async_watch_providers(
        self,
        *,
        media_type: str,
        content_id: str,
        region: str,
        season: int | None = None,
    ) -> dict[str, Any]:
        """Return configured-country provider availability."""
        region = str(region or "").strip().upper() or "US"
        tmdb_id = await self.async_tmdb_id(media_type, content_id)
        if tmdb_id is None:
            return {
                "configured": True,
                "tmdb_id": None,
                "region": region,
                "scope": None,
                "providers": [],
                "link": None,
            }

        if media_type == "series":
            if season is None:
                return {
                    "configured": True,
                    "tmdb_id": tmdb_id,
                    "region": region,
                    "scope": None,
                    "providers": [],
                    "link": None,
                }
            path = f"tv/{tmdb_id}/season/{int(season)}/watch/providers"
            scope = "season"
        else:
            path = f"movie/{tmdb_id}/watch/providers"
            scope = "movie"

        key = ("watch", path, region)
        cached = self._cached(key)
        if cached is not None:
            return cached

        data = await self._get_json(path)
        results = data.get("results")
        region_blob = results.get(region) if isinstance(results, dict) else None
        if not isinstance(region_blob, dict):
            region_blob = {}

        result = {
            "configured": True,
            "tmdb_id": tmdb_id,
            "region": region,
            "scope": scope,
            "providers": self._provider_rows(region_blob),
            "link": region_blob.get("link"),
        }
        return self._store(key, result)
