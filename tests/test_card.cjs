/* Run: npm install --prefix tests && node tests/test_card.cjs */
const {parseHTML}=require('linkedom');
const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const {window}=parseHTML('<html><body></body></html>');
const timers=new Map(),timeouts=new Map();let timerId=0;
window.matchMedia=()=>({matches:false});
const context=vm.createContext({window,document:window.document,HTMLElement:window.HTMLElement,customElements:window.customElements,console,
  setTimeout:fn=>{timeouts.set(++timerId,fn);return timerId;},clearTimeout:id=>timeouts.delete(id),
  setInterval:(fn)=>{timers.set(++timerId,fn);return timerId;},clearInterval:id=>timers.delete(id)});
vm.runInContext(readFileSync('custom_components/nuvio/frontend/nuvio-card.js','utf8'),context);
const cardSource=readFileSync('custom_components/nuvio/frontend/nuvio-card.js','utf8');
assert.match(cardSource,/mdi:chevron-up/);
assert.match(cardSource,/mdi:chevron-down/);
assert.match(cardSource,/mdi:chevron-left/);
assert.match(cardSource,/mdi:chevron-right/);
assert.doesNotMatch(cardSource,/data-remote-key="up"[^\n]*⌃/);
assert.match(cardSource,/nuvio-ring-up ha-icon\{transform:translateY\(-6px\)\}/);
assert.match(cardSource,/ring-btn\.right ha-icon\{transform:translateX\(6px\)\}/);
assert.equal((cardSource.match(/paginate:true/g)||[]).length,0);
assert.match(cardSource,/async loadMoreCatalog\(\)/);
assert.doesNotMatch(cardSource,/_catalogItems\.length\s*>?=\s*300/);
assert.match(cardSource,/refreshCatalogGrid\(\)/);
assert.match(cardSource,/grid\.insertAdjacentHTML\("beforeend",html\)/);
assert.doesNotMatch(cardSource,/grid\.innerHTML=visible\.map/);
assert.match(cardSource,/nuvioScrollTrack/);
assert.match(cardSource,/catalog-sentinel\{overflow-anchor:none\}/);
assert.doesNotMatch(cardSource,/this\._catalogVisibleCount=Math\.min\(this\._catalogItems\.length,this\._catalogVisibleCount\+chunk\);\s*this\.render\(\)/);
assert.match(cardSource,/scroller\.scrollTop=this\._catalogScrollTop/);
assert.match(cardSource,/catalog-sentinel/);
assert.match(cardSource,/IntersectionObserver/);
assert.match(cardSource,/skip:this\._catalogPaging\.nextSkip/);
assert.match(cardSource,/\.catalog-scroll\{height:clamp/);
assert.match(cardSource,/\.catalog-fixed\{/);
assert.match(cardSource,/async loadLazyCatalog[\s\S]*?type:"nuvio\/catalog"[\s\S]*?hide_unreleased:[^\n]+\n\s*\}\);/);
assert.match(cardSource,/\.header\{position:sticky;top:0;z-index:20;/);
assert.match(cardSource,/toolbar-player/);
assert.doesNotMatch(cardSource,/await this\.play\(false,this\._streamContext\|\|null\)/);
assert.match(cardSource,/aria-label="Media player"/);
assert.match(cardSource,/id="homeTop"/);
// The visible logo begins inside the PNG's transparent left inset. Only shift
// the version while the image is displayed; keep text fallback flush-left.
assert.match(cardSource,/\.header-title\.wordmark-loaded \.card-version\{margin-left:16px\}/);
assert.match(cardSource,/wordmark\.closest\("\.header-title"\)\?\.classList\.toggle\("wordmark-loaded",loaded\)/);
assert.equal((cardSource.match(/this\.playerSelect\(\)/g)||[]).length,1);
// Logos must be bundled on the HA backend, with no external brand image URLs.
const localAssets = require('node:fs');
assert.deepEqual([...localAssets.readFileSync('custom_components/nuvio/frontend/assets/wordmark.png').subarray(0,8)],[137,80,78,71,13,10,26,10]);
assert.deepEqual([...localAssets.readFileSync('custom_components/nuvio/frontend/assets/vertical.png').subarray(0,8)],[137,80,78,71,13,10,26,10]);
assert.deepEqual([...localAssets.readFileSync('custom_components/nuvio/frontend/assets/icon-only.png').subarray(0,8)],[137,80,78,71,13,10,26,10]);
assert.doesNotMatch(cardSource,/https:\/\/nuvio\.tv\/assets\/nuvio-app-logo-wordmark\.webp/);
assert.doesNotMatch(cardSource,/\/nuvio\/assets\/wordmark\.webp/);
assert.doesNotMatch(cardSource,/https:\/\/raw\.githubusercontent\.com\/NuvioMedia\/NuvioTVSmart\/main\/assets\/brand\/app_logo_mark\.png/);
// Popup launcher: official logo by default, explicit icon overrides it.
const launcher=window.document.createElement('nuvio-popup-card');
assert.equal(launcher.constructor.getStubConfig().button_icon,undefined);
launcher.setConfig({type:'custom:nuvio-popup-card',button_label:'Nuvio',popup_width:'wide'});
assert.equal(launcher.shadowRoot.querySelector('.launcher-logo').getAttribute('src'),'/nuvio/assets/wordmark.png?v=0.4.99');
assert.equal(launcher.shadowRoot.querySelector('.launcher-visual ha-icon'),null);
assert.equal(launcher.shadowRoot.querySelector('.launcher-caption').style.display,'none');
launcher.setConfig({type:'custom:nuvio-popup-card',button_icon:'mdi:television-play',button_label:'Nuvio'});
assert.equal(launcher.shadowRoot.querySelector('.launcher-logo'),null);
assert.equal(launcher.shadowRoot.querySelector('.launcher-visual ha-icon').getAttribute('icon'),'mdi:television-play');
assert.notEqual(launcher.shadowRoot.querySelector('.launcher-caption').style.display,'none');
launcher.setConfig({type:'custom:nuvio-popup-card',button_icon:'',button_label:'Movies'});
assert.ok(launcher.shadowRoot.querySelector('.launcher-logo'));
assert.equal(launcher.shadowRoot.querySelector('.launcher-caption').textContent,'Movies');
// The simulated DOM lacks the native select and CustomEvent implementations.
// Check editor field/handler statically; logo and icon rendering run in the DOM.
assert.match(cardSource,/Button icon \(MDI, optional\)/);
assert.match(cardSource,/Used for Icon \+ text/);
assert.match(cardSource,/input.addEventListener\("change", \(\) => this.emit/);
// Appearance choices: the user's exact stacked PNG for vertical,
// the official wordmark for horizontal, and custom MDI icon with caption.
launcher.setConfig({type:'custom:nuvio-popup-card',button_style:'vertical',button_label:'Nuvio'});
assert.equal(launcher.getCardSize(),2);
assert.equal(launcher.shadowRoot.querySelector('.launcher-vertical-logo').getAttribute('src'),'/nuvio/assets/vertical.png?v=0.4.99');
assert.equal(launcher.shadowRoot.querySelector('.launcher-caption').textContent,'Nuvio');
assert.equal(launcher.shadowRoot.querySelector('.launcher-caption').style.display,'none');
launcher.setConfig({type:'custom:nuvio-popup-card',button_style:'horizontal',button_icon:'mdi:star',button_label:'Nuvio'});
assert.equal(launcher.getCardSize(),2);
assert.equal(launcher.shadowRoot.querySelector('.launcher-logo').getAttribute('src'),'/nuvio/assets/wordmark.png?v=0.4.99');
assert.equal(launcher.shadowRoot.querySelector('.launcher-visual ha-icon'),null);
launcher.setConfig({type:'custom:nuvio-popup-card',button_style:'icon_text',button_label:'Watch'});
assert.equal(launcher.shadowRoot.querySelector('.launcher-visual ha-icon').getAttribute('icon'),'mdi:television-play');
assert.equal(launcher.shadowRoot.querySelector('.launcher-caption').textContent,'Watch');
launcher.setConfig({type:'custom:nuvio-popup-card',button_style:'icon_text',button_icon:'mdi:movie-open',button_label:'Movies'});
assert.equal(launcher.shadowRoot.querySelector('.launcher-visual ha-icon').getAttribute('icon'),'mdi:movie-open');
assert.equal(launcher.shadowRoot.querySelector('.launcher-logo'),null);
assert.match(cardSource,/Button appearance<select data-field="button_style"/);
assert.match(cardSource,/buttonStyle.addEventListener\("change",\(\)=>this.emit/);
// Logo-only: the user's exact uploaded icon PNG, without caption or MDI icon.
launcher.setConfig({type:'custom:nuvio-popup-card',button_style:'logo_only',button_label:'Custom label',button_icon:'mdi:star',popup_width:'normal'});
assert.equal(launcher.launcherStyle(),'logo_only');
assert.equal(launcher.getCardSize(),2);
assert.equal(launcher.shadowRoot.querySelector('.launcher-mark').getAttribute('src'),'/nuvio/assets/icon-only.png?v=0.4.99');
assert.equal(launcher.shadowRoot.querySelector('.launcher-logo'),null);
assert.equal(launcher.shadowRoot.querySelector('.launcher-visual ha-icon'),null);
assert.equal(launcher.shadowRoot.querySelector('.launcher-caption').style.display,'none');
assert.equal(launcher.shadowRoot.querySelector('button').getAttribute('aria-label'),'Open Nuvio');
assert.match(cardSource,/<option value="logo_only">Logo only<\/option>/);
assert.match(cardSource,/"logo_only","icon_text"\]\.includes\(this\._config\.button_style\)/);
// Auto-close: default, disable, invalid input, changes while open, and cleanup.
assert.equal(launcher.constructor.getStubConfig().popup_auto_close_minutes,2);
assert.equal(launcher.popupAutoCloseMinutes(),2);
assert.match(cardSource,/Popup auto-close \(minutes\)/);
assert.match(cardSource,/data-field="popup_auto_close_minutes" type="number" min="0"/);
assert.match(cardSource,/this\.startAutoCloseTimer\(\);\s*\}\s*closePopup\(\)/);
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
// Home Assistant discovers the native visual editor and preserves unrelated YAML.
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
// The TV's source_list becomes a real selectable menu, not static HDMI guesses.
let tvSource=visualEditor.shadowRoot.querySelector('[data-route="0"][data-key="source"]');
assert.equal(tvSource.localName,'select');
assert.deepEqual([...tvSource.querySelectorAll('option')].map(o=>o.value),['','HDMI 1','HDMI 2']);
assert.equal(tvSource.value,'HDMI 1');
assert.equal(visualEditor.shadowRoot.querySelectorAll('datalist').length,0);
const edits=[];
visualEditor.addEventListener('config-changed',e=>edits.push(e.detail.config));
const columns=visualEditor.shadowRoot.querySelector('[data-field="columns"]');
columns.value='7';columns.dispatchEvent(new window.Event('change',{bubbles:true}));
assert.equal(edits.at(-1).columns,7);
assert.equal(edits.at(-1).other_custom_setting,'keep-me');
assert.equal(edits.at(-1).display_routes[0].source,'HDMI 1');
// Changing the selected input updates the saved route and preserves custom keys.
tvSource=visualEditor.shadowRoot.querySelector('[data-route="0"][data-key="source"]');
visualEditor.change({target:{getAttribute:key=>({'data-route':'0','data-key':'source'})[key]??null,type:'select-one',value:'HDMI 2'}});
assert.equal(edits.at(-1).display_routes[0].source,'HDMI 2');
assert.equal(edits.at(-1).other_custom_setting,'keep-me');
// A changed TV source_list refreshes the options.
visualEditor.hass={states:{'media_player.box':{attributes:{}},'media_player.lg':{attributes:{source_list:['HDMI 2','Game console']}}}};
tvSource=visualEditor.shadowRoot.querySelector('[data-route="0"][data-key="source"]');
assert.deepEqual([...tvSource.querySelectorAll('option')].map(o=>o.value),['','HDMI 2','Game console']);
// Different physical TV: no stale source, and show that TV's actual source_list.
visualEditor.hass={states:{'media_player.box':{attributes:{}},'media_player.lg':{attributes:{source_list:['HDMI 2']}},'media_player.roku':{attributes:{source_list:['HDMI 3','Android TV']}}}};
let tvDisplay=visualEditor.shadowRoot.querySelector('[data-route="0"][data-key="display"]');
visualEditor.change({target:{getAttribute:key=>({'data-route':'0','data-key':'display'})[key]??null,type:'select-one',value:'media_player.roku'}});
assert.equal(edits.at(-1).display_routes[0].source,'');
tvSource=visualEditor.shadowRoot.querySelector('[data-route="0"][data-key="source"]');
assert.deepEqual([...tvSource.querySelectorAll('option')].map(o=>o.value),['','HDMI 3','Android TV']);
// TVs not reporting source_list retain a manual input fallback.
visualEditor.hass={states:{'media_player.box':{attributes:{}},'media_player.roku':{attributes:{}}}};
tvSource=visualEditor.shadowRoot.querySelector('[data-route="0"][data-key="source"]');
assert.equal(tvSource.localName,'input');
tvSource.value='Custom input';tvSource.dispatchEvent(new window.Event('change',{bubbles:true}));
assert.equal(edits.at(-1).display_routes[0].source,'Custom input');

visualEditor.shadowRoot.querySelector('[data-action="add"]').click();
assert.equal(edits.at(-1).display_routes.length,2);
visualEditor.shadowRoot.querySelector('[data-action="remove"][data-index="0"]').click();
assert.equal(edits.at(-1).display_routes.length,1);
assert.equal(edits.at(-1).other_custom_setting,'keep-me');
visualEditor.remove();editorCard.remove();

// Room mapping and TV volume regressions.
assert.match(cardSource,/id="room" aria-label="Room"/);
assert.match(cardSource,/data-volume="up"/);
assert.match(cardSource,/data-volume="down"/);
assert.match(cardSource,/data-volume="mute"/);
const roomEditor=window.document.createElement('nuvio-card-editor');
roomEditor.setConfig({type:'custom:nuvio-card',other_custom_setting:'preserved',default_room:'living',
  rooms:[{id:'living',name:'Living room',player:'media_player.box',display:'media_player.lg',source:'HDMI 1',power_entity:'switch.tv_plug',volume_entity:'media_player.lg'}],
  display_routes:[{player:'media_player.other',display:'media_player.roku',source:'HDMI 3'}]});
roomEditor.hass={states:{
  'media_player.box':{attributes:{friendly_name:'Box'}},
  'media_player.lg':{attributes:{friendly_name:'LG TV',source_list:['HDMI 1','Console']}},
  'media_player.roku':{attributes:{source_list:['HDMI 3','HDMI 4']}},
  'switch.tv_plug':{state:'off',attributes:{friendly_name:'TV plug'}}}};
assert.equal(roomEditor.shadowRoot.querySelector('[data-field="default_room"]').value,'living');
assert.deepEqual([...roomEditor.shadowRoot.querySelectorAll('[data-room="0"][data-key="source"] option')].map(o=>o.value),['','HDMI 1','Console']);
assert.equal(roomEditor.shadowRoot.querySelector('[data-room="0"][data-key="power_entity"]').value,'switch.tv_plug');
const roomEdits=[];
roomEditor.addEventListener('config-changed',event=>roomEdits.push(event.detail.config));
roomEditor.change({target:{getAttribute:key=>({'data-room':'0','data-key':'display'})[key]??null,type:'select-one',value:'media_player.roku'}});
assert.equal(roomEdits.at(-1).rooms[0].source,'');
assert.equal(roomEdits.at(-1).other_custom_setting,'preserved');
assert.equal(roomEdits.at(-1).display_routes[0].source,'HDMI 3');
assert.deepEqual([...roomEditor.shadowRoot.querySelectorAll('[data-room="0"][data-key="source"] option')].map(o=>o.value),['','HDMI 3','HDMI 4']);
roomEditor.shadowRoot.querySelector('[data-action="add-room"]').click();
assert.equal(roomEdits.at(-1).rooms.length,2);
roomEditor.shadowRoot.querySelector('[data-action="remove-room"][data-index="0"]').click();
assert.equal(roomEdits.at(-1).rooms.length,1);
assert.notEqual(roomEdits.at(-1).default_room,'living');
roomEditor.remove();

const flush=()=>new Promise(r=>setImmediate(r));
(async()=>{
 // Route HDMI first while preserving the selected Nuvio playback entity.
 const routed=window.document.createElement('nuvio-card');
 routed.setConfig({show_remote:false,display_routes:[{player:'media_player.android_box',display:'media_player.lg_tv',source:'HDMI 2',wake_delay_ms:0,delay_ms:0}]});
 routed._playerId='media_player.android_box';routed._item={id:'tt1',type:'movie',name:'Movie'};
 const routedCalls=[],display={state:'on',attributes:{source:'HDMI 1'}};
 routed._hass={states:{'media_player.lg_tv':display,'media_player.android_box':{}},callService:async(...args)=>routedCalls.push(args)};
 await routed.play(false,null);
 assert.deepEqual(routedCalls.map(x=>x[0]+'.'+x[1]),['media_player.select_source','nuvio.play']);
 assert.equal(routedCalls[0][2].source,'HDMI 2');
 assert.equal(routedCalls[0][3].entity_id,'media_player.lg_tv');
 assert.equal(routedCalls[1][3].entity_id,'media_player.android_box');
 routedCalls.length=0;routed._playerId='media_player.no_route';
 await routed.play(false,null);
 assert.equal(routedCalls.length,1);assert.equal(routedCalls[0][1],'play');
 routed._playerId='media_player.android_box';routed._lastDisplaySwitch=null;
 display.attributes.source='HDMI 2';routedCalls.length=0;
 await routed.play(false,null);
 assert.deepEqual(routedCalls.map(x=>x[1]),['play']);
 display.state='off';display.attributes.source='HDMI 1';routed._lastDisplaySwitch=null;routedCalls.length=0;
 await routed.play(false,null);
 assert.deepEqual(routedCalls.map(x=>x[1]),['turn_on','select_source','play']);
 routed.remove();
 // Room selection controls playback, HDMI switching and the physical TV's volume.
 const roomCard=window.document.createElement('nuvio-card');
 roomCard.setConfig({show_remote:false,default_room:'living',rooms:[
   {id:'living',name:'Living room',player:'media_player.room_box',display:'media_player.room_tv',source:'HDMI 2',volume_entity:'',power_entity:'switch.room_plug',turn_on:true,power_delay_ms:0,wake_delay_ms:0,delay_ms:0},
   {id:'bed',name:'Bedroom',player:'media_player.bedroom_box',display:'',source:''}
 ]});
 roomCard._item={id:'tt22',type:'movie',name:'Room test'};
 const roomCalls=[];
 roomCard._hass={states:{
   'switch.room_plug':{state:'off',attributes:{}},
   'media_player.room_tv':{state:'on',attributes:{source:'HDMI 1',is_volume_muted:false}},
   'media_player.room_box':{state:'on',attributes:{}},
   'media_player.bedroom_box':{state:'on',attributes:{is_volume_muted:true}}
 },callService:async(...args)=>roomCalls.push(args)};
 assert.equal(roomCard.player(),'media_player.room_box');
 assert.equal(roomCard.selectedRoom().name,'Living room');
 assert.match(roomCard.header(),/id="room"/);
 await roomCard.playSource({url:'https://example.com/test.mp4',name:'Room video'},true);
 assert.deepEqual(roomCalls.map(args=>args[0]+'.'+args[1]),['homeassistant.turn_on','media_player.select_source','nuvio.play_source']);
 assert.equal(roomCalls[0][3].entity_id,'switch.room_plug');
 assert.equal(roomCalls[1][2].source,'HDMI 2');
 assert.equal(roomCalls[1][3].entity_id,'media_player.room_tv');
 assert.equal(roomCalls[2][3].entity_id,'media_player.room_box');
 roomCalls.length=0;
 await roomCard.volumeControl('up');
 await roomCard.volumeControl('down');
 await roomCard.volumeControl('mute');
 assert.deepEqual(roomCalls.map(args=>args[1]),['volume_up','volume_down','volume_mute']);
 assert.ok(roomCalls.every(args=>args[3].entity_id==='media_player.room_tv'));
 assert.equal(roomCalls[2][2].is_volume_muted,true);
 roomCalls.length=0;
 await roomCard.chooseRoom('bed');
 assert.equal(roomCard.player(),'media_player.bedroom_box');
 assert.equal(roomCard.selectedRoom().id,'bed');
 await roomCard.volumeControl('mute');
 assert.equal(roomCalls.at(-1)[3].entity_id,'media_player.bedroom_box');
 assert.equal(roomCalls.at(-1)[2].is_volume_muted,false);
 roomCalls.length=0;
 await roomCard.chooseRoom('living');
 roomCalls.length=0;
 await roomCard.toggleRoomPower();
 assert.equal(roomCalls[0][0]+'.'+roomCalls[0][1],'homeassistant.turn_on');
 assert.equal(roomCalls[0][3].entity_id,'switch.room_plug');
 roomCard.remove();
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
 unresolved.remove();
 const card=window.document.createElement('nuvio-card');window.document.body.append(card);
 card.setConfig({show_remote:false});card._loaded=true;
 card._hass={states:{'media_player.living_room':{attributes:{friendly_name:'Living Room TV'}},'media_player.bedroom':{attributes:{friendly_name:'Bedroom TV'}}}};
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

 card._hero=Array.from({length:12},(_,i)=>({id:'tt'+i,type:'movie',name:'Featured '+i}));
 card._sections=['Discover','Streaming','Genres','Themes','Studios','Decades','Runtime','World'].map((name,i)=>({kind:'collection',name,items:[{name:i===1?'Netflix':name,hide_title:true,sources:[{addonId:'aio-metadata',catalogId:'movies'+i,type:'movie',genre:'None'},{addonId:'aio-metadata',catalogId:'series'+i,type:'series',genre:'Drama'}]}]}));
 card._sections.push({kind:'catalog',name:'Popular',manifest_url:'https://example.test/manifest.json',catalog_id:'popular',media_type:'movie',items:[]});
 const calls=[];
 card.ws=async m=>{calls.push(m);if(m.type==='nuvio/details')return {id:m.content_id,type:m.media_type,name:'Details'};return {items:[{id:'tt1',type:m.media_type,name:'Title',manifest_url:'https://example.test/manifest.json'}]};};
 card.render();
 const root=card.shadowRoot,click=s=>{assert.ok(root.querySelector(s),s);root.querySelector(s).click();};
 for(let i=0;i<8;i++){
  root.querySelectorAll('.collection-card')[i].click();await flush();
  assert.equal(card._catalogItems.length,2);assert.equal(root.querySelectorAll('.collection-tab').length,3);
  click('[data-tab="1"]');assert.equal(card._catalogItems[0].type,'series');assert.equal(card._catalogItems.length,1);
  click('.catalog-grid .pc');await flush();assert.equal(card._view,'details');
  click('#back');assert.equal(card._view,'catalog');assert.equal(card._catalogItems.length,1);
  click('#back');assert.equal(card._view,'home');
 }
 assert.equal(calls[0].addon_id,'aio-metadata');assert.equal(calls[0].genre,'None');assert.equal(calls[1].genre,'Drama');
 click('.see-all');await flush();assert.equal(card._catalogItems.length,1);assert.equal(card._collectionTabs,null);click('#back');
 // Routine HA state pushes must preserve the rendered DOM and click targets.
 const tile=root.querySelector('.collection-card');card.hass={states:{}};assert.equal(root.querySelector('.collection-card'),tile);
 click('[data-hero-step="-1"]');assert.equal(card._heroIndex,11);click('[data-hero-step="1"]');assert.equal(card._heroIndex,0);
 assert.equal(root.querySelectorAll('.home-hero-dot').length,7);
 const stage=root.querySelector('.home-hero-stage');stage.matches=()=>false;
 timers.get(card._heroTimer)();assert.equal(card._heroIndex,1);
 click('.hero-pause');root.querySelector('.home-hero-stage').matches=()=>false;timers.get(card._heroTimer)();assert.equal(card._heroIndex,1);
 // Preserve successful catalogs if another source fails.
 card.ws=async m=>{if(m.media_type==='series')throw new Error('Unavailable');return {items:[{id:'tt2',type:'movie',name:'Available'}]};};
 root.querySelector('.collection-card').click();await flush();assert.equal(card._catalogItems.length,1);assert.match(card._error,/Unavailable/);
 click('#back');
 // A slow, abandoned folder request cannot overwrite a later catalog.
 const resolve=[];card.ws=()=>new Promise(r=>resolve.push(r));
 const pending=card.openCollection(card._sections[0].items[0],card._sections[0]);
 card.ws=async()=>({items:[{id:'new',type:'movie',name:'New catalog'}]});
 await card.openCatalog(card._sections[8]);resolve.forEach(r=>r({items:[]}));await pending;
 assert.equal(card._catalogItems[0].id,'new');
 card.remove();assert.equal(card._heroTimer,null);assert.equal(timers.size,0);
 // External provider links (for example WatchHub/Amazon) are navigation URLs,
 // not media streams: never expose the direct-player buttons for them.
 const external=window.document.createElement('nuvio-card');external.setConfig({show_remote:false,entity:'media_player.tv'});external._loaded=true;external._view='sources';
 external._item={id:'tt1',type:'movie',name:'Movie'};external._details=external._item;external._streams=[{addon:'WatchHub',name:'Amazon Video',external_url:'https://watch.amazon.com/detail?gti=test',external:true,direct:false,resolvable:false,badges:[]}];
 const providerCalls=[];external._hass={states:{'media_player.tv':{}},callService:async(...args)=>providerCalls.push(args)};external.render();const externalHtml=external.shadowRoot.innerHTML;
 assert.match(externalHtml,/>▶ Play<\/button>/);assert.match(externalHtml,/Streaming app/);assert.doesNotMatch(externalHtml,/Play on TV/);assert.doesNotMatch(externalHtml,/Play in Nuvio/);assert.doesNotMatch(externalHtml,/Open title in Nuvio/);
 external.shadowRoot.querySelector('.nuvioplay').click();await flush();assert.equal(providerCalls.length,1);assert.equal(providerCalls[0][0],'nuvio');assert.equal(providerCalls[0][1],'play_provider');assert.equal(providerCalls[0][2].external_url,'https://watch.amazon.com/detail?gti=test');assert.equal(providerCalls[0][2].provider_name,'Amazon Video');assert.equal(providerCalls[0][2].media_type,'movie');assert.equal(providerCalls[0][2].title,'Movie');assert.equal(providerCalls[0][2].content_id,'tt1');assert.equal(providerCalls[0][3].entity_id,'media_player.tv');
 external.remove();
 // Direct and resolvable rows also expose only the same Nuvio-backed Play action.
 const onePlay=window.document.createElement('nuvio-card');onePlay.setConfig({show_remote:false});onePlay._loaded=true;onePlay._view='sources';onePlay._item={id:'tt2',type:'movie',name:'Movie'};onePlay._details=onePlay._item;
 onePlay._streams=[{addon:'Direct',name:'HTTP',url:'https://cdn.example/video.mp4',direct:true,resolvable:false,badges:[]},{addon:'Debrid',name:'Torrent',info_hash:'abc',direct:false,resolvable:true,badges:[]}];onePlay._debridMeta={configured:true,providers:['Test']};onePlay.render();
 const playLabels=[...onePlay.shadowRoot.querySelectorAll('.nuvioplay')].map(b=>b.textContent.trim());assert.deepEqual(playLabels,['▶ Play','▶ Play']);assert.equal(onePlay.shadowRoot.querySelectorAll('.playsource,.playdirect').length,0);
 onePlay.remove();
 // Movies with no episodes skip Details and open Sources immediately.
 const movieAuto=window.document.createElement('nuvio-card');movieAuto.setConfig({show_remote:false});movieAuto._loaded=true;movieAuto._view='catalog';
 const movieCalls=[];movieAuto.ws=async m=>{movieCalls.push(m);if(m.type==='nuvio/details')return {id:m.content_id,type:'movie',name:'Movie details',releaseInfo:'2026',genres:['Drama','Sci-Fi'],description:'Movie overview text',poster:'https://img.example/movie.jpg',videos:[]};if(m.type==='nuvio/streams')return {streams:m.addon_scope==='watchhub'?[{addon:'WatchHub',name:'Netflix',provider_key:'netflix',external_url:'https://www.netflix.com/title/test',external:true,direct:false,badges:[]}]:[{addon:'Direct',name:'Movie stream',url:'https://cdn.example/movie.mp4',direct:true,badges:[]}],debrid:{configured:false}};if(m.type==='nuvio/watch_providers')return {configured:true,tmdb_configured:true,tvdb_configured:true,justwatch_enabled:true,region:'US',scope:'movie',providers:[{provider_id:8,name:'Netflix',provider_key:'netflix',logo_url:'https://img.example/netflix.jpg',access:['Subscription'],deep_link:'https://www.netflix.com/title/exact',deep_link_source:'justwatch',justwatch_provider_name:'Netflix'},{provider_id:337,name:'Disney Plus',provider_key:'disney',logo_url:'https://img.example/disney.jpg',access:['Subscription'],deep_link:'https://www.disneyplus.com/browse/entity-exact',deep_link_source:'thetvdb'}],attribution:'Availability by JustWatch via TMDB · Offer links via unofficial JustWatch GraphQL · Fallback exact links via TheTVDB'};throw new Error('Unexpected '+m.type);};
 await movieAuto.selectItem({id:'movie1',type:'movie',name:'Movie',manifest_url:'https://example.test/manifest.json'});
 const movieStreamCalls=movieCalls.filter(x=>x.type==='nuvio/streams');assert.equal(movieAuto._view,'sources');assert.equal(movieAuto._sourcesBackView,'catalog');assert.equal(movieStreamCalls.length,2);assert.deepEqual(movieStreamCalls.map(x=>x.addon_scope),['watchhub','other']);assert.equal(movieStreamCalls[0].video_id,'movie1');assert.deepEqual(movieAuto._streams.map(x=>x.addon),['WatchHub','Direct']);
 assert.equal(movieAuto.shadowRoot.querySelector('.header h2').textContent.trim(),'Nuvio');assert.ok(movieAuto.shadowRoot.querySelector('#homeTop'));assert.ok(movieAuto.shadowRoot.querySelector('#refresh'));assert.ok(movieAuto.shadowRoot.querySelector('#addonsToggle'));assert.equal(movieAuto.shadowRoot.querySelectorAll('.watch-provider').length,2);assert.equal(movieAuto.shadowRoot.querySelectorAll('[data-watch-provider-index]').length,2);assert.match(movieAuto.shadowRoot.innerHTML,/Offer links via unofficial JustWatch GraphQL/);assert.match(movieAuto.shadowRoot.innerHTML,/Movie availability · US/);assert.match(movieAuto.shadowRoot.innerHTML,/JustWatch offer/);assert.match(movieAuto.shadowRoot.innerHTML,/TheTVDB exact link/);const providerRequest=movieCalls.find(x=>x.type==='nuvio/watch_providers');assert.equal(providerRequest.title,'Movie details');
 movieAuto.shadowRoot.querySelector('#addonsToggle').click();assert.equal(movieAuto.shadowRoot.querySelectorAll('.source-filter-chip').length,3);const directChip=[...movieAuto.shadowRoot.querySelectorAll('.source-filter-chip')].find(x=>x.textContent.trim()==='Direct');directChip.click();assert.equal(movieAuto._addonFilter,'Direct');assert.match(movieAuto.shadowRoot.querySelector('.source-summary').textContent,/1 of 2 sources/);assert.doesNotMatch(movieAuto.shadowRoot.querySelector('.sources').textContent,/Netflix/);
 assert.ok(movieAuto.shadowRoot.querySelector('.source-context-movie'));assert.match(movieAuto.shadowRoot.querySelector('.source-context-movie').textContent,/Movie details/);assert.match(movieAuto.shadowRoot.querySelector('.source-context-movie').textContent,/2026/);assert.match(movieAuto.shadowRoot.querySelector('.source-context-movie').textContent,/Drama, Sci-Fi/);assert.match(movieAuto.shadowRoot.querySelector('.source-context-movie').textContent,/Movie overview text/);
 movieAuto.shadowRoot.querySelector('#backDetails').click();assert.equal(movieAuto._view,'catalog');assert.ok(movieAuto.shadowRoot.querySelector('#homeTop'));movieAuto.shadowRoot.querySelector('#homeTop').click();await flush();assert.equal(movieAuto._view,'home');movieAuto.remove();
 // Series still opens its episode list; selecting an episode opens that episode's Sources directly.
 const seriesAuto=window.document.createElement('nuvio-card');seriesAuto.setConfig({show_remote:false});seriesAuto._loaded=true;seriesAuto._view='catalog';
 const seriesCalls=[];seriesAuto.ws=async m=>{seriesCalls.push(m);if(m.type==='nuvio/details')return {id:m.content_id,type:'series',name:'Series details',poster:'https://img.example/show.jpg',videos:[{id:'series1:1:1',season:1,episode:1,title:'Pilot',overview:'Pilot episode overview',thumbnail:'https://img.example/pilot.jpg'},{id:'series1:1:2',season:1,episode:2,title:'Second',thumbnail:''}]};if(m.type==='nuvio/streams')return {streams:m.addon_scope==='watchhub'?[]:[{addon:'Direct',name:'Episode stream',url:'https://cdn.example/episode.mp4',direct:true,badges:[]}],debrid:{configured:false}};throw new Error('Unexpected '+m.type);};
 await seriesAuto.selectItem({id:'series1',type:'series',name:'Series',manifest_url:'https://example.test/manifest.json'});
 assert.equal(seriesAuto._view,'details');assert.equal(seriesAuto.shadowRoot.querySelectorAll('.sourceep').length,2);assert.equal(seriesAuto.shadowRoot.querySelectorAll('.playep').length,0);assert.doesNotMatch(seriesAuto.shadowRoot.innerHTML,/>Sources<\/button>/);
 seriesAuto.shadowRoot.querySelector('.sourceep').click();await flush();await flush();assert.equal(seriesAuto._view,'sources');assert.equal(seriesAuto._streamContext.id,'series1:1:1');assert.equal(seriesAuto._sourcesBackView,'details');const seriesStreamCalls=seriesCalls.filter(x=>x.type==='nuvio/streams');assert.deepEqual(seriesStreamCalls.map(x=>x.addon_scope),['watchhub','other']);assert.equal(seriesStreamCalls[0].video_id,'series1:1:1');
 const episodeContext=seriesAuto.shadowRoot.querySelector('.source-context-episode');assert.ok(episodeContext);assert.match(episodeContext.textContent,/Series details/);assert.match(episodeContext.textContent,/Pilot/);assert.match(episodeContext.textContent,/Season 1 · Episode 1/);assert.match(episodeContext.textContent,/Pilot episode overview/);assert.equal(episodeContext.querySelector('img').getAttribute('src'),'https://img.example/pilot.jpg');
 seriesAuto._streams=[{addon:'WatchHub',name:'Netflix',external_url:'https://www.netflix.com/title/80014749',external:true,direct:false,resolvable:false,badges:[{kind:'availability',label:'Series-level'}],watchhub_series_level:true}];
 const episodeProviderCalls=[];seriesAuto._hass={states:{'media_player.tv':{}},callService:async(...args)=>episodeProviderCalls.push(args)};seriesAuto._playerId='media_player.tv';seriesAuto.render();seriesAuto.shadowRoot.querySelector('.nuvioplay').click();await flush();assert.equal(episodeProviderCalls.length,1);const episodeProviderData=episodeProviderCalls[0][2];assert.equal(episodeProviderData.media_type,'series');assert.equal(episodeProviderData.content_id,'series1');assert.equal(episodeProviderData.video_id,'series1:1:1');assert.equal(episodeProviderData.season,1);assert.equal(episodeProviderData.episode,1);assert.equal(episodeProviderData.episode_title,'Pilot');assert.match(seriesAuto.shadowRoot.innerHTML,/Series-level/);
 seriesAuto.shadowRoot.querySelector('#backDetails').click();assert.equal(seriesAuto._view,'details');seriesAuto.remove();
 // Empty cold-start responses recover without a browser reload.
 const cold=window.document.createElement('nuvio-card');window.document.body.append(cold);cold.setConfig({show_remote:false});
 const recovered={sections:[{kind:'collection',name:'Streaming',items:[]}],hero:{items:[]}};
 let requests=0,retryMessages=[];cold.ws=async m=>{retryMessages.push(m);return ++requests===1?{sections:[],hero:{items:[]}}:recovered;};
 cold.hass={states:{}};await flush();assert.equal(requests,1);assert.ok(cold._homeRetryTimer);assert.match(cold.home(),/Retrying automatically/);
 cold.hass={states:{}};assert.equal(requests,1);
 let retryTimer=cold._homeRetryTimer,retryFn=timeouts.get(retryTimer);timeouts.delete(retryTimer);retryFn();await flush();assert.equal(cold._sections.length,1);assert.equal(cold._homeRetryCount,0);assert.equal(retryMessages[1].refresh,false);
 cold.ws=async()=>({sections:[],hero:{items:[]}});await cold.loadHome(true);assert.equal(cold._sections.length,1);
 cold.remove();assert.equal(cold._homeRetryTimer,null);
 // Home keeps all catalog descriptors but only fetches lazy rows as needed.
 const lazy=window.document.createElement('nuvio-card');lazy.setConfig({show_remote:false});lazy._view='catalog';
 lazy._homePrefs={layout:'modern'};lazy._sections=[{id:'lazy1',kind:'catalog',name:'Lazy',lazy:true,manifest_url:'https://example.test/manifest.json',media_type:'movie',catalog_id:'lazy',items:[]}];
 lazy.ws=async()=>({items:Array.from({length:20},(_,i)=>({id:'l'+i,type:'movie',name:'Lazy '+i}))});
 await lazy.loadLazyCatalog(0);assert.equal(lazy._sections[0].lazy,false);assert.equal(lazy._sections[0].items.length,15);
 // Defensive card cap keeps a malformed/older backend from rendering >7 Hero items.
 const heroCap=window.document.createElement('nuvio-card');heroCap.setConfig({show_remote:false});heroCap._hass={states:{}};
 heroCap.ws=async()=>({sections:[{kind:'collection',name:'Home',items:[]}],hero:{items:Array.from({length:12},(_,i)=>({id:'h'+i,type:'movie',name:'Hero '+i}))},players:[],preferences:{}});
 await heroCap.loadHome();assert.equal(heroCap._hero.length,7);
 const empty=window.document.createElement('nuvio-card');window.document.body.append(empty);empty.setConfig({show_remote:false});empty.ws=async()=>({sections:[]});empty.hass={states:{}};await flush();
 for(let i=0;i<3;i++){let id=empty._homeRetryTimer,fn=timeouts.get(id);timeouts.delete(id);fn();await flush();}
 assert.equal(empty._homeRetryTimer,null);assert.equal(empty._homeRetryCount,3);empty.remove();assert.equal(timeouts.size,0);
 console.log('PASS: JustWatch-first provider links, configured-country TMDB provider row, WatchHub-first progressive sources, addon source filtering, persistent header controls, source movie/episode details, streaming-app Play routing, direct movie and episode Sources, single Play action, external provider-link safety, lazy Home catalogs, seven-item Hero cap, progressive recovery, cached automatic retries, retained content, plus collection rows, source tabs, details/back, regular catalogs, stable HA updates, hero controls, partial failures, request races, timer cleanup');
})().catch(e=>{console.error(e);process.exitCode=1;});
