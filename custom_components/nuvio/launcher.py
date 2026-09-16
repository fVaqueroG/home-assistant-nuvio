"""Build Nuvio deep links and TV launch commands."""

from __future__ import annotations

import shlex
from typing import Any
from urllib.parse import quote

from .const import NUVIO_ACTIVITY, NUVIO_WEBOS_APP_ID


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

    Nuvio TV for webOS currently launches correctly with these parameters but
    does not yet consume them for route navigation. Keeping the Android-compatible
    field names makes the integration ready when the app adds launch-param routing.
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
