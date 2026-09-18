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
    """Extract the provider's stable title/entity id from a provider URL."""
    raw = _decoded_url(external_url)
    parsed = urlparse(raw)
    query = parse_qs(parsed.query)
    path = parsed.path or ""

    if provider == "netflix":
        return netflix_content_id(raw)

    if provider == "prime":
        for key in ("gti", "asin", "contentId", "contentid"):
            values = query.get(key)
            if values and values[0]:
                return values[0]
        for pattern in (
            r"/detail/([^/?#]+)",
            r"/gp/video/detail/([^/?#]+)",
        ):
            match = re.search(pattern, path, re.IGNORECASE)
            if match:
                return match.group(1)

    if provider == "disney":
        provider_id = provider_content_id(provider, raw_url)
        requests: list[tuple[str, dict[str, Any]]] = []

        for app_id in WEBOS_PROVIDER_APP_IDS.get("disney", ()):
            if not raw_url:
                continue

            # Preserve the exact destination returned by the authenticated
            # JustWatch account. Do not rewrite /browse/entity/... into a
            # guessed /video/... URL: real-TV testing showed that rewrite does
            # not navigate to the selected title on this LG build.
            params: dict[str, Any] = {
                "contentTarget": raw_url,
                "target": raw_url,
            }
            if provider_id:
                # Different Disney+ webOS builds have inspected either of
                # these id keys. Sending both in the same launch avoids relying
                # on a second request after webOS has already accepted the first.
                params["contentId"] = provider_id
                params["entityId"] = provider_id

            requests.append(
                (
                    "com.webos.applicationManager/launch",
                    {"id": app_id, "params": params},
                )
            )

        return requests

    if provider == "max":
        for key in ("id", "contentId", "contentid"):
            values = query.get(key)
            if values and values[0]:
                return values[0]

        # Max playable URLs commonly use:
        #   /video/watch/<videoId>/<editId>
        # The first UUID after /video/watch/ is the content/video id.
        match = re.search(
            r"/video/watch/([a-z0-9-]{8,})(?:/|$)",
            path,
            re.IGNORECASE,
        )
        if match:
            return match.group(1)

        match = re.search(
            r"/(?:movie|movies|show|watch)/([a-z0-9-]{8,})(?:/|$)",
            path,
            re.IGNORECASE,
        )
        if match:
            return match.group(1)

    if provider == "crunchyroll":
        match = re.search(r"/(?:watch|series)/([A-Z0-9]+)", path, re.IGNORECASE)
        if match:
            return match.group(1)

    if provider == "paramount":
        for key in ("id", "contentId", "contentid"):
            values = query.get(key)
            if values and values[0]:
                return values[0]
        for pattern in (
            r"/(?:movies|shows)/video/([^/?#]+)",
            r"/video/([^/?#]+)",
            r"/(?:movies|shows)/([^/?#]+)/?$",
        ):
            match = re.search(pattern, path, re.IGNORECASE)
            if match:
                return match.group(1)

    return None


def android_provider_target(provider: str, external_url: str) -> str:
    """Return the Android app/deep-link target for a provider source."""
    if provider == "netflix":
        content_id = netflix_content_id(external_url)
        if content_id:
            return f"netflix://title/{content_id}"

    if provider == "prime":
        content_id = provider_content_id(provider, external_url)
        if content_id:
            return (
                "https://app.primevideo.com/detail?gti="
                f"{quote(content_id, safe='.:_-')}"
            )

    return str(external_url or "").strip()


def _android_view_command(target: str, package: str | None = None) -> str:
    parts = [
        "am",
        "start",
        "-W",
        "-a",
        "android.intent.action.VIEW",
        "-d",
        _arg(target),
    ]
    if package:
        parts.extend(("-p", package))
    return " ".join(parts)


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

    packages = ANDROID_PROVIDER_PACKAGES.get(provider, ())
    if not packages:
        return _android_view_command(target)

    if len(packages) == 1:
        package = packages[0]
        direct = _android_view_command(target, package)
        fallback = _android_view_command(str(external_url or "").strip())
        return (
            f"if pm path {_arg(package)} >/dev/null 2>&1; "
            f"then {direct}; else {fallback}; fi"
        )

    checks: list[str] = []
    for index, package in enumerate(packages):
        prefix = "if" if index == 0 else "elif"
        checks.append(
            f"{prefix} pm path {_arg(package)} >/dev/null 2>&1; "
            f"then {_android_view_command(target, package)}"
        )
    checks.append(
        f"else {_android_view_command(str(external_url or '').strip())}; fi"
    )
    return "; ".join(checks)


def _webos_provider_params(
    provider: str,
    external_url: str,
    *,
    media_type: str | None = None,
    content_id: str | None = None,
    video_id: str | None = None,
    season: int | None = None,
    episode: int | None = None,
    episode_title: str | None = None,
) -> dict[str, Any]:
    """Build a broad set of provider launch params accepted by LG TV apps."""
    target = android_provider_target(provider, external_url)
    provider_id = provider_content_id(provider, external_url)
    params: dict[str, Any] = {
        "contentTarget": target,
        "target": target,
        "uri": target,
        "url": target,
    }
    if media_type:
        params["mediaType"] = media_type
    if content_id:
        params["sourceContentId"] = content_id
    if video_id:
        params["sourceVideoId"] = video_id
    if season is not None:
        params["season"] = season
    if episode is not None:
        params["episode"] = episode
    if episode_title:
        params["episodeTitle"] = episode_title
    if provider_id:
        params["contentId"] = provider_id
        if provider == "prime":
            params["gti"] = provider_id
        elif provider == "disney":
            params["entityId"] = provider_id
        elif provider == "apple":
            params["adamId"] = provider_id
        elif provider == "max":
            params["videoId"] = provider_id
        elif provider == "crunchyroll":
            params["mediaId"] = provider_id
    return params


def webos_provider_search_query(
    title: str | None,
    *,
    media_type: str | None = None,
    season: int | None = None,
    episode: int | None = None,
    episode_title: str | None = None,
) -> str:
    """Build the title text handed to LG's native content search."""
    clean_title = " ".join(str(title or "").split())
    if not clean_title:
        return ""

    if media_type == "series" and episode is not None:
        parts = [clean_title]
        if season is not None:
            parts.append(f"S{int(season):02d}E{int(episode):02d}")
        else:
            parts.append(f"E{int(episode):02d}")
        clean_episode_title = " ".join(str(episode_title or "").split())
        if clean_episode_title:
            parts.append(clean_episode_title)
        return " ".join(parts)

    return clean_title


def webos_provider_prefers_native_search(
    provider: str | None,
    external_url: str | None,
    *,
    title: str | None = None,
    media_type: str | None = None,
    season: int | None = None,
    episode: int | None = None,
    episode_title: str | None = None,
) -> bool:
    """Return whether real-TV behavior makes native LG search more reliable."""
    if not webos_provider_search_query(
        title,
        media_type=media_type,
        season=season,
        episode=episode,
        episode_title=episode_title,
    ):
        return False

    if (
        provider == "netflix"
        and media_type == "series"
        and episode is not None
    ):
        return "/watch/" not in str(external_url or "").casefold()

    return False


def webos_provider_launch_requests(
    provider: str,
    external_url: str,
    *,
    media_type: str | None = None,
    content_id: str | None = None,
    video_id: str | None = None,
    season: int | None = None,
    episode: int | None = None,
    episode_title: str | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """Return ordered LG webOS launch attempts for one provider title.

    For Netflix and providers proven to ignore broad app parameters on the
    user's TV, first mirror aiowebostv/smartest-tv's launch_app_with_content_id
    contract exactly: system.launcher/launch with only id + contentId.
    Apple TV deliberately keeps its already-working application-manager path.
    """
    raw_url = str(external_url or "").strip()

    if provider == "disney":
        provider_id = provider_content_id(provider, raw_url)
        targets: list[str] = []
        if provider_id and re.fullmatch(
            r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}",
            provider_id,
            re.IGNORECASE,
        ):
            # LG Disney+ accepts the canonical video UUID through
            # Application Manager params.contentTarget.
            targets.append(f"https://www.disneyplus.com/video/{provider_id}")
        if raw_url and raw_url not in targets:
            targets.append(raw_url)

        requests: list[tuple[str, dict[str, Any]]] = []
        for app_id in WEBOS_PROVIDER_APP_IDS.get("disney", ()):
            for target in targets:
                requests.append(
                    (
                        "com.webos.applicationManager/launch",
                        {
                            "id": app_id,
                            "params": {
                                "contentTarget": target,
                                # Keep the legacy alias as a harmless fallback
                                # for Disney app variants that inspect target.
                                "target": target,
                            },
                        },
                    )
                )
        return requests

    if provider == "max":
        provider_id = provider_content_id(provider, raw_url)
        requests: list[tuple[str, dict[str, Any]]] = []

        for app_id in WEBOS_PROVIDER_APP_IDS.get("max", ()):
            if provider_id:
                # Native webOS Max/HBO Max contract: hand the provider's
                # content id directly to Application Manager.
                requests.append(
                    (
                        "com.webos.applicationManager/launch",
                        {
                            "id": app_id,
                            "params": {"contentId": provider_id},
                        },
                    )
                )

            if raw_url:
                # Some Max builds consume the official universal/deep URL
                # instead of the bare content id.
                requests.append(
                    (
                        "com.webos.applicationManager/launch",
                        {
                            "id": app_id,
                            "params": {
                                "contentTarget": raw_url,
                                "target": raw_url,
                            },
                        },
                    )
                )

        return requests

    if provider == "netflix":
        provider_id = netflix_content_id(raw_url)
        requests: list[tuple[str, dict[str, Any]]] = []
        if provider_id:
            # smartest-tv uses the public Netflix /watch/<videoId> DIAL-style
            # content target. This works for both movie IDs and exact episode
            # videoIds when JustWatch gives us /watch/<id>.
            netflix_target = (
                f"m=https://www.netflix.com/watch/{provider_id}&source_type=4"
            )
            requests.append(
                (
                    "system.launcher/launch",
                    {"id": "netflix", "contentId": netflix_target},
                )
            )

            # Keep the older ConnectSDK payload as a service-level fallback
            # for firmware that rejects the modern URL form entirely.
            legacy_target = (
                "m=http%3A%2F%2Fapi.netflix.com%2Fcatalog%2Ftitles%2Fmovies%2F"
                f"{provider_id}&source_type=4"
            )
            requests.append(
                (
                    "system.launcher/launch",
                    {
                        "id": "netflix",
                        "contentId": legacy_target,
                        "params": {"contentId": legacy_target},
                    },
                )
            )
        return requests

    app_ids = WEBOS_PROVIDER_APP_IDS.get(provider, ())
    if not app_ids:
        return []

    params = _webos_provider_params(
        provider,
        raw_url,
        media_type=media_type,
        content_id=content_id,
        video_id=video_id,
        season=season,
        episode=episode,
        episode_title=episode_title,
    )
    requests: list[tuple[str, dict[str, Any]]] = []

    minimal_content_id_providers = {
        "prime",
        "crunchyroll",
        "paramount",
    }

    for app_id in app_ids:
        if provider in minimal_content_id_providers and raw_url:
            # Exact aiowebostv.launch_app_with_content_id contract used by
            # smartest-tv for non-Netflix services.
            requests.append(
                (
                    "system.launcher/launch",
                    {"id": app_id, "contentId": raw_url},
                )
            )

            # If the firmware rejects the minimal form, retain our broader
            # provider-specific launch contracts as service-level fallbacks.
            requests.append(
                (
                    "system.launcher/launch",
                    {
                        "id": app_id,
                        "contentId": raw_url,
                        "params": dict(params),
                    },
                )
            )
            requests.append(
                (
                    "com.webos.applicationManager/launch",
                    {"id": app_id, "params": dict(params)},
                )
            )
            continue

        # Apple TV stays on the existing path because it is already confirmed
        # to open the requested title/episode correctly on the user's LG TV.
        requests.append(
            (
                "com.webos.applicationManager/launch",
                {"id": app_id, "params": dict(params)},
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
