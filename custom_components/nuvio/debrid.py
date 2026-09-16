"""Resolve Nuvio torrent/debrid sources into playable HTTP links."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import re
import time
from typing import Any
from urllib.parse import quote_plus

from aiohttp import ClientError, ClientSession, FormData

REAL_DEBRID = "realdebrid"
TORBOX = "torbox"
PREMIUMIZE = "premiumize"
SUPPORTED_PROVIDERS = {REAL_DEBRID, TORBOX, PREMIUMIZE}

REAL_DEBRID_BASE = "https://api.real-debrid.com/rest/1.0"
TORBOX_BASE = "https://api.torbox.app"
PREMIUMIZE_BASE = "https://www.premiumize.me"

VIDEO_EXTENSIONS = (
    ".mp4",
    ".mkv",
    ".webm",
    ".avi",
    ".mov",
    ".m4v",
    ".ts",
    ".m2ts",
    ".wmv",
    ".flv",
)
CACHE_TTL = 15 * 60


class DebridResolveError(Exception):
    """Raised when a debrid source cannot be resolved."""


class DebridNotConfigured(DebridResolveError):
    """Raised when no matching debrid credential is configured."""


class DebridNotCached(DebridResolveError):
    """Raised when the source is not instantly available."""


@dataclass(slots=True)
class ResolvedStream:
    """Final direct link returned by a debrid provider."""

    url: str
    filename: str | None = None
    video_size: int | None = None
    provider: str | None = None


def normalize_provider(value: Any) -> str:
    """Normalize provider IDs used by Nuvio."""
    text = str(value or "").strip().lower().replace("-", "").replace("_", "")
    aliases = {
        "rd": REAL_DEBRID,
        "realdebrid": REAL_DEBRID,
        "realdebridinstant": REAL_DEBRID,
        "tb": TORBOX,
        "torbox": TORBOX,
        "torboxinstant": TORBOX,
        "pm": PREMIUMIZE,
        "premiumize": PREMIUMIZE,
        "premiumizeinstant": PREMIUMIZE,
    }
    return aliases.get(text, "")


def _video_name(file: dict[str, Any]) -> str:
    for key in ("short_name", "name", "absolute_path", "path", "filename"):
        value = file.get(key)
        if isinstance(value, str) and value.strip():
            return value.replace("\\", "/").rsplit("/", 1)[-1]
    return ""


def _video_size(file: dict[str, Any]) -> int:
    for key in ("size", "bytes"):
        try:
            value = int(file.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return 0


def _is_video(file: dict[str, Any]) -> bool:
    mime = str(file.get("mimetype") or file.get("mime_type") or "").lower()
    if mime.startswith("video/"):
        return True
    return _video_name(file).lower().endswith(VIDEO_EXTENSIONS)


def _normalized_name(value: str) -> str:
    value = value.replace("\\", "/").rsplit("/", 1)[-1]
    value = value.rsplit(".", 1)[0]
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _episode_patterns(season: int | None, episode: int | None) -> list[str]:
    if season is None or episode is None:
        return []
    return [
        f"s{season:02d}e{episode:02d}",
        f"{season}x{episode:02d}",
        f"{season}x{episode}",
    ]


def _select_file(
    files: list[dict[str, Any]],
    *,
    file_idx: int | None,
    filename: str | None,
    season: int | None,
    episode: int | None,
) -> dict[str, Any] | None:
    """Select the same kind of playable file Nuvio chooses."""
    playable = [file for file in files if isinstance(file, dict) and _is_video(file)]
    if not playable:
        return None

    patterns = _episode_patterns(season, episode)

    if filename:
        wanted = _normalized_name(filename)
        if wanted:
            for file in playable:
                candidate = _normalized_name(_video_name(file))
                if candidate and (candidate in wanted or wanted in candidate):
                    return file

    if patterns:
        for file in playable:
            lowered = _video_name(file).lower()
            if any(pattern in lowered for pattern in patterns):
                return file

    if file_idx is not None:
        if 0 <= file_idx < len(files) and isinstance(files[file_idx], dict) and _is_video(files[file_idx]):
            return files[file_idx]
        if file_idx > 0 and file_idx - 1 < len(files):
            candidate = files[file_idx - 1]
            if isinstance(candidate, dict) and _is_video(candidate):
                return candidate
        for file in playable:
            try:
                if int(file.get("id")) == file_idx:
                    return file
            except (TypeError, ValueError):
                pass

    return max(playable, key=_video_size)


def _magnet_uri(source: dict[str, Any]) -> str | None:
    magnet = source.get("magnet_uri")
    if isinstance(magnet, str) and magnet.strip():
        return magnet.strip()

    info_hash = str(source.get("info_hash") or "").strip()
    if not info_hash:
        return None

    parts = [f"magnet:?xt=urn:btih:{info_hash}"]
    trackers = source.get("torrent_sources")
    if isinstance(trackers, list):
        for tracker in trackers:
            value = str(tracker or "").strip()
            if not value or value.lower().startswith("dht:"):
                continue
            if value.lower().startswith("tracker:"):
                value = value.split(":", 1)[1].strip()
            if value:
                parts.append("&tr=" + quote_plus(value))
    return "".join(parts)


class DebridResolver:
    """Resolve debrid/torrent streams using user-provided provider credentials."""

    def __init__(
        self,
        session: ClientSession,
        *,
        provider: str | None,
        api_key: str | None,
        credentials: dict[str, str] | None = None,
    ) -> None:
        self._session = session
        self.provider = normalize_provider(provider)
        self.api_key = str(api_key or "").strip()
        self._credentials: dict[str, str] = {}
        for provider_id, credential in (credentials or {}).items():
            normalized = normalize_provider(provider_id)
            value = str(credential or "").strip()
            if normalized in SUPPORTED_PROVIDERS and value:
                self._credentials[normalized] = value
        if self.provider in SUPPORTED_PROVIDERS and self.api_key:
            self._credentials[self.provider] = self.api_key
        self._cache: dict[str, tuple[float, ResolvedStream]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    @property
    def configured(self) -> bool:
        return bool(self._credentials)

    @property
    def providers(self) -> list[str]:
        """Return configured provider IDs without exposing credentials."""
        return list(self._credentials)

    def can_resolve(self, source: dict[str, Any]) -> bool:
        """Return whether a credential is available for this source."""
        try:
            self._credential_for(source)
        except DebridNotConfigured:
            return False
        return True

    def _credential_for(self, source: dict[str, Any]) -> tuple[str, str]:
        requested = normalize_provider(source.get("resolver_service"))
        if requested:
            api_key = self._credentials.get(requested)
            if api_key:
                return requested, api_key
            raise DebridNotConfigured(
                f"This source expects {requested}, but that credential is not available."
            )

        if self.provider in self._credentials:
            return self.provider, self._credentials[self.provider]

        for candidate in (TORBOX, PREMIUMIZE, REAL_DEBRID):
            api_key = self._credentials.get(candidate)
            if api_key:
                return candidate, api_key

        raise DebridNotConfigured(
            "No debrid credential is available for this source."
        )

    def _cache_key(
        self,
        source: dict[str, Any],
        season: int | None,
        episode: int | None,
        provider: str,
    ) -> str:
        return "|".join(
            (
                provider,
                str(source.get("info_hash") or source.get("magnet_uri") or "").lower(),
                str(source.get("file_idx") if source.get("file_idx") is not None else ""),
                str(source.get("filename") or "").lower(),
                str(season or ""),
                str(episode or ""),
            )
        )

    async def _json(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        data: Any = None,
        params: dict[str, Any] | None = None,
        allow_empty: bool = False,
    ) -> tuple[int, Any]:
        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                data=data,
                params=params,
                timeout=30,
            ) as response:
                status = response.status
                if allow_empty and status in {200, 201, 202, 204}:
                    text = await response.text()
                    if not text.strip():
                        return status, None
                try:
                    body = await response.json(content_type=None)
                except ValueError:
                    body = await response.text()
                return status, body
        except (ClientError, TimeoutError) as err:
            raise DebridResolveError(f"Could not contact debrid provider: {err}") from err

    async def async_resolve(
        self,
        source: dict[str, Any],
        *,
        season: int | None = None,
        episode: int | None = None,
    ) -> ResolvedStream:
        """Resolve one Nuvio source to a direct URL."""
        provider, api_key = self._credential_for(source)

        cache_key = self._cache_key(source, season, episode, provider)
        cached = self._cache.get(cache_key)
        now = time.monotonic()
        if cached and now - cached[0] < CACHE_TTL:
            return cached[1]

        lock = self._locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            cached = self._cache.get(cache_key)
            now = time.monotonic()
            if cached and now - cached[0] < CACHE_TTL:
                return cached[1]

            if provider == REAL_DEBRID:
                result = await self._resolve_real_debrid(source, season, episode, api_key)
            elif provider == TORBOX:
                result = await self._resolve_torbox(source, season, episode, api_key)
            elif provider == PREMIUMIZE:
                result = await self._resolve_premiumize(source, season, episode, api_key)
            else:
                raise DebridNotConfigured("Unsupported debrid provider.")

            self._cache[cache_key] = (time.monotonic(), result)
            return result

    async def _resolve_real_debrid(
        self,
        source: dict[str, Any],
        season: int | None,
        episode: int | None,
        api_key: str,
    ) -> ResolvedStream:
        magnet = _magnet_uri(source)
        if not magnet:
            raise DebridResolveError("This source does not contain a torrent hash or magnet link.")

        headers = {"Authorization": f"Bearer {api_key}"}
        status, add = await self._json(
            "POST",
            f"{REAL_DEBRID_BASE}/torrents/addMagnet",
            headers=headers,
            data={"magnet": magnet},
        )
        if status in {401, 403}:
            raise DebridResolveError("Real-Debrid rejected the configured API key.")
        if status >= 400 or not isinstance(add, dict) or not add.get("id"):
            raise DebridResolveError("Real-Debrid could not add this magnet.")

        torrent_id = str(add["id"])
        resolved = False
        try:
            status, info = await self._json(
                "GET",
                f"{REAL_DEBRID_BASE}/torrents/info/{torrent_id}",
                headers=headers,
            )
            if status >= 400 or not isinstance(info, dict):
                raise DebridResolveError("Real-Debrid could not read torrent information.")

            files = info.get("files")
            if not isinstance(files, list):
                files = []
            selected = _select_file(
                files,
                file_idx=_coerce_int(source.get("file_idx")),
                filename=_source_filename(source),
                season=season,
                episode=episode,
            )
            if selected is None or selected.get("id") is None:
                raise DebridResolveError("No playable video file was found in this torrent.")

            status, _ = await self._json(
                "POST",
                f"{REAL_DEBRID_BASE}/torrents/selectFiles/{torrent_id}",
                headers=headers,
                data={"files": str(selected["id"])},
                allow_empty=True,
            )
            if status not in {200, 201, 202, 204}:
                raise DebridResolveError("Real-Debrid could not select the video file.")

            status, info = await self._json(
                "GET",
                f"{REAL_DEBRID_BASE}/torrents/info/{torrent_id}",
                headers=headers,
            )
            if status >= 400 or not isinstance(info, dict):
                raise DebridResolveError("Real-Debrid could not refresh torrent information.")
            if str(info.get("status") or "").lower() != "downloaded":
                raise DebridNotCached("This Real-Debrid torrent is not instantly available.")
            links = info.get("links")
            link = next(
                (str(value) for value in links or [] if str(value or "").strip()),
                None,
            )
            if not link:
                raise DebridResolveError("Real-Debrid returned no download link.")

            status, unrestricted = await self._json(
                "POST",
                f"{REAL_DEBRID_BASE}/unrestrict/link",
                headers=headers,
                data={"link": link},
            )
            if status >= 400 or not isinstance(unrestricted, dict):
                raise DebridResolveError("Real-Debrid could not unrestrict the selected file.")
            url = str(unrestricted.get("download") or "").strip()
            if not url:
                raise DebridResolveError("Real-Debrid returned no playable URL.")

            resolved = True
            return ResolvedStream(
                url=url,
                filename=str(unrestricted.get("filename") or _video_name(selected) or "") or None,
                video_size=_coerce_int(unrestricted.get("filesize")) or _video_size(selected) or None,
                provider=REAL_DEBRID,
            )
        finally:
            if not resolved:
                try:
                    await self._json(
                        "DELETE",
                        f"{REAL_DEBRID_BASE}/torrents/delete/{torrent_id}",
                        headers=headers,
                        allow_empty=True,
                    )
                except DebridResolveError:
                    pass

    async def _resolve_torbox(
        self,
        source: dict[str, Any],
        season: int | None,
        episode: int | None,
        api_key: str,
    ) -> ResolvedStream:
        magnet = _magnet_uri(source)
        if not magnet:
            raise DebridResolveError("This source does not contain a torrent hash or magnet link.")

        headers = {"Authorization": f"Bearer {api_key}"}
        form = FormData()
        form.add_field("magnet", magnet, content_type="text/plain")
        form.add_field("add_only_if_cached", "true", content_type="text/plain")
        form.add_field("allow_zip", "false", content_type="text/plain")
        status, created = await self._json(
            "POST",
            f"{TORBOX_BASE}/v1/api/torrents/createtorrent",
            headers=headers,
            data=form,
        )
        if status in {401, 403}:
            raise DebridResolveError("TorBox rejected the configured API key.")
        if status == 409:
            raise DebridNotCached("This TorBox torrent is not cached.")
        data = created.get("data") if isinstance(created, dict) else None
        if status >= 400 or not isinstance(data, dict):
            raise DebridResolveError("TorBox could not create this cached torrent.")
        torrent_id = data.get("torrent_id")
        if torrent_id is None:
            torrent_id = data.get("id")
        torrent_id_int = _coerce_int(torrent_id)
        if torrent_id_int is None:
            raise DebridResolveError("TorBox returned no torrent ID.")

        status, torrent = await self._json(
            "GET",
            f"{TORBOX_BASE}/v1/api/torrents/mylist",
            headers=headers,
            params={"id": torrent_id_int, "bypass_cache": "true"},
        )
        data = torrent.get("data") if isinstance(torrent, dict) else None
        if status >= 400 or not isinstance(data, dict):
            raise DebridResolveError("TorBox could not read torrent information.")
        files = data.get("files")
        if not isinstance(files, list):
            files = []
        selected = _select_file(
            files,
            file_idx=_coerce_int(source.get("file_idx")),
            filename=_source_filename(source),
            season=season,
            episode=episode,
        )
        if selected is None or selected.get("id") is None:
            raise DebridResolveError("No playable video file was found in this torrent.")

        file_id = _coerce_int(selected.get("id"))
        if file_id is None:
            raise DebridResolveError("TorBox returned an invalid file ID.")

        status, link = await self._json(
            "GET",
            f"{TORBOX_BASE}/v1/api/torrents/requestdl",
            headers=headers,
            params={
                "token": api_key,
                "torrent_id": torrent_id_int,
                "file_id": file_id,
                "zip_link": "false",
                "redirect": "false",
                "append_name": "false",
            },
        )
        url = link.get("data") if isinstance(link, dict) else None
        if status >= 400 or not isinstance(url, str) or not url.strip():
            raise DebridResolveError("TorBox returned no playable URL.")

        return ResolvedStream(
            url=url.strip(),
            filename=_video_name(selected) or None,
            video_size=_video_size(selected) or None,
            provider=TORBOX,
        )

    async def _resolve_premiumize(
        self,
        source: dict[str, Any],
        season: int | None,
        episode: int | None,
        api_key: str,
    ) -> ResolvedStream:
        magnet = _magnet_uri(source)
        if not magnet:
            raise DebridResolveError("This source does not contain a torrent hash or magnet link.")

        headers = {"Authorization": f"Bearer {api_key}"}
        status, body = await self._json(
            "POST",
            f"{PREMIUMIZE_BASE}/api/transfer/directdl",
            headers=headers,
            data={"src": magnet},
        )
        if status in {401, 403}:
            raise DebridResolveError("Premiumize rejected the configured API key.")
        if status >= 400 or not isinstance(body, dict):
            raise DebridResolveError("Premiumize could not resolve this source.")
        if str(body.get("status") or "").lower() == "error":
            message = f"{body.get('message') or ''} {body.get('code') or ''}".lower()
            if "cache" in message or "not found" in message:
                raise DebridNotCached("This Premiumize source is not cached.")
            raise DebridResolveError(str(body.get("message") or "Premiumize resolve failed."))

        files = body.get("content")
        if not isinstance(files, list):
            files = []
        selected = _select_file(
            files,
            file_idx=_coerce_int(source.get("file_idx")),
            filename=_source_filename(source),
            season=season,
            episode=episode,
        )
        if selected is None:
            raise DebridResolveError("No playable video file was found in this source.")
        url = str(selected.get("link") or "").strip()
        if not url:
            raise DebridResolveError("Premiumize returned no playable URL.")

        return ResolvedStream(
            url=url,
            filename=_video_name(selected) or None,
            video_size=_video_size(selected) or None,
            provider=PREMIUMIZE,
        )


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _source_filename(source: dict[str, Any]) -> str | None:
    for key in ("resolve_filename", "filename", "torrent_name"):
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
