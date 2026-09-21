"""Resolve missing Continue Watching display metadata without changing playback IDs."""

from __future__ import annotations

import asyncio
import re
from typing import Any


_IMDB_ID = re.compile(r"^tt\d+(?::\d+:\d+)?$", re.IGNORECASE)


def missing_title(item: dict[str, Any]) -> bool:
    """A synced watch-progress content ID is not a human-readable title."""
    name = str(item.get("name") or "").strip()
    content_id = str(item.get("id") or "").strip()
    return not name or name.casefold() == content_id.casefold() or bool(_IMDB_ID.fullmatch(name))


def _usable_title(meta: dict[str, Any], content_id: str) -> str:
    for key in ("name", "title", "originalTitle", "original_title", "original_name"):
        value = meta.get(key)
        if not isinstance(value, str):
            continue
        name = value.strip()
        if name and name.casefold() != content_id.casefold() and not _IMDB_ID.fullmatch(name):
            return name
    return ""


def _metadata_from(meta: dict[str, Any], content_id: str) -> dict[str, Any]:
    title = _usable_title(meta, content_id)
    if not title:
        return {}
    return {
        "name": title,
        "poster": meta.get("poster") or meta.get("poster_url"),
        "background": meta.get("background") or meta.get("backdrop"),
        "logo": meta.get("logo"),
        "description": meta.get("description") or meta.get("overview"),
        "releaseInfo": meta.get("releaseInfo") or meta.get("release_info"),
    }


def _meta_addons(addons: list[Any], item: dict[str, Any]) -> list[Any]:
    """Use the app's configured metadata addons, not arbitrary stream addons."""
    content_id = str(item.get("id") or "").split(":", 1)[0]
    media_type = str(item.get("type") or "movie").casefold()
    type_aliases = {"series", "tv", "anime"} if media_type in {"series", "tv", "anime"} else {"movie"}
    preferred = str(item.get("manifest_url") or "").strip()
    matches: list[Any] = []
    for addon in addons:
        manifest = getattr(addon, "manifest", {}) or {}
        resources = manifest.get("resources") or []
        relevant = False
        for resource in resources:
            if isinstance(resource, str):
                if resource.casefold() == "meta":
                    relevant = True
                    break
            elif isinstance(resource, dict) and str(resource.get("name") or "").casefold() == "meta":
                advertised = resource.get("types")
                if not advertised or type_aliases.intersection(str(t).casefold() for t in advertised):
                    relevant = True
                    break
        if not relevant:
            continue
        prefixes = manifest.get("idPrefixes") or manifest.get("id_prefixes") or []
        if isinstance(prefixes, list) and prefixes and not any(
            content_id.casefold().startswith(str(prefix).casefold()) for prefix in prefixes
        ):
            continue
        matches.append(addon)
    matches.sort(key=lambda addon: (
        0 if getattr(addon, "manifest_url", "") == preferred else 1,
        0 if "cinemeta" in str(getattr(addon, "name", "")).casefold() else 1,
    ))
    return matches


async def enrich_continue_watching(
    items: list[dict[str, Any]],
    *,
    api: Any,
    addons: list[Any],
    tmdb_api: Any = None,
    catalog_items: list[dict[str, Any]] | None = None,
    budget: float = 5.0,
) -> None:
    """Populate missing movie/show titles using catalog, addon and TMDB metadata.

    Keep ID/type/video_id/season/episode and progress intact; the display title
    is never used to identify a stream. All external lookups are bounded so Home
    does not stall when an addon is offline. Calls use the account's existing
    configured metadata sources and optional TMDB client.
    """
    missing = [item for item in items if missing_title(item) and item.get("id")]
    if not missing:
        return

    # Home has already fetched some catalogs; reuse their full metadata first.
    catalog_index: dict[str, dict[str, Any]] = {}
    for candidate in catalog_items or []:
        content_id = str(candidate.get("id") or "")
        if content_id and content_id not in catalog_index:
            found = _metadata_from(candidate, content_id)
            if found:
                catalog_index[content_id] = found
    remaining: list[dict[str, Any]] = []
    for item in missing:
        metadata = catalog_index.get(str(item["id"]))
        if metadata:
            _merge(item, metadata)
        else:
            remaining.append(item)
    if not remaining:
        return

    semaphore = asyncio.Semaphore(12)
    lookups: dict[tuple[str, str], asyncio.Task[dict[str, Any]]] = {}

    async def lookup(item: dict[str, Any]) -> dict[str, Any]:
        content_id = str(item["id"])
        lookup_id = content_id.split(":", 1)[0]
        media_type = str(item.get("type") or "movie").casefold()
        types = ["series", "tv"] if media_type in {"series", "tv", "anime"} else ["movie"]
        async with semaphore:
            # Try the metadata addons available in Nuvio. Prefer the linked
            # source and Cinemeta before trying other metadata providers.
            for addon in _meta_addons(addons, item)[:3]:
                for kind in types:
                    try:
                        meta = await asyncio.wait_for(api.async_meta(addon, kind, lookup_id), timeout=1.25)
                    except Exception:
                        continue
                    if isinstance(meta, dict):
                        result = _metadata_from(meta, content_id)
                        if result:
                            return result
            # The configured TMDB integration can recover titles for IMDb IDs
            # even when the active Nuvio addons lack a metadata resource.
            if tmdb_api is not None and getattr(tmdb_api, "configured", False) and re.fullmatch(r"tt\d+", lookup_id, re.IGNORECASE):
                try:
                    meta = await asyncio.wait_for(tmdb_api.async_title_metadata(types[0], lookup_id), timeout=1.75)
                except Exception:
                    return {}
                if isinstance(meta, dict):
                    return _metadata_from(meta, content_id)
        return {}

    for item in remaining:
        key = (str(item.get("type") or "movie").casefold(), str(item["id"]))
        if key not in lookups:
            lookups[key] = asyncio.create_task(lookup(item))
    done, pending = await asyncio.wait(list(lookups.values()), timeout=budget)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    results: dict[tuple[str, str], dict[str, Any]] = {}
    for key, task in lookups.items():
        if task not in done:
            continue
        try:
            results[key] = task.result()
        except Exception:
            continue
    for item in remaining:
        key = (str(item.get("type") or "movie").casefold(), str(item["id"]))
        if results.get(key):
            _merge(item, results[key])


def _merge(item: dict[str, Any], metadata: dict[str, Any]) -> None:
    if missing_title(item):
        item["name"] = metadata["name"]
    for key in ("poster", "background", "logo", "description", "releaseInfo"):
        if not item.get(key) and metadata.get(key):
            item[key] = metadata[key]
