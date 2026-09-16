"""Build Nuvio deep links and Android launch commands."""

from __future__ import annotations

import shlex
from typing import Any
from urllib.parse import quote

from .const import NUVIO_ACTIVITY


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
