"""Frontend API and bundled Lovelace card for Nuvio."""

from __future__ import annotations

import asyncio
from pathlib import Path
import re
import time
from typing import Any

import probatio
from homeassistant.components import frontend, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import (
    CONF_RESOURCE_TYPE_WS,
    LOVELACE_DATA,
    MODE_STORAGE,
)
from homeassistant.const import CONF_ID, CONF_TYPE, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

from .account import NuvioAuthError
from .api import Addon, NuvioApiError
from .const import CONF_PROFILE_ID, DATA_ACCOUNT_API, DATA_API, DOMAIN

CARD_URL = "/nuvio/nuvio-card.js"
CARD_VERSION = "0.3.8"
CARD_RESOURCE_URL = f"{CARD_URL}?v={CARD_VERSION}"
CARD_FILE = Path(__file__).parent / "frontend" / "nuvio-card.js"
DATA_FRONTEND_REGISTERED = "frontend_registered"
DATA_HOME_CACHE = "home_cache"
HOME_CACHE_TTL = 30.0


def _entry(hass: HomeAssistant):
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise NuvioApiError("Nuvio is not configured")
    return entries[0]


def _item(meta: dict[str, Any], media_type: str, manifest_url: str | None = None) -> dict[str, Any]:
    result = {
        "id": str(meta.get("id") or meta.get("content_id") or ""),
        "type": str(meta.get("type") or meta.get("content_type") or media_type),
        "name": str(meta.get("name") or meta.get("title") or meta.get("content_id") or ""),
        "poster": meta.get("poster"),
        "background": meta.get("background") or meta.get("backdrop"),
        "logo": meta.get("logo"),
        "description": meta.get("description"),
        "releaseInfo": meta.get("releaseInfo") or meta.get("release_info"),
        "genres": meta.get("genres") or [],
        "manifest_url": manifest_url,
    }
    return result


async def _home(hass: HomeAssistant, *, refresh: bool = False) -> dict[str, Any]:
    domain_data = hass.data.setdefault(DOMAIN, {})
    cached = domain_data.get(DATA_HOME_CACHE)
    now = time.monotonic()
    if not refresh and cached is not None and now - cached[0] < HOME_CACHE_TTL:
        return cached[1]

    entry = _entry(hass)
    api = entry.runtime_data[DATA_API]
    account = entry.runtime_data.get(DATA_ACCOUNT_API)
    sections: list[dict[str, Any]] = []

    if account is not None:
        profile_id = int(entry.data.get(CONF_PROFILE_ID, 1))
        try:
            library, progress = await asyncio.gather(
                account.async_library(profile_id),
                account.async_watch_progress(profile_id),
            )
            lib_index = {
                (str(x.get("content_type")), str(x.get("content_id"))): x for x in library
            }
            active = [
                p for p in progress
                if int(p.get("duration") or 0) > 0
                and int(p.get("position") or 0) < int(p.get("duration") or 0) * 0.95
            ]
            active.sort(key=lambda x: int(x.get("last_watched") or 0), reverse=True)
            continue_items = []
            for p in active[:20]:
                media_type = str(p.get("content_type") or "movie")
                content_id = str(p.get("content_id") or "")
                meta = lib_index.get((media_type, content_id), {})
                addon_base = meta.get("addon_base_url")
                item = _item(
                    {**meta, "id": content_id, "type": media_type},
                    media_type,
                    f"{str(addon_base).rstrip('/')}/manifest.json" if addon_base else None,
                )
                item.update({
                    "season": p.get("season"),
                    "episode": p.get("episode"),
                    "video_id": p.get("video_id"),
                    "position": p.get("position"),
                    "duration": p.get("duration"),
                })
                continue_items.append(item)
            if continue_items:
                sections.append({"id": "continue", "name": "Continue Watching", "items": continue_items})

            library_items = []
            for meta in sorted(library, key=lambda x: int(x.get("added_at") or 0), reverse=True)[:30]:
                media_type = str(meta.get("content_type") or "movie")
                addon_base = meta.get("addon_base_url")
                library_items.append(_item(
                    meta,
                    media_type,
                    f"{str(addon_base).rstrip('/')}/manifest.json" if addon_base else None,
                ))
            if library_items:
                sections.append({"id": "library", "name": "My Library", "items": library_items})
        except NuvioAuthError:
            pass

    catalog_specs: list[tuple[Addon, dict[str, Any], str, str]] = []
    for addon in await api.async_addons():
        for catalog in addon.manifest.get("catalogs", []):
            if not isinstance(catalog, dict):
                continue
            media_type = str(catalog.get("type") or "")
            catalog_id = str(catalog.get("id") or "")
            if media_type in {"movie", "series"} and catalog_id:
                catalog_specs.append((addon, catalog, media_type, catalog_id))

    semaphore = asyncio.Semaphore(8)

    async def load_section(
        addon: Addon,
        catalog: dict[str, Any],
        media_type: str,
        catalog_id: str,
    ) -> dict[str, Any] | None:
        try:
            async with semaphore:
                metas = await api.async_catalog(addon, media_type, catalog_id)
        except NuvioApiError:
            return None
        items = [_item(meta, media_type, addon.manifest_url) for meta in metas[:20]]
        if not items:
            return None
        return {
            "id": f"{addon.name}:{media_type}:{catalog_id}",
            "name": str(catalog.get("name") or catalog_id),
            "addon": addon.name,
            "media_type": media_type,
            "items": items,
        }

    catalog_sections = await asyncio.gather(
        *(
            load_section(addon, catalog, media_type, catalog_id)
            for addon, catalog, media_type, catalog_id in catalog_specs
        )
    )
    sections.extend(section for section in catalog_sections if section is not None)
    registry = async_get_entity_registry(hass)
    players: list[dict[str, Any]] = []
    for entity in registry.entities.values():
        if entity.domain != "media_player" or entity.platform not in {"androidtv", "androidtv_remote", "webostv"}:
            continue
        state = hass.states.get(entity.entity_id)
        if state is None:
            continue
        players.append(
            {
                "entity_id": entity.entity_id,
                "platform": entity.platform,
                "name": str(state.attributes.get("friendly_name") or entity.entity_id),
            }
        )
    players.sort(key=lambda value: value["name"].casefold())
    result = {"sections": sections, "players": players}
    domain_data[DATA_HOME_CACHE] = (now, result)
    return result


@websocket_api.websocket_command({
    probatio.Required("type"): "nuvio/home",
    probatio.Optional("refresh", default=False): bool,
})
@websocket_api.async_response
async def ws_home(hass, connection, msg) -> None:
    try:
        connection.send_result(msg["id"], await _home(hass, refresh=msg["refresh"]))
    except (NuvioApiError, NuvioAuthError) as err:
        connection.send_error(msg["id"], "nuvio_error", str(err))


@websocket_api.websocket_command({
    probatio.Required("type"): "nuvio/search",
    probatio.Required("query"): str,
})
@websocket_api.async_response
async def ws_search(hass, connection, msg) -> None:
    try:
        api = _entry(hass).runtime_data[DATA_API]
        results = await api.async_search(msg["query"])
        connection.send_result(msg["id"], {
            "items": [_item(meta, str(meta.get("type") or "movie"), addon.manifest_url)
                      for addon, meta in results[:80]]
        })
    except (NuvioApiError, NuvioAuthError) as err:
        connection.send_error(msg["id"], "nuvio_error", str(err))



def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _format_bytes(value: Any) -> str | None:
    try:
        size = int(value)
    except (TypeError, ValueError):
        return None
    if size <= 0:
        return None
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(size)
    unit = units[0]
    for candidate in units:
        unit = candidate
        if amount < 1024 or candidate == units[-1]:
            break
        amount /= 1024
    if unit in {"GB", "TB"}:
        return f"{amount:.1f} {unit}"
    if unit == "MB":
        return f"{amount:.0f} {unit}"
    return f"{amount:.0f} {unit}"


def _stream_presentation(
    stream: dict[str, Any],
    behavior: dict[str, Any],
    client_resolve: dict[str, Any],
) -> dict[str, Any]:
    """Normalize useful source metadata into compact Nuvio-like badges."""
    resolve_stream = _as_dict(client_resolve.get("stream"))
    raw = _as_dict(resolve_stream.get("raw"))
    parsed = _as_dict(raw.get("parsed"))

    filename = (
        behavior.get("filename")
        or client_resolve.get("filename")
        or raw.get("filename")
    )
    searchable = " ".join(
        str(value)
        for value in (
            stream.get("name"),
            stream.get("title"),
            stream.get("description"),
            filename,
            parsed.get("raw_title"),
            parsed.get("rawTitle"),
            parsed.get("parsed_title"),
            parsed.get("parsedTitle"),
            parsed.get("quality"),
            parsed.get("resolution"),
            parsed.get("codec"),
        )
        if value
    )
    lowered = searchable.casefold()

    badges: list[dict[str, str]] = []
    seen: set[str] = set()

    def add_badge(label: Any, kind: str) -> None:
        text = str(label or "").strip()
        key = text.casefold()
        if not text or key in seen:
            return
        seen.add(key)
        badges.append({"label": text, "kind": kind})

    resolution = str(parsed.get("resolution") or "").strip()
    if not resolution:
        resolution_match = re.search(
            r"(?<!\d)(4320p|8k|2160p|4k|1080p|720p|576p|480p)(?!\d)",
            lowered,
            re.IGNORECASE,
        )
        if resolution_match:
            resolution = resolution_match.group(1)
    resolution_map = {
        "4320p": "8K",
        "8k": "8K",
        "2160p": "4K",
        "4k": "4K",
        "1080p": "1080p",
        "720p": "720p",
        "576p": "576p",
        "480p": "480p",
    }
    if resolution:
        add_badge(resolution_map.get(resolution.casefold(), resolution), "resolution")

    quality = str(parsed.get("quality") or "").strip()
    if not quality:
        quality_patterns = (
            (r"\b(remux)\b", "REMUX"),
            (r"\b(uhd[ ._-]?blu[ ._-]?ray|blu[ ._-]?ray|bluray|bdrip|brrip)\b", "BluRay"),
            (r"\b(web[ ._-]?dl)\b", "WEB-DL"),
            (r"\b(web[ ._-]?rip)\b", "WEBRip"),
            (r"\b(hd[ ._-]?rip|hdrip)\b", "HDRip"),
            (r"\b(dvdrip|dvd)\b", "DVD"),
            (r"\b(telesync|\bts\b)\b", "TS"),
            (r"\b(camrip|\bcam\b)\b", "CAM"),
        )
        for pattern, label in quality_patterns:
            if re.search(pattern, lowered, re.IGNORECASE):
                quality = label
                break
    if quality:
        add_badge(quality, "source")

    hdr_values = _string_list(parsed.get("hdr"))
    if hdr_values:
        for hdr in hdr_values[:3]:
            normalized = {
                "dolby vision": "DV",
                "dolbyvision": "DV",
                "hdr10plus": "HDR10+",
                "hdr10+": "HDR10+",
            }.get(hdr.casefold(), hdr)
            add_badge(normalized, "hdr")
    else:
        if re.search(r"\b(dolby[ ._-]?vision|dovi|dv)\b", lowered, re.IGNORECASE):
            add_badge("DV", "hdr")
        if re.search(r"\bhdr10\+\b|\bhdr10plus\b", lowered, re.IGNORECASE):
            add_badge("HDR10+", "hdr")
        elif re.search(r"\bhdr10\b", lowered, re.IGNORECASE):
            add_badge("HDR10", "hdr")
        elif re.search(r"\bhdr\b", lowered, re.IGNORECASE):
            add_badge("HDR", "hdr")

    bit_depth = parsed.get("bit_depth") or parsed.get("bitDepth")
    if bit_depth:
        add_badge(str(bit_depth), "hdr")
    elif re.search(r"\b10[ ._-]?bit\b", lowered, re.IGNORECASE):
        add_badge("10-bit", "hdr")

    codec = str(parsed.get("codec") or "").strip()
    if not codec:
        codec_patterns = (
            (r"\b(av1)\b", "AV1"),
            (r"\b(hevc|h[ ._-]?265|x265)\b", "HEVC"),
            (r"\b(avc|h[ ._-]?264|x264)\b", "AVC"),
            (r"\b(vp9)\b", "VP9"),
        )
        for pattern, label in codec_patterns:
            if re.search(pattern, lowered, re.IGNORECASE):
                codec = label
                break
    if codec:
        add_badge(codec.upper() if codec.casefold() in {"av1", "vp9"} else codec, "codec")

    audio_values = _string_list(parsed.get("audio"))
    if audio_values:
        for audio in audio_values[:2]:
            add_badge(audio, "audio")
    else:
        audio_patterns = (
            (r"\batmos\b", "Atmos"),
            (r"\btruehd\b", "TrueHD"),
            (r"\bdts[ ._-]?(?:hd|x|ma)\b", "DTS-HD"),
            (r"\bdts\b", "DTS"),
            (r"\b(eac3|e-ac-3|ddp|dd\+)\b", "DD+"),
            (r"\b(ac3|ac-3)\b", "AC3"),
            (r"\bflac\b", "FLAC"),
            (r"\baac\b", "AAC"),
        )
        for pattern, label in audio_patterns:
            if re.search(pattern, lowered, re.IGNORECASE):
                add_badge(label, "audio")

    for channel in _string_list(parsed.get("channels"))[:1]:
        add_badge(channel, "audio")

    for language in _string_list(parsed.get("languages"))[:3]:
        add_badge(language.upper() if len(language) <= 3 else language, "language")

    size_bytes = (
        behavior.get("videoSize")
        or behavior.get("video_size")
        or raw.get("size")
        or raw.get("folderSize")
        or raw.get("folder_size")
    )
    size_label = _format_bytes(size_bytes)
    if size_label:
        add_badge(size_label, "size")

    return {
        "badges": badges[:12],
        "size_bytes": size_bytes,
        "size_label": size_label,
        "quality": quality or None,
        "resolution": resolution_map.get(resolution.casefold(), resolution) if resolution else None,
        "filename": filename,
    }


@websocket_api.websocket_command({
    probatio.Required("type"): "nuvio/streams",
    probatio.Required("media_type"): probatio.In(["movie", "series"]),
    probatio.Required("video_id"): str,
})
@websocket_api.async_response
async def ws_streams(hass, connection, msg) -> None:
    """Return selectable streams for one movie or episode."""
    try:
        api = _entry(hass).runtime_data[DATA_API]
        rows = []
        for addon, stream in await api.async_all_streams(
            msg["media_type"], msg["video_id"]
        ):
            behavior = stream.get("behaviorHints")
            if not isinstance(behavior, dict):
                behavior = {}
            client_resolve = stream.get("clientResolve")
            if not isinstance(client_resolve, dict):
                client_resolve = {}

            direct_url = None
            for candidate in (stream.get("url"), stream.get("externalUrl")):
                if not isinstance(candidate, str):
                    continue
                stripped = candidate.lstrip().lower()
                if stripped.startswith(("http://", "https://")):
                    direct_url = candidate
                    break

            proxy_headers = behavior.get("proxyHeaders")
            if not isinstance(proxy_headers, dict):
                proxy_headers = {}
            request_headers = proxy_headers.get("request")
            if not isinstance(request_headers, dict):
                request_headers = {}

            presentation = _stream_presentation(stream, behavior, client_resolve)
            rows.append(
                {
                    "addon": addon.name,
                    "addon_logo": addon.manifest.get("logo"),
                    "name": stream.get("name"),
                    "title": stream.get("title"),
                    "description": stream.get("description"),
                    "url": direct_url,
                    "info_hash": stream.get("infoHash")
                    or client_resolve.get("infoHash"),
                    "magnet_uri": client_resolve.get("magnetUri"),
                    "torrent_sources": client_resolve.get("sources")
                    or stream.get("sources")
                    or [],
                    "file_idx": stream.get("fileIdx")
                    if stream.get("fileIdx") is not None
                    else client_resolve.get("fileIdx"),
                    "filename": presentation["filename"],
                    "binge_group": behavior.get("bingeGroup"),
                    "badges": presentation["badges"],
                    "size_bytes": presentation["size_bytes"],
                    "size_label": presentation["size_label"],
                    "quality": presentation["quality"],
                    "resolution": presentation["resolution"],
                    "requires_headers": bool(request_headers),
                    "direct": bool(direct_url) and not request_headers,
                }
            )

        connection.send_result(msg["id"], {"streams": rows})
    except (NuvioApiError, NuvioAuthError) as err:
        connection.send_error(msg["id"], "nuvio_error", str(err))


@websocket_api.websocket_command({
    probatio.Required("type"): "nuvio/details",
    probatio.Required("manifest_url"): str,
    probatio.Required("media_type"): probatio.In(["movie", "series"]),
    probatio.Required("content_id"): str,
})
@websocket_api.async_response
async def ws_details(hass, connection, msg) -> None:
    try:
        api = _entry(hass).runtime_data[DATA_API]
        addon: Addon | None = None
        for candidate in await api.async_addons():
            if candidate.manifest_url == msg["manifest_url"]:
                addon = candidate
                break
        if addon is None:
            raise NuvioApiError("The addon for this title is no longer configured")
        meta = await api.async_meta(addon, msg["media_type"], msg["content_id"])
        result = _item(meta, msg["media_type"], addon.manifest_url)
        result["videos"] = [
            {
                "id": str(v.get("id") or ""),
                "title": str(v.get("title") or ""),
                "season": v.get("season"),
                "episode": v.get("episode"),
                "thumbnail": v.get("thumbnail"),
                "overview": v.get("overview") or v.get("description"),
            }
            for v in meta.get("videos", [])
            if isinstance(v, dict)
        ]
        connection.send_result(msg["id"], result)
    except (NuvioApiError, NuvioAuthError) as err:
        connection.send_error(msg["id"], "nuvio_error", str(err))


async def _async_register_lovelace_resource(hass: HomeAssistant) -> None:
    """Ensure the bundled card is a Lovelace module resource in storage mode."""
    lovelace = hass.data.get(LOVELACE_DATA)
    if lovelace is None or lovelace.resource_mode != MODE_STORAGE:
        return

    resource_collection = lovelace.resources
    await resource_collection.async_get_info()
    resources = resource_collection.async_items() or []

    for resource in resources:
        url = str(resource.get(CONF_URL) or "")
        if url.split("?", 1)[0] != CARD_URL:
            continue

        if (
            url != CARD_RESOURCE_URL
            or resource.get(CONF_TYPE) != "module"
        ):
            await resource_collection.async_update_item(
                resource[CONF_ID],
                {
                    CONF_URL: CARD_RESOURCE_URL,
                    CONF_RESOURCE_TYPE_WS: "module",
                },
            )
        return

    await resource_collection.async_create_item(
        {
            CONF_URL: CARD_RESOURCE_URL,
            CONF_RESOURCE_TYPE_WS: "module",
        }
    )


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Register the Nuvio card, APIs, and Lovelace resource."""
    data = hass.data.setdefault(DOMAIN, {})
    if data.get(DATA_FRONTEND_REGISTERED):
        return

    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(CARD_FILE), cache_headers=False)]
    )

    # Extra-module registration makes the card available outside Lovelace too,
    # while the Lovelace resource below makes dashboard loading deterministic.
    frontend.add_extra_js_url(hass, CARD_RESOURCE_URL)
    await _async_register_lovelace_resource(hass)

    websocket_api.async_register_command(hass, ws_home)
    websocket_api.async_register_command(hass, ws_search)
    websocket_api.async_register_command(hass, ws_streams)
    websocket_api.async_register_command(hass, ws_details)
    data[DATA_FRONTEND_REGISTERED] = True
