"""Tests for Nuvio launch contracts."""

from custom_components.nuvio.launcher import (
    deep_link,
    stream_intent_command,
    webos_launch_payload,
)


def test_deep_link() -> None:
    assert deep_link("movie", "tt123") == "nuvio://movie/tt123"
    assert deep_link("tv", "tmdb:42") == "nuvio://series/tmdb:42"


def test_movie_stream_intent() -> None:
    command = stream_intent_command(
        package_name="com.nuvio.app",
        media_type="movie",
        content_id="tt123",
        title="A Movie",
    )
    assert "com.nuvio.app/com.nuvio.tv.MainActivity" in command
    assert "--es contentId tt123" in command
    assert "--es videoId tt123" in command
    assert "--es launchMode stream" in command


def test_episode_stream_intent_and_quoting() -> None:
    command = stream_intent_command(
        package_name="com.nuvio.tv",
        media_type="series",
        content_id="tt456",
        title="Bob's Show",
        season=2,
        episode=4,
    )
    assert "--es videoId tt456:2:4" in command
    assert "'Bob'\"'\"'s Show'" in command
    assert "--ei season 2" in command
    assert "--ei episode 4" in command


def test_webos_launch_payload() -> None:
    payload = webos_launch_payload(
        media_type="series",
        content_id="tt456",
        title="A Show",
        season=2,
        episode=4,
        launch_mode="stream",
    )
    assert payload["id"] == "space.nuvio.webos"
    assert payload["params"]["target"] == "nuvio://series/tt456"
    assert payload["params"]["contentId"] == "tt456"
    assert payload["params"]["contentType"] == "series"
    assert payload["params"]["videoId"] == "tt456:2:4"
    assert payload["params"]["season"] == 2
    assert payload["params"]["episode"] == 4
    assert payload["params"]["launchMode"] == "stream"
