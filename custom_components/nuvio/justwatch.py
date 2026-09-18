"""Unofficial JustWatch GraphQL offer resolver.

This module intentionally implements only the small subset Nuvio needs:
country-specific provider offer URLs for an exact movie or TV episode.
It uses JustWatch's public web GraphQL endpoint without account credentials.
Because this endpoint is unofficial, every caller must treat failures as optional.
"""

from __future__ import annotations

import time
from typing import Any

from aiohttp import ClientError, ClientSession

from .providers import streaming_provider_key

JUSTWATCH_GRAPHQL_URL = "https://apis.justwatch.com/graphql"

_SEARCH_QUERY = """
query NuvioSearch(
  $searchTitlesFilter: TitleFilter!,
  $country: Country!,
  $language: Language!,
  $first: Int!,
  $filter: OfferFilter!
) {
  popularTitles(
    country: $country
    filter: $searchTitlesFilter
    first: $first
    sortBy: POPULAR
    sortRandomSeed: 0
  ) {
    edges {
      node {
        id
        objectType
        content(country: $country, language: $language) {
          title
          originalReleaseYear
          ... on MovieOrShowOrSeasonContent {
            externalIds {
              imdbId
              tmdbId
            }
          }
        }
        offers(country: $country, platform: WEB, filter: $filter) {
          standardWebURL
          monetizationType
          presentationType
          package {
            clearName
            technicalName
            shortName
            packageId
          }
        }
      }
    }
  }
}
"""

_SEASONS_QUERY = """
query NuvioSeasons(
  $nodeId: ID!,
  $country: Country!,
  $language: Language!
) {
  node(id: $nodeId) {
    ... on Show {
      seasons(sortDirection: ASC) {
        id
        content(country: $country, language: $language) {
          ... on SeasonContent {
            seasonNumber
          }
        }
      }
    }
  }
}
"""

_EPISODES_QUERY = """
query NuvioEpisodes(
  $nodeId: ID!,
  $country: Country!,
  $language: Language!,
  $filter: OfferFilter!
) {
  node(id: $nodeId) {
    ... on Season {
      episodes(sortDirection: ASC) {
        id
        content(country: $country, language: $language) {
          title
          ... on EpisodeContent {
            seasonNumber
            episodeNumber
          }
        }
        offers(country: $country, platform: WEB, filter: $filter) {
          standardWebURL
          monetizationType
          presentationType
          package {
            clearName
            technicalName
            shortName
            packageId
          }
        }
      }
    }
  }
}
"""


class JustWatchApiError(Exception):
    """Raised when the unofficial JustWatch GraphQL request fails."""


class JustWatchGraphQLApi:
    """Resolve direct provider offer URLs through JustWatch GraphQL."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session
        self._cache: dict[tuple[Any, ...], tuple[float, Any]] = {}
        self._ttl = 3600.0

    @staticmethod
    def _language(value: str | None) -> str:
        raw = str(value or "en").strip()
        if not raw:
            return "en"
        # HA commonly uses en, en-US, es, es-MX, etc., which JustWatch accepts.
        return raw.replace("_", "-")

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

    async def _post(
        self,
        *,
        operation_name: str,
        query: str,
        variables: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            async with self._session.post(
                JUSTWATCH_GRAPHQL_URL,
                json={
                    "operationName": operation_name,
                    "variables": variables,
                    "query": query,
                },
                headers={
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                timeout=15,
            ) as response:
                if response.status >= 400:
                    raise JustWatchApiError(
                        f"JustWatch GraphQL returned HTTP {response.status}"
                    )
                body = await response.json(content_type=None)
        except JustWatchApiError:
            raise
        except (ClientError, TimeoutError, ValueError) as err:
            raise JustWatchApiError("Could not connect to JustWatch GraphQL") from err

        if not isinstance(body, dict):
            raise JustWatchApiError("JustWatch returned an invalid response")
        errors = body.get("errors")
        if errors:
            message = ""
            if isinstance(errors, list) and errors and isinstance(errors[0], dict):
                message = str(errors[0].get("message") or "")
            raise JustWatchApiError(
                f"JustWatch GraphQL error{': ' + message if message else ''}"
            )
        return body

    @staticmethod
    def _offers(raw_offers: Any) -> list[dict[str, Any]]:
        """Normalize streaming offers and collapse duplicates by provider."""
        if not isinstance(raw_offers, list):
            return []

        priority = {"FLATRATE": 0, "FREE": 1, "ADS": 2}
        selected: dict[str, dict[str, Any]] = {}

        for raw in raw_offers:
            if not isinstance(raw, dict):
                continue
            monetization = str(raw.get("monetizationType") or "").upper()
            if monetization not in priority:
                continue
            url = str(raw.get("standardWebURL") or "").strip()
            package = raw.get("package")
            if not url or not isinstance(package, dict):
                continue
            name = str(package.get("clearName") or "").strip()
            technical_name = str(package.get("technicalName") or "").strip()
            short_name = str(package.get("shortName") or "").strip()
            key = streaming_provider_key(name or technical_name, url)
            if not key:
                continue

            candidate = {
                "provider_key": key,
                "provider_name": name or technical_name or key,
                "provider_code": short_name or None,
                "package_id": package.get("packageId"),
                "url": url,
                "monetization_type": monetization,
                "presentation_type": raw.get("presentationType"),
                "source": "justwatch",
            }
            existing = selected.get(key)
            if existing is None or priority[monetization] < priority.get(
                str(existing.get("monetization_type") or ""), 99
            ):
                selected[key] = candidate

        return list(selected.values())

    async def _search_title(
        self,
        *,
        title: str,
        media_type: str,
        country: str,
        language: str,
        tmdb_id: int | str | None,
        imdb_id: str | None,
    ) -> dict[str, Any] | None:
        key = (
            "search",
            title.casefold(),
            media_type,
            country,
            language,
            str(tmdb_id or ""),
            str(imdb_id or "").casefold(),
        )
        cached = self._cached(key)
        if cached is not None:
            return cached or None

        object_type = "SHOW" if media_type == "series" else "MOVIE"
        body = await self._post(
            operation_name="NuvioSearch",
            query=_SEARCH_QUERY,
            variables={
                "first": 8,
                "searchTitlesFilter": {
                    "searchQuery": title,
                    "includeTitlesWithoutUrl": True,
                    "objectTypes": [object_type],
                },
                "country": country,
                "language": language,
                "filter": {"bestOnly": True},
            },
        )
        popular = (body.get("data") or {}).get("popularTitles") or {}
        edges = popular.get("edges") if isinstance(popular, dict) else []
        candidates: list[dict[str, Any]] = []
        for edge in edges if isinstance(edges, list) else []:
            if not isinstance(edge, dict) or not isinstance(edge.get("node"), dict):
                continue
            node = edge["node"]
            if str(node.get("objectType") or "") != object_type:
                continue
            candidates.append(node)

        wanted_tmdb = str(tmdb_id or "")
        wanted_imdb = str(imdb_id or "").casefold()
        for node in candidates:
            content = node.get("content")
            external = content.get("externalIds") if isinstance(content, dict) else None
            if not isinstance(external, dict):
                continue
            if wanted_tmdb and str(external.get("tmdbId") or "") == wanted_tmdb:
                return self._store(key, node)
        for node in candidates:
            content = node.get("content")
            external = content.get("externalIds") if isinstance(content, dict) else None
            if (
                wanted_imdb
                and isinstance(external, dict)
                and str(external.get("imdbId") or "").casefold() == wanted_imdb
            ):
                return self._store(key, node)

        normalized_title = " ".join(title.casefold().split())
        for node in candidates:
            content = node.get("content")
            candidate_title = (
                " ".join(str(content.get("title") or "").casefold().split())
                if isinstance(content, dict)
                else ""
            )
            if candidate_title == normalized_title:
                return self._store(key, node)

        result = candidates[0] if candidates else None
        return self._store(key, result or {})

    async def _season_id(
        self,
        *,
        show_id: str,
        season: int,
        country: str,
        language: str,
    ) -> str | None:
        key = ("season", show_id, int(season), country, language)
        cached = self._cached(key)
        if cached is not None:
            return str(cached) or None

        body = await self._post(
            operation_name="NuvioSeasons",
            query=_SEASONS_QUERY,
            variables={
                "nodeId": show_id,
                "country": country,
                "language": language,
            },
        )
        node = (body.get("data") or {}).get("node") or {}
        seasons = node.get("seasons") if isinstance(node, dict) else []
        for raw in seasons if isinstance(seasons, list) else []:
            if not isinstance(raw, dict):
                continue
            content = raw.get("content")
            try:
                season_number = int(
                    content.get("seasonNumber")
                    if isinstance(content, dict)
                    else -1
                )
            except (TypeError, ValueError):
                continue
            if season_number == int(season):
                season_id = str(raw.get("id") or "")
                return self._store(key, season_id)

        return self._store(key, "")

    async def _episode_offers(
        self,
        *,
        season_id: str,
        episode: int,
        country: str,
        language: str,
    ) -> list[dict[str, Any]]:
        key = ("episode", season_id, int(episode), country, language)
        cached = self._cached(key)
        if cached is not None:
            return list(cached)

        body = await self._post(
            operation_name="NuvioEpisodes",
            query=_EPISODES_QUERY,
            variables={
                "nodeId": season_id,
                "country": country,
                "language": language,
                "filter": {"bestOnly": True},
            },
        )
        node = (body.get("data") or {}).get("node") or {}
        episodes = node.get("episodes") if isinstance(node, dict) else []
        for raw in episodes if isinstance(episodes, list) else []:
            if not isinstance(raw, dict):
                continue
            content = raw.get("content")
            try:
                episode_number = int(
                    content.get("episodeNumber")
                    if isinstance(content, dict)
                    else -1
                )
            except (TypeError, ValueError):
                continue
            if episode_number == int(episode):
                result = self._offers(raw.get("offers"))
                return self._store(key, result)

        return self._store(key, [])

    async def async_provider_offers(
        self,
        *,
        media_type: str,
        title: str,
        country: str,
        language: str | None = None,
        tmdb_id: int | str | None = None,
        imdb_id: str | None = None,
        season: int | None = None,
        episode: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return direct provider URLs for the exact movie or episode.

        For series episodes, only episode-level offers are returned. We deliberately
        avoid silently falling back to show-level URLs here; TheTVDB/WatchHub handle
        lower-confidence fallbacks separately.
        """
        title = " ".join(str(title or "").split())
        if not title:
            return []

        country = str(country or "US").upper()
        language = self._language(language)
        cache_key = (
            "offers",
            media_type,
            title.casefold(),
            country,
            language,
            str(tmdb_id or ""),
            str(imdb_id or "").casefold(),
            season,
            episode,
        )
        cached = self._cached(cache_key)
        if cached is not None:
            return list(cached)

        node = await self._search_title(
            title=title,
            media_type=media_type,
            country=country,
            language=language,
            tmdb_id=tmdb_id,
            imdb_id=imdb_id,
        )
        if not node:
            return self._store(cache_key, [])

        if media_type != "series":
            return self._store(cache_key, self._offers(node.get("offers")))

        if season is None or episode is None:
            # A show-level offer is still useful outside an episode context.
            return self._store(cache_key, self._offers(node.get("offers")))

        show_id = str(node.get("id") or "")
        if not show_id:
            return self._store(cache_key, [])
        season_id = await self._season_id(
            show_id=show_id,
            season=int(season),
            country=country,
            language=language,
        )
        if not season_id:
            return self._store(cache_key, [])
        offers = await self._episode_offers(
            season_id=season_id,
            episode=int(episode),
            country=country,
            language=language,
        )
        return self._store(cache_key, offers)
