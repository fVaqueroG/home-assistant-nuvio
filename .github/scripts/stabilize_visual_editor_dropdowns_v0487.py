import json
from pathlib import Path

root = Path('custom_components/nuvio')
main = root / 'frontend/nuvio-card.js'
separate = root / 'frontend/nuvio-popup-card.js'
s = main.read_text()
p = separate.read_text()

def once(source, old, new, label):
    assert source.count(old) == 1, (label, source.count(old))
    return source.replace(old, new, 1)

s = once(s, '''  set hass(h){
    const previousSources=this.displaySourceSignature();
    const first=!this._hass;
    this._hass=h;
    // Refresh input choices only when the configured displays' sources change.
    if(first||!this._rendered||previousSources!==this.displaySourceSignature())this.render();
  }
  setConfig(config){this._config={...(config||{})};this.render();}''', '''  set hass(h){
    const previousSources=this.displaySourceSignature();
    const first=!this._hass;
    this._hass=h;
    // A focused select must not be rebuilt by Home Assistant state updates.
    if(first||!this._rendered||
       (previousSources!==this.displaySourceSignature()&&!this.matches(':focus-within')))this.render();
  }
  setConfig(config){
    const next={...(config||{})};
    const changed=JSON.stringify(next)!==JSON.stringify(this._config);
    this._config=next;
    // HA echoes config-changed; ignore unchanged echoes and keep active menus.
    if(!this._rendered||(changed&&!this.matches(':focus-within')))this.render();
  }''', 'full editor setters')

popup_old = '''  setConfig(config) { this._config={...config}; this.render(); }
  emit(config) {'''
popup_new = '''  setConfig(config) {
    const next={...config};
    const changed=JSON.stringify(this._config)!==JSON.stringify(next);
    this._config=next;
    if(!this.shadowRoot.querySelector('nuvio-card-editor')||
       (changed&&!this.matches(':focus-within')))this.render();
  }
  emit(config) {'''
s = once(s, popup_old, popup_new, 'bundled popup editor')
p = once(p, popup_old, popup_new, 'standalone popup editor')
s = once(s, 'console.info("NUVIO-CARD v0.4.86");', 'console.info("NUVIO-CARD v0.4.87");', 'console version')
s = once(s, '<span class="card-version">v0.4.86</span>', '<span class="card-version">v0.4.87</span>', 'visible version')
manifest = root / 'manifest.json'
meta = json.loads(manifest.read_text())
assert meta['version'] == '0.4.86', meta['version']
meta['version'] = '0.4.87'
main.write_text(s)
separate.write_text(p)
manifest.write_text(json.dumps(meta, indent=2) + '\n')
print('PASS: Nuvio main and popup visual editors preserve open native dropdowns')
