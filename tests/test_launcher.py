"""Tests for Nuvio launch contracts."""

from custom_components.nuvio.launcher import (
    deep_link,
    direct_stream_command,
    player_intent_command,
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


def test_direct_stream_command() -> None:
    command = direct_stream_command(
        "https://example.com/video/master.m3u8?token=a&b=2",
        mime_type="application/vnd.apple.mpegurl",
    )
    assert "android.intent.action.VIEW" in command
    assert "https://example.com/video/master.m3u8?token=a&b=2" in command
    assert "application/vnd.apple.mpegurl" in command



def test_player_intent_command() -> None:
    command = player_intent_command(
        package_name="com.nuviodebug.com",
        stream_url="https://cdn.example.com/movie.mkv?token=a&b=2",
        stream_title="Movie REMUX",
        media_type="movie",
        content_id="tt123",
        video_id="tt123",
        title="Movie",
        filename="Movie.REMUX.mkv",
        video_size=9_876_543_210,
        addon_name="Torrentio",
        info_hash="abcdef",
        file_idx=3,
        profile_id=2,
    )
    assert "com.nuviodebug.com/com.nuvio.tv.MainActivity" in command
    assert "--es launchMode player" in command
    assert "--es streamUrl" in command
    assert "https://cdn.example.com/movie.mkv?token=a&b=2" in command
    assert "--es streamTitle" in command
    assert "--el videoSize 9876543210" in command
    assert "--ei fileIdx 3" in command
    assert "--ei profileId 2" in command


def test_webos_player_launch_payload() -> None:
    payload = webos_launch_payload(
        media_type="movie",
        content_id="tt123",
        title="Movie",
        video_id="tt123",
        launch_mode="player",
        stream_url="https://cdn.example.com/movie.mkv",
        stream_title="Movie REMUX",
        filename="Movie.REMUX.mkv",
        video_size=123456789,
        addon_name="Torrentio",
        info_hash="abcdef",
        file_idx=2,
        profile_id=1,
    )
    params = payload["params"]
    assert payload["id"] == "space.nuvio.webos"
    assert params["launchMode"] == "player"
    assert params["streamUrl"] == "https://cdn.example.com/movie.mkv"
    assert params["streamTitle"] == "Movie REMUX"
    assert params["filename"] == "Movie.REMUX.mkv"
    assert params["videoSize"] == 123456789
    assert params["addonName"] == "Torrentio"
    assert params["infoHash"] == "abcdef"
    assert params["fileIdx"] == 2
    assert params["profileId"] == 1
