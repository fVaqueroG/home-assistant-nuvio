"""Frontend API and bundled Lovelace card for Nuvio."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import urlencode

import probatio
import pycountry
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
from .tmdb import TmdbApiError
from .providers import (
    normalize_provider_text,
    normalize_selected_provider,
    streaming_provider_key,
)
from .const import (
    CONF_PROFILE_ID,
    CONF_STREAMING_PROVIDERS,
    CONF_WATCHHUB_COUNTRY,
    DATA_ACCOUNT_API,
    DATA_API,
    DATA_DEBRID_RESOLVER,
    DATA_TMDB_API,
    DEFAULT_STREAMING_PROVIDERS,
    DEFAULT_WATCHHUB_COUNTRY,
    DOMAIN,
)

CARD_URL = "/nuvio/nuvio-card.js"
CARD_VERSION = "0.4.35"
CARD_RESOURCE_URL = f"{CARD_URL}?v={CARD_VERSION}"
CARD_FILE = Path(__file__).parent / "frontend" / "nuvio-card.js"
DATA_FRONTEND_REGISTERED = "frontend_registered"
DATA_HOME_CACHE = "home_cache"
HOME_CACHE_TTL = 120.0
HOME_EAGER_CATALOGS = 4


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


def _feature_settings(blob: dict[str, Any], feature: str) -> dict[str, Any]:
    """Decode one synchronized Nuvio profile-settings feature."""
    features = blob.get("features")
    if not isinstance(features, dict):
        return {}
    raw = features.get(feature)
    if not isinstance(raw, dict):
        return {}
    return {str(key): _decode_synced_value(value) for key, value in raw.items()}


def _layout_settings(blob: dict[str, Any]) -> dict[str, Any]:
    return _feature_settings(blob, "layout_settings")


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


def _selected_streaming_providers(entry: Any) -> set[str]:
    raw = entry.data.get(CONF_STREAMING_PROVIDERS)
    if raw is None:
        raw = DEFAULT_STREAMING_PROVIDERS
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple, set)):
        return set()

    selected: set[str] = set()
    for value in raw:
        key = normalize_selected_provider(value)
        if key:
            selected.add(key)
    return selected


def _country_code_variants(value: Any) -> set[str]:
    """Return comparable ISO alpha-2/alpha-3 variants for a country."""
    alpha2 = str(value or "").strip().upper()
    if not alpha2:
        return set()
    variants = {alpha2.casefold()}
    country = pycountry.countries.get(alpha_2=alpha2)
    if country is not None:
        variants.add(str(country.alpha_3).casefold())
    if alpha2 == "GB":
        variants.add("uk")
    return variants


def _watchhub_stream_matches_country(
    stream: dict[str, Any],
    behavior: dict[str, Any],
    country_code: str,
) -> bool:
    """Apply Stremio geo hints when WatchHub returns them."""
    selected = _country_code_variants(country_code)
    if not selected:
        return True

    raw_geo_values = (
        stream.get("geos"),
        stream.get("countryWhitelist"),
        behavior.get("countryWhitelist"),
        behavior.get("country_whitelist"),
    )
    restricted: set[str] = set()
    for raw in raw_geo_values:
        if isinstance(raw, str):
            restricted.add(raw.strip().casefold())
        elif isinstance(raw, (list, tuple, set)):
            restricted.update(
                str(value).strip().casefold()
                for value in raw
                if str(value).strip()
            )

    # No geo hint means the country-specific WatchHub endpoint (or WatchHub
    # itself) is authoritative, so keep the source.
    return not restricted or bool(selected & restricted)


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
    """Return the same Home composition Nuvio builds for the active profile.

    The TV apps use three synchronized sources for Home: profile layout settings,
    Home catalog settings, and collections.  Keep the Lovelace card aligned with
    those sources instead of inventing a separate Home ordering.
    """
    domain_data = hass.data.setdefault(DOMAIN, {})
    cached = domain_data.get(DATA_HOME_CACHE)
    now_monotonic = time.monotonic()
    if not refresh and cached is not None and now_monotonic - cached[0] < HOME_CACHE_TTL:
        return cached[1]

    entry = _entry(hass)
    api = entry.runtime_data[DATA_API]
    streaming_providers = _selected_streaming_providers(entry)
    if refresh:
        api.clear_catalog_cache()
    account = entry.runtime_data.get(DATA_ACCOUNT_API)
    profile_id = int(entry.data.get(CONF_PROFILE_ID, 1))
    home_incomplete = False

    async def home_call(coro, timeout: float, fallback: Any):
        """Bound optional Home calls so one slow addon cannot stall the card."""
        nonlocal home_incomplete
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except (TimeoutError, NuvioApiError, NuvioAuthError):
            home_incomplete = True
            return fallback

    # Manifest discovery is independent of account/profile sync; start it now
    # so slow account endpoints do not add serial delay to Home startup.
    addons_task = asyncio.create_task(
        home_call(api.async_addons(refresh=refresh), 3.0, [])
    )

    home_settings: dict[str, Any] = {}
    profile_settings: dict[str, Any] = {}
    collections: list[dict[str, Any]] = []
    library: list[dict[str, Any]] = []
    progress: list[dict[str, Any]] = []
    watched_items: list[dict[str, Any]] = []

    if account is not None:
        results = await asyncio.gather(
            home_call(account.async_library(profile_id), 2.5, []),
            home_call(account.async_watch_progress(profile_id), 2.5, []),
            home_call(account.async_home_catalog_settings(profile_id), 2.5, {}),
            home_call(account.async_profile_settings_blob(profile_id), 2.5, {}),
            home_call(account.async_collections(profile_id), 2.5, []),
            home_call(account.async_watched_items(profile_id), 2.5, []),
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
        if not isinstance(results[5], Exception):
            watched_items = results[5]

    layout = _layout_settings(profile_settings)
    trakt_settings = _feature_settings(profile_settings, "trakt_settings")
    home_prefs = _home_catalog_preferences(home_settings)

    selected_layout = str(layout.get("selected_layout") or "MODERN").strip().casefold()
    continue_watching_enabled = _decode_synced_value(
        layout.get("continue_watching_enabled", True)
    ) is not False
    hero_section_enabled = _decode_synced_value(
        layout.get("hero_section_enabled", True)
    ) is not False
    hero_catalog_keys = _home_string_list(layout.get("hero_catalog_keys"))
    if not hero_catalog_keys:
        hero_catalog_keys = _home_string_list(layout.get("hero_catalog_key"))

    hide_unreleased = (
        bool(home_settings.get("hide_unreleased_content"))
        if "hide_unreleased_content" in home_settings
        else bool(_decode_synced_value(layout.get("hide_unreleased_content", False)))
    )

    # Android keeps full Modern rows, while Classic/Grid cap the Home preview
    # at 24 items before See All.  The Smart-TV Modern implementation uses 15.
    row_limit = 15 if selected_layout == "modern" else 24

    addons = await addons_task
    if not addons:
        addons = api.cached_addons
    addon_by_id = {_addon_id(addon): addon for addon in addons}

    catalog_specs: list[tuple[Addon, dict[str, Any], str, str, str, int]] = []
    default_catalog_keys: list[str] = []
    catalog_spec_by_key: dict[str, tuple[Addon, dict[str, Any], str, str, str, int]] = {}
    manifest_index = 0
    for addon in addons:
        for catalog in addon.manifest.get("catalogs", []):
            if not isinstance(catalog, dict) or not _catalog_should_show_on_home(catalog):
                continue
            media_type = str(catalog.get("type") or "").strip()
            catalog_id = str(catalog.get("id") or "").strip()
            if not media_type or not catalog_id:
                continue
            key = _catalog_key(addon, media_type, catalog_id)
            spec = (addon, catalog, media_type, catalog_id, key, manifest_index)
            catalog_spec_by_key[key] = spec
            default_catalog_keys.append(key)
            manifest_index += 1

            disable_key = (
                f"{addon.base_url}_{media_type}_{catalog_id}_"
                f"{str(catalog.get('name') or catalog_id)}"
            )
            if key in home_prefs["disabled"] or disable_key in home_prefs["disabled"]:
                continue
            catalog_specs.append(spec)

    semaphore = asyncio.Semaphore(8)
    loaded_sections: dict[str, dict[str, Any]] = {}
    enabled_catalog_spec_by_key = {spec[4]: spec for spec in catalog_specs}

    def catalog_section(
        spec: tuple[Addon, dict[str, Any], str, str, str, int],
        *,
        items: list[dict[str, Any]] | None = None,
        lazy: bool = True,
    ) -> dict[str, Any]:
        addon, catalog, media_type, catalog_id, key, _manifest_index = spec
        return {
            "id": key,
            "kind": "catalog",
            "name": home_prefs["custom_titles"].get(key)
            or str(catalog.get("name") or catalog_id),
            "addon": addon.name,
            "addon_id": _addon_id(addon),
            "manifest_url": addon.manifest_url,
            "media_type": media_type,
            "catalog_id": catalog_id,
            "items": items or [],
            "lazy": lazy,
        }

    async def load_catalog_spec(
        spec: tuple[Addon, dict[str, Any], str, str, str, int],
        *,
        include_if_disabled: bool = False,
    ) -> dict[str, Any] | None:
        addon, catalog, media_type, catalog_id, key, _manifest_index = spec
        if key in loaded_sections:
            return loaded_sections[key]
        if not include_if_disabled:
            disable_key = (
                f"{addon.base_url}_{media_type}_{catalog_id}_"
                f"{str(catalog.get('name') or catalog_id)}"
            )
            if key in home_prefs["disabled"] or disable_key in home_prefs["disabled"]:
                return None
        try:
            async with semaphore:
                metas = await asyncio.wait_for(
                    api.async_catalog(
                        addon,
                        media_type,
                        catalog_id,
                        refresh=refresh,
                    ),
                    timeout=5.0,
                )
        except (NuvioApiError, TimeoutError):
            return None

        items = _dedupe_catalog_items(
            metas,
            media_type,
            addon.manifest_url,
            hide_unreleased=hide_unreleased,
            limit=row_limit,
        )
        if not items:
            return None
        section = catalog_section(spec, items=items, lazy=False)
        loaded_sections[key] = section
        return section

    async def bounded_catalog_load(
        spec: tuple[Addon, dict[str, Any], str, str, str, int],
        *,
        include_if_disabled: bool = False,
    ) -> dict[str, Any] | None:
        try:
            return await asyncio.wait_for(
                load_catalog_spec(spec, include_if_disabled=include_if_disabled),
                timeout=4.5,
            )
        except (TimeoutError, NuvioApiError):
            return None

    async def load_catalog_batch(
        specs: list[tuple[Addon, dict[str, Any], str, str, str, int]],
        *,
        include_if_disabled: bool = False,
        budget: float = 2.25,
        mark_incomplete: bool = True,
    ) -> list[dict[str, Any] | None]:
        """Return catalog results that finish within a bounded initial budget."""
        nonlocal home_incomplete
        tasks = [
            asyncio.create_task(
                bounded_catalog_load(spec, include_if_disabled=include_if_disabled)
            )
            for spec in specs
        ]
        if not tasks:
            return []
        done, pending = await asyncio.wait(tasks, timeout=budget)
        if pending:
            if mark_incomplete:
                home_incomplete = True
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        results: list[dict[str, Any] | None] = []
        for task in done:
            try:
                results.append(task.result())
            except Exception:
                results.append(None)
        return results

    # Match NuvioTV's Home strategy: every catalog row is represented
    # immediately, while only the first four visible catalogs are fetched
    # eagerly. Remaining rows are lazy placeholders that the card loads as
    # they approach the viewport.
    ordered_catalog_keys: list[str] = []
    seen_catalog_keys: set[str] = set()
    for key in home_prefs["order"]:
        if key in enabled_catalog_spec_by_key and key not in seen_catalog_keys:
            seen_catalog_keys.add(key)
            ordered_catalog_keys.append(key)
    ordered_catalog_keys.extend(
        spec[4] for spec in catalog_specs if spec[4] not in seen_catalog_keys
    )
    eager_specs = [
        enabled_catalog_spec_by_key[key]
        for key in ordered_catalog_keys[:HOME_EAGER_CATALOGS]
    ]
    loaded_home = await load_catalog_batch(
        eager_specs,
        budget=1.25,
        mark_incomplete=False,
    )
    for section in loaded_home:
        if section:
            loaded_sections[section["id"]] = section

    # Hero catalogs are independent of Home row visibility in Nuvio.  A catalog
    # selected for Hero can remain hidden as a normal Home row.
    if hero_section_enabled and hero_catalog_keys:
        hero_specs = [
            catalog_spec_by_key[key]
            for key in hero_catalog_keys
            if key in catalog_spec_by_key
        ]
        hero_loaded = await load_catalog_batch(
            hero_specs,
            include_if_disabled=True,
            budget=0.75 if home_incomplete else 1.5,
        )
        for section in hero_loaded:
            if section:
                loaded_sections[section["id"]] = section

    # Collections are Home rows of folder tiles, not media-title rows.  Keep
    # their exact synchronized identity/order metadata for the card.
    collections_by_key: dict[str, dict[str, Any]] = {}
    collection_keys: list[str] = []
    for collection in collections:
        collection_id = str(collection.get("id") or "").strip()
        if not collection_id:
            continue
        key = f"collection_{collection_id}"
        collection_keys.append(key)
        collection_title = str(collection.get("title") or "").strip()
        normalized_collection_title = normalize_provider_text(collection_title)
        is_streaming_collection = normalized_collection_title in {
            "streaming",
            "streaming services",
            "servicios de streaming",
            "plataformas de streaming",
        }
        folders: list[dict[str, Any]] = []
        for folder in collection.get("folders") or []:
            if not isinstance(folder, dict):
                continue
            folder_id = str(folder.get("id") or "").strip()
            title = str(folder.get("title") or "").strip()
            if not folder_id or not title:
                continue
            if streaming_providers and is_streaming_collection:
                provider_key = streaming_provider_key(title)
                if provider_key not in streaming_providers:
                    continue
            folders.append(
                {
                    "id": folder_id,
                    "folder_id": folder_id,
                    "collection_id": collection_id,
                    "type": "collection_folder",
                    "name": title,
                    "poster": folder.get("coverImageUrl") or folder.get("cover_image_url"),
                    "focus_gif": folder.get("focusGifUrl") or folder.get("focus_gif_url"),
                    "focus_gif_enabled": folder.get("focusGifEnabled", True) is not False,
                    "cover_emoji": folder.get("coverEmoji") or folder.get("cover_emoji"),
                    "posterShape": str(
                        folder.get("tileShape") or folder.get("tile_shape") or "SQUARE"
                    ).upper(),
                    "hide_title": folder.get("hideTitle", False) is True,
                    "hero_backdrop": folder.get("heroBackdropUrl")
                    or folder.get("hero_backdrop_url"),
                    "hero_video": folder.get("heroVideoUrl")
                    or folder.get("hero_video_url"),
                    "title_logo": folder.get("titleLogoUrl")
                    or folder.get("title_logo_url"),
                    "sources": folder.get("sources")
                    or folder.get("catalogSources")
                    or [],
                }
            )
        collections_by_key[key] = {
            "id": key,
            "kind": "collection",
            "name": home_prefs["custom_titles"].get(key)
            or str(collection.get("title") or "Collection"),
            "collection_id": collection_id,
            "backdrop": collection.get("backdropImageUrl")
            or collection.get("backdrop_image_url"),
            "pin_to_top": collection.get("pinToTop", False) is True,
            "focus_glow_enabled": collection.get("focusGlowEnabled", True) is not False,
            "view_mode": collection.get("viewMode") or collection.get("view_mode"),
            "show_all_tab": collection.get("showAllTab", True) is not False,
            "items": folders,
        }

    # Rebuild the exact Home row ordering rule:
    # pinned collections first; then synchronized order; then newly discovered
    # addon catalogs; then newly discovered collections.
    available_keys = set(default_catalog_keys) | set(collection_keys)
    saved_order = []
    seen_order: set[str] = set()
    for key in home_prefs["order"]:
        if key in available_keys and key not in seen_order:
            seen_order.add(key)
            saved_order.append(key)
    effective_order = (
        saved_order
        + [key for key in default_catalog_keys if key not in seen_order]
        + [key for key in collection_keys if key not in seen_order]
    )

    sections: list[dict[str, Any]] = []

    if continue_watching_enabled:
        lib_index = {
            (str(x.get("content_type")), str(x.get("content_id"))): x for x in library
        }

        def timestamp_ms(raw: Any) -> float:
            try:
                value = float(raw or 0)
                # Nuvio stores epoch milliseconds. Be tolerant of epoch seconds.
                return value * 1000 if 0 < value < 10_000_000_000 else value
            except (TypeError, ValueError):
                parsed = _parse_release_instant(raw)
                return parsed.timestamp() * 1000 if parsed else 0.0

        days_cap_raw = _decode_synced_value(
            trakt_settings.get("continue_watching_days_cap", 60)
        )
        try:
            days_cap = int(days_cap_raw)
        except (TypeError, ValueError):
            days_cap = 60
        cutoff_ms = (
            None
            if days_cap == 0
            else datetime.now(tz=UTC).timestamp() * 1000
            - max(7, min(365, days_cap)) * 86_400_000
        )
        show_unaired_next_up = _decode_synced_value(
            layout.get("show_unaired_next_up", True)
        ) is not False
        prefer_furthest = _decode_synced_value(
            layout.get("next_up_from_furthest_episode", True)
        ) is not False
        continue_sort_mode = str(
            _decode_synced_value(layout.get("continue_watching_sort_mode", "DEFAULT"))
            or "DEFAULT"
        ).strip().upper()
        dismissed_raw = _decode_synced_value(
            trakt_settings.get("dismissed_next_up_keys", [])
        )
        if isinstance(dismissed_raw, (list, set, tuple)):
            dismissed_next_up = {
                str(value).strip().split("|", 1)[0]
                for value in dismissed_raw
                if str(value).strip()
            }
        else:
            dismissed_next_up = set()

        active: list[dict[str, Any]] = []
        for item in progress:
            if cutoff_ms is not None and timestamp_ms(
                item.get("last_watched") or item.get("updated_at") or item.get("updatedAt")
            ) < cutoff_ms:
                continue
            try:
                duration = int(item.get("duration") or item.get("duration_ms") or 0)
                position = int(item.get("position") or item.get("position_ms") or 0)
            except (TypeError, ValueError):
                continue
            if duration <= 0 or position <= 0 or position >= duration * 0.95:
                continue
            active.append(item)

        active.sort(
            key=lambda item: timestamp_ms(
                item.get("last_watched") or item.get("updated_at") or item.get("updatedAt")
            ),
            reverse=True,
        )
        in_progress_items: list[dict[str, Any]] = []
        in_progress_series_ids: set[str] = set()
        for progress_item in active[:300]:
            media_type = str(progress_item.get("content_type") or "movie")
            content_id = str(progress_item.get("content_id") or "")
            if not content_id:
                continue
            if media_type.casefold() in {"series", "tv", "anime"}:
                in_progress_series_ids.add(content_id)
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
                        or progress_item.get("name")
                        or progress_item.get("title")
                        or content_id
                    ),
                    "poster": meta.get("poster") or progress_item.get("poster"),
                    "background": (
                        meta.get("background")
                        or progress_item.get("background")
                        or progress_item.get("backdrop")
                    ),
                    "logo": meta.get("logo") or progress_item.get("logo"),
                },
                media_type,
                f"{str(addon_base).rstrip('/')}/manifest.json" if addon_base else None,
            )
            item.update(
                {
                    "season": progress_item.get("season"),
                    "episode": progress_item.get("episode"),
                    "video_id": progress_item.get("video_id"),
                    "episode_title": progress_item.get("episode_title")
                    or progress_item.get("episodeTitle"),
                    "episode_thumbnail": progress_item.get("thumbnail")
                    or progress_item.get("episode_thumbnail"),
                    "position": progress_item.get("position")
                    or progress_item.get("position_ms"),
                    "duration": progress_item.get("duration")
                    or progress_item.get("duration_ms"),
                    "_cw_kind": "in_progress",
                    "_cw_sort": timestamp_ms(
                        progress_item.get("last_watched")
                        or progress_item.get("updated_at")
                        or progress_item.get("updatedAt")
                    ),
                    "_cw_has_aired": True,
                }
            )
            in_progress_items.append(item)

        # Nuvio derives Next Up from watched episode history, then resolves each
        # series against addon metadata. Limit to the same 32 expensive lookups
        # used by the TV app.
        watched_by_series: dict[str, list[dict[str, Any]]] = {}
        for watched in watched_items:
            content_type = str(watched.get("content_type") or "").casefold()
            content_id = str(watched.get("content_id") or "").strip()
            if content_type not in {"series", "tv", "anime"} or not content_id:
                continue
            if cutoff_ms is not None and timestamp_ms(watched.get("watched_at")) < cutoff_ms:
                continue
            try:
                season = int(watched.get("season"))
                episode = int(watched.get("episode"))
            except (TypeError, ValueError):
                continue
            if season <= 0 or episode <= 0:
                continue
            watched_by_series.setdefault(content_id, []).append(watched)

        async def resolve_series_meta(
            content_id: str, content_type: str, saved: dict[str, Any]
        ) -> tuple[Addon | None, dict[str, Any] | None]:
            preferred_base = str(saved.get("addon_base_url") or "").rstrip("/")
            preferred = next(
                (addon for addon in addons if addon.base_url.rstrip("/") == preferred_base),
                None,
            )
            candidates = ([preferred] if preferred is not None else []) + [
                addon for addon in addons if addon is not preferred
            ]
            for addon in candidates:
                try:
                    async with semaphore:
                        return addon, await asyncio.wait_for(
                            api.async_meta(addon, content_type, content_id),
                            timeout=1.75,
                        )
                except (NuvioApiError, TimeoutError):
                    continue
            # Some addons expose TV metadata under series even when sync state
            # identifies the content as tv/anime.
            if content_type != "series":
                for addon in candidates:
                    try:
                        async with semaphore:
                            return addon, await asyncio.wait_for(
                                api.async_meta(addon, "series", content_id),
                                timeout=1.75,
                            )
                    except (NuvioApiError, TimeoutError):
                        continue
            return None, None

        next_up_semaphore = asyncio.Semaphore(4)
        now_utc = datetime.now(tz=UTC)

        async def build_next_up(
            content_id: str, history: list[dict[str, Any]]
        ) -> dict[str, Any] | None:
            if content_id in dismissed_next_up or content_id in in_progress_series_ids:
                return None
            sorted_history = sorted(
                history,
                key=lambda entry: (
                    int(entry.get("season") or 0),
                    int(entry.get("episode") or 0),
                ),
            )
            if not sorted_history:
                return None
            if prefer_furthest:
                seed = sorted_history[-1]
            else:
                seed = max(
                    sorted_history,
                    key=lambda entry: timestamp_ms(entry.get("watched_at")),
                )
            seed_season = int(seed.get("season") or 0)
            seed_episode = int(seed.get("episode") or 0)
            content_type = str(seed.get("content_type") or "series")
            saved = (
                lib_index.get((content_type, content_id))
                or lib_index.get(("series", content_id))
                or lib_index.get(("tv", content_id))
                or {}
            )
            async with next_up_semaphore:
                addon, meta = await resolve_series_meta(content_id, content_type, saved)
            if addon is None or not isinstance(meta, dict):
                return None

            videos = [
                video
                for video in meta.get("videos") or []
                if isinstance(video, dict)
                and video.get("available") is not False
                and video.get("season") is not None
                and video.get("episode") is not None
            ]
            normalized_videos: list[tuple[int, int, dict[str, Any]]] = []
            for video in videos:
                try:
                    season = int(video.get("season"))
                    episode = int(video.get("episode"))
                except (TypeError, ValueError):
                    continue
                if season <= 0 or episode <= 0:
                    continue
                normalized_videos.append((season, episode, video))
            normalized_videos.sort(key=lambda value: (value[0], value[1]))
            next_entry = next(
                (
                    value
                    for value in normalized_videos
                    if (value[0], value[1]) > (seed_season, seed_episode)
                ),
                None,
            )
            if next_entry is None:
                return None
            season, episode, video = next_entry
            released_raw = video.get("released")
            released_at = _parse_release_instant(released_raw)
            has_aired = released_at is None or released_at <= now_utc
            if not has_aired and not show_unaired_next_up:
                return None

            manifest_url = addon.manifest_url
            item = _item(meta, str(meta.get("type") or content_type or "series"), manifest_url)
            item.update(
                {
                    "season": season,
                    "episode": episode,
                    "video_id": video.get("id")
                    or f"{content_id}:{season}:{episode}",
                    "episode_title": video.get("title"),
                    "episode_description": video.get("overview"),
                    "episode_thumbnail": video.get("thumbnail"),
                    "released": released_raw,
                    "has_aired": has_aired,
                    "position": 0,
                    "duration": 0,
                    "_cw_kind": "next_up",
                    "_cw_has_aired": has_aired,
                    "_cw_sort": (
                        released_at.timestamp() * 1000
                        if has_aired and released_at is not None
                        else timestamp_ms(seed.get("watched_at"))
                    ),
                    "_cw_release": (
                        released_at.timestamp() * 1000 if released_at is not None else 0
                    ),
                }
            )
            if not item.get("name"):
                item["name"] = str(seed.get("title") or content_id)
            return item

        recent_series = sorted(
            watched_by_series.items(),
            key=lambda pair: max(
                (timestamp_ms(value.get("watched_at")) for value in pair[1]),
                default=0,
            ),
            reverse=True,
        )[:32]
        next_up_tasks = [
            asyncio.create_task(build_next_up(content_id, history))
            for content_id, history in recent_series
        ]
        next_up_items: list[dict[str, Any]] = []
        if next_up_tasks:
            done, pending = await asyncio.wait(
                next_up_tasks,
                timeout=0.5 if home_incomplete else 1.5,
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                try:
                    item = task.result()
                except Exception:
                    item = None
                if item is not None:
                    next_up_items.append(item)

        combined: list[dict[str, Any]] = in_progress_items + next_up_items
        deduped: list[dict[str, Any]] = []
        seen_content: set[str] = set()
        for item in combined:
            content_id = str(item.get("id") or "")
            if content_id and content_id in seen_content:
                continue
            if content_id:
                seen_content.add(content_id)
            deduped.append(item)

        if continue_sort_mode == "STREAMING_STYLE":
            released_items = [item for item in deduped if item.get("_cw_has_aired") is not False]
            unreleased_items = [item for item in deduped if item.get("_cw_has_aired") is False]
            released_items.sort(key=lambda item: float(item.get("_cw_sort") or 0), reverse=True)
            unreleased_items.sort(
                key=lambda item: float(item.get("_cw_release") or float("inf"))
            )
            main_cw = released_items + unreleased_items
            upcoming_cw: list[dict[str, Any]] = []
        elif continue_sort_mode == "SPLIT_UPCOMING":
            main_cw = [item for item in deduped if item.get("_cw_has_aired") is not False]
            upcoming_cw = [item for item in deduped if item.get("_cw_has_aired") is False]
            main_cw.sort(key=lambda item: float(item.get("_cw_sort") or 0), reverse=True)
            upcoming_cw.sort(
                key=lambda item: float(item.get("_cw_release") or float("inf"))
            )
        else:
            main_cw = deduped
            main_cw.sort(key=lambda item: float(item.get("_cw_sort") or 0), reverse=True)
            upcoming_cw = []

        for item in main_cw + upcoming_cw:
            item.pop("_cw_kind", None)
            item.pop("_cw_has_aired", None)
            item.pop("_cw_sort", None)
            item.pop("_cw_release", None)

        if main_cw:
            sections.append(
                {
                    "id": "continue_watching",
                    "kind": "continue",
                    "name": "Continue Watching",
                    "items": main_cw,
                }
            )
        if upcoming_cw:
            sections.append(
                {
                    "id": "upcoming_section",
                    "kind": "upcoming",
                    "name": "Upcoming",
                    "items": upcoming_cw,
                }
            )

    added_collections: set[str] = set()
    for key in collection_keys:
        collection = collections_by_key.get(key)
        if (
            collection
            and collection["pin_to_top"]
            and key not in home_prefs["disabled"]
            and collection["collection_id"] not in added_collections
        ):
            sections.append(collection)
            added_collections.add(collection["collection_id"])

    for key in effective_order:
        if key in home_prefs["disabled"]:
            continue
        if key.startswith("collection_"):
            collection = collections_by_key.get(key)
            if (
                collection
                and not collection["pin_to_top"]
                and collection["collection_id"] not in added_collections
            ):
                sections.append(collection)
                added_collections.add(collection["collection_id"])
            continue
        section = loaded_sections.get(key)
        if section is None:
            spec = enabled_catalog_spec_by_key.get(key)
            if spec is not None:
                section = catalog_section(spec)
        if section is not None:
            sections.append(section)

    # Build Nuvio's Hero candidate pool.  It distributes at most seven items
    # across the selected Hero catalogs; if none are selected, it falls back
    # to visible Home catalogs with artwork.
    hero_rows: list[dict[str, Any]] = []
    if hero_section_enabled:
        if hero_catalog_keys:
            hero_rows = [
                loaded_sections[key] for key in hero_catalog_keys if key in loaded_sections
            ]
        else:
            hero_rows = [section for section in sections if section.get("kind") == "catalog"]

    def has_hero_artwork(item: dict[str, Any]) -> bool:
        return bool(
            item.get("background")
            or item.get("landscapePoster")
            or item.get("poster")
        )

    hero_items: list[dict[str, Any]] = []
    if hero_rows:
        total_rows = len(hero_rows)
        base_slot = 7 // max(1, total_rows)
        remainder = 7 % max(1, total_rows)
        seen_hero: set[str] = set()
        for index, row in enumerate(hero_rows):
            if len(hero_items) >= 7:
                break
            slot = base_slot + (1 if index < remainder else 0)
            if slot <= 0:
                continue
            candidates = [item for item in row.get("items", []) if has_hero_artwork(item)]
            if not candidates and hero_catalog_keys:
                candidates = list(row.get("items", []))
            for item in candidates:
                identity = str(item.get("id") or "")
                if not identity or identity in seen_hero:
                    continue
                seen_hero.add(identity)
                hero_items.append(item)
                slot -= 1
                if slot <= 0 or len(hero_items) >= 7:
                    break

    if hero_items and not home_incomplete:
        addon_by_manifest = {addon.manifest_url: addon for addon in addons}

        async def enrich_hero_item(item: dict[str, Any]) -> dict[str, Any]:
            manifest_url = str(item.get("manifest_url") or "")
            addon = addon_by_manifest.get(manifest_url)
            content_id = str(item.get("id") or "")
            media_type = str(item.get("type") or "movie")
            if addon is None or not content_id:
                return item
            try:
                async with semaphore:
                    meta = await asyncio.wait_for(
                        api.async_meta(addon, media_type, content_id),
                        timeout=1.5,
                    )
            except (NuvioApiError, TimeoutError):
                return item
            enriched = _item(meta, media_type, manifest_url)
            # Preserve catalog-only fields if the full meta endpoint omits them.
            return {**item, **{key: value for key, value in enriched.items() if value not in (None, "", [])}}

        hero_tasks = [asyncio.create_task(enrich_hero_item(item)) for item in hero_items]
        if hero_tasks:
            done, pending = await asyncio.wait(hero_tasks, timeout=1.5)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            enriched_by_id: dict[str, dict[str, Any]] = {}
            for task in done:
                try:
                    enriched = task.result()
                except Exception:
                    continue
                enriched_by_id[str(enriched.get("id") or "")] = enriched
            hero_items = [
                enriched_by_id.get(str(item.get("id") or ""), item)
                for item in hero_items
            ]

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

    preferences = {
        "layout": selected_layout,
        "hero_section_enabled": hero_section_enabled,
        "continue_watching_enabled": continue_watching_enabled,
        "show_poster_labels": _decode_synced_value(
            layout.get("poster_labels_enabled", True)
        ) is not False,
        "show_catalog_addon_name": (
            selected_layout == "classic"
            and _decode_synced_value(layout.get("catalog_addon_name_enabled", True))
            is not False
        ),
        "show_catalog_type_suffix": _decode_synced_value(
            layout.get("catalog_type_suffix_enabled", True)
        ) is not False,
        "modern_landscape_posters_enabled": _decode_synced_value(
            layout.get("modern_landscape_posters_enabled", False)
        ) is True,
        "use_episode_thumbnails_in_cw": _decode_synced_value(
            layout.get("use_episode_thumbnails_in_cw", True)
        ) is not False,
        "show_full_release_date": _decode_synced_value(
            layout.get("show_full_release_date", True)
        ) is not False,
        "poster_card_width_dp": _decode_synced_value(
            layout.get("poster_card_width_dp", 126)
        ),
        "poster_card_height_dp": _decode_synced_value(
            layout.get("poster_card_height_dp", 189)
        ),
        "poster_card_corner_radius_dp": _decode_synced_value(
            layout.get("poster_card_corner_radius_dp", 12)
        ),
        "hide_unreleased_content": hide_unreleased,
        "synced_home_settings": bool(home_settings),
        "collection_count": len(collections_by_key),
        "hero_catalog_keys": hero_catalog_keys,
        "streaming_providers": sorted(streaming_providers),
        "watchhub_country": str(
            entry.data.get(CONF_WATCHHUB_COUNTRY)
            or getattr(hass.config, "country", None)
            or DEFAULT_WATCHHUB_COUNTRY
        ).upper(),
    }

    result = {
        "retry": home_incomplete,
        "sections": sections,
        "hero": {
            "enabled": hero_section_enabled,
            "items": hero_items,
        },
        "players": players,
        "preferences": preferences,
    }
    has_content = bool(sections or hero_items)
    if home_incomplete and not has_content and cached is not None:
        previous = cached[1]
        if previous.get("sections") or previous.get("hero", {}).get("items"):
            return {**previous, "retry": True}
    # Never turn a transient timeout or an empty startup into a cached Home.
    if has_content and not home_incomplete:
        domain_data[DATA_HOME_CACHE] = (time.monotonic(), result)
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
    probatio.Required("type"): "nuvio/catalog",
    probatio.Optional("manifest_url", default=""): str,
    probatio.Optional("addon_id", default=""): str,
    probatio.Required("media_type"): str,
    probatio.Required("catalog_id"): str,
    probatio.Optional("genre", default=""): str,
    probatio.Optional("hide_unreleased", default=False): bool,
})
@websocket_api.async_response
async def ws_catalog(hass, connection, msg) -> None:
    """Return the full first page for one Nuvio Home catalog."""
    try:
        api = _entry(hass).runtime_data[DATA_API]
        addon: Addon | None = None
        addons = await api.async_addons()
        for candidate in addons:
            if (msg["manifest_url"] and candidate.manifest_url == msg["manifest_url"]) or (
                not msg["manifest_url"] and _addon_id(candidate) == msg["addon_id"]
            ):
                addon = candidate
                break
        # Imported folders can retain an old addon ID after an addon migration.
        # Resolve an exact, unambiguous catalog match among configured addons.
        if addon is None and not msg["manifest_url"]:
            matches = [candidate for candidate in addons if any(
                str(catalog.get("id")) == msg["catalog_id"]
                and str(catalog.get("type")) == msg["media_type"]
                for catalog in candidate.manifest.get("catalogs", [])
                if isinstance(catalog, dict)
            )]
            if len(matches) == 1:
                addon = matches[0]
        if addon is None:
            raise NuvioApiError("The addon for this catalog is no longer configured")
        genre = str(msg.get("genre") or "").strip()
        metas = await api.async_catalog(
            addon,
            str(msg["media_type"]),
            str(msg["catalog_id"]),
            extra=urlencode({"genre": genre}) if genre.lower() not in {"", "none", "all"} else None,
        )
        items = _dedupe_catalog_items(
            metas,
            str(msg["media_type"]),
            addon.manifest_url,
            hide_unreleased=bool(msg.get("hide_unreleased", False)),
            limit=300,
        )
        connection.send_result(
            msg["id"],
            {
                "items": items,
                "addon": addon.name,
                "catalog_id": str(msg["catalog_id"]),
                "media_type": str(msg["media_type"]),
            },
        )
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


def _infer_stream_mime(
    stream: dict[str, Any],
    behavior: dict[str, Any],
    client_resolve: dict[str, Any],
    filename: Any,
    direct_url: Any,
) -> str | None:
    """Infer the same useful container hint Nuvio gives its player."""
    for value in (
        stream.get("mimeType"),
        stream.get("mime_type"),
        behavior.get("mimeType"),
        behavior.get("mime_type"),
        client_resolve.get("mimeType"),
        client_resolve.get("mime_type"),
    ):
        text = str(value or "").strip()
        if "/" in text and text not in {"video/*", "application/octet-stream"}:
            return text

    hint = f"{filename or ''} {direct_url or ''}".casefold()
    mapping = (
        ((".m3u8",), "application/vnd.apple.mpegurl"),
        ((".mpd",), "application/dash+xml"),
        ((".mkv",), "video/x-matroska"),
        ((".webm",), "video/webm"),
        ((".mov",), "video/quicktime"),
        ((".m2ts", ".ts"), "video/mp2t"),
        ((".mp4", ".m4v"), "video/mp4"),
    )
    for suffixes, mime_type in mapping:
        if any(suffix in hint for suffix in suffixes):
            return mime_type
    return None


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
    probatio.Optional("addon_scope", default="all"): probatio.In(
        ["all", "watchhub", "other"]
    ),
})
@websocket_api.async_response
async def ws_streams(hass, connection, msg) -> None:
    """Return selectable streams for one movie or episode."""
    try:
        entry = _entry(hass)
        api = entry.runtime_data[DATA_API]
        streaming_providers = _selected_streaming_providers(entry)
        watchhub_country = str(
            entry.data.get(CONF_WATCHHUB_COUNTRY)
            or getattr(hass.config, "country", None)
            or DEFAULT_WATCHHUB_COUNTRY
        ).upper()
        rows = []
        stream_pairs = await api.async_all_streams(
            msg["media_type"],
            msg["video_id"],
            watchhub_country=watchhub_country,
            addon_scope=msg["addon_scope"],
        )
        watchhub_series_fallback = False
        if (
            not stream_pairs
            and msg["addon_scope"] == "watchhub"
            and msg["media_type"] == "series"
        ):
            # WatchHub often exposes subscription availability at series level
            # even when an episode-specific Stremio id returns no streams.
            # Retry only when the episode lookup is empty; episode-level results
            # remain authoritative whenever WatchHub supplies them.
            series_video_id = re.sub(r":\d+:\d+$", "", msg["video_id"])
            if series_video_id and series_video_id != msg["video_id"]:
                stream_pairs = await api.async_all_streams(
                    "series",
                    series_video_id,
                    watchhub_country=watchhub_country,
                    addon_scope="watchhub",
                )
                watchhub_series_fallback = bool(stream_pairs)

        for addon, stream in stream_pairs:
            behavior = stream.get("behaviorHints")
            if not isinstance(behavior, dict):
                behavior = {}
            client_resolve = stream.get("clientResolve")
            if not isinstance(client_resolve, dict):
                client_resolve = {}

            direct_url = None
            candidate = stream.get("url")
            if isinstance(candidate, str):
                stripped = candidate.lstrip().lower()
                if stripped.startswith(("http://", "https://")):
                    direct_url = candidate

            # Stremio's externalUrl is a provider/navigation link, not a media
            # stream.  Treating WatchHub links such as watch.amazon.com as
            # playable video makes webOS media.viewer/open reject them and
            # makes Nuvio's internal HTML media element report FORMAT_ERR.
            external_url = None
            candidate = stream.get("externalUrl")
            if isinstance(candidate, str):
                stripped = candidate.lstrip().lower()
                if stripped.startswith(("http://", "https://")):
                    external_url = candidate

            provider_key = streaming_provider_key(
                stream.get("name") or stream.get("title"),
                external_url,
            )
            addon_id = str(addon.manifest.get("id") or "").strip().casefold()
            is_watchhub = (
                addon_id == "org.stremio.watchhub"
                or "watchhub" in str(addon.name or "").casefold()
            )
            if (
                external_url
                and streaming_providers
                and is_watchhub
                and provider_key not in streaming_providers
            ):
                continue
            if (
                external_url
                and is_watchhub
                and not _watchhub_stream_matches_country(
                    stream,
                    behavior,
                    watchhub_country,
                )
            ):
                continue

            proxy_headers = behavior.get("proxyHeaders")
            if not isinstance(proxy_headers, dict):
                proxy_headers = {}
            request_headers = proxy_headers.get("request")
            if not isinstance(request_headers, dict):
                request_headers = {}

            presentation = _stream_presentation(stream, behavior, client_resolve)
            watchhub_series_level = bool(
                is_watchhub
                and msg["media_type"] == "series"
                and external_url
            )
            if watchhub_series_level:
                presentation["badges"] = [
                    {"kind": "availability", "label": "Series-level"},
                    *presentation["badges"],
                ]
            rows.append(
                {
                    "addon": addon.name,
                    "addon_logo": addon.manifest.get("logo"),
                    "name": stream.get("name"),
                    "title": stream.get("title"),
                    "description": stream.get("description"),
                    "url": direct_url,
                    "external_url": external_url,
                    "external": bool(external_url) and not bool(direct_url),
                    "provider_key": provider_key,
                    "watchhub_series_fallback": bool(
                        watchhub_series_fallback and is_watchhub
                    ),
                    "watchhub_series_level": watchhub_series_level,
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
                    "mime_type": _infer_stream_mime(
                        stream,
                        behavior,
                        client_resolve,
                        presentation["filename"],
                        direct_url,
                    ),
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
    probatio.Required("type"): "nuvio/watch_providers",
    probatio.Required("media_type"): probatio.In(["movie", "series"]),
    probatio.Required("content_id"): str,
    probatio.Optional("season"): probatio.Coerce(int),
})
@websocket_api.async_response
async def ws_watch_providers(hass, connection, msg) -> None:
    """Return configured-country streaming availability from TMDB/JustWatch."""
    try:
        entry = _entry(hass)
        api = entry.runtime_data.get(DATA_TMDB_API)
        region = str(
            entry.data.get(CONF_WATCHHUB_COUNTRY)
            or getattr(hass.config, "country", None)
            or DEFAULT_WATCHHUB_COUNTRY
        ).upper()
        if api is None or not api.configured:
            connection.send_result(
                msg["id"],
                {
                    "configured": False,
                    "region": region,
                    "scope": None,
                    "providers": [],
                    "link": None,
                    "attribution": None,
                },
            )
            return

        result = await api.async_watch_providers(
            media_type=msg["media_type"],
            content_id=msg["content_id"],
            region=region,
            season=msg.get("season"),
        )
        selected = _selected_streaming_providers(entry)
        providers: list[dict[str, Any]] = []
        for raw in result.get("providers") or []:
            if not isinstance(raw, dict):
                continue
            provider = dict(raw)
            key = streaming_provider_key(provider.get("name"))
            if selected and key not in selected:
                continue
            provider["provider_key"] = key
            providers.append(provider)

        connection.send_result(
            msg["id"],
            {
                **result,
                "providers": providers,
                "attribution": "Availability data by JustWatch via TMDB",
            },
        )
    except TmdbApiError as err:
        connection.send_error(msg["id"], "tmdb_error", str(err))


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
    websocket_api.async_register_command(hass, ws_catalog)
    websocket_api.async_register_command(hass, ws_search)
    websocket_api.async_register_command(hass, ws_streams)
    websocket_api.async_register_command(hass, ws_resolve_stream)
    websocket_api.async_register_command(hass, ws_watch_providers)
    websocket_api.async_register_command(hass, ws_details)
    data[DATA_FRONTEND_REGISTERED] = True
