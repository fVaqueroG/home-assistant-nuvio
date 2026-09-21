"""One-time patch: wire Continue Watching title enrichment and version v0.4.65."""
from pathlib import Path


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one match in {path}, found {count}: {old[:100]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


frontend = "custom_components/nuvio/frontend.py"
replace_once(frontend,
    "from .debrid import DebridNotCached, DebridNotConfigured, DebridResolveError\n",
    "from .debrid import DebridNotCached, DebridNotConfigured, DebridResolveError\n"
    "from .cw_metadata import enrich_continue_watching\n")
replace_once(frontend,
    "        if main_cw:\n            sections.append(\n",
    "        # Synced watch-progress rows often contain only an IMDb ID. Resolve\n"
    "        # their display title using the same configured metadata providers\n"
    "        # Nuvio uses, without replacing their IDs or episode/playback state.\n"
    "        await enrich_continue_watching(\n"
    "            main_cw + upcoming_cw,\n"
    "            api=api,\n"
    "            addons=addons,\n"
    "            tmdb_api=entry.runtime_data.get(DATA_TMDB_API),\n"
    "            catalog_items=[\n"
    "                item\n"
    "                for section in loaded_sections.values()\n"
    "                for item in section.get(\"items\", [])\n"
    "            ],\n"
    "        )\n\n"
    "        if main_cw:\n            sections.append(\n")

tmdb = "custom_components/nuvio/tmdb.py"
method = '''    async def async_title_metadata(self, media_type: str, content_id: str) -> dict[str, Any]:
        """Resolve a movie/show's display metadata by IMDb ID, when configured."""
        imdb_id = re.sub(r":\\d+:\\d+$", "", str(content_id or "").strip())
        if not re.fullmatch(r"tt\\d+", imdb_id, re.IGNORECASE):
            return {}
        kind = "series" if str(media_type).casefold() in {"tv", "series", "anime"} else "movie"
        key = ("title-metadata", kind, imdb_id.casefold())
        cached = self._cached(key)
        if cached is not None:
            return dict(cached)
        data = await self._get_json(
            f"find/{imdb_id}", {"external_source": "imdb_id"}
        )
        results = data.get("tv_results" if kind == "series" else "movie_results")
        match = next(
            (result for result in results or [] if isinstance(result, dict)
             and (result.get("name") or result.get("title"))),
            None,
        )
        if match is None:
            return self._store(key, {})
        poster = match.get("poster_path")
        backdrop = match.get("backdrop_path")
        release = str(match.get("first_air_date") or match.get("release_date") or "")
        return self._store(key, {
            "name": match.get("name") or match.get("title"),
            "poster": f"https://image.tmdb.org/t/p/w500{poster}"
                if isinstance(poster, str) and poster.startswith("/") else None,
            "background": f"https://image.tmdb.org/t/p/w780{backdrop}"
                if isinstance(backdrop, str) and backdrop.startswith("/") else None,
            "description": match.get("overview"),
            "releaseInfo": release[:4] if len(release) >= 4 else None,
        })

'''
replace_once(tmdb, "    async def async_external_ids(\n", method + "    async def async_external_ids(\n")

card = "custom_components/nuvio/frontend/nuvio-card.js"
replace_once(card, '<span class="card-version">v0.4.64</span>', '<span class="card-version">v0.4.65</span>')
replace_once(card, 'console.info("NUVIO-CARD v0.4.64");', 'console.info("NUVIO-CARD v0.4.65");')
manifest = "custom_components/nuvio/manifest.json"
replace_once(manifest, '"version": "0.4.64"', '"version": "0.4.65"')
print("Applied Continue Watching title enrichment and v0.4.65 patch")
