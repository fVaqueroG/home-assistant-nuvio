"""Frontend API and bundled Lovelace card for Nuvio."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import probatio
from homeassistant.components import frontend, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .account import NuvioAuthError
from .api import Addon, NuvioApiError
from .const import CONF_PROFILE_ID, DATA_ACCOUNT_API, DATA_API, DOMAIN

CARD_URL = "/nuvio/nuvio-card.js"
CARD_FILE = Path(__file__).parent / "frontend" / "nuvio-card.js"
DATA_FRONTEND_REGISTERED = "frontend_registered"


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


async def _home(hass: HomeAssistant) -> dict[str, Any]:
    entry = _entry(hass)
    api = entry.runtime_data[DATA_API]
    account = entry.runtime_data.get(DATA_ACCOUNT_API)
    sections: list[dict[str, Any]] = []

    if account is not None:
        profile_id = int(entry.data.get(CONF_PROFILE_ID, 1))
        try:
            library = await account.async_library(profile_id)
            progress = await account.async_watch_progress(profile_id)
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
            for p in active[:30]:
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
            for meta in sorted(library, key=lambda x: int(x.get("added_at") or 0), reverse=True)[:40]:
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

    for addon in await api.async_addons():
        for catalog in addon.manifest.get("catalogs", []):
            if not isinstance(catalog, dict):
                continue
            media_type = str(catalog.get("type") or "")
            catalog_id = str(catalog.get("id") or "")
            if media_type not in {"movie", "series"} or not catalog_id:
                continue
            try:
                metas = await api.async_catalog(addon, media_type, catalog_id)
            except NuvioApiError:
                continue
            items = [_item(meta, media_type, addon.manifest_url) for meta in metas[:30]]
            if items:
                sections.append({
                    "id": f"{addon.name}:{media_type}:{catalog_id}",
                    "name": str(catalog.get("name") or catalog_id),
                    "addon": addon.name,
                    "media_type": media_type,
                    "items": items,
                })
    return {"sections": sections}


@websocket_api.websocket_command({probatio.Required("type"): "nuvio/home"})
@websocket_api.async_response
async def ws_home(hass, connection, msg) -> None:
    try:
        connection.send_result(msg["id"], await _home(hass))
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


async def async_register_frontend(hass: HomeAssistant) -> None:
    data = hass.data.setdefault(DOMAIN, {})
    if data.get(DATA_FRONTEND_REGISTERED):
        return
    await hass.http.async_register_static_paths([
        StaticPathConfig(CARD_URL, str(CARD_FILE), cache_headers=False)
    ])
    frontend.add_extra_js_url(hass, CARD_URL)
    websocket_api.async_register_command(hass, ws_home)
    websocket_api.async_register_command(hass, ws_search)
    websocket_api.async_register_command(hass, ws_details)
    data[DATA_FRONTEND_REGISTERED] = True
