"""One-time patch applied by a release-branch workflow then deleted."""
from pathlib import Path

p=Path('custom_components/nuvio/frontend/nuvio-card.js')
s=p.read_text()

def swap(old,new,name):
    global s
    n=s.count(old)
    if n!=1: raise RuntimeError(f'{name}: expected one match, found {n}')
    s=s.replace(old,new,1)

swap('''  set hass(h){
    const first=!this._hass;
    this._hass=h;
    if(first||!this._rendered)this.render();
  }
  setConfig(config){this._config={...(config||{})};this.render();}
''','''  set hass(h){
    const previousSources=this.displaySourceSignature();
    const first=!this._hass;
    this._hass=h;
    // Refresh input choices only when the configured displays' sources change.
    if(first||!this._rendered||previousSources!==this.displaySourceSignature())this.render();
  }
  setConfig(config){this._config={...(config||{})};this.render();}
  displaySources(display){
    const states=(this._hass&&this._hass.states)||{};
    const list=((states[display]||{}).attributes||{}).source_list;
    return Array.isArray(list)?[...new Set(list.filter(item=>typeof item==="string"&&item.trim()))]:[];
  }
  displaySourceSignature(){
    return JSON.stringify(this.routes().map(route=>[route&&route.display,this.displaySources(route&&route.display)]));
  }
''','hass setter')
a=s.index('  sourceOptions(display,index){',s.index('class NuvioCardEditor extends HTMLElement'))
b=s.index('  routes(){',a)
s=s[:a]+'''  sourceOptions(display,index,selected=""){
    const sources=this.displaySources(display);
    const attrs=' data-route="'+index+'" data-key="source"';
    if(sources.length){
      // Source names are TV-provided: HDMI inputs may also have custom names.
      const options='<option value="">Select a TV source</option>'+sources.map(source=>'<option value="'+this.esc(source)+'" '+(source===selected?'selected':'')+'>'+this.esc(source)+'</option>').join("");
      const saved=selected&&!sources.includes(selected)?'<option value="'+this.esc(selected)+'" selected>'+this.esc(selected)+' (saved; not currently reported)</option>':"";
      return '<select'+attrs+'>'+options+saved+'</select><small>Available sources reported by the selected TV in Home Assistant.</small>';
    }
    return '<input'+attrs+' type="text" value="'+this.esc(selected)+'" placeholder="Enter TV input name" autocomplete="off"><small>This TV does not report its sources; enter the exact input name manually.</small>';
  }
''' + s[b:]
swap('''    const states=(this._hass&&this._hass.states)||{};
    const inputList=((states[r.display]||{}).attributes||{}).source_list;
    const hint=Array.isArray(inputList)&&inputList.length?'Choose a suggested TV input or enter its exact name.':'Enter the exact input name shown by the TV in Home Assistant.';
''','','remove datalist hint')
old=next((line for line in s.splitlines(keepends=True) if "'<label>TV input / HDMI source<input" in line),None)
if not old: raise RuntimeError('source input HTML not found')
s=s.replace(old,"      '<label>TV input / HDMI source'+this.sourceOptions(r.display,index,source)+'</label>'+\n",1)
swap('''    if(key==="delay_ms"||key==="wake_delay_ms")value=Math.max(0,Math.min(10000,Math.round(Number(value)||0)));
    routes[index][key]=value;
''','''    if(key==="delay_ms"||key==="wake_delay_ms")value=Math.max(0,Math.min(10000,Math.round(Number(value)||0)));
    if(key==="display"&&routes[index].display!==value)routes[index].source="";
    routes[index][key]=value;
''','clear stale TV input')
swap('Input names must match the TV’s source list.','Input choices come from the selected TV’s Home Assistant media sources; TVs without a source list allow manual input.','editor description')
swap('<span class="card-version">v0.4.61</span>','<span class="card-version">v0.4.62</span>','card version')
swap('console.info("NUVIO-CARD v0.4.61");','console.info("NUVIO-CARD v0.4.62");','console version')
p.write_text(s)

p=Path('custom_components/nuvio/manifest.json');s=p.read_text();assert s.count('"version": "0.4.61"')==1
p.write_text(s.replace('"version": "0.4.61"','"version": "0.4.62"',1))

p=Path('tests/test_card.cjs');s=p.read_text()
a="assert.equal(visualEditor.shadowRoot.querySelectorAll('datalist option').length,2);"
assert s.count(a)==1
s=s.replace(a,'''// The TV's source_list becomes a real selectable menu, not static HDMI guesses.
let tvSource=visualEditor.shadowRoot.querySelector('[data-route="0"][data-key="source"]');
assert.equal(tvSource.localName,'select');
assert.deepEqual([...tvSource.querySelectorAll('option')].map(o=>o.value),['','HDMI 1','HDMI 2']);
assert.equal(tvSource.value,'HDMI 1');
assert.equal(visualEditor.shadowRoot.querySelectorAll('datalist').length,0);''',1)
a="assert.equal(edits.at(-1).display_routes[0].source,'HDMI 1');"
assert s.count(a)==1
s=s.replace(a,a+'''
// Changing the selected input updates the saved route and preserves custom keys.
tvSource=visualEditor.shadowRoot.querySelector('[data-route="0"][data-key="source"]');
tvSource.value='HDMI 2';tvSource.dispatchEvent(new window.Event('change',{bubbles:true}));
assert.equal(edits.at(-1).display_routes[0].source,'HDMI 2');
assert.equal(edits.at(-1).other_custom_setting,'keep-me');
// A changed TV source_list refreshes the options.
visualEditor.hass={states:{'media_player.box':{attributes:{}},'media_player.lg':{attributes:{source_list:['HDMI 2','Game console']}}}};
tvSource=visualEditor.shadowRoot.querySelector('[data-route="0"][data-key="source"]');
assert.deepEqual([...tvSource.querySelectorAll('option')].map(o=>o.value),['','HDMI 2','Game console']);
// Different physical TV: no stale source, and show that TV's actual source_list.
visualEditor.hass={states:{'media_player.box':{attributes:{}},'media_player.lg':{attributes:{source_list:['HDMI 2']}},'media_player.roku':{attributes:{source_list:['HDMI 3','Android TV']}}}};
let tvDisplay=visualEditor.shadowRoot.querySelector('[data-route="0"][data-key="display"]');
tvDisplay.value='media_player.roku';tvDisplay.dispatchEvent(new window.Event('change',{bubbles:true}));
assert.equal(edits.at(-1).display_routes[0].source,'');
tvSource=visualEditor.shadowRoot.querySelector('[data-route="0"][data-key="source"]');
assert.deepEqual([...tvSource.querySelectorAll('option')].map(o=>o.value),['','HDMI 3','Android TV']);
// TVs not reporting source_list retain a manual input fallback.
visualEditor.hass={states:{'media_player.box':{attributes:{}},'media_player.roku':{attributes:{}}}};
tvSource=visualEditor.shadowRoot.querySelector('[data-route="0"][data-key="source"]');
assert.equal(tvSource.localName,'input');
tvSource.value='Custom input';tvSource.dispatchEvent(new window.Event('change',{bubbles:true}));
assert.equal(edits.at(-1).display_routes[0].source,'Custom input');
''',1)
p.write_text(s)

p=Path('README.md');s=p.read_text()
a="Use the **exact** HDMI input name from the physical TV's `source_list` attribute"
assert a in s
p.write_text(s.replace(a,"The visual editor now reads the selected TV's `source_list` to offer its actual HDMI and other media inputs. Manual entry remains available if no sources are reported. In YAML, use the **exact** HDMI input name from the physical TV's `source_list` attribute",1))
print('Applied visual TV source-list selector and v0.4.62 tests')
