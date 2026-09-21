"""Run with: python tests/test_continue_titles.py"""

import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace

path = Path(__file__).resolve().parents[1] / "custom_components/nuvio/cw_metadata.py"
spec = importlib.util.spec_from_file_location("nuvio_cw_metadata_test", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeApi:
    def __init__(self):
        self.calls = []

    async def async_meta(self, addon, media_type, content_id):
        self.calls.append((addon.name, media_type, content_id))
        if content_id == "tt1234567":
            return {"id": content_id, "name": "A Real Movie", "poster": "https://example.org/movie.jpg"}
        raise ValueError("No addon metadata")


class FakeTmdb:
    configured = True

    def __init__(self):
        self.calls = []

    async def async_title_metadata(self, media_type, content_id):
        self.calls.append((media_type, content_id))
        if content_id == "tt9876543":
            return {"name": "A Real Series", "background": "https://example.org/show.jpg"}
        return {}


async def main():
    meta_addon = SimpleNamespace(name="Cinemeta", manifest_url="https://meta.example/manifest.json", manifest={"resources": ["meta"]})
    stream_only = SimpleNamespace(name="Streams", manifest_url="https://streams.example/manifest.json", manifest={"resources": ["stream"]})
    api, tmdb = FakeApi(), FakeTmdb()
    items = [
        {"id": "tt1234567", "name": "tt1234567", "type": "movie", "position": 300, "duration": 2000, "video_id": "movie-url"},
        {"id": "tt9876543", "name": "tt9876543", "type": "series", "season": 2, "episode": 5, "video_id": "tt9876543:2:5"},
        {"id": "tt1112223", "name": "tt1112223", "type": "movie"},
        {"id": "tt2223334", "name": "Already Correct", "type": "movie"},
    ]
    await module.enrich_continue_watching(
        items, api=api, addons=[stream_only, meta_addon], tmdb_api=tmdb,
        catalog_items=[{"id": "tt1112223", "name": "Catalog Movie", "poster": "https://example.org/catalog.jpg"}],
    )
    assert items[0]["name"] == "A Real Movie" and items[0]["poster"].endswith("movie.jpg")
    assert items[0]["id"] == "tt1234567" and items[0]["video_id"] == "movie-url"
    assert items[0]["position"] == 300 and items[0]["duration"] == 2000
    assert items[1]["name"] == "A Real Series" and items[1]["id"] == "tt9876543"
    assert (items[1]["season"], items[1]["episode"], items[1]["video_id"]) == (2, 5, "tt9876543:2:5")
    assert items[2]["name"] == "Catalog Movie" and items[2]["poster"].endswith("catalog.jpg")
    assert items[3]["name"] == "Already Correct"
    assert all(name != "Streams" for name, _, _ in api.calls)
    assert tmdb.calls == [("series", "tt9876543")]
    assert not module.missing_title(items[0])
    assert module.missing_title({"id": "tt1234567", "name": "tt1234567"})

    class SlowApi:
        async def async_meta(self, addon, media_type, content_id):
            await asyncio.sleep(0.2)
            return {"name": "Late result"}

    delayed = [{"id": "tt1111111", "name": "tt1111111", "type": "movie"}]
    await asyncio.wait_for(module.enrich_continue_watching(
        delayed, api=SlowApi(), addons=[meta_addon], budget=0.01,
    ), timeout=0.15)
    assert delayed[0]["name"] == "tt1111111", "No stale result after cancelled lookup"
    print("Continue Watching title and playback identity tests passed")


if __name__ == "__main__":
    asyncio.run(main())
