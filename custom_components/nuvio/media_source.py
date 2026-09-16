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

from .api import Addon, NuvioApi, NuvioApiError
from .const import DATA_API, DOMAIN
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
            if kind == "title" and payload.get("t") == "series":
                return await self._series(payload)
            if kind == "season":
                return await self._season(payload)
            raise BrowseError("This Nuvio item cannot be expanded")
        except NuvioApiError as err:
            raise BrowseError(str(err)) from err

    async def _root(self) -> BrowseMediaSource:
        children: list[BrowseMediaSource] = []
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
