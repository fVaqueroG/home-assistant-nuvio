"""One-time release-branch patch, removed before merging."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def replace(path, old, new, count=1):
    f = ROOT / path
    data = f.read_text()
    actual = data.count(old)
    if actual != count:
        raise RuntimeError(f"{path}: expected {count} occurrences, found {actual}: {old[:100]!r}")
    f.write_text(data.replace(old, new, count))

CARD = "custom_components/nuvio/frontend/nuvio-card.js"
LAUNCHER = "custom_components/nuvio/launcher.py"
INTEGRATION = "custom_components/nuvio/__init__.py"

# ADB must deliver an intent to the running MainActivity, not re-create it.
replace(LAUNCHER,
    '        "--activity-clear-top",\n    ]',
    '        "--activity-clear-top",\n        "--activity-single-top",\n    ]', 2)
# The webOS launcher may honor target as a details deep link, overriding player params.
# For an exact player URL, the app consumes launchMode=player + streamUrl directly.
replace(LAUNCHER,
    '        "target": deep_link(normalized_type, content_id),\n        "contentId": content_id,',
    '        "contentId": content_id,')
replace(LAUNCHER,
    '    if stream_url is not None:\n        params["streamUrl"] = stream_url',
    '    if launch_mode != "player" or not stream_url:\n        params["target"] = deep_link(normalized_type, content_id)\n    if stream_url is not None:\n        params["streamUrl"] = stream_url')

# A link without an exact URL must never claim to play a selected source.
replace(CARD,
    '    // No exact URL is available to Home Assistant for this row. Keep the\n    // legacy behavior as a fallback: open Nuvio\'s source screen for the title.\n    await this.play(false,this._streamContext||null);',
    '    // No exact URL is available: do NOT substitute a title-open command for Play.\n    this._error=s.requires_headers\n      ? "This source requires HTTP headers that cannot currently be passed to Nuvio. Choose another source."\n      : "This addon did not supply a playable stream URL for this selection. Choose a direct link or configure a supported debrid resolver; opening the title would not play the selected source.";\n    this.render();')
replace(CARD, '<span class="card-version">v0.4.62</span>', '<span class="card-version">v0.4.63</span>')
replace(CARD, 'NUVIO-CARD v0.4.62', 'NUVIO-CARD v0.4.63')

# Android TV Remote has no mechanism to deliver stream URL/metadata extras.
# Reject instead of silently opening just the title. Fail before sending to other players.
replace(INTEGRATION,
    '            if call.data.get(ATTR_IN_NUVIO):\n                loaded_entry = hass.config_entries.async_loaded_entries(DOMAIN)[0]',
    '            if call.data.get(ATTR_IN_NUVIO):\n                if android_remote_ids:\n                    raise HomeAssistantError(\n                        "Exact Nuvio stream playback requires the ADB-based Android TV "\n                        "media_player entity. Android TV Remote can open a title, but "\n                        "cannot send the selected stream URL to Nuvio."\n                    )\n                loaded_entry = hass.config_entries.async_loaded_entries(DOMAIN)[0]')
init = ROOT / INTEGRATION
content = init.read_text()
start = content.index('                if android_remote_ids:', content.index('            if call.data.get(ATTR_IN_NUVIO):') + 100)
end = content.index('                if webos_ids:', start)
if 'Fall back to Nuvio\'s title/episode stream screen.' not in content[start:end]:
    raise RuntimeError('old Android Remote title fallback not found')
init.write_text(content[:start] + content[end:])

replace('custom_components/nuvio/manifest.json', '"version": "0.4.62"', '"version": "0.4.63"')
replace('tests/test_launcher.py',
    '    assert "--es launchMode stream" in command',
    '    assert "--es launchMode stream" in command\n    assert "--activity-clear-top --activity-single-top" in command')
replace('tests/test_launcher.py',
    '    assert "--es launchMode player" in command',
    '    assert "--es launchMode player" in command\n    assert "--activity-clear-top --activity-single-top" in command')
replace('tests/test_launcher.py',
    '    assert params["launchMode"] == "player"',
    '    assert params["launchMode"] == "player"\n    assert "target" not in params')
replace('tests/test_card.cjs',
    'assert.match(cardSource,/toolbar-player/);',
    'assert.match(cardSource,/toolbar-player/);\nassert.doesNotMatch(cardSource,/await this\\.play\\(false,this\\._streamContext\\|\\|null\\)/);')
replace('tests/test_card.cjs',
    ' routed.remove();',
    ''' routed.remove();
 // An addon row without an exact URL must not silently open the title.
 const unresolved=window.document.createElement('nuvio-card');
 unresolved.setConfig({show_remote:false});
 const unresolvedCalls=[];
 unresolved._hass={states:{'media_player.tv':{}},callService:async(...args)=>unresolvedCalls.push(args)};
 unresolved._playerId='media_player.tv';unresolved._item={id:'demo',type:'movie',name:'Demo'};
 unresolved._streams=[{name:'Addon source',direct:false,resolvable:false}];
 await unresolved.playInNuvioIndex(0);
 assert.equal(unresolvedCalls.length,0);
 assert.match(unresolved._error,/did not supply a playable stream URL/);
 unresolved.remove();''')
print('Applied exact-stream and relaunch routing fixes (v0.4.63)')
