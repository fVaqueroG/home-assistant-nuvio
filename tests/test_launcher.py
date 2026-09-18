"""Tests for Nuvio launch contracts."""

from custom_components.nuvio.launcher import (
    android_provider_command,
    android_provider_target,
    deep_link,
    direct_stream_command,
    netflix_content_id,
    provider_content_id,
    provider_key,
    provider_source_match,
    player_intent_command,
    stream_intent_command,
    webos_launch_payload,
    webos_provider_launch_payload,
    webos_provider_launch_requests,
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


def test_provider_detection_and_source_matching() -> None:
    assert provider_key("Amazon Video", "https://watch.amazon.com/detail?gti=abc") == "prime"
    assert provider_key("Netflix", "https://www.netflix.com/watch/81234567") == "netflix"
    assert provider_key("Disney Plus", "https://www.disneyplus.com/movies/test") == "disney"
    assert provider_key("Mercado Play", "https://www.mercadolibre.com/") == "mercado_play"
    assert provider_key("ViX Premium", "https://vix.com/") == "vix"
    assert provider_key("Pluto TV", "https://pluto.tv/") == "pluto_tv"
    assert provider_key("A New Future Service", None) == "a_new_future_service"
    assert provider_source_match("disney", ["Live TV", "Disney+", "HDMI 1"]) == "Disney+"
    assert provider_source_match("max", ["Netflix", "Max", "Prime Video"]) == "Max"
    assert provider_source_match("pluto_tv", ["Netflix", "Pluto TV", "HDMI 1"]) == "Pluto TV"


def test_netflix_provider_targets() -> None:
    url = "https://www.netflix.com/watch/81234567"
    assert netflix_content_id(url) == "81234567"
    assert provider_content_id("netflix", url) == "81234567"
    assert android_provider_target("netflix", url) == "netflix://title/81234567"
    command = android_provider_command("netflix", url)
    assert "com.netflix.ninja/.MainActivity" in command
    assert "netflix://title/81234567" in command
    requests = webos_provider_launch_requests("netflix", url)
    assert requests[0][0] == "system.launcher/launch"
    payload = requests[0][1]
    assert payload["id"] == "netflix"
    assert "81234567" in payload["contentId"]


def test_prime_provider_targets() -> None:
    url = "https://watch.amazon.com/detail?gti=amzn1.dv.gti.example"
    assert provider_content_id("prime", url) == "amzn1.dv.gti.example"
    assert (
        android_provider_target("prime", url)
        == "https://app.primevideo.com/detail?gti=amzn1.dv.gti.example"
    )
    command = android_provider_command("prime", url)
    assert "com.amazon.amazonvideo.livingroom" in command
    assert "-p com.amazon.amazonvideo.livingroom" in command
    assert "app.primevideo.com/detail?gti=amzn1.dv.gti.example" in command
    requests = webos_provider_launch_requests("prime", url)
    assert requests[0][0] == "com.webos.applicationManager/launch"
    assert requests[0][1]["id"] == "amazon"
    params = requests[0][1]["params"]
    assert params["gti"] == "amzn1.dv.gti.example"
    assert params["contentId"] == "amzn1.dv.gti.example"


def test_disney_provider_targets() -> None:
    url = (
        "https://www.disneyplus.com/browse/"
        "entity-12345678-1234-1234-1234-123456789abc"
    )
    content_id = "12345678-1234-1234-1234-123456789abc"
    assert provider_content_id("disney", url) == content_id
    command = android_provider_command("disney", url)
    assert "com.disney.disneyplus" in command
    assert "-p com.disney.disneyplus" in command
    requests = webos_provider_launch_requests("disney", url)
    assert requests[0][1]["id"] == "com.disney.disneyplus-prod"
    assert requests[0][1]["params"]["entityId"] == content_id


def test_apple_provider_targets() -> None:
    url = "https://tv.apple.com/us/movie/example/umc.cmc.6abc123xyz"
    assert provider_content_id("apple", url) == "umc.cmc.6abc123xyz"
    command = android_provider_command("apple", url)
    assert "com.apple.atve.androidtv.appletv" in command
    requests = webos_provider_launch_requests("apple", url)
    assert requests[0][1]["id"] == "com.apple.appletv"
    assert requests[0][1]["params"]["contentId"] == "umc.cmc.6abc123xyz"


def test_max_provider_targets_support_both_android_packages() -> None:
    url = "https://play.max.com/movie/12345678-abcd-4321-abcd-123456789abc"
    content_id = "12345678-abcd-4321-abcd-123456789abc"
    assert provider_content_id("max", url) == content_id
    command = android_provider_command("max", url)
    assert "com.wbd.hbomax" in command
    assert "com.wbd.stream" in command
    requests = webos_provider_launch_requests("max", url)
    assert [payload["id"] for _, payload in requests][:2] == [
        "com.wbd.stream",
        "hbo-go-2",
    ]
    assert requests[0][1]["params"]["videoId"] == content_id


def test_crunchyroll_provider_targets() -> None:
    url = "https://www.crunchyroll.com/watch/GABCDE123/example"
    assert provider_content_id("crunchyroll", url) == "GABCDE123"
    command = android_provider_command("crunchyroll", url)
    assert "com.crunchyroll.crunchyroid" in command
    requests = webos_provider_launch_requests("crunchyroll", url)
    assert requests[0][1]["id"] == "crunchyroll"
    assert requests[0][1]["params"]["mediaId"] == "GABCDE123"


def test_paramount_provider_targets() -> None:
    url = "https://www.paramountplus.com/movies/video/abcDEF123/"
    assert provider_content_id("paramount", url) == "abcDEF123"
    command = android_provider_command("paramount", url)
    assert "com.cbs.ott" in command
    requests = webos_provider_launch_requests("paramount", url)
    assert requests
    assert requests[0][1]["params"]["contentId"] == "abcDEF123"


def test_generic_provider_has_no_hardcoded_webos_payload() -> None:
    assert webos_provider_launch_payload(
        "unknown", "https://example.com/title"
    ) is None

