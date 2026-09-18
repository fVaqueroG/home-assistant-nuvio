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
        self._addons_load_task: asyncio.Task[list[Addon]] | None = None
        self._catalog_cache: dict[tuple[str, str, str, str | None], tuple[float, list[dict[str, Any]]]] = {}
        self._meta_cache: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}
        self._catalog_ttl = 300.0
        self._meta_ttl = 300.0
        self._watchhub_country_host_failures: set[str] = set()

    async def _get_json(self, url: str, *, timeout: float = 20) -> dict[str, Any]:
        try:
            async with self._session.get(url, timeout=timeout) as response:
                response.raise_for_status()
                data = await response.json(content_type=None)
        except (ClientError, TimeoutError, ValueError) as err:
            raise NuvioApiError(f"Could not load {url}: {err}") from err
        if not isinstance(data, dict):
            raise NuvioApiError(f"Unexpected response from {url}")
        return data

    async def async_addons(self, *, refresh: bool = False) -> list[Addon]:
        """Load configured addon manifests without cancelling shared discovery."""
        cached_by_url = {addon.manifest_url: addon for addon in self._addons or []}
        if not refresh and all(url in cached_by_url for url in self.manifest_urls):
            return [cached_by_url[url] for url in self.manifest_urls]

        async def load_all() -> list[Addon]:
            starting_cache = {
                addon.manifest_url: addon for addon in self._addons or []
            }

            async def load_manifest(manifest_url: str):
                if not refresh and manifest_url in starting_cache:
                    return starting_cache[manifest_url], None
                try:
                    manifest = await self._get_json(manifest_url)
                    addon = Addon(
                        manifest_url,
                        addon_base_url(manifest_url),
                        manifest,
                    )
                    # Publish each completed manifest immediately. Home can use
                    # partial discovery while slower manifests keep loading.
                    by_url = {
                        item.manifest_url: item for item in self._addons or []
                    }
                    by_url[manifest_url] = addon
                    self._addons = [
                        by_url[url] for url in self.manifest_urls if url in by_url
                    ]
                    return addon, None
                except NuvioApiError as err:
                    return None, str(err)

            loaded = await asyncio.gather(
                *(load_manifest(manifest_url) for manifest_url in self.manifest_urls)
            )
            by_url = {item.manifest_url: item for item in self._addons or []}
            errors: list[str] = []
            for addon, error in loaded:
                if addon is not None:
                    by_url[addon.manifest_url] = addon
                if error:
                    errors.append(error)
            addons = [by_url[url] for url in self.manifest_urls if url in by_url]
            if not addons:
                raise NuvioApiError(
                    "; ".join(errors) or "No addon manifests configured"
                )
            self._addons = addons
            return addons

        task = self._addons_load_task
        if task is None or task.done():
            task = asyncio.create_task(load_all())
            # Home uses a short timeout around async_addons(). Shielding below
            # means that timeout cancels only the waiter, not this shared task.
            # Retrieve a terminal exception even if no later caller awaits it.
            task.add_done_callback(
                lambda done: None if done.cancelled() else done.exception()
            )
            self._addons_load_task = task

        return await asyncio.shield(task)

    @property
    def cached_addons(self) -> list[Addon]:
        """Return manifests already loaded, including partial discovery."""
        return list(self._addons or [])

    def clear_catalog_cache(self) -> None:
        """Drop cached catalog pages so a manual Home refresh is truly fresh."""
        self._catalog_cache.clear()

    async def async_catalog(
        self,
        addon: Addon,
        media_type: str,
        catalog_id: str,
        *,
        extra: str | None = None,
        refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """Return catalog metas."""
        cache_key = (addon.manifest_url, media_type, catalog_id, extra)
        cached = self._catalog_cache.get(cache_key)
        now = time.monotonic()
        if not refresh and cached is not None and now - cached[0] < self._catalog_ttl:
            return cached[1]

        path = f"catalog/{quote(media_type, safe='')}/{quote(catalog_id, safe='')}"
        if extra:
            path += f"/{extra}"
        data = await self._get_json(f"{addon.base_url}/{path}.json")
        metas = [meta for meta in data.get("metas", []) if isinstance(meta, dict)]
        self._catalog_cache[cache_key] = (now, metas)
        return metas

    async def async_streams(
        self,
        addon: Addon,
        media_type: str,
        video_id: str,
        *,
        watchhub_country: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return stream sources for a video from one addon."""
        path = (
            f"stream/{quote(media_type, safe='')}/"
            f"{quote(video_id, safe=':')}.json"
        )

        addon_id = str(addon.manifest.get("id") or "").strip().casefold()
        is_watchhub = (
            addon_id == "org.stremio.watchhub"
            or "watchhub" in addon.name.casefold()
        )
        country = str(watchhub_country or "").strip().lower()

        # Stremio's own deep-link documentation uses country-specific WatchHub
        # hosts such as watchhub-us.strem.io. Try the selected country first,
        # but cache failures and immediately fall back to the normal endpoint.
        if is_watchhub and country and addon.base_url == "https://watchhub.strem.io":
            country_base = f"https://watchhub-{country}.strem.io"
            if country_base not in self._watchhub_country_host_failures:
                try:
                    data = await self._get_json(
                        f"{country_base}/{path}",
                        timeout=4,
                    )
                except NuvioApiError:
                    self._watchhub_country_host_failures.add(country_base)
                else:
                    streams = data.get("streams", [])
                    return [
                        stream for stream in streams if isinstance(stream, dict)
                    ]

        data = await self._get_json(f"{addon.base_url}/{path}")
        streams = data.get("streams", [])
        return [stream for stream in streams if isinstance(stream, dict)]

    @staticmethod
    def is_watchhub_addon(addon: Addon) -> bool:
        """Return whether an addon is Stremio WatchHub."""
        addon_id = str(addon.manifest.get("id") or "").strip().casefold()
        return (
            addon_id == "org.stremio.watchhub"
            or "watchhub" in addon.name.casefold()
        )

    async def async_all_streams(
        self,
        media_type: str,
        video_id: str,
        *,
        watchhub_country: str | None = None,
        addon_scope: str = "all",
    ) -> list[tuple[Addon, dict[str, Any]]]:
        """Return streams from configured addons for the requested source scope."""

        async def load(addon: Addon) -> tuple[Addon, list[dict[str, Any]]]:
            try:
                return addon, await self.async_streams(
                    addon,
                    media_type,
                    video_id,
                    watchhub_country=watchhub_country,
                )
            except NuvioApiError:
                return addon, []

        addons = await self.async_addons()
        scope = str(addon_scope or "all").strip().casefold()
        if scope == "watchhub":
            addons = [addon for addon in addons if self.is_watchhub_addon(addon)]
        elif scope == "other":
            addons = [addon for addon in addons if not self.is_watchhub_addon(addon)]

        batches = await asyncio.gather(*(load(addon) for addon in addons))
        return [
            (addon, stream)
            for addon, streams in batches
            for stream in streams
        ]

    async def async_meta(
        self, addon: Addon, media_type: str, content_id: str
    ) -> dict[str, Any]:
        """Return full metadata for a title."""
        cache_key = (addon.manifest_url, media_type, content_id)
        cached = self._meta_cache.get(cache_key)
        now = time.monotonic()
        if cached is not None and now - cached[0] < self._meta_ttl:
            return cached[1]

        url = (
            f"{addon.base_url}/meta/{quote(media_type, safe='')}/"
            f"{quote(content_id, safe='')}.json"
        )
        data = await self._get_json(url)
        meta = data.get("meta")
        if not isinstance(meta, dict):
            raise NuvioApiError("Addon returned no metadata")
        self._meta_cache[cache_key] = (now, meta)
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
