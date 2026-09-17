"""Frontend API and bundled Lovelace card for Nuvio."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
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
from .debrid import DebridNotCached, DebridNotConfigured, DebridResolveError
from .const import CONF_PROFILE_ID, DATA_ACCOUNT_API, DATA_API, DATA_DEBRID_RESOLVER, DOMAIN

CARD_URL = "/nuvio/nuvio-card.js"
CARD_VERSION = "0.4.13"
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
    """Map addon/account metadata using the same Home fields Nuvio renders."""
    return {
        "id": str(meta.get("id") or meta.get("content_id") or ""),
        "type": str(meta.get("type") or meta.get("content_type") or media_type),
        "name": str(meta.get("name") or meta.get("title") or meta.get("content_id") or ""),
        "poster": meta.get("poster"),
        "posterShape": meta.get("posterShape") or meta.get("poster_shape"),
        "landscapePoster": meta.get("landscapePoster") or meta.get("landscape_poster"),
        "background": meta.get("background") or meta.get("backdrop"),
        "logo": meta.get("logo"),
        "description": meta.get("description"),
        "releaseInfo": meta.get("releaseInfo") or meta.get("release_info"),
        "released": meta.get("released") or meta.get("release_date"),
        "imdbRating": meta.get("imdbRating") or meta.get("imdb_rating"),
        "runtime": meta.get("runtime"),
        "genres": meta.get("genres") or [],
        "manifest_url": manifest_url,
    }


def _addon_id(addon: Addon) -> str:
    return str(addon.manifest.get("id") or addon.base_url).strip()


def _catalog_key(addon: Addon, media_type: str, catalog_id: str) -> str:
    return f"{_addon_id(addon)}_{media_type}_{catalog_id}"


def _truthy_required(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().casefold() == "true"


def _catalog_should_show_on_home(catalog: dict[str, Any]) -> bool:
    """Mirror Nuvio's catalogShouldShowOnHome()."""
    if "showInHome" in catalog and catalog.get("showInHome") is not True:
        return False
    for extra in catalog.get("extra") or []:
        if not isinstance(extra, dict):
            continue
        if (
            str(extra.get("name") or "").strip().casefold() == "search"
            and _truthy_required(extra.get("isRequired"))
        ):
            return False
    return True


def _decode_synced_value(value: Any) -> Any:
    if (
        isinstance(value, dict)
        and isinstance(value.get("type"), str)
        and "value" in value
    ):
        return value.get("value")
    return value


def _layout_settings(blob: dict[str, Any]) -> dict[str, Any]:
    features = blob.get("features")
    if not isinstance(features, dict):
        return {}
    raw = features.get("layout_settings")
    if not isinstance(raw, dict):
        return {}
    return {str(key): _decode_synced_value(value) for key, value in raw.items()}


def _home_string_list(value: Any) -> list[str]:
    value = _decode_synced_value(value)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if text.startswith("[") and text.endswith("]"):
            try:
                import json
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except (TypeError, ValueError):
                pass
        return [text]
    return []


def _home_catalog_preferences(settings: dict[str, Any]) -> dict[str, Any]:
    """Normalize current and legacy Nuvio Home catalog settings."""
    items = settings.get("items")
    normalized_items: list[dict[str, Any]] = []
    if isinstance(items, list):
        for fallback_order, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            is_collection = bool(item.get("is_collection") or item.get("isCollection"))
            if is_collection:
                collection_id = str(
                    item.get("collection_id") or item.get("collectionId") or ""
                ).strip()
                key = f"collection_{collection_id}" if collection_id else ""
            else:
                addon_id = str(item.get("addon_id") or item.get("addonId") or "").strip()
                media_type = str(item.get("type") or "").strip()
                catalog_id = str(
                    item.get("catalog_id") or item.get("catalogId") or ""
                ).strip()
                key = (
                    f"{addon_id}_{media_type}_{catalog_id}"
                    if addon_id and media_type and catalog_id
                    else ""
                )
            if not key:
                continue
            try:
                order = int(item.get("order", fallback_order))
            except (TypeError, ValueError):
                order = fallback_order
            normalized_items.append(
                {
                    "key": key,
                    "enabled": item.get("enabled") is not False,
                    "order": order,
                    "custom_title": str(
                        item.get("custom_title") or item.get("customTitle") or ""
                    ).strip(),
                    "is_collection": is_collection,
                }
            )
        normalized_items.sort(key=lambda item: item["order"])

    if normalized_items:
        order = [item["key"] for item in normalized_items]
        disabled = {item["key"] for item in normalized_items if not item["enabled"]}
        custom_titles = {
            item["key"]: item["custom_title"]
            for item in normalized_items
            if item["custom_title"]
        }
    else:
        order = []
        for key in (
            "catalog_order_keys",
            "home_catalog_order",
            "catalog_order",
            "order",
        ):
            order = _home_string_list(settings.get(key))
            if order:
                break
        disabled_list: list[str] = []
        for key in (
            "disabled_catalog_keys",
            "hidden_catalog_keys",
            "catalog_disabled_keys",
            "home_catalog_disabled",
            "disabled",
        ):
            disabled_list = _home_string_list(settings.get(key))
            if disabled_list:
                break
        disabled = set(disabled_list)
        custom_titles = {}

    return {
        "order": order,
        "disabled": disabled,
        "custom_titles": custom_titles,
        "hide_unreleased_content": bool(settings.get("hide_unreleased_content", False)),
    }


def _parse_release_instant(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = text
    if len(candidate) >= 10 and candidate[4:5] == "-" and candidate[7:8] == "-":
        # Nuvio treats plain release dates as midnight and timestamps as their
        # actual instant. UTC is sufficient for Home's release-date filtering.
        if len(candidate) == 10:
            candidate += "T00:00:00+00:00"
        elif candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            return None
    return None


def _is_unreleased(meta: dict[str, Any], now: datetime | None = None) -> bool:
    """Mirror Nuvio Home's release filtering."""
    now = now or datetime.now(UTC)
    for value in (meta.get("released"), meta.get("releaseInfo"), meta.get("release_info")):
        parsed = _parse_release_instant(value)
        if parsed is not None:
            return parsed > now
    release_info = str(meta.get("releaseInfo") or meta.get("release_info") or "")
    match = re.search(r"\\b(19|20)\\d{2}\\b", release_info)
    return bool(match and int(match.group(0)) > now.year)


def _dedupe_catalog_items(
    metas: list[dict[str, Any]],
    media_type: str,
    manifest_url: str,
    *,
    hide_unreleased: bool,
    limit: int = 15,
) -> list[dict[str, Any]]:
    """Match Nuvio's Home mapper: require id/name and keep first duplicate id."""
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    now = datetime.now(UTC)
    for meta in metas:
        raw_id = meta.get("id")
        raw_name = meta.get("name")
        if not isinstance(raw_id, str) or not isinstance(raw_name, str):
            continue
        content_id = raw_id.strip()
        name = raw_name.strip()
        if not content_id or not name or content_id in seen:
            continue
        if hide_unreleased and _is_unreleased(meta, now):
            continue
        seen.add(content_id)
        result.append(_item(meta, media_type, manifest_url))
        if len(result) >= limit:
            break
    return result


async def _home(hass: HomeAssistant, *, refresh: bool = False) -> dict[str, Any]:
    domain_data = hass.data.setdefault(DOMAIN, {})
    cached = domain_data.get(DATA_HOME_CACHE)
    now_monotonic = time.monotonic()
    if not refresh and cached is not None and now_monotonic - cached[0] < HOME_CACHE_TTL:
        return cached[1]

    entry = _entry(hass)
    api = entry.runtime_data[DATA_API]
    account = entry.runtime_data.get(DATA_ACCOUNT_API)
    sections: list[dict[str, Any]] = []
    home_settings: dict[str, Any] = {}
    profile_settings: dict[str, Any] = {}
    collections: list[dict[str, Any]] = []
    profile_id = int(entry.data.get(CONF_PROFILE_ID, 1))

    library: list[dict[str, Any]] = []
    progress: list[dict[str, Any]] = []
    if account is not None:
        results = await asyncio.gather(
            account.async_library(profile_id),
            account.async_watch_progress(profile_id),
            account.async_home_catalog_settings(profile_id),
            account.async_profile_settings_blob(profile_id),
            account.async_collections(profile_id),
            return_exceptions=True,
        )
        if not isinstance(results[0], Exception):
            library = results[0]
        if not isinstance(results[1], Exception):
            progress = results[1]
        if not isinstance(results[2], Exception):
            home_settings = results[2]
        if not isinstance(results[3], Exception):
            profile_settings = results[3]
        if not isinstance(results[4], Exception):
            collections = results[4]

    layout = _layout_settings(profile_settings)
    home_prefs = _home_catalog_preferences(home_settings)
    hide_unreleased = (
        bool(home_settings.get("hide_unreleased_content"))
        if "hide_unreleased_content" in home_settings
        else bool(layout.get("hide_unreleased_content", False))
    )

    # Nuvio renders Continue Watching independently before catalog rows. It
    # does not inject "My Library" as a Home row.
    if progress:
        lib_index = {
            (str(x.get("content_type")), str(x.get("content_id"))): x for x in library
        }
        active = []
        for item in progress:
            try:
                duration = int(item.get("duration") or item.get("duration_ms") or 0)
                position = int(item.get("position") or item.get("position_ms") or 0)
            except (TypeError, ValueError):
                continue
            if duration <= 0 or position <= 0 or position >= duration * 0.95:
                continue
            active.append(item)
        active.sort(
            key=lambda item: int(
                item.get("last_watched")
                or item.get("updated_at")
                or item.get("updatedAt")
                or 0
            ),
            reverse=True,
        )
        continue_items: list[dict[str, Any]] = []
        for progress_item in active[:30]:
            media_type = str(progress_item.get("content_type") or "movie")
            content_id = str(progress_item.get("content_id") or "")
            meta = lib_index.get((media_type, content_id), {})
            addon_base = meta.get("addon_base_url") or progress_item.get("addon_base_url")
            item = _item(
                {
                    **meta,
                    "id": content_id,
                    "type": media_type,
                    "name": (
                        meta.get("name")
                        or meta.get("title")
                        or progress_item.get("title")
                        or content_id
                    ),
                    "poster": meta.get("poster") or progress_item.get("poster"),
                    "background": (
                        meta.get("background")
                        or progress_item.get("background")
                        or progress_item.get("backdrop")
                    ),
                },
                media_type,
                f"{str(addon_base).rstrip('/')}/manifest.json" if addon_base else None,
            )
            item.update(
                {
                    "season": progress_item.get("season"),
                    "episode": progress_item.get("episode"),
                    "video_id": progress_item.get("video_id"),
                    "position": progress_item.get("position")
                    or progress_item.get("position_ms"),
                    "duration": progress_item.get("duration")
                    or progress_item.get("duration_ms"),
                }
            )
            continue_items.append(item)
        if continue_items:
            sections.append(
                {
                    "id": "continue",
                    "kind": "continue",
                    "name": "Continue Watching",
                    "items": continue_items,
                }
            )

    catalog_specs: list[tuple[Addon, dict[str, Any], str, str, str, int]] = []
    manifest_index = 0
    for addon in await api.async_addons(refresh=refresh):
        for catalog in addon.manifest.get("catalogs", []):
            if not isinstance(catalog, dict) or not _catalog_should_show_on_home(catalog):
                continue
            media_type = str(catalog.get("type") or "").strip()
            catalog_id = str(catalog.get("id") or "").strip()
            if not media_type or not catalog_id:
                continue
            key = _catalog_key(addon, media_type, catalog_id)
            disable_key = (
                f"{addon.base_url}_{media_type}_{catalog_id}_"
                f"{str(catalog.get('name') or catalog_id)}"
            )
            if key in home_prefs["disabled"] or disable_key in home_prefs["disabled"]:
                continue
            catalog_specs.append(
                (addon, catalog, media_type, catalog_id, key, manifest_index)
            )
            manifest_index += 1

    order_index = {
        key: index for index, key in enumerate(home_prefs["order"])
    }
    catalog_specs.sort(
        key=lambda spec: (
            order_index.get(spec[4], len(order_index) + spec[5]),
            spec[5],
        )
    )

    semaphore = asyncio.Semaphore(8)

    async def load_section(
        addon: Addon,
        catalog: dict[str, Any],
        media_type: str,
        catalog_id: str,
        key: str,
        _manifest_index: int,
    ) -> dict[str, Any] | None:
        try:
            async with semaphore:
                metas = await api.async_catalog(addon, media_type, catalog_id)
        except NuvioApiError:
            return None
        items = _dedupe_catalog_items(
            metas,
            media_type,
            addon.manifest_url,
            hide_unreleased=hide_unreleased,
            limit=15,
        )
        if not items:
            return None
        return {
            "id": key,
            "kind": "catalog",
            "name": home_prefs["custom_titles"].get(key)
            or str(catalog.get("name") or catalog_id),
            "addon": addon.name,
            "addon_id": _addon_id(addon),
            "media_type": media_type,
            "catalog_id": catalog_id,
            "items": items,
        }

    catalog_sections = await asyncio.gather(
        *(load_section(*spec) for spec in catalog_specs)
    )
    sections.extend(section for section in catalog_sections if section is not None)

    registry = async_get_entity_registry(hass)
    players: list[dict[str, Any]] = []
    for entity in registry.entities.values():
        if (
            entity.domain != "media_player"
            or entity.platform not in {"androidtv", "androidtv_remote", "webostv"}
        ):
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

    selected_layout = str(layout.get("selected_layout") or "MODERN").strip().casefold()
    preferences = {
        "layout": selected_layout,
        "show_poster_labels": layout.get("poster_labels_enabled", True) is not False,
        "show_catalog_addon_name": (
            selected_layout == "classic"
            and layout.get("catalog_addon_name_enabled", True) is not False
        ),
        "show_catalog_type_suffix": layout.get("catalog_type_suffix_enabled", True) is not False,
        "hide_unreleased_content": hide_unreleased,
        "synced_home_settings": bool(home_settings),
        # Exposed so the frontend can be explicit about app-only collection
        # rows until their provider-specific drill-down is mirrored as well.
        "collection_count": len(collections),
    }
    result = {"sections": sections, "players": players, "preferences": preferences}
    domain_data[DATA_HOME_CACHE] = (now_monotonic, result)
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
                    "resolver_service": client_resolve.get("service"),
                    "torrent_name": client_resolve.get("torrentName"),
                    "resolve_filename": client_resolve.get("filename"),
                    "resolve_season": client_resolve.get("season"),
                    "resolve_episode": client_resolve.get("episode"),
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

        resolver = _entry(hass).runtime_data.get(DATA_DEBRID_RESOLVER)
        if resolver is not None:
            for row in rows:
                row["resolvable"] = resolver.can_resolve(row)

        connection.send_result(
            msg["id"],
            {
                "streams": rows,
                "debrid": {
                    "configured": bool(resolver and resolver.configured),
                    "providers": resolver.providers if resolver else [],
                    "provider": (
                        resolver.providers[0]
                        if resolver and resolver.providers
                        else ""
                    ),
                },
            },
        )
    except (NuvioApiError, NuvioAuthError) as err:
        connection.send_error(msg["id"], "nuvio_error", str(err))


@websocket_api.websocket_command({
    probatio.Required("type"): "nuvio/resolve_stream",
    probatio.Optional("info_hash"): str,
    probatio.Optional("magnet_uri"): str,
    probatio.Optional("torrent_sources", default=[]): [str],
    probatio.Optional("file_idx"): probatio.Coerce(int),
    probatio.Optional("filename"): str,
    probatio.Optional("resolve_filename"): str,
    probatio.Optional("torrent_name"): str,
    probatio.Optional("resolver_service"): str,
    probatio.Optional("season"): probatio.Coerce(int),
    probatio.Optional("episode"): probatio.Coerce(int),
})
@websocket_api.async_response
async def ws_resolve_stream(hass, connection, msg) -> None:
    """Resolve a torrent/debrid source into its final HTTP URL."""
    try:
        entry = _entry(hass)
        resolver = entry.runtime_data.get(DATA_DEBRID_RESOLVER)
        if resolver is None:
            raise DebridNotConfigured(
                "No debrid credential is available from the Nuvio account or local integration settings."
            )
        source = {
            key: msg.get(key)
            for key in (
                "info_hash",
                "magnet_uri",
                "torrent_sources",
                "file_idx",
                "filename",
                "resolve_filename",
                "torrent_name",
                "resolver_service",
            )
        }
        resolved = await resolver.async_resolve(
            source,
            season=msg.get("season"),
            episode=msg.get("episode"),
        )
        connection.send_result(
            msg["id"],
            {
                "url": resolved.url,
                "filename": resolved.filename,
                "video_size": resolved.video_size,
                "provider": resolved.provider,
            },
        )
    except DebridNotConfigured as err:
        connection.send_error(msg["id"], "debrid_not_configured", str(err))
    except DebridNotCached as err:
        connection.send_error(msg["id"], "debrid_not_cached", str(err))
    except DebridResolveError as err:
        connection.send_error(msg["id"], "debrid_error", str(err))


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
    websocket_api.async_register_command(hass, ws_resolve_stream)
    websocket_api.async_register_command(hass, ws_details)
    data[DATA_FRONTEND_REGISTERED] = True
