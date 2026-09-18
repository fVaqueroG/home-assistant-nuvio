"""Build Nuvio deep links and TV launch commands."""

from __future__ import annotations

import re
import shlex
from typing import Any
from urllib.parse import quote, unquote, urlparse

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



_PROVIDER_ALIASES: dict[str, tuple[str, ...]] = {
    "netflix": ("netflix", "netflixstandardwithads"),
    "prime": ("amazonprimevideo", "primevideo", "amazonvideo", "amazon", "prime"),
    "disney": ("disneyplus", "disney"),
    "max": ("hbomax", "max"),
    "paramount": ("paramountplus", "paramount"),
    "apple": ("appletvplus", "appletv", "apple"),
    "crunchyroll": ("crunchyroll",),
    "vix": ("vixpremium", "vix"),
    "claro": ("clarovideo", "claro"),
}


def _provider_norm(value: str | None) -> str:
    """Normalize a provider/app label for fuzzy source matching."""
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold().replace("+", "plus"))


def provider_key(provider_name: str | None, external_url: str | None = None) -> str | None:
    """Return a canonical streaming-provider key from a label and/or URL."""
    name = _provider_norm(provider_name)
    raw_url = str(external_url or "").strip()
    parsed = urlparse(raw_url)
    host = parsed.netloc.casefold()
    path = parsed.path.casefold()
    combined = _provider_norm(f"{host}{path}")

    host_rules = (
        ("netflix", ("netflix.com",)),
        ("prime", ("primevideo.com", "watch.amazon.", "amazon.com", "amazon.com.mx")),
        ("disney", ("disneyplus.com",)),
        ("max", ("max.com", "hbomax.com")),
        ("paramount", ("paramountplus.com",)),
        ("apple", ("tv.apple.com",)),
        ("crunchyroll", ("crunchyroll.com",)),
        ("vix", ("vix.com",)),
        ("claro", ("clarovideo.com",)),
    )
    for key, needles in host_rules:
        if any(needle in host for needle in needles):
            return key

    for key, aliases in _PROVIDER_ALIASES.items():
        if any(alias == name or (len(alias) >= 4 and alias in name) for alias in aliases):
            return key
        if any(alias == combined or (len(alias) >= 4 and alias in combined) for alias in aliases):
            return key
    return None


def provider_source_match(provider: str, sources: list[str]) -> str | None:
    """Match a canonical provider to a Home Assistant webOS source label."""
    aliases = _PROVIDER_ALIASES.get(provider, (provider,))
    best: str | None = None
    best_score = -1
    for source in sources:
        normalized = _provider_norm(source)
        for alias in aliases:
            if normalized == alias:
                score = 100
            elif len(alias) >= 3 and (alias in normalized or normalized in alias):
                score = min(len(normalized), len(alias))
            else:
                continue
            if score > best_score:
                best = source
                best_score = score
    return best


def netflix_content_id(external_url: str) -> str | None:
    """Extract the numeric Netflix title id from a provider URL."""
    raw = str(external_url or "")
    try:
        decoded = unquote(raw)
    except ValueError:
        decoded = raw
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


def android_provider_target(provider: str, external_url: str) -> str:
    """Return the Android app/deep-link target for a provider source."""
    if provider == "netflix":
        content_id = netflix_content_id(external_url)
        if content_id:
            return f"netflix://title/{content_id}"
    return external_url


def android_provider_command(provider: str, external_url: str) -> str:
    """Build an ADB command that hands a provider title to its Android TV app."""
    target = android_provider_target(provider, external_url)
    if provider == "netflix" and target.startswith("netflix://title/"):
        return " ".join(
            [
                "am",
                "start",
                "-W",
                "-n",
                "com.netflix.ninja/.MainActivity",
                "-a",
                "android.intent.action.VIEW",
                "-d",
                _arg(target),
                "-f",
                "0x10000020",
                "-e",
                "source",
                "30",
            ]
        )
    return " ".join(
        [
            "am",
            "start",
            "-W",
            "-a",
            "android.intent.action.VIEW",
            "-d",
            _arg(target),
        ]
    )


def webos_provider_launch_payload(
    provider: str, external_url: str
) -> dict[str, Any] | None:
    """Build an exact-title webOS launcher payload where the app supports it."""
    if provider == "netflix":
        content_id = netflix_content_id(external_url)
        if content_id:
            return {
                "id": "netflix",
                "contentId": (
                    "m=http%3A%2F%2Fapi.netflix.com%2Fcatalog%2Ftitles%2Fmovies%2F"
                    f"{content_id}&source_type=4"
                ),
            }
        return {"id": "netflix"}

    if provider == "prime":
        target = str(external_url or "").strip()
        if target:
            return {
                "id": "amazon",
                "contentId": target,
                "params": {"contentTarget": target},
            }
        return {"id": "amazon"}

    return None


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
