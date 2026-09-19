"""One-time, assertion-guarded toolbar migration for release/0.4.59."""
from pathlib import Path

CARD = Path('custom_components/nuvio/frontend/nuvio-card.js')
TESTS = Path('tests/test_card.cjs')
MANIFEST = Path('custom_components/nuvio/manifest.json')

c = CARD.read_text(encoding='utf-8')

def swap(before, after, label):
    global c
    count = c.count(before)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    c = c.replace(before, after, 1)

# Keep exactly one player picker, in the shared toolbar.
swap("'<div class=\"controls\">'+this.playerSelect()+actions+'</div>'", "'<div class=\"controls\">'+actions+'</div>'", 'Details player duplication')
swap("'<div class=\"controls\">'+this.playerSelect()+debridControls+'</div>'", "'<div class=\"controls\">'+debridControls+'</div>'", 'Sources player duplication')
swap("return '<select id=\"player\">'+this.players().map", "return '<select id=\"player\" aria-label=\"Media player\" title=\"Select media player\">'+this.players().map", 'Accessible player selector')

# Preserve icon-only accessible controls: screen readers and mouse users get
# aria-label/title, while sighted users see icons without repeated text.
for text in ('Home', 'Refresh', 'Control', 'Addons'):
    swap('<span>'+text+'</span></button>', '</button>', text+' icon-only button')

swap("'<div class=\"tools\">'+search+\n      home+", "'<div class=\"tools\">'+search+\n      '<label class=\"toolbar-player\" title=\"Select media player\"><ha-icon icon=\"mdi:television\" aria-hidden=\"true\"></ha-icon>'+this.playerSelect()+'</label>'+\n      home+", 'Top toolbar player')

# The selection is already owned by _playerId. Do not rebuild the entire card
# merely to change player while the user is scrolling a catalog.
swap('r.querySelector("#player")?.addEventListener("change",e=>{this._playerId=e.target.value;this.render();});', 'r.querySelector("#player")?.addEventListener("change",e=>{this._playerId=e.target.value;if(this._view==="details")this.render();});', 'Player selection handler')

# Sticky top-level header with a single scrollable catalog body underneath.
swap('ha-card{overflow:hidden;padding:0;color:var(--primary-text-color)}.header{display:flex;', 'ha-card{overflow:visible;padding:0;color:var(--primary-text-color)}.header{position:sticky;top:0;z-index:20;display:flex;', 'Sticky header CSS')
swap('.ib,.back,.action,.season{border:0;cursor:pointer;background:var(--secondary-background-color);color:var(--primary-text-color);border-radius:18px;padding:9px 13px}', '.ib,.back,.action,.season{border:0;cursor:pointer;background:var(--secondary-background-color);color:var(--primary-text-color);border-radius:18px;padding:9px 13px}.ib.toolbar-btn{width:38px;height:38px;flex:0 0 38px;padding:0;border-radius:50%;display:grid;place-items:center}.toolbar-player{display:flex;align-items:center;gap:6px;min-width:155px;max-width:260px;flex:0 1 240px;border-radius:18px;padding:0 9px;background:var(--secondary-background-color);color:var(--primary-text-color)}.toolbar-player ha-icon{--mdc-icon-size:19px;flex:0 0 auto}.toolbar-player select{width:100%;min-width:0;max-width:100%;padding:9px 0;border:0;outline:0;background:transparent;color:inherit;text-overflow:ellipsis;font:inherit;cursor:pointer}', 'Compact icon toolbar and player CSS')
swap('.hero{height:220px}}</style>\';', '.hero{height:220px}.tools{width:100%;gap:6px}.toolbar-player{min-width:110px;max-width:none;flex:1 1 130px}.search{min-width:0;flex:1 1 100%;width:100%}}</style>\';', 'Mobile toolbar CSS')

swap('<span class="card-version">v0.4.58</span>', '<span class="card-version">v0.4.59</span>', 'Visible version')
swap('NUVIO-CARD v0.4.58', 'NUVIO-CARD v0.4.59', 'Console version')
CARD.write_text(c, encoding='utf-8')

m = MANIFEST.read_text(encoding='utf-8')
if m.count('"version": "0.4.58"') != 1:
    raise SystemExit('Unexpected manifest version')
MANIFEST.write_text(m.replace('"version": "0.4.58"', '"version": "0.4.59"'), encoding='utf-8')

t = TESTS.read_text(encoding='utf-8')
anchor = 'const flush=()=>new Promise(r=>setImmediate(r));'
if t.count(anchor) != 1:
    raise SystemExit('Missing regression test anchor')
checks = '''assert.match(cardSource,/\\.header\\{position:sticky;top:0;z-index:20;/);
assert.match(cardSource,/toolbar-player/);
assert.match(cardSource,/aria-label="Media player"/);
assert.doesNotMatch(cardSource,/<span>(?:Home|Refresh|Control|Addons)<\\/span><\\/button>/);
assert.equal((cardSource.match(/this\\.playerSelect\\(\\)/g)||[]).length,1);
'''
t = t.replace(anchor, checks + anchor, 1)
runtime_anchor = " card.setConfig({show_remote:false});card._loaded=true;"
if t.count(runtime_anchor) != 1:
    raise SystemExit('Missing runtime test anchor')
runtime = ''' card._hass={states:{'media_player.living_room':{attributes:{friendly_name:'Living Room TV'}},'media_player.bedroom':{attributes:{friendly_name:'Bedroom TV'}}}};
 card._playerId='media_player.living_room';card.render();
 assert.equal(card.shadowRoot.querySelectorAll('.header #player').length,1);
 assert.equal(card.shadowRoot.querySelectorAll('.header .toolbar-btn span').length,0);
 assert.equal(card.shadowRoot.querySelectorAll('.header #homeTop,.header #refresh,.header .remote-toggle-button').length,2);
 assert.equal(card.shadowRoot.querySelector('#player').value,'media_player.living_room');
 card._playerId='media_player.bedroom';card._view='details';card._item={id:'demo',type:'series',name:'Demo'};card._details={id:'demo',type:'series',name:'Demo',videos:[]};card.render();
 assert.equal(card.shadowRoot.querySelectorAll('#player').length,1);
 assert.equal(card.shadowRoot.querySelector('#player').value,'media_player.bedroom');
 card._view='sources';card.render();
 assert.equal(card.shadowRoot.querySelectorAll('#player').length,1);
 card._view='home';card.render();
'''
t = t.replace(runtime_anchor, runtime_anchor + '\n' + runtime, 1)
TESTS.write_text(t, encoding='utf-8')

# Remove temporary helper and its workflow from the resulting PR diff.
Path('tools/apply_toolbar_once.py').unlink()
Path('.github/workflows/nuvio-toolbar-once.yml').unlink()
print('Applied Nuvio 0.4.59 sticky toolbar/player migration')
