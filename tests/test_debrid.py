"""Tests for Nuvio debrid source selection helpers."""

from custom_components.nuvio.debrid import (
    PREMIUMIZE,
    REAL_DEBRID,
    TORBOX,
    DebridResolver,
    _magnet_uri,
    _select_file,
    normalize_provider,
)


def test_normalize_provider_aliases() -> None:
    assert normalize_provider("Real-Debrid") == REAL_DEBRID
    assert normalize_provider("RD") == REAL_DEBRID
    assert normalize_provider("TorBox") == TORBOX
    assert normalize_provider("PM") == PREMIUMIZE


def test_build_magnet_from_hash_and_trackers() -> None:
    magnet = _magnet_uri(
        {
            "info_hash": "ABC123",
            "torrent_sources": [
                "tracker:https://tracker.example/announce",
                "dht:ABC123",
            ],
        }
    )
    assert magnet is not None
    assert magnet.startswith("magnet:?xt=urn:btih:ABC123")
    assert "tracker.example" in magnet
    assert "dht" not in magnet


def test_select_episode_file_before_largest() -> None:
    files = [
        {"id": 1, "path": "/Show.S01E01.1080p.mkv", "bytes": 3_000},
        {"id": 2, "path": "/Show.S01E02.1080p.mkv", "bytes": 2_000},
        {"id": 3, "path": "/sample.mkv", "bytes": 9_000},
    ]
    selected = _select_file(
        files,
        file_idx=None,
        filename=None,
        season=1,
        episode=2,
    )
    assert selected is not None
    assert selected["id"] == 2


def test_select_named_file() -> None:
    files = [
        {"id": 1, "name": "Movie.1080p.mkv", "size": 2_000},
        {"id": 2, "name": "Movie.2160p.REMUX.mkv", "size": 8_000},
    ]
    selected = _select_file(
        files,
        file_idx=None,
        filename="Movie.2160p.REMUX.mkv",
        season=None,
        episode=None,
    )
    assert selected is not None
    assert selected["id"] == 2


def test_synced_provider_credentials_are_selected_by_source() -> None:
    resolver = DebridResolver(
        object(),  # type: ignore[arg-type]
        provider=None,
        api_key=None,
        credentials={"torbox": "tb-token", "premiumize": "pm-token"},
    )
    assert resolver.configured
    assert resolver.providers == ["torbox", "premiumize"]
    assert resolver.can_resolve({"resolver_service": "torbox"})
    assert resolver.can_resolve({"resolver_service": "premiumize"})
    assert not resolver.can_resolve({"resolver_service": "realdebrid"})


def test_local_provider_override_is_available() -> None:
    resolver = DebridResolver(
        object(),  # type: ignore[arg-type]
        provider="realdebrid",
        api_key="rd-token",
        credentials={"torbox": "tb-token"},
    )
    assert resolver.can_resolve({"resolver_service": "realdebrid"})
    assert resolver.can_resolve({"resolver_service": "torbox"})
