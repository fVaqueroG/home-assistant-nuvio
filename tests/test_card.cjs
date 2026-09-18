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
 // External provider links (for example WatchHub/Amazon) are navigation URLs,
 // not media streams: never expose the direct-player buttons for them.
 const external=window.document.createElement('nuvio-card');external.setConfig({show_remote:false});external._loaded=true;external._view='sources';
 external._item={id:'tt1',type:'movie',name:'Movie'};external._details=external._item;external._streams=[{addon:'WatchHub',name:'Amazon Video',external_url:'https://watch.amazon.com/detail?gti=test',external:true,direct:false,resolvable:false,badges:[]}];
 external.render();const externalHtml=external.shadowRoot.innerHTML;
 assert.match(externalHtml,/>▶ Play<\/button>/);assert.match(externalHtml,/External provider link/);assert.doesNotMatch(externalHtml,/Play on TV/);assert.doesNotMatch(externalHtml,/Play in Nuvio/);assert.doesNotMatch(externalHtml,/Open title in Nuvio/);
 external.remove();
 // Direct and resolvable rows also expose only the same Nuvio-backed Play action.
 const onePlay=window.document.createElement('nuvio-card');onePlay.setConfig({show_remote:false});onePlay._loaded=true;onePlay._view='sources';onePlay._item={id:'tt2',type:'movie',name:'Movie'};onePlay._details=onePlay._item;
 onePlay._streams=[{addon:'Direct',name:'HTTP',url:'https://cdn.example/video.mp4',direct:true,resolvable:false,badges:[]},{addon:'Debrid',name:'Torrent',info_hash:'abc',direct:false,resolvable:true,badges:[]}];onePlay._debridMeta={configured:true,providers:['Test']};onePlay.render();
 const playLabels=[...onePlay.shadowRoot.querySelectorAll('.nuvioplay')].map(b=>b.textContent.trim());assert.deepEqual(playLabels,['▶ Play','▶ Play']);assert.equal(onePlay.shadowRoot.querySelectorAll('.playsource,.playdirect').length,0);
 onePlay.remove();
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
 console.log('PASS: single Nuvio Play action, external provider-link safety, lazy Home catalogs, seven-item Hero cap, progressive recovery, cached automatic retries, retained content, plus collection rows, source tabs, details/back, regular catalogs, stable HA updates, hero controls, partial failures, request races, timer cleanup');
})().catch(e=>{console.error(e);process.exitCode=1;});
