"""Streaming-provider catalog and normalization helpers."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


# Built-in provider catalog. This is intentionally broader than the small set
# used by the launcher because filtering and selection should still work for
# providers that Home Assistant cannot deep-link into directly.
STREAMING_PROVIDER_CATALOG: tuple[tuple[str, str], ...] = (
    ("netflix", "Netflix"),
    ("prime", "Prime Video"),
    ("disney", "Disney+"),
    ("max", "Max"),
    ("apple", "Apple TV+"),
    ("paramount", "Paramount+"),
    ("crunchyroll", "Crunchyroll"),
    ("vix", "ViX"),
    ("mercado_play", "Mercado Play"),
    ("pluto_tv", "Pluto TV"),
    ("claro_video", "Claro video"),
    ("tubi", "Tubi"),
    ("plex", "Plex"),
    ("mubi", "MUBI"),
    ("universal_plus", "Universal+"),
    ("mgm_plus", "MGM+"),
    ("starz", "STARZ"),
    ("lionsgate_plus", "Lionsgate+"),
    ("peacock", "Peacock"),
    ("hulu", "Hulu"),
    ("discovery_plus", "Discovery+"),
    ("amc_plus", "AMC+"),
    ("shudder", "Shudder"),
    ("sundance_now", "Sundance Now"),
    ("acorn_tv", "Acorn TV"),
    ("britbox", "BritBox"),
    ("criterion_channel", "The Criterion Channel"),
    ("curiosity_stream", "Curiosity Stream"),
    ("magellan_tv", "MagellanTV"),
    ("history_vault", "History Vault"),
    ("hidive", "HIDIVE"),
    ("anime_onegai", "Anime Onegai"),
    ("kocowa", "KOCOWA+"),
    ("rakuten_viki", "Rakuten Viki"),
    ("rakuten_tv", "Rakuten TV"),
    ("runtime", "Runtime"),
    ("filmzie", "Filmzie"),
    ("kanopy", "Kanopy"),
    ("hoopla", "Hoopla"),
    ("youtube", "YouTube"),
    ("youtube_premium", "YouTube Premium"),
    ("google_play", "Google Play Movies"),
    ("microsoft_store", "Microsoft Store"),
    ("fandango_at_home", "Fandango at Home"),
    ("roku_channel", "The Roku Channel"),
    ("freevee", "Amazon Freevee"),
    ("pbs", "PBS"),
    ("pbs_kids", "PBS Kids"),
    ("dazn", "DAZN"),
    ("espn", "ESPN"),
    ("fubo", "Fubo"),
    ("sling", "Sling TV"),
    ("philo", "Philo"),
    ("directv_stream", "DIRECTV STREAM"),
    ("globoplay", "Globoplay"),
    ("telecine", "Telecine"),
    ("canal_plus", "CANAL+"),
    ("skyshowtime", "SkyShowtime"),
    ("movistar_plus", "Movistar Plus+"),
    ("atresplayer", "Atresplayer"),
    ("rtve_play", "RTVE Play"),
    ("flixole", "FlixOlé"),
    ("hayu", "Hayu"),
    ("canela_tv", "Canela.TV"),
    ("lg_channels", "LG Channels"),
    ("samsung_tv_plus", "Samsung TV Plus"),
    ("sony_one", "Sony One"),
)


PROVIDER_ALIASES: dict[str, tuple[str, ...]] = {
    "netflix": ("netflix", "netflix standard with ads"),
    "prime": ("prime video", "amazon prime video", "amazon video", "prime"),
    "disney": ("disney+", "disney plus", "disney"),
    "max": ("max", "hbo max"),
    "apple": ("apple tv+", "apple tv plus", "apple tv"),
    "paramount": ("paramount+", "paramount plus", "paramount"),
    "crunchyroll": ("crunchyroll",),
    "vix": ("vix", "vix premium"),
    "mercado_play": ("mercado play", "mercadoplay"),
    "pluto_tv": ("pluto tv", "pluto"),
    "claro_video": ("claro video", "clarovideo"),
    "tubi": ("tubi",),
    "plex": ("plex",),
    "mubi": ("mubi",),
    "universal_plus": ("universal+", "universal plus"),
    "mgm_plus": ("mgm+", "mgm plus"),
    "starz": ("starz",),
    "lionsgate_plus": ("lionsgate+", "lionsgate plus", "starzplay"),
    "peacock": ("peacock", "peacock tv"),
    "hulu": ("hulu",),
    "discovery_plus": ("discovery+", "discovery plus"),
    "amc_plus": ("amc+", "amc plus"),
    "shudder": ("shudder",),
    "sundance_now": ("sundance now",),
    "acorn_tv": ("acorn tv",),
    "britbox": ("britbox",),
    "criterion_channel": ("the criterion channel", "criterion channel"),
    "curiosity_stream": ("curiosity stream", "curiositystream"),
    "magellan_tv": ("magellantv", "magellan tv"),
    "history_vault": ("history vault",),
    "hidive": ("hidive",),
    "anime_onegai": ("anime onegai",),
    "kocowa": ("kocowa+", "kocowa plus", "kocowa"),
    "rakuten_viki": ("rakuten viki", "viki"),
    "rakuten_tv": ("rakuten tv",),
    "runtime": ("runtime",),
    "filmzie": ("filmzie",),
    "kanopy": ("kanopy",),
    "hoopla": ("hoopla",),
    "youtube": ("youtube",),
    "youtube_premium": ("youtube premium",),
    "google_play": ("google play movies", "google play"),
    "microsoft_store": ("microsoft store",),
    "fandango_at_home": ("fandango at home", "vudu"),
    "roku_channel": ("the roku channel", "roku channel"),
    "freevee": ("amazon freevee", "freevee", "imdb tv"),
    "pbs": ("pbs",),
    "pbs_kids": ("pbs kids",),
    "dazn": ("dazn",),
    "espn": ("espn", "espn+"),
    "fubo": ("fubo", "fubotv"),
    "sling": ("sling tv", "sling"),
    "philo": ("philo",),
    "directv_stream": ("directv stream",),
    "globoplay": ("globoplay",),
    "telecine": ("telecine",),
    "canal_plus": ("canal+", "canal plus"),
    "skyshowtime": ("skyshowtime",),
    "movistar_plus": ("movistar plus+", "movistar plus", "movistar+"),
    "atresplayer": ("atresplayer",),
    "rtve_play": ("rtve play",),
    "flixole": ("flixolé", "flixole"),
    "hayu": ("hayu",),
    "canela_tv": ("canela.tv", "canela tv", "canela"),
    "lg_channels": ("lg channels",),
    "samsung_tv_plus": ("samsung tv plus",),
    "sony_one": ("sony one",),
}


PROVIDER_HOSTS: dict[str, tuple[str, ...]] = {
    "netflix": ("netflix.com",),
    "prime": ("primevideo.com", "watch.amazon.com", "amazon.com"),
    "disney": ("disneyplus.com",),
    "max": ("max.com", "hbomax.com"),
    "apple": ("tv.apple.com",),
    "paramount": ("paramountplus.com",),
    "crunchyroll": ("crunchyroll.com",),
    "vix": ("vix.com",),
    "mercado_play": ("mercadolibre.com", "mercadoplay.com"),
    "pluto_tv": ("pluto.tv",),
    "claro_video": ("clarovideo.com",),
    "tubi": ("tubitv.com", "tubi.tv"),
    "plex": ("plex.tv",),
    "mubi": ("mubi.com",),
    "peacock": ("peacocktv.com",),
    "hulu": ("hulu.com",),
    "discovery_plus": ("discoveryplus.com",),
    "amc_plus": ("amcplus.com",),
    "shudder": ("shudder.com",),
    "acorn_tv": ("acorn.tv",),
    "britbox": ("britbox.com",),
    "curiosity_stream": ("curiositystream.com",),
    "hidive": ("hidive.com",),
    "kocowa": ("kocowa.com",),
    "rakuten_viki": ("viki.com",),
    "rakuten_tv": ("rakuten.tv",),
    "runtime": ("runtime.tv",),
    "filmzie": ("filmzie.com",),
    "kanopy": ("kanopy.com",),
    "hoopla": ("hoopladigital.com",),
    "youtube": ("youtube.com", "youtu.be"),
    "roku_channel": ("therokuchannel.roku.com",),
    "freevee": ("freevee.com",),
    "dazn": ("dazn.com",),
    "espn": ("espn.com",),
    "fubo": ("fubo.tv",),
    "sling": ("sling.com",),
    "philo": ("philo.com",),
    "directv_stream": ("directv.com",),
    "globoplay": ("globoplay.globo.com",),
    "skyshowtime": ("skyshowtime.com",),
    "atresplayer": ("atresplayer.com",),
    "rtve_play": ("rtve.es",),
    "flixole": ("flixole.com",),
    "hayu": ("hayu.com",),
    "canela_tv": ("canela.tv",),
}


_PROVIDER_LABELS = dict(STREAMING_PROVIDER_CATALOG)


def normalize_provider_text(value: Any) -> str:
    """Normalize a provider label for matching."""
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def provider_slug(value: Any) -> str:
    """Create a stable config key for a provider label not in the catalog."""
    normalized = normalize_provider_text(value)
    return re.sub(r"\s+", "_", normalized).strip("_")


def streaming_provider_key(name: Any, external_url: Any = None) -> str | None:
    """Map provider labels/URLs to a stable key.

    Known providers get canonical keys. Unknown providers fall back to a slug
    made from the returned provider name so they can still be selected and
    filtered without a code update.
    """
    normalized = normalize_provider_text(name)

    # Prefer exact aliases globally before fuzzy containment. This prevents
    # names such as "YouTube Premium" from being classified as "YouTube".
    for key, aliases in PROVIDER_ALIASES.items():
        if any(normalized == normalize_provider_text(alias) for alias in aliases):
            return key

    padded = f" {normalized} "
    fuzzy_aliases = sorted(
        (
            (normalize_provider_text(alias), key)
            for key, aliases in PROVIDER_ALIASES.items()
            for alias in aliases
        ),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for alias_normalized, key in fuzzy_aliases:
        if alias_normalized and f" {alias_normalized} " in padded:
            return key

    if external_url:
        try:
            host = (urlparse(str(external_url)).hostname or "").casefold()
        except ValueError:
            host = ""
        for key, domains in PROVIDER_HOSTS.items():
            if any(host == domain or host.endswith(f".{domain}") for domain in domains):
                return key

    slug = provider_slug(name)
    return slug or None


def normalize_selected_provider(value: Any) -> str | None:
    """Normalize a stored/user-entered provider value."""
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw in _PROVIDER_LABELS:
        return raw
    return streaming_provider_key(raw)


def provider_label(key: str) -> str:
    """Return a human-friendly provider label."""
    if key in _PROVIDER_LABELS:
        return _PROVIDER_LABELS[key]
    return str(key or "").replace("_", " ").strip().title()


def provider_catalog_options(
    extra: dict[str, str] | None = None,
) -> list[tuple[str, str]]:
    """Return built-in providers plus discovered/custom provider labels."""
    merged = dict(STREAMING_PROVIDER_CATALOG)
    for key, label in (extra or {}).items():
        normalized_key = normalize_selected_provider(key or label)
        if normalized_key:
            merged.setdefault(normalized_key, str(label or provider_label(normalized_key)))
    return sorted(merged.items(), key=lambda item: item[1].casefold())
