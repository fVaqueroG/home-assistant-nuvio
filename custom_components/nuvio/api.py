"""Small async client for the Stremio addon protocol used by Nuvio."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

from aiohttp import ClientError, ClientSession


class NuvioApiError(Exception):
    """Raised when an addon cannot be queried."""


@dataclass(frozen=True, slots=True)
class Addon:
    """An addon manifest and its resource base URL."""

    manifest_url: str
    base_url: str
    manifest: dict[str, Any]

    @property
    def name(self) -> str:
        """Return the addon's display name."""
        return str(self.manifest.get("name") or self.manifest.get("id") or "Addon")


def normalize_manifest_url(value: str) -> str:
    """Validate and normalize an addon manifest URL."""
    value = value.strip()
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("Manifest URLs must use http or https")
    path = parts.path.rstrip("/")
    if not path.endswith("manifest.json"):
        path = f"{path}/manifest.json"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def addon_base_url(manifest_url: str) -> str:
    """Return the resource root adjacent to manifest.json."""
    parts = urlsplit(manifest_url)
    path = parts.path.rsplit("/", 1)[0]
    return urlunsplit((parts.scheme, parts.netloc, path, "", "")).rstrip("/")


class NuvioApi:
    """Read addon manifests, catalogs, metadata, and search results."""

    def __init__(self, session: ClientSession, manifest_urls: list[str]) -> None:
        self._session = session
        self.manifest_urls = [normalize_manifest_url(url) for url in manifest_urls]
        self._addons: list[Addon] | None = None
        self._catalog_cache: dict[tuple[str, str, str, str | None], tuple[float, list[dict[str, Any]]]] = {}
        self._catalog_ttl = 60.0

    async def _get_json(self, url: str) -> dict[str, Any]:
        try:
            async with self._session.get(url, timeout=20) as response:
                response.raise_for_status()
                data = await response.json(content_type=None)
        except (ClientError, TimeoutError, ValueError) as err:
            raise NuvioApiError(f"Could not load {url}: {err}") from err
        if not isinstance(data, dict):
            raise NuvioApiError(f"Unexpected response from {url}")
        return data

    async def async_addons(self, *, refresh: bool = False) -> list[Addon]:
        """Load configured addon manifests."""
        if self._addons is not None and not refresh:
            return self._addons
        async def load_manifest(manifest_url: str):
            try:
                manifest = await self._get_json(manifest_url)
                return Addon(manifest_url, addon_base_url(manifest_url), manifest), None
            except NuvioApiError as err:
                return None, str(err)

        loaded = await asyncio.gather(
            *(load_manifest(manifest_url) for manifest_url in self.manifest_urls)
        )
        addons = [addon for addon, _ in loaded if addon is not None]
        errors = [error for _, error in loaded if error]
        if not addons:
            raise NuvioApiError("; ".join(errors) or "No addon manifests configured")
        self._addons = addons
        return addons

    async def async_catalog(
        self,
        addon: Addon,
        media_type: str,
        catalog_id: str,
        *,
        extra: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return catalog metas."""
        cache_key = (addon.manifest_url, media_type, catalog_id, extra)
        cached = self._catalog_cache.get(cache_key)
        now = time.monotonic()
        if cached is not None and now - cached[0] < self._catalog_ttl:
            return cached[1]

        path = f"catalog/{quote(media_type, safe='')}/{quote(catalog_id, safe='')}"
        if extra:
            path += f"/{extra}"
        data = await self._get_json(f"{addon.base_url}/{path}.json")
        metas = [meta for meta in data.get("metas", []) if isinstance(meta, dict)]
        self._catalog_cache[cache_key] = (now, metas)
        return metas

    async def async_meta(
        self, addon: Addon, media_type: str, content_id: str
    ) -> dict[str, Any]:
        """Return full metadata for a title."""
        url = (
            f"{addon.base_url}/meta/{quote(media_type, safe='')}/"
            f"{quote(content_id, safe='')}.json"
        )
        data = await self._get_json(url)
        meta = data.get("meta")
        if not isinstance(meta, dict):
            raise NuvioApiError("Addon returned no metadata")
        return meta

    async def async_search(self, text: str) -> list[tuple[Addon, dict[str, Any]]]:
        """Search all catalogs that advertise the search extra."""
        tasks: list[tuple[Addon, str, str]] = []
        for addon in await self.async_addons():
            for catalog in addon.manifest.get("catalogs", []):
                if not isinstance(catalog, dict):
                    continue
                extras = catalog.get("extra", [])
                if not any(
                    isinstance(extra, dict) and extra.get("name") == "search"
                    for extra in extras
                ):
                    continue
                media_type = str(catalog.get("type", ""))
                catalog_id = str(catalog.get("id", ""))
                if media_type and catalog_id:
                    tasks.append((addon, media_type, catalog_id))

        async def run_search(addon: Addon, media_type: str, catalog_id: str):
            try:
                metas = await self.async_catalog(
                    addon,
                    media_type,
                    catalog_id,
                    extra=f"search={quote(text, safe='')}",
                )
                return addon, media_type, metas
            except NuvioApiError:
                return addon, media_type, []

        batches = await asyncio.gather(
            *(run_search(addon, media_type, catalog_id) for addon, media_type, catalog_id in tasks)
        )

        results: list[tuple[Addon, dict[str, Any]]] = []
        seen: set[tuple[str, str]] = set()
        for addon, media_type, metas in batches:
            for meta in metas:
                key = (str(meta.get("type", media_type)), str(meta.get("id", "")))
                if not key[1] or key in seen:
                    continue
                seen.add(key)
                results.append((addon, meta))
        return results
