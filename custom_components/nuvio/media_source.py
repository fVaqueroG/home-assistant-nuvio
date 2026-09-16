"""Expose configured Nuvio catalogs to Home Assistant's Media browser."""

from __future__ import annotations

import base64
import json
from typing import Any, override

from homeassistant.components.media_player import (
    BrowseError,
    MediaClass,
    MediaType,
    SearchMedia,
    SearchMediaQuery,
)
from homeassistant.components.media_source import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
    Unresolvable,
)
from homeassistant.core import HomeAssistant

from .account import NuvioAccountApi, NuvioAuthError
from .api import Addon, NuvioApi, NuvioApiError
from .const import CONF_PROFILE_ID, DATA_ACCOUNT_API, DATA_API, DOMAIN
from .launcher import deep_link


def _encode(data: dict[str, Any]) -> str:
    raw = json.dumps(data, separators=(",", ":"), ensure_ascii=True).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode(identifier: str) -> dict[str, Any]:
    try:
        raw = base64.urlsafe_b64decode(identifier + "=" * (-len(identifier) % 4))
        value = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as err:
        raise BrowseError("Invalid Nuvio media identifier") from err
    if not isinstance(value, dict):
        raise BrowseError("Invalid Nuvio media identifier")
    return value


def _media_class(media_type: str, *, episode: bool = False) -> MediaClass:
    if episode:
        return MediaClass.EPISODE
    return MediaClass.TV_SHOW if media_type == "series" else MediaClass.MOVIE


def _media_type(media_type: str, *, episode: bool = False) -> MediaType:
    if episode:
        return MediaType.EPISODE
    return MediaType.TVSHOW if media_type == "series" else MediaType.MOVIE


class NuvioMediaSource(MediaSource):
    """Nuvio media source."""

    name = "Nuvio"

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(DOMAIN)
        self.hass = hass

    @property
    def api(self) -> NuvioApi:
        """Return the configured client."""
        entries = self.hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            raise BrowseError("Nuvio is not configured")
        return entries[0].runtime_data[DATA_API]

    @property
    def account_api(self) -> NuvioAccountApi | None:
        """Return the optional authenticated account client."""
        entries = self.hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            return None
        return entries[0].runtime_data.get(DATA_ACCOUNT_API)

    @property
    def profile_id(self) -> int:
        """Return the selected Nuvio profile index."""
        entries = self.hass.config_entries.async_loaded_entries(DOMAIN)
        return int(entries[0].data.get(CONF_PROFILE_ID, 1)) if entries else 1

    async def _addon(self, manifest_url: str) -> Addon:
        for addon in await self.api.async_addons():
            if addon.manifest_url == manifest_url:
                return addon
        raise BrowseError("The addon is no longer configured")

    @override
    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        """Browse catalogs, titles, seasons, and episodes."""
        try:
            if not item.identifier:
                return await self._root()
            payload = _decode(item.identifier)
            kind = payload.get("k")
            if kind == "catalog":
                return await self._catalog(payload)
            if kind == "library":
                return await self._library(payload)
            if kind == "continue":
                return await self._continue_watching(payload)
            if kind in {"title", "account_title"} and payload.get("t") == "series":
                return await self._series(payload)
            if kind == "season":
                return await self._season(payload)
            raise BrowseError("This Nuvio item cannot be expanded")
        except (NuvioApiError, NuvioAuthError) as err:
            raise BrowseError(str(err)) from err

    async def _root(self) -> BrowseMediaSource:
        children: list[BrowseMediaSource] = []
        if self.account_api is not None:
            children.extend(
                [
                    BrowseMediaSource(
                        domain=DOMAIN,
                        identifier=_encode({"k": "continue"}),
                        media_class=MediaClass.DIRECTORY,
                        media_content_type=MediaType.VIDEO,
                        title="Continue Watching",
                        can_play=False,
                        can_expand=True,
                        children_media_class=MediaClass.VIDEO,
                    ),
                    BrowseMediaSource(
                        domain=DOMAIN,
                        identifier=_encode({"k": "library"}),
                        media_class=MediaClass.DIRECTORY,
                        media_content_type=MediaType.VIDEO,
                        title="My Library",
                        can_play=False,
                        can_expand=True,
                        children_media_class=MediaClass.VIDEO,
                    ),
                ]
            )
        for addon in await self.api.async_addons():
            for catalog in addon.manifest.get("catalogs", []):
                if not isinstance(catalog, dict):
                    continue
                media_type = str(catalog.get("type", ""))
                catalog_id = str(catalog.get("id", ""))
                if media_type not in {"movie", "series"} or not catalog_id:
                    continue
                label = catalog.get("name") or catalog_id
                children.append(
                    BrowseMediaSource(
                        domain=DOMAIN,
                        identifier=_encode(
                            {
                                "k": "catalog",
                                "a": addon.manifest_url,
                                "t": media_type,
                                "c": catalog_id,
                            }
                        ),
                        media_class=MediaClass.DIRECTORY,
                        media_content_type=_media_type(media_type),
                        title=f"{label} · {addon.name}",
                        can_play=False,
                        can_expand=True,
                        children_media_class=_media_class(media_type),
                    )
                )
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=None,
            media_class=MediaClass.APP,
            media_content_type=MediaType.APPS,
            title="Nuvio",
            can_play=False,
            can_expand=True,
            can_search=True,
            search_media_classes=[MediaClass.MOVIE, MediaClass.TV_SHOW],
            children_media_class=MediaClass.DIRECTORY,
            children=children,
        )

    async def _library(self, payload: dict[str, Any]) -> BrowseMediaSource:
        """Build the signed-in profile's Nuvio library."""
        if self.account_api is None:
            raise BrowseError("Nuvio account is not connected")
        items = await self.account_api.async_library(self.profile_id)
        children: list[BrowseMediaSource] = []
        for meta in sorted(
            items, key=lambda value: int(value.get("added_at") or 0), reverse=True
        ):
            media_type = str(meta.get("content_type") or "movie")
            content_id = str(meta.get("content_id") or "")
            if not content_id:
                continue
            title_payload: dict[str, Any] = {
                "k": "account_title",
                "t": media_type,
                "i": content_id,
            }
            if addon_base := meta.get("addon_base_url"):
                title_payload["a"] = f"{str(addon_base).rstrip('/')}/manifest.json"
            children.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=_encode(title_payload),
                    media_class=_media_class(media_type),
                    media_content_type=_media_type(media_type),
                    title=str(meta.get("name") or content_id),
                    can_play=True,
                    can_expand=media_type == "series" and "a" in title_payload,
                    thumbnail=meta.get("poster") or meta.get("background"),
                )
            )
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=_encode(payload),
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.VIDEO,
            title="My Library",
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.VIDEO,
            children=children,
        )

    async def _continue_watching(self, payload: dict[str, Any]) -> BrowseMediaSource:
        """Build the signed-in profile's active watch-progress list."""
        if self.account_api is None:
            raise BrowseError("Nuvio account is not connected")
        progress = await self.account_api.async_watch_progress(self.profile_id)
        library = await self.account_api.async_library(self.profile_id)
        metadata = {
            (str(item.get("content_type")), str(item.get("content_id"))): item
            for item in library
        }
        active = [
            item
            for item in progress
            if int(item.get("duration") or 0) > 0
            and int(item.get("position") or 0) < int(item.get("duration") or 0) * 0.95
        ]
        active.sort(key=lambda value: int(value.get("last_watched") or 0), reverse=True)
        children: list[BrowseMediaSource] = []
        for item in active:
            media_type = str(item.get("content_type") or "movie")
            content_id = str(item.get("content_id") or "")
            meta = metadata.get((media_type, content_id), {})
            season = item.get("season")
            episode = item.get("episode")
            episode_suffix = (
                f" · S{season} E{episode}"
                if season is not None and episode is not None
                else ""
            )
            children.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=_encode(
                        {
                            "k": "episode"
                            if media_type == "series"
                            else "account_title",
                            "t": media_type,
                            "i": content_id,
                            "v": item.get("video_id") or content_id,
                            "s": season,
                            "e": episode,
                        }
                    ),
                    media_class=_media_class(
                        media_type, episode=media_type == "series"
                    ),
                    media_content_type=_media_type(
                        media_type, episode=media_type == "series"
                    ),
                    title=f"{meta.get('name') or content_id}{episode_suffix}",
                    can_play=True,
                    can_expand=False,
                    thumbnail=meta.get("poster") or meta.get("background"),
                )
            )
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=_encode(payload),
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.VIDEO,
            title="Continue Watching",
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.VIDEO,
            children=children,
        )

    async def _catalog(self, payload: dict[str, Any]) -> BrowseMediaSource:
        addon = await self._addon(payload["a"])
        metas = await self.api.async_catalog(addon, payload["t"], payload["c"])
        children = [self._title_item(addon, meta, payload["t"]) for meta in metas]
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=_encode(payload),
            media_class=MediaClass.DIRECTORY,
            media_content_type=_media_type(payload["t"]),
            title=str(payload["c"]),
            can_play=False,
            can_expand=True,
            can_search=True,
            search_media_classes=[MediaClass.MOVIE, MediaClass.TV_SHOW],
            children_media_class=_media_class(payload["t"]),
            children=children,
        )

    def _title_item(
        self, addon: Addon, meta: dict[str, Any], fallback_type: str
    ) -> BrowseMediaSource:
        media_type = str(meta.get("type") or fallback_type)
        content_id = str(meta.get("id", ""))
        payload = {
            "k": "title",
            "a": addon.manifest_url,
            "t": media_type,
            "i": content_id,
        }
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=_encode(payload),
            media_class=_media_class(media_type),
            media_content_type=_media_type(media_type),
            title=str(meta.get("name") or content_id),
            can_play=True,
            can_expand=media_type == "series",
            thumbnail=meta.get("poster") or meta.get("background"),
        )

    async def _series(self, payload: dict[str, Any]) -> BrowseMediaSource:
        addon = await self._addon(payload["a"])
        meta = await self.api.async_meta(addon, "series", payload["i"])
        videos = [v for v in meta.get("videos", []) if isinstance(v, dict)]
        seasons = sorted(
            {
                int(video["season"])
                for video in videos
                if str(video.get("season", "")).isdigit()
            }
        )
        children = [
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=_encode({**payload, "k": "season", "s": season}),
                media_class=MediaClass.SEASON,
                media_content_type=MediaType.SEASON,
                title=f"Season {season}",
                can_play=False,
                can_expand=True,
                thumbnail=meta.get("poster"),
                children_media_class=MediaClass.EPISODE,
            )
            for season in seasons
        ]
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=_encode(payload),
            media_class=MediaClass.TV_SHOW,
            media_content_type=MediaType.TVSHOW,
            title=str(meta.get("name") or payload["i"]),
            can_play=True,
            can_expand=True,
            thumbnail=meta.get("poster"),
            children_media_class=MediaClass.SEASON,
            children=children,
        )

    async def _season(self, payload: dict[str, Any]) -> BrowseMediaSource:
        addon = await self._addon(payload["a"])
        meta = await self.api.async_meta(addon, "series", payload["i"])
        season = int(payload["s"])
        videos = [
            video
            for video in meta.get("videos", [])
            if isinstance(video, dict) and video.get("season") == season
        ]
        videos.sort(key=lambda video: int(video.get("episode") or 0))
        children = []
        for video in videos:
            episode = int(video.get("episode") or 0)
            ep_payload = {
                "k": "episode",
                "t": "series",
                "i": payload["i"],
                "v": str(video.get("id") or f"{payload['i']}:{season}:{episode}"),
                "s": season,
                "e": episode,
            }
            children.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=_encode(ep_payload),
                    media_class=MediaClass.EPISODE,
                    media_content_type=MediaType.EPISODE,
                    title=str(video.get("title") or f"Episode {episode}"),
                    can_play=True,
                    can_expand=False,
                    thumbnail=video.get("thumbnail") or meta.get("poster"),
                )
            )
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=_encode(payload),
            media_class=MediaClass.SEASON,
            media_content_type=MediaType.SEASON,
            title=f"Season {season}",
            can_play=False,
            can_expand=True,
            thumbnail=meta.get("poster"),
            children_media_class=MediaClass.EPISODE,
            children=children,
        )

    @override
    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve a selection to Nuvio's native details deep link."""
        try:
            payload = _decode(item.identifier)
            media_type = str(payload["t"])
            content_id = str(payload["i"])
        except (KeyError, BrowseError) as err:
            raise Unresolvable("Invalid Nuvio item") from err
        return PlayMedia(deep_link(media_type, content_id), "video")

    @override
    async def async_search_media(
        self, item: MediaSourceItem, query: SearchMediaQuery
    ) -> SearchMedia:
        """Search configured addon catalogs."""
        try:
            results = await self.api.async_search(query.search_query)
        except NuvioApiError as err:
            raise BrowseError(str(err)) from err
        return SearchMedia(
            result=[
                self._title_item(addon, meta, str(meta.get("type", "movie")))
                for addon, meta in results
            ]
        )


async def async_get_media_source(hass: HomeAssistant) -> NuvioMediaSource:
    """Set up the Nuvio media source."""
    return NuvioMediaSource(hass)
