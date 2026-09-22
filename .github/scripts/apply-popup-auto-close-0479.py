from pathlib import Path
import json


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match; found {count}')
    return text.replace(old, new, 1)


for name in ('custom_components/nuvio/frontend/nuvio-popup-card.js',
             'custom_components/nuvio/frontend/nuvio-card.js'):
    path = Path(name)
    s = path.read_text()
    assert '0.4.78' in s, name
    s = s.replace('0.4.78', '0.4.79')
    s = replace_once(s,
        '''    this._popupCard = null;
    this._onKeydown = event => {''',
        '''    this._popupCard = null;
    this._autoCloseTimer = null;
    this._onKeydown = event => {''', name + ' constructor')
    s = replace_once(s,
        '  static getStubConfig() { return {button_label: "Nuvio", button_style: "horizontal", popup_width: "wide"}; }',
        '  static getStubConfig() { return {button_label: "Nuvio", button_style: "horizontal", popup_width: "wide", popup_auto_close_minutes: 2}; }',
        name + ' stub')
    s = replace_once(s,
        '''  popupSize() { return ["normal", "wide", "fullscreen"].includes(this._config.popup_width) ? this._config.popup_width : "wide"; }
  setConfig(config) {
    this._config = {...config};''',
        '''  popupSize() { return ["normal", "wide", "fullscreen"].includes(this._config.popup_width) ? this._config.popup_width : "wide"; }
  popupAutoCloseMinutes() {
    const raw = this._config.popup_auto_close_minutes;
    if (raw === undefined || raw === null || String(raw).trim() === "") return 2;
    const minutes = Number(raw);
    return Number.isFinite(minutes) && minutes >= 0 ? minutes : 2;
  }
  startAutoCloseTimer() {
    if (this._autoCloseTimer !== null) {
      clearTimeout(this._autoCloseTimer);
      this._autoCloseTimer = null;
    }
    if (!this._overlay) return;
    const minutes = this.popupAutoCloseMinutes();
    if (minutes > 0) this._autoCloseTimer = setTimeout(() => this.closePopup(), minutes * 60000);
  }
  setConfig(config) {
    const previousAutoClose = this.popupAutoCloseMinutes();
    this._config = {...config};''',
        name + ' timer methods')
    s = replace_once(s,
        '''    if (this._overlay) this._overlay.dataset.size = this.popupSize();
    if (this._popupCard) this._popupCard.setConfig({...this._config, type: "custom:nuvio-card"});''',
        '''    if (this._overlay) this._overlay.dataset.size = this.popupSize();
    if (this._overlay && previousAutoClose !== this.popupAutoCloseMinutes()) this.startAutoCloseTimer();
    if (this._popupCard) this._popupCard.setConfig({...this._config, type: "custom:nuvio-card"});''',
        name + ' config update')
    s = replace_once(s,
        '''    overlay.querySelector(".nuvio-popup-top button").focus();
  }
  closePopup() {''',
        '''    overlay.querySelector(".nuvio-popup-top button").focus();
    this.startAutoCloseTimer();
  }
  closePopup() {''',
        name + ' open timer')
    s = replace_once(s,
        '''  closePopup() {
    document.removeEventListener("keydown", this._onKeydown, true);''',
        '''  closePopup() {
    if (this._autoCloseTimer !== null) {
      clearTimeout(this._autoCloseTimer);
      this._autoCloseTimer = null;
    }
    document.removeEventListener("keydown", this._onKeydown, true);''',
        name + ' close cleanup')
    s = replace_once(s,
        '''<label>Popup size<select data-field="popup_width"><option value="normal">Normal</option><option value="wide">Wide</option><option value="fullscreen">Full screen</option></select></label></div><nuvio-card-editor>''',
        '''<label>Popup size<select data-field="popup_width"><option value="normal">Normal</option><option value="wide">Wide</option><option value="fullscreen">Full screen</option></select></label><label>Popup auto-close (minutes)<input data-field="popup_auto_close_minutes" type="number" min="0" step="any" value="2"><small>Default: 2 minutes after opening. Set 0 to disable.</small></label></div><nuvio-card-editor>''',
        name + ' editor field')
    s = replace_once(s,
        '''    popupSize.addEventListener("change",()=>this.emit({...this._config,popup_width:popupSize.value}));
    const editor=this.shadowRoot.querySelector("nuvio-card-editor");''',
        '''    popupSize.addEventListener("change",()=>this.emit({...this._config,popup_width:popupSize.value}));
    const autoClose=this.shadowRoot.querySelector("input[data-field=popup_auto_close_minutes]");
    autoClose.value=String(this._config.popup_auto_close_minutes ?? 2);
    autoClose.addEventListener("change",()=>{
      const raw=autoClose.value.trim(),minutes=Number(raw);
      this.emit({...this._config,popup_auto_close_minutes:raw === "" || !Number.isFinite(minutes) || minutes < 0 ? 2 : minutes});
    });
    const editor=this.shadowRoot.querySelector("nuvio-card-editor");''',
        name + ' editor handler')
    path.write_text(s)

manifest = Path('custom_components/nuvio/manifest.json')
data = json.loads(manifest.read_text())
assert data['version'] == '0.4.78'
data['version'] = '0.4.79'
manifest.write_text(json.dumps(data, indent=2) + '\n')

tests = Path('tests/test_card.cjs')
t = tests.read_text().replace('0.4.78', '0.4.79')
t = replace_once(t,
    '''launcher.remove();
// Home Assistant discovers the native visual editor''',
    '''// Auto-close: default, disable, invalid input, changes while open, and cleanup.
assert.equal(launcher.constructor.getStubConfig().popup_auto_close_minutes,2);
assert.equal(launcher.popupAutoCloseMinutes(),2);
assert.match(cardSource,/Popup auto-close \\(minutes\\)/);
assert.match(cardSource,/data-field="popup_auto_close_minutes" type="number" min="0"/);
assert.match(cardSource,/this\\.startAutoCloseTimer\\(\\);\\s*\\}\\s*closePopup\\(\\)/);
launcher.setConfig({type:'custom:nuvio-popup-card',popup_auto_close_minutes:0});
assert.equal(launcher.popupAutoCloseMinutes(),0);
launcher.setConfig({type:'custom:nuvio-popup-card',popup_auto_close_minutes:'not-a-number'});
assert.equal(launcher.popupAutoCloseMinutes(),2);
const autoCloseOverlay=window.document.createElement('div');
window.document.body.appendChild(autoCloseOverlay);
launcher._overlay=autoCloseOverlay;
launcher.startAutoCloseTimer();
const firstTimer=launcher._autoCloseTimer;
assert.ok(timeouts.has(firstTimer));
launcher.setConfig({type:'custom:nuvio-popup-card',popup_auto_close_minutes:0});
assert.equal(launcher._autoCloseTimer,null);
assert.equal(timeouts.has(firstTimer),false);
launcher.setConfig({type:'custom:nuvio-popup-card',popup_auto_close_minutes:0.5});
const secondTimer=launcher._autoCloseTimer;
assert.ok(timeouts.has(secondTimer));
assert.notEqual(secondTimer,firstTimer);
timeouts.get(secondTimer)();
assert.equal(launcher._overlay,null);
assert.equal(launcher._autoCloseTimer,null);
assert.equal(timeouts.has(secondTimer),false);
launcher.remove();
// Home Assistant discovers the native visual editor''',
    'timer regression tests')
tests.write_text(t)

docs = Path('docs/popup-card.md')
docs.write_text(docs.read_text() + '''\n\nPopup auto-close: the popup automatically closes 2 minutes after it opens by default. Set `popup_auto_close_minutes: 5` to change the duration, or `popup_auto_close_minutes: 0` to disable automatic closing. Fractional minute values are supported. The visual editor exposes **Popup auto-close (minutes)**; changing the value while the popup is open restarts or cancels the countdown. The timer is cleared if the popup is closed manually or the card is removed. It only closes the popup UI and does not stop TV playback.\n''')
print('Implemented popup auto-close in standalone and bundled sources, editor, documentation and tests.')
