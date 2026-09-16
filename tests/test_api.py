"""Tests for addon URL handling."""

from custom_components.nuvio.api import addon_base_url, normalize_manifest_url


def test_manifest_url_normalization() -> None:
    assert normalize_manifest_url("https://example.test/addon/") == (
        "https://example.test/addon/manifest.json"
    )
    assert normalize_manifest_url("https://example.test/manifest.json") == (
        "https://example.test/manifest.json"
    )


def test_addon_base_url_preserves_config_path() -> None:
    url = "https://example.test/token/settings/manifest.json"
    assert addon_base_url(url) == "https://example.test/token/settings"
