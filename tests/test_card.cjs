/* Run: npm install --prefix tests && node tests/test_card.cjs */
const {parseHTML}=require('linkedom');
const {readFileSync}=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const {window}=parseHTML('<html><body></body></html>');
const timers=new Map();let timerId=0;
window.matchMedia=()=>({matches:false});
const context=vm.createContext({window,document:window.document,HTMLElement:window.HTMLElement,customElements:window.customElements,console,
  setInterval:(fn)=>{timers.set(++timerId,fn);return timerId;},clearInterval:id=>timers.delete(id)});
vm.runInContext(readFileSync('custom_components/nuvio/frontend/nuvio-card.js','utf8'),context);
const flush=()=>new Promise(r=>setImmediate(r));
(async()=>{
 const card=window.document.createElement('nuvio-card');window.document.body.append(card);
 card.setConfig({show_remote:false});card._loaded=true;
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
 console.log('PASS: 8 collection rows, source tabs, details/back, regular catalogs, stable HA updates, hero arrows/rotation/pause, partial failures, request races, timer cleanup');
})().catch(e=>{console.error(e);process.exitCode=1;});
