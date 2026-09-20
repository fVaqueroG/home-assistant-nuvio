"""One-time source patch applied to the release branch, then deleted."""
from pathlib import Path
import json

card_path = Path('custom_components/nuvio/frontend/nuvio-card.js')
card = card_path.read_text(encoding='utf-8')
old_stub = '  static getStubConfig(){ return {title:"Nuvio",columns:6,show_remote:true,remote_side:"left"}; }'
assert card.count(old_stub) == 1, 'Nuvio card stub signature changed'
assert 'getConfigElement()' not in card, 'Editor already registered'
card = card.replace(old_stub, '  static getConfigElement(){ return document.createElement("nuvio-card-editor"); }\n' + old_stub, 1)

editor_code = r'''
// Lovelace visual editor. Preserve all unrelated configuration keys (including
// future additions) and only update the setting that the user changes.
class NuvioCardEditor extends HTMLElement {
  constructor(){
    super();
    this.attachShadow({mode:"open"});
    this._config={};
    this._hass=null;
    this._rendered=false;
    this.shadowRoot.addEventListener("change",e=>this.change(e));
    this.shadowRoot.addEventListener("click",e=>this.clickAction(e));
  }
  set hass(h){
    const first=!this._hass;
    this._hass=h;
    if(first||!this._rendered)this.render();
  }
  setConfig(config){this._config={...(config||{})};this.render();}
  esc(value){return String(value==null?"":value).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#39;");}
  playerIds(extra=[]){
    const states=(this._hass&&this._hass.states)||{};
    return [...new Set([...Object.keys(states).filter(id=>id.startsWith("media_player.")),...extra.filter(id=>typeof id==="string"&&id.startsWith("media_player."))])].sort((a,b)=>this.name(a).localeCompare(this.name(b)));
  }
  name(id){
    const states=(this._hass&&this._hass.states)||{};
    return ((states[id]||{}).attributes||{}).friendly_name||id;
  }
  playerOptions(selected,includeEmpty=true){
    const routes=Array.isArray(this._config.display_routes)?this._config.display_routes:[];
    const extras=[selected,this._config.default_player,this._config.entity,...routes.flatMap(r=>[r&&r.player,r&&r.display])];
    const empty=includeEmpty?'<option value="">Select a media player</option>':"";
    return empty+this.playerIds(extras).map(id=>'<option value="'+this.esc(id)+'" '+(id===selected?'selected':'')+'>'+this.esc(this.name(id))+' · '+this.esc(id)+'</option>').join("");
  }
  sourceOptions(display,index){
    const state=((this._hass&&this._hass.states)||{})[display];
    const sources=((state||{}).attributes||{}).source_list;
    return '<datalist id="nuvio-inputs-'+index+'">'+(Array.isArray(sources)?sources:[]).map(source=>'<option value="'+this.esc(source)+'"></option>').join("")+'</datalist>';
  }
  routes(){return Array.isArray(this._config.display_routes)?this._config.display_routes:[];}
  routeHtml(route,index){
    const r=route||{},source=String(r.source||"");
    const on=r.turn_on!==false;
    const wake=r.wake_delay_ms==null?2000:r.wake_delay_ms;
    const settle=r.delay_ms==null?1000:r.delay_ms;
    const states=(this._hass&&this._hass.states)||{};
    const inputList=((states[r.display]||{}).attributes||{}).source_list;
    const hint=Array.isArray(inputList)&&inputList.length?'Choose a suggested TV input or enter its exact name.':'Enter the exact input name shown by the TV in Home Assistant.';
    return '<section class="route"><div class="route-heading"><strong>Connection '+(index+1)+'</strong><button type="button" data-action="remove" data-index="'+index+'" aria-label="Remove connection '+(index+1)+'">Remove</button></div>'+
      '<div class="fields"><label>Playback device<select data-route="'+index+'" data-key="player">'+this.playerOptions(r.player||"")+'</select></label>'+
      '<label>Physical TV / display<select data-route="'+index+'" data-key="display">'+this.playerOptions(r.display||"")+'</select></label>'+
      '<label>TV input / HDMI source<input data-route="'+index+'" data-key="source" type="text" list="nuvio-inputs-'+index+'" value="'+this.esc(source)+'" placeholder="HDMI 1" autocomplete="off">'+this.sourceOptions(r.display,index)+'<small>'+this.esc(hint)+'</small></label>'+
      '<label class="switch"><input type="checkbox" data-route="'+index+'" data-key="turn_on" '+(on?'checked':'')+'>Turn on the display if needed</label>'+
      '<label>Wake delay (ms)<input type="number" min="0" max="10000" step="100" data-route="'+index+'" data-key="wake_delay_ms" value="'+this.esc(wake)+'"></label>'+
      '<label>Delay after input change (ms)<input type="number" min="0" max="10000" step="100" data-route="'+index+'" data-key="delay_ms" value="'+this.esc(settle)+'"></label></div></section>';
  }
  emit(config){
    this._config=config;
    this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:{...config}},bubbles:true,composed:true}));
    this.render();
  }
  change(event){
    const target=event.target;
    if(!target||!target.getAttribute)return;
    const field=target.getAttribute("data-field");
    const routeIndex=target.getAttribute("data-route");
    const checkbox=target.type==="checkbox";
    if(field){
      let value=checkbox?target.checked:target.value;
      if(field==="columns")value=Math.max(1,Math.min(12,Number(value)||6));
      const config={...this._config,[field]:value};
      if(field==="default_player"&&!value)delete config.default_player;
      this.emit(config);
      return;
    }
    if(routeIndex==null)return;
    const key=target.getAttribute("data-key");
    const index=Number(routeIndex),routes=this.routes().map(r=>({...r}));
    if(!Number.isInteger(index)||index<0||index>=routes.length||!key)return;
    let value=checkbox?target.checked:target.value;
    if(key==="delay_ms"||key==="wake_delay_ms")value=Math.max(0,Math.min(10000,Math.round(Number(value)||0)));
    routes[index][key]=value;
    this.emit({...this._config,display_routes:routes});
  }
  clickAction(event){
    const btn=event.target&&event.target.closest&&event.target.closest("button[data-action]");
    if(!btn)return;
    const routes=this.routes().map(route=>({...route}));
    if(btn.getAttribute("data-action")==="add")routes.push({player:"",display:"",source:"",turn_on:true,wake_delay_ms:2000,delay_ms:1000});
    else if(btn.getAttribute("data-action")==="remove"){
      const index=Number(btn.getAttribute("data-index"));
      if(!Number.isInteger(index)||index<0||index>=routes.length)return;
      routes.splice(index,1);
    }else return;
    this.emit({...this._config,display_routes:routes});
  }
  render(){
    if(!this.shadowRoot)return;
    const cfg=this._config,routes=this.routes();
    this.shadowRoot.innerHTML=`<style>
      :host{display:block;color:var(--primary-text-color);font:inherit}
      .editor{display:grid;gap:18px;padding:12px 4px 24px}
      section.group,.route{padding:14px;border:1px solid var(--divider-color);border-radius:14px;background:var(--card-background-color)}
      h3{margin:0 0 12px;font-size:16px}p{color:var(--secondary-text-color);font-size:12px;line-height:1.4;margin:6px 0 12px}
      .fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,210px),1fr));gap:12px;align-items:start}
      label{display:flex;flex-direction:column;gap:6px;font-size:13px;font-weight:500;min-width:0}
      select,input[type=text],input[type=number]{box-sizing:border-box;width:100%;min-width:0;padding:10px;border:1px solid var(--divider-color);border-radius:9px;background:var(--secondary-background-color);color:var(--primary-text-color);font:inherit}
      input[type=checkbox]{width:18px;height:18px;accent-color:var(--primary-color)}
      .switch{display:flex;flex-direction:row;align-items:center;gap:9px;padding:9px 0}
      .route{margin:12px 0;background:var(--secondary-background-color)}
      .route-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}
      button{cursor:pointer;border:1px solid var(--divider-color);background:var(--card-background-color);color:var(--primary-text-color);border-radius:10px;padding:9px 13px;font:inherit}
      button.add{background:var(--primary-color);color:white;border-color:transparent}
      small{font-weight:400;color:var(--secondary-text-color);line-height:1.35}
      @media(max-width:480px){.fields{grid-template-columns:minmax(0,1fr)}section.group,.route{padding:12px}}
    </style><div class="editor">
      <section class="group"><h3>General</h3><div class="fields">
        <label>Card title<input type="text" data-field="title" value="${this.esc(cfg.title==null?"Nuvio":cfg.title)}"></label>
        <label>Catalog columns<input type="number" data-field="columns" min="1" max="12" step="1" value="${this.esc(cfg.columns==null?6:cfg.columns)}"></label>
        <label class="switch"><input type="checkbox" data-field="show_search" ${cfg.show_search!==false?'checked':''}>Show search</label>
      </div></section>
      <section class="group"><h3>Playback device</h3><p>Choose the default device. The player selector remains available in the card’s top toolbar.</p>
        <label>Default player<select data-field="default_player">${this.playerOptions(cfg.default_player||cfg.entity||"")}</select></label>
      </section>
      <section class="group"><h3>Remote control</h3><div class="fields">
        <label class="switch"><input type="checkbox" data-field="show_remote" ${cfg.show_remote!==false?'checked':''}>Show control button</label>
        <label>Remote panel side<select data-field="remote_side"><option value="left" ${cfg.remote_side!=="right"?'selected':''}>Left</option><option value="right" ${cfg.remote_side==="right"?'selected':''}>Right</option></select></label>
      </div></section>
      <section class="group"><h3>HDMI and TV connections</h3><p>When you select a playback device, Nuvio can turn on its physical TV and switch to the connected HDMI input. This mapping is optional, and players without a connection are unchanged. Input names must match the TV’s source list.</p>
        ${routes.map((route,index)=>this.routeHtml(route,index)).join("")}
        <button class="add" type="button" data-action="add">+ Add TV connection</button>
      </section>
    </div>`;
    this._rendered=true;
  }
}
if(!customElements.get("nuvio-card-editor"))customElements.define("nuvio-card-editor",NuvioCardEditor);
'''
anchor = 'if(!customElements.get("nuvio-card"))customElements.define("nuvio-card",NuvioCard);'
assert card.count(anchor)==1, 'Nuvio card registration moved'
card=card.replace(anchor,editor_code+'\n'+anchor,1)
assert 'v0.4.60' in card and 'v0.4.61' not in card
card=card.replace('v0.4.60','v0.4.61')
card_path.write_text(card,encoding='utf-8')

manifest_path=Path('custom_components/nuvio/manifest.json')
manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
assert manifest['version']=='0.4.60'
manifest['version']='0.4.61'
content=manifest_path.read_text(encoding='utf-8')
manifest_path.write_text(content.replace('"version": "0.4.60"','"version": "0.4.61"',1),encoding='utf-8')

readme=Path('README.md')
text=readme.read_text(encoding='utf-8')
marker='### Automatically switch the physical TV to a playback device\n'
assert text.count(marker)==1
text=text.replace(marker,'''### Visual card editor

In **Edit dashboard → Edit Nuvio card**, use the visual editor to choose the
card title, catalog columns, search and remote controls, default playback device,
and optional HDMI/TV connections. Each connection includes the playback device,
physical TV entity, exact input name (with suggestions from `source_list`),
display power-on preference, and optional wake/input delays. You can add or remove
multiple connections without opening the YAML editor. Existing custom YAML keys
are preserved when the visual editor changes another field.

'''+marker,1)
readme.write_text(text,encoding='utf-8')

tests_path=Path('tests/test_card.cjs')
tests=tests_path.read_text(encoding='utf-8')
needle='const flush=()=>new Promise(r=>setImmediate(r));\n'
assert tests.count(needle)==1
editor_tests=r'''// Home Assistant discovers the native visual editor and preserves unrelated YAML.
const editorCard=window.document.createElement('nuvio-card');
const visualEditor=editorCard.constructor.getConfigElement();
assert.equal(visualEditor.localName,'nuvio-card-editor');
visualEditor.setConfig({type:'custom:nuvio-card',title:'Living room',columns:5,
  other_custom_setting:'keep-me',display_routes:[{player:'media_player.box',display:'media_player.lg',source:'HDMI 1',turn_on:true,delay_ms:900}]});
visualEditor.hass={states:{'media_player.box':{attributes:{friendly_name:'Android box'}},
  'media_player.lg':{attributes:{friendly_name:'Living room LG',source_list:['HDMI 1','HDMI 2']}}}};
assert.ok(visualEditor.shadowRoot.querySelector('[data-field="default_player"]'));
assert.ok(visualEditor.shadowRoot.querySelector('[data-field="show_remote"]'));
assert.ok(visualEditor.shadowRoot.querySelector('[data-action="add"]'));
assert.equal(visualEditor.shadowRoot.querySelectorAll('datalist option').length,2);
const edits=[];
visualEditor.addEventListener('config-changed',e=>edits.push(e.detail.config));
const columns=visualEditor.shadowRoot.querySelector('[data-field="columns"]');
columns.value='7';columns.dispatchEvent(new window.Event('change',{bubbles:true}));
assert.equal(edits.at(-1).columns,7);
assert.equal(edits.at(-1).other_custom_setting,'keep-me');
assert.equal(edits.at(-1).display_routes[0].source,'HDMI 1');
visualEditor.shadowRoot.querySelector('[data-action="add"]').click();
assert.equal(edits.at(-1).display_routes.length,2);
visualEditor.shadowRoot.querySelector('[data-action="remove"][data-index="0"]').click();
assert.equal(edits.at(-1).display_routes.length,1);
assert.equal(edits.at(-1).other_custom_setting,'keep-me');
visualEditor.remove();editorCard.remove();
'''
tests=tests.replace(needle,editor_tests+'\n'+needle,1)
tests_path.write_text(tests,encoding='utf-8')
print('Visual editor added; updated version, README, and editor regression tests')
