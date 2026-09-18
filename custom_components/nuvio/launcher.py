"""Build Nuvio deep links and TV launch commands."""

from __future__ import annotations

import re
import shlex
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

from .const import NUVIO_ACTIVITY, NUVIO_WEBOS_APP_ID
from .providers import (
    ANDROID_PROVIDER_PACKAGES,
    PROVIDER_ALIASES,
    WEBOS_PROVIDER_APP_IDS,
    streaming_provider_key,
)


def deep_link(media_type: str, content_id: str) -> str:
    """Create a Nuvio details deep link."""
    normalized_type = "series" if media_type in {"series", "show", "tv"} else "movie"
    return f"nuvio://{normalized_type}/{quote(content_id, safe=':')}"


def _arg(value: Any) -> str:
    """Quote one shell argument for adb shell."""
    return shlex.quote(str(value))


def stream_intent_command(
    *,
    package_name: str,
    media_type: str,
    content_id: str,
    title: str,
    video_id: str | None = None,
    poster: str | None = None,
    backdrop: str | None = None,
    logo: str | None = None,
    season: int | None = None,
    episode: int | None = None,
    episode_title: str | None = None,
) -> str:
    """Create the exact ADB command Nuvio expects for direct playback."""
    normalized_type = "series" if media_type in {"series", "show", "tv"} else "movie"
    effective_video_id = video_id or (
        f"{content_id}:{season}:{episode}"
        if season is not None and episode is not None
        else content_id
    )
    string_extras: dict[str, str | None] = {
        "contentId": content_id,
        "contentType": normalized_type,
        "videoId": effective_video_id,
        "name": title,
        "poster": poster,
        "backdrop": backdrop,
        "logo": logo,
        "episodeTitle": episode_title,
        "launchMode": "stream",
    }
    parts = [
        "am",
        "start",
        "-W",
        "-a",
        "android.intent.action.VIEW",
        "-n",
        f"{package_name}/{NUVIO_ACTIVITY}",
        "--activity-clear-top",
    ]
    for key, value in string_extras.items():
        if value is not None:
            parts.extend(("--es", key, _arg(value)))
    for key, value in (("season", season), ("episode", episode)):
        if value is not None:
            parts.extend(("--ei", key, str(value)))
    return " ".join(parts)


def player_intent_command(
    *,
    package_name: str,
    stream_url: str,
    stream_title: str,
    mime_type: str | None = None,
    media_type: str | None = None,
    content_id: str | None = None,
    video_id: str | None = None,
    title: str | None = None,
    poster: str | None = None,
    backdrop: str | None = None,
    logo: str | None = None,
    season: int | None = None,
    episode: int | None = None,
    episode_title: str | None = None,
    filename: str | None = None,
    video_size: int | None = None,
    addon_name: str | None = None,
    addon_logo: str | None = None,
    stream_description: str | None = None,
    info_hash: str | None = None,
    file_idx: int | None = None,
    content_language: str | None = None,
    profile_id: int | None = None,
) -> str:
    """Launch one exact URL in Nuvio's internal Android player."""
    normalized_type = (
        "series" if media_type in {"series", "show", "tv"} else "movie"
        if media_type
        else None
    )
    string_extras: dict[str, str | None] = {
        "launchMode": "player",
        "streamUrl": stream_url,
        "streamTitle": stream_title,
        "mimeType": mime_type,
        "contentType": normalized_type,
        "contentId": content_id,
        "videoId": video_id,
        "name": title,
        "poster": poster,
        "backdrop": backdrop,
        "logo": logo,
        "episodeTitle": episode_title,
        "filename": filename,
        "addonName": addon_name,
        "addonLogo": addon_logo,
        "streamDescription": stream_description,
        "infoHash": info_hash,
        "contentLanguage": content_language,
    }
    parts = [
        "am",
        "start",
        "-W",
        "-a",
        "android.intent.action.VIEW",
        "-n",
        f"{package_name}/{NUVIO_ACTIVITY}",
        "--activity-clear-top",
    ]
    for key, value in string_extras.items():
        if value is not None:
            parts.extend(("--es", key, _arg(value)))
    for key, value in (
        ("season", season),
        ("episode", episode),
        ("fileIdx", file_idx),
        ("profileId", profile_id),
    ):
        if value is not None:
            parts.extend(("--ei", key, str(value)))
    if video_size is not None:
        parts.extend(("--el", "videoSize", str(int(video_size))))
    return " ".join(parts)


def webos_launch_payload(
    *,
    media_type: str,
    content_id: str,
    title: str | None = None,
    video_id: str | None = None,
    poster: str | None = None,
    backdrop: str | None = None,
    logo: str | None = None,
    season: int | None = None,
    episode: int | None = None,
    episode_title: str | None = None,
    launch_mode: str = "details",
    stream_url: str | None = None,
    stream_title: str | None = None,
    mime_type: str | None = None,
    filename: str | None = None,
    video_size: int | None = None,
    addon_name: str | None = None,
    addon_logo: str | None = None,
    stream_description: str | None = None,
    info_hash: str | None = None,
    file_idx: int | None = None,
    content_language: str | None = None,
    profile_id: int | None = None,
) -> dict[str, Any]:
    """Build webOS Application Manager payload for Nuvio TV.

    HA-compatible NuvioTVSmart builds consume launchMode="player" plus streamUrl
    and route the exact selected source into Nuvio's internal player. The same
    payload remains backward-compatible with builds that only launch the app.
    """
    normalized_type = "series" if media_type in {"series", "show", "tv"} else "movie"
    effective_video_id = video_id or (
        f"{content_id}:{season}:{episode}"
        if season is not None and episode is not None
        else content_id
    )
    params: dict[str, Any] = {
        "target": deep_link(normalized_type, content_id),
        "contentId": content_id,
        "contentType": normalized_type,
        "launchMode": launch_mode,
    }
    if stream_url is not None:
        params["streamUrl"] = stream_url
    if stream_title is not None:
        params["streamTitle"] = stream_title
    if mime_type is not None:
        params["mimeType"] = mime_type
    optional: dict[str, Any] = {
        "videoId": effective_video_id,
        "name": title,
        "poster": poster,
        "backdrop": backdrop,
        "logo": logo,
        "season": season,
        "episode": episode,
        "episodeTitle": episode_title,
        "filename": filename,
        "videoSize": video_size,
        "addonName": addon_name,
        "addonLogo": addon_logo,
        "streamDescription": stream_description,
        "infoHash": info_hash,
        "fileIdx": file_idx,
        "contentLanguage": content_language,
        "profileId": profile_id,
    }
    params.update({key: value for key, value in optional.items() if value is not None})
    return {"id": NUVIO_WEBOS_APP_ID, "params": params}



_PROVIDER_ALIASES = PROVIDER_ALIASES


def _provider_norm(value: str | None) -> str:
    """Normalize a provider/app label for fuzzy source matching."""
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold().replace("+", "plus"))


def provider_key(provider_name: str | None, external_url: str | None = None) -> str | None:
    """Return a canonical or generic streaming-provider key."""
    return streaming_provider_key(provider_name, external_url)


def provider_source_match(provider: str, sources: list[str]) -> str | None:
    """Match a canonical provider to a Home Assistant webOS source label."""
    aliases = _PROVIDER_ALIASES.get(provider, (provider,))
    best: str | None = None
    best_score = -1
    for source in sources:
        normalized = _provider_norm(source)
        for alias in aliases:
            normalized_alias = _provider_norm(alias)
            if normalized == normalized_alias:
                score = 100
            elif len(normalized_alias) >= 3 and (
                normalized_alias in normalized or normalized in normalized_alias
            ):
                score = min(len(normalized), len(normalized_alias))
            else:
                continue
            if score > best_score:
                best = source
                best_score = score
    return best


def _decoded_url(external_url: str) -> str:
    raw = str(external_url or "").strip()
    try:
        return unquote(raw)
    except ValueError:
        return raw


def netflix_content_id(external_url: str) -> str | None:
    """Extract the numeric Netflix title id from a provider URL."""
    raw = str(external_url or "")
    decoded = _decoded_url(raw)
    patterns = (
        r"netflix\.com/(?:watch|title)/(\d+)",
        r"api\.netflix\.com/catalog/titles/(?:movies|series|programs)/(\d+)",
        r"(?:^|[?&])(?:movieid|contentid|titleid)=(\d+)",
    )
    for candidate in (raw, decoded):
        for pattern in patterns:
            match = re.search(pattern, candidate, re.IGNORECASE)
            if match:
                return match.group(1)
    return None


def provider_content_id(provider: str, external_url: str) -> str | None:
    """Extract the provider's stable title/entity id from a WatchHub URL."""
    raw = _decoded_url(external_url)
    parsed = urlparse(raw)
    query = parse_qs(parsed.query)
    path = parsed.path or ""

    if provider == "netflix":
        provider_id = netflix_content_id(external_url)
        raw_url = str(external_url or "").strip()
        exact_watch_url = "/watch/" in raw_url.casefold()

        legacy_payload: dict[str, Any] = {"id": "netflix"}
        if provider_id:
            netflix_target = (
                "m=http%3A%2F%2Fapi.netflix.com%2Fcatalog%2Ftitles%2Fmovies%2F"
                f"{provider_id}&source_type=4"
            )
            legacy_payload["contentId"] = netflix_target
            # ConnectSDK-compatible webOS launchers commonly duplicate the
            # Netflix content id inside params as well as at the top level.
            legacy_payload["params"] = {"contentId": netflix_target}
        if media_type:
            legacy_payload["mediaType"] = media_type
        if content_id:
            legacy_payload["sourceContentId"] = content_id
        if video_id:
            legacy_payload["videoId"] = video_id
        if season is not None:
            legacy_payload["season"] = season
        if episode is not None:
            legacy_payload["episode"] = episode
        if episode_title:
            legacy_payload["episodeTitle"] = episode_title

        # Exact Netflix /watch/<playable-id> links identify the individual
        # episode. Give that URL the first launch attempt using the application
        # manager contract seen in other webOS Netflix controllers. If webOS
        # rejects that request, the caller falls back to Netflix's established
        # legacy contentId contract below.
        if exact_watch_url and media_type == "series" and episode is not None:
            exact_params: dict[str, Any] = {
                "contentTarget": raw_url,
                "target": raw_url,
                "url": raw_url,
            }
            if provider_id:
                exact_params["contentId"] = provider_id
            if content_id:
                exact_params["sourceContentId"] = content_id
            if video_id:
                exact_params["sourceVideoId"] = video_id
            if season is not None:
                exact_params["season"] = season
            exact_params["episode"] = episode
            if episode_title:
                exact_params["episodeTitle"] = episode_title
            return [
                (
                    "com.webos.applicationManager/launch",
                    {"id": "netflix", "params": exact_params},
                ),
                ("system.launcher/launch", legacy_payload),
            ]

        return [("system.launcher/launch", legacy_payload)]

    app_ids = WEBOS_PROVIDER_APP_IDS.get(provider, ())
    if not app_ids:
        return []

    params = _webos_provider_params(
        provider,
        external_url,
        media_type=media_type,
        content_id=content_id,
        video_id=video_id,
        season=season,
        episode=episode,
        episode_title=episode_title,
    )
    requests: list[tuple[str, dict[str, Any]]] = []
    target = str(params.get("contentTarget") or external_url or "").strip()

    # Netflix has its own special contentId format above. Apple TV is already
    # confirmed working through applicationManager/launch on the user's TV, so
    # preserve that path. For the providers below, prefer system.launcher/launch
    # and send the exact title target in BOTH contentId and params.contentTarget.
    # This matches the Prime Video launch contract used successfully by the
    # companion Streaming Browser Card and gives older/newer webOS launchers
    # both forms they are known to inspect.
    prefer_system_launcher = provider in {
        "prime",
        "disney",
        "max",
        "crunchyroll",
        "paramount",
    }

    for app_id in app_ids:
        if prefer_system_launcher:
            payload: dict[str, Any] = {
                "id": app_id,
                "params": dict(params),
            }
            if target:
                payload["contentId"] = target
            requests.append(("system.launcher/launch", payload))
            # Keep applicationManager as a fallback for app-id / firmware
            # combinations where system.launcher rejects the request entirely.
            requests.append(
                (
                    "com.webos.applicationManager/launch",
                    {
                        "id": app_id,
                        "params": dict(params),
                    },
                )
            )
            continue

        requests.append(
            (
                "com.webos.applicationManager/launch",
                {
                    "id": app_id,
                    "params": dict(params),
                },
            )
        )
    return requests


def webos_provider_launch_payload(
    provider: str, external_url: str
) -> dict[str, Any] | None:
    """Compatibility helper returning the first provider-specific webOS payload."""
    requests = webos_provider_launch_requests(provider, external_url)
    return requests[0][1] if requests else None

def direct_stream_command(url: str, *, mime_type: str | None = None) -> str:
    """Open an exact stream URL with Android's media handler."""
    parts = [
        "am",
        "start",
        "-W",
        "-a",
        "android.intent.action.VIEW",
        "-d",
        _arg(url),
    ]
    if mime_type:
        parts.extend(("-t", _arg(mime_type)))
    return " ".join(parts)
