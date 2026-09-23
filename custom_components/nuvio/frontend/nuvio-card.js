class NuvioCard extends HTMLElement {
  constructor(){
    super(); this.attachShadow({mode:"open"});
    this._config={}; this._hass=null; this._loaded=false; this._loading=false;
    this._sections=[]; this._hero=[]; this._heroIndex=0; this._homePrefs={}; this._results=[]; this._catalogSection=null; this._catalogItems=[]; this._catalogLoading=false; this._catalogLoadingMore=false; this._catalogVisibleCount=0; this._catalogPaging=null; this._catalogObserver=null; this._catalogScrollTop=0; this._catalogLoadError=""; this._resetCatalogScroll=false; this._catalogReload=null; this._returnView="home"; this._playersMeta=[]; this._playerId=""; this._roomId=null; this._streams=[]; this._streamLoading=false; this._streamLoadingStage=""; this._streamContext=null; this._sourceRequest=0; this._addonFilter="all"; this._addonFilterExpanded=false; this._watchProviders=[]; this._watchProviderMeta={configured:false}; this._watchProvidersLoading=false; this._debridMeta={configured:false,provider:""}; this._resolving=new Set(); this._lazyCatalogLoads=new Set(); this._lazyObserver=null; this._remoteExpanded=false; this._view="home"; this._item=null; this._details=null; this._season=null; this._query=""; this._error="";
  }
  static getConfigElement(){ return document.createElement("nuvio-card-editor"); }
  static getStubConfig(){ return {title:"Nuvio",columns:6,show_remote:true,remote_side:"left"}; }
  setConfig(c){
    this._config=Object.assign({title:"Nuvio",columns:6,show_search:true,show_remote:true,remote_side:"left"},c||{});
    var rooms=this.rooms();
    if(this._roomId===null||(this._roomId&&!rooms.some(r=>r.id===this._roomId))){
      var initial=rooms.find(r=>r.id===this._config.default_room)||rooms[0];
      this._roomId=initial?initial.id:"";
    }
    var room=this.selectedRoom();
    if(room&&room.player)this._playerId=room.player;
    this.render();
  }
  set hass(h){ this._hass=h; if(!this._loaded&&!this._loading&&!this._homeRetryTimer&&(this._homeRetryCount||0)<3)this.loadHome(); }
  getCardSize(){ return 8; }
  ws(m){ return this._hass.connection.sendMessagePromise(m); }
  esc(v){ return String(v==null?"":v).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;"); }
  players(){ return this._playersMeta.length?this._playersMeta.map(x=>x.entity_id):(this._hass?Object.keys(this._hass.states).filter(x=>x.startsWith("media_player.")).sort():[]); }
  platform(id){ var p=this._playersMeta.find(x=>x.entity_id===id); return p?p.platform:""; }
  rooms(){ return Array.isArray(this._config.rooms)?this._config.rooms.filter(r=>r&&typeof r.id==="string"&&r.id&&typeof r.name==="string"&&r.name.trim()):[]; }
  selectedRoom(){ return this.rooms().find(r=>r.id===this._roomId)||null; }
  player(){ var room=this.selectedRoom(); if(room&&room.player)return room.player; var s=this.shadowRoot&&this.shadowRoot.querySelector("#player"); return this._playerId||(s&&s.value)||this._config.default_player||this._config.entity||this.players()[0]||""; }
  roomSelect(){
    var rooms=this.rooms();if(!rooms.length)return "";
    var options='<option value="">Manual player</option>'+rooms.map(r=>'<option value="'+this.esc(r.id)+'" '+(r.id===this._roomId?'selected':'')+'>'+this.esc(r.name)+'</option>').join("");
    return '<label class="toolbar-room" title="Select room"><ha-icon icon="mdi:home-map-marker" aria-hidden="true"></ha-icon><select id="room" aria-label="Room">'+options+'</select></label>';
  }
  async chooseRoom(id){
    var room=this.rooms().find(r=>r.id===id)||null;
    this._roomId=room?room.id:"";
    if(room&&room.player)this._playerId=room.player;
    this._error="";
    this.removeRemotePortal();this.render();
    if(room&&room.player){
      try{await this.ensureDisplaySource(room.player);}
      catch(e){this._error="Could not activate room: "+(e.message||e);this.render();}
    }
  }
  volumeTarget(){
    var room=this.selectedRoom(),player=this.player();
    if(room&&room.player===player)return room.volume_entity||room.display||player;
    var route=this.displayRoute(player);
    return route&&route.display||player;
  }
  async volumeControl(action){
    var entity=this.volumeTarget(),state=this._hass&&this._hass.states&&this._hass.states[entity];
    if(!entity||!state||state.state==="unavailable"||state.state==="unknown"){
      this._error="The room's volume device is unavailable: "+(entity||"none");this.render();return;
    }
    try{
      if(action==="mute")await this._hass.callService("media_player","volume_mute",{is_volume_muted:!Boolean(state.attributes&&state.attributes.is_volume_muted)},{entity_id:entity});
      else if(action==="up"||action==="down")await this._hass.callService("media_player",action==="up"?"volume_up":"volume_down",{},{entity_id:entity});
    }catch(e){this._error="Volume control failed: "+(e.message||e);this.render();}
  }
  async toggleRoomPower(){
    var room=this.selectedRoom(),entity=room&&room.power_entity;
    if(!entity)return;
    var state=this._hass&&this._hass.states&&this._hass.states[entity];
    if(!state||state.state==="unavailable"||state.state==="unknown"){
      this._error="The room's power helper is unavailable: "+entity;this.render();return;
    }
    try{await this._hass.callService("homeassistant",state.state==="on"?"turn_off":"turn_on",{},{entity_id:entity});}
    catch(e){this._error="Power helper failed: "+(e.message||e);this.render();}
  }
  displayRoute(player){
  var room=this.selectedRoom();
  if(room&&room.player===player){
    return typeof room.display==="string"&&room.display.startsWith("media_player.")&&String(room.source||"").trim()?room:null;
  }
  var routes=Array.isArray(this._config.display_routes)?this._config.display_routes:[];
  return routes.find(r=>r&&r.player===player&&typeof r.display==="string"&&r.display.startsWith("media_player.")&&String(r.source||"").trim())||null;
}
async ensureDisplaySource(player){
  var room=this.selectedRoom();
  if(room&&room.player===player&&room.power_entity){
    var helper=room.power_entity,state=this._hass&&this._hass.states&&this._hass.states[helper];
    if(!state||state.state==="unavailable"||state.state==="unknown")throw new Error("Room power helper "+helper+" is unavailable.");
    if(state.state==="off"){
      await this._hass.callService("homeassistant","turn_on",{},{entity_id:helper});
      var boot=Math.max(0,Math.min(30000,Number(room.power_delay_ms??2000)||0));
      if(boot)await new Promise(resolve=>setTimeout(resolve,boot));
    }
  }
  var route=this.displayRoute(player);
  if(!route)return;
  var display=route.display,source=String(route.source).trim();
  if(!this._hass||!this._hass.states||!this._hass.states[display])throw new Error("Display "+display+" is not available in Home Assistant.");
  var state=this._hass.states[display];
  if(state.state==="unavailable"||state.state==="unknown")throw new Error("Display "+display+" is "+state.state+".");
  var pending=this._displayRoutePending;
  if(pending&&pending.player===player&&pending.display===display&&pending.source===source)return pending.promise;
  var task=(async()=>{
    if(state.state==="off"&&route.turn_on!==false){
      await this._hass.callService("media_player","turn_on",{},{entity_id:display});
      var wakeDelay=Math.max(0,Math.min(10000,Number(route.wake_delay_ms??2000)||0));
      if(wakeDelay)await new Promise(resolve=>setTimeout(resolve,wakeDelay));
    }
    if(((this._hass.states[display]||{}).attributes||{}).source===source)return;
    var recent=this._lastDisplaySwitch;
    if(recent&&recent.player===player&&recent.display===display&&recent.source===source&&Date.now()-recent.time<2000)return;
    await this._hass.callService("media_player","select_source",{source:source},{entity_id:display});
    this._lastDisplaySwitch={player,display,source,time:Date.now()};
    var settle=Math.max(0,Math.min(10000,Number(route.delay_ms??1000)||0));
    if(settle)await new Promise(resolve=>setTimeout(resolve,settle));
  })();
  this._displayRoutePending={player,display,source,promise:task};
  try{await task;}
  finally{if(this._displayRoutePending&&this._displayRoutePending.promise===task)this._displayRoutePending=null;}
}
async choosePlayer(player){
  this._playerId=player;
  var active=this.selectedRoom();
  if(!active||active.player!==player){var match=this.rooms().find(r=>r.player===player);this._roomId=match?match.id:"";}
  this.removeRemotePortal();this.render();
  try{await this.ensureDisplaySource(player);}
  catch(e){this._error="Could not switch TV input: "+(e.message||e);this.render();}
  finally{if(this._view==="details")this.render();}
}
  async loadHome(refresh=false,retry=false){
    if(!this._hass||this._loading)return;
    clearTimeout(this._homeRetryTimer);this._homeRetryTimer=null;
    if(!retry)this._homeRetryCount=0;
    this._loading=true;this._error="";this.render();
    var needsRetry=false;
    try{
      var r=await this.ws({type:"nuvio/home",refresh:refresh});
      var sections=r.sections||[],hero=(r.hero||{}).enabled===false?[]:((r.hero||{}).items||[]).slice(0,7);
      var empty=!sections.length&&!hero.length;
      needsRetry=r.retry===true||empty;
      // An empty refresh must not erase content that was already displayed.
      if(!empty){this._sections=sections;this._hero=hero;this._homePrefs=r.preferences||{};this._loaded=true;}
      this._heroIndex=Math.min(this._heroIndex,Math.max(0,this._hero.length-1));
      this._playersMeta=r.players||[];
      if(!this._playerId)this._playerId=this._config.default_player||this._config.entity||this.players()[0]||"";
    }catch(e){needsRetry=true;this._error=e.message||"Could not load Nuvio.";}
    this._loading=false;
    if(needsRetry&&(this._homeRetryCount||0)<3&&this.isConnected){
      this._homeRetryCount=(this._homeRetryCount||0)+1;
      var delay=[1500,3000,5000][this._homeRetryCount-1]||5000;
      this._homeRetryTimer=setTimeout(()=>{this._homeRetryTimer=null;this.loadHome(false,true);},delay);
    }else if(!needsRetry){this._homeRetryCount=0;}
    this.render();
  }
  async loadLazyCatalog(index){
    var section=this._sections[index];
    if(!section||section.kind!=="catalog"||section.lazy!==true||!section.manifest_url)return;
    var key=section.id||("catalog-"+index);
    if(this._lazyCatalogLoads.has(key))return;
    this._lazyCatalogLoads.add(key);
    try{
      var r=await this.ws({
        type:"nuvio/catalog",
        manifest_url:section.manifest_url,
        media_type:section.media_type||"movie",
        catalog_id:section.catalog_id,
        hide_unreleased:this._homePrefs.hide_unreleased_content===true
      });
      var current=this._sections[index];
      if(current&&current.id===section.id){
        var limit=this._homePrefs.layout==="modern"?15:24;
        current.items=(r.items||[]).slice(0,limit);
        current.lazy=false;
        current.load_error="";
      }
    }catch(e){
      var current=this._sections[index];
      if(current&&current.id===section.id){
        current.lazy=false;
        current.load_error=e.message||"Could not load this catalog.";
      }
    }finally{
      this._lazyCatalogLoads.delete(key);
      if(this._view==="home"&&this.isConnected)this.render();
    }
  }
  observeLazyCatalogs(){
    if(this._lazyObserver){this._lazyObserver.disconnect();this._lazyObserver=null;}
    if(this._view!=="home"||!this.shadowRoot)return;
    var nodes=[...this.shadowRoot.querySelectorAll("[data-lazy-catalog-index]")];
    if(!nodes.length)return;
    if(!window.IntersectionObserver){
      nodes.slice(0,2).forEach(node=>this.loadLazyCatalog(Number(node.dataset.lazyCatalogIndex)));
      return;
    }
    this._lazyObserver=new window.IntersectionObserver(entries=>{
      entries.forEach(entry=>{
        if(!entry.isIntersecting)return;
        this._lazyObserver?.unobserve(entry.target);
        this.loadLazyCatalog(Number(entry.target.dataset.lazyCatalogIndex));
      });
    },{root:null,rootMargin:"700px 0px",threshold:0.01});
    nodes.forEach(node=>this._lazyObserver.observe(node));
  }
  async search(){
    var q=this._query.trim(); if(!q){this._view="home";this.render();return;}
    this._view="search";this._loading=true;this._error="";this.render();
    try{var r=await this.ws({type:"nuvio/search",query:q});this._results=r.items||[];}
    catch(e){this._error=e.message||"Search failed.";}
    this._loading=false;this.render();
  }
  episodeForItem(item){
    var videos=(this._details&&this._details.videos)||[];
    if(!item||!videos.length)return null;
    if(item.video_id){
      var byId=videos.find(v=>String(v.id||"")===String(item.video_id));
      if(byId)return byId;
    }
    if(item.season!=null&&item.episode!=null){
      return videos.find(v=>Number(v.season)===Number(item.season)&&Number(v.episode)===Number(item.episode))||null;
    }
    return null;
  }
  async selectItem(item){
    this._returnView=this._view==="catalog"?"catalog":(this._view==="search"?"search":"home");
    this._item=item;this._details=null;this._season=item.season==null?null:Number(item.season);this._view="details";this._error="";this.render();
    var itemType=String(item.type||"movie").toLowerCase();
    if(!item.manifest_url){
      if(itemType==="movie"||itemType==="movies")await this.showSources(null,{backTo:this._returnView});
      return;
    }
    this._loading=true;this.render();
    try{
      this._details=await this.ws({type:"nuvio/details",manifest_url:item.manifest_url,media_type:item.type,content_id:item.id});
      var ss=this.seasons(); if(ss.length&&!ss.includes(this._season))this._season=ss[0];
    }catch(e){this._error=e.message||"Could not load title details.";}
    this._loading=false;
    var detail=this._details||item,videos=Array.isArray(detail.videos)?detail.videos:[];
    var detailType=String(detail.type||item.type||"movie").toLowerCase();
    if(!this._error&&(detailType==="movie"||detailType==="movies")&&!videos.length){
      await this.showSources(null,{backTo:this._returnView});
      return;
    }
    if(!this._error&&(detailType==="series"||detailType==="tv")&&item.video_id){
      var episode=this.episodeForItem(item)||{id:item.video_id,season:item.season,episode:item.episode,title:item.episode_title||item.name};
      await this.showSources(episode,{backTo:"details"});
      return;
    }
    this.render();
  }
  catalogChunkSize(){
    var mobile=typeof window!=="undefined"&&window.matchMedia&&window.matchMedia("(max-width:700px)").matches;
    var cols=mobile?3:Math.max(1,Number(this._config.columns)||6);
    return Math.max(12,cols*4);
  }
  mergeCatalogItems(existing,incoming){
    var items=Array.isArray(existing)?existing.slice():[];
    var seen=new Set(items.map(x=>String(x.type||"")+":"+String(x.id||"")));
    var added=0;
    for(var item of (incoming||[])){
      var key=String(item.type||"")+":"+String(item.id||"");
      if(seen.has(key))continue;
      seen.add(key);items.push(item);added++;
    }
    return {items,added};
  }
  updatePagingState(state,result,added){
    if(!state)return;
    var raw=Math.max(0,Number(result&&result.raw_count)||0);
    var next=Math.max(0,Number(result&&result.next_skip)||0);
    state.duplicatePages=added===0&&raw>0?(state.duplicatePages||0)+1:0;
    state.nextSkip=next>(state.nextSkip||0)?next:(raw>0?(state.nextSkip||0)+raw:(state.nextSkip||0));
    state.hasMore=!!(result&&result.has_more)&&raw>0&&state.duplicatePages<3;
  }
  collectionItems(index=this._collectionTab){
    var tabs=index<0?(this._collectionTabs||[]):[(this._collectionTabs||[])[index]].filter(Boolean);
    var seen=new Set(),items=[];
    for(var n=0;n<Math.max(0,...tabs.map(t=>t.items.length));n++)for(var tab of tabs){
      var item=tab.items[n];if(!item)continue;
      var key=String(item.type||"")+":"+String(item.id||"");
      if(!seen.has(key)){seen.add(key);items.push(item);}
    }
    return items;
  }
  activeCollectionTabs(){
    if(!this._collectionTabs)return [];
    return this._collectionTab<0?this._collectionTabs:[this._collectionTabs[this._collectionTab]].filter(Boolean);
  }
  catalogCanGrow(){
    if(this._catalogVisibleCount<this._catalogItems.length)return true;
    if(this._collectionTabs)return this.activeCollectionTabs().some(t=>t&&t.hasMore);
    return !!(this._catalogPaging&&this._catalogPaging.hasMore);
  }
  async openCollection(folder,section){
    if(!folder)return;
    this._catalogReload=()=>this.openCollection(folder,section);
    var request=(this._catalogRequest||0)+1;this._catalogRequest=request;
    this._catalogSection={kind:"collection",name:folder.name,show_all_tab:section.show_all_tab};
    this._catalogItems=[];this._collectionTabs=[];this._collectionTab=section.show_all_tab===false?0:-1;
    this._catalogPaging=null;this._catalogVisibleCount=0;this._catalogLoadingMore=false;this._catalogLoadError="";this._resetCatalogScroll=true;
    this._catalogLoading=true;this._view="catalog";this._error="";this.render();
    var sources=Array.isArray(folder.sources)?folder.sources:[];
    var tabs=await Promise.all(sources.map(async source=>{
      var type=source.type||source.apiType||source.api_type||"movie";
      var tab={name:source.title||source.catalogName||source.catalog_name||this.homeTypeLabel(type),items:[],error:"",hasMore:false,nextSkip:0,duplicatePages:0,request:null};
      try{
        if(source.provider&&source.provider!=="addon")throw new Error("This folder source is not an addon catalog.");
        var base=source.addonBaseUrl||source.addon_base_url||source.baseUrl||source.base_url||source.addonUrl||source.url||"";
        var manifest=base?(base.replace(/\/+$/,"").endsWith("manifest.json")?base:base.replace(/\/+$/,"")+"/manifest.json"):"";
        tab.request={type:"nuvio/catalog",manifest_url:manifest,addon_id:source.addonId||source.addon_id||"",media_type:type,catalog_id:source.catalogId||source.catalog_id||"",genre:source.genre||"",hide_unreleased:this._homePrefs.hide_unreleased_content===true};
        var result=await this.ws(tab.request);
        tab.items=result.items||[];
        tab.nextSkip=Math.max(0,Number(result.next_skip)||0);
        tab.hasMore=!!result.has_more;
      }catch(e){tab.error=e.message||"Could not load this catalog.";}
      return tab;
    }));
    if(request!==this._catalogRequest)return;
    this._collectionTabs=tabs;this._catalogItems=this.collectionItems(this._collectionTab);
    this._catalogVisibleCount=Math.min(this.catalogChunkSize(),this._catalogItems.length);
    this._catalogLoading=false;
    if(!sources.length)this._error="This folder has no saved catalog sources.";
    else this._error=tabs.filter(t=>t.error).map(t=>t.name+": "+t.error).join(" · ");
    this.render();
  }
  selectCollectionTab(index){
    this._collectionTab=index;
    this._catalogItems=this.collectionItems(index);
    this._catalogVisibleCount=Math.min(this.catalogChunkSize(),this._catalogItems.length);
    this._catalogLoadError="";
    this._resetCatalogScroll=true;
    var tabs=this.activeCollectionTabs();
    if(tabs.length)this._error=tabs.filter(t=>t.error).map(t=>t.name+": "+t.error).join(" · ");
    this.render();
  }
  async openCatalog(section){
    if(!section||section.kind!=="catalog")return;
    this._catalogReload=()=>this.openCatalog(section);
    this._catalogRequest=(this._catalogRequest||0)+1;var request=this._catalogRequest;
    this._collectionTabs=null;this._catalogSection=section;this._catalogPaging=null;
    this._catalogItems=Array.isArray(section.items)?section.items.slice():[];
    this._catalogVisibleCount=Math.min(this.catalogChunkSize(),this._catalogItems.length);
    this._catalogLoadingMore=false;this._catalogLoadError="";this._resetCatalogScroll=true;
    this._catalogLoading=true;this._view="catalog";this._error="";this.render();
    try{
      if(!section.manifest_url)throw new Error("This catalog is missing its addon reference. Refresh the card once after updating Nuvio.");
      var payload={
        type:"nuvio/catalog",
        manifest_url:section.manifest_url,
        media_type:section.media_type||"movie",
        catalog_id:section.catalog_id,
        hide_unreleased:this._homePrefs.hide_unreleased_content===true
      };
      var result=await this.ws(payload);
      if(request!==this._catalogRequest)return;
      var merged=this.mergeCatalogItems([],result.items||[]);
      this._catalogItems=merged.items;
      this._catalogPaging={request:payload,nextSkip:Math.max(0,Number(result.next_skip)||0),hasMore:!!result.has_more,duplicatePages:0};
      this._catalogVisibleCount=Math.min(this.catalogChunkSize(),this._catalogItems.length);
      if(section.lazy===true){
        var limit=this._homePrefs.layout==="modern"?15:24;
        section.items=this._catalogItems.slice(0,limit);
        section.lazy=false;section.load_error="";
      }
    }catch(e){
      if(request!==this._catalogRequest)return;
      this._error=e.message||"Could not open this catalog.";
    }
    this._catalogLoading=false;this.render();
  }
  wireCatalogCards(root=this.shadowRoot){
    if(!root)return;
    root.querySelectorAll(".pc[data-source=\"catalog\"]").forEach(b=>{
      if(b.dataset.nuvioWired==="1")return;
      b.dataset.nuvioWired="1";
      b.addEventListener("click",()=>{
        var item=this._catalogItems[Number(b.dataset.index)];
        if(item)this.selectItem(item);
      });
    });
  }
  refreshCatalogGrid(){
    if(this._view!=="catalog"||!this.shadowRoot)return;
    var scroller=this.shadowRoot.querySelector(".catalog-scroll");
    if(!scroller)return;
    this._catalogScrollTop=scroller.scrollTop;

    var cols=Number(this._config.columns)||6;
    var visibleCount=Math.max(0,this._catalogVisibleCount||this.catalogChunkSize());
    var visible=this._catalogItems.slice(0,visibleCount);
    var grid=scroller.querySelector(".catalog-grid");
    var empty=scroller.querySelector(".catalog-empty");
    if(visible.length){
      if(!grid){
        grid=document.createElement("div");
        grid.className="grid catalog-grid";
        scroller.prepend(grid);
      }
      grid.setAttribute("style","--cols:"+cols);

      // Never replace already-rendered poster nodes while scrolling. Replacing
      // grid.innerHTML removes the browser/WebView scroll anchor and can jump
      // the internal catalog scroller back to the beginning.
      var rendered=grid.querySelectorAll(".pc[data-source=\"catalog\"]").length;
      if(rendered<visible.length){
        var html=visible.slice(rendered).map((x,n)=>this.card(x,"catalog",rendered+n)).join("");
        grid.insertAdjacentHTML("beforeend",html);
      }
      if(empty)empty.remove();
      this.wireCatalogCards(grid);
    }else{
      if(grid)grid.remove();
      if(!empty){
        empty=document.createElement("div");
        empty.className="status catalog-empty";
        scroller.prepend(empty);
      }
      empty.textContent=this._catalogLoading?"Loading catalog…":"No titles were returned by this catalog.";
    }

    var sentinel=scroller.querySelector(".catalog-sentinel");
    if(this.catalogCanGrow()){
      if(!sentinel){
        sentinel=document.createElement("div");
        sentinel.className="catalog-sentinel";
        sentinel.setAttribute("aria-hidden","true");
        scroller.append(sentinel);
      }
      sentinel.innerHTML=this._catalogLoadingMore?"<span>Loading more…</span>":(this._catalogLoadError?"<span>"+this.esc(this._catalogLoadError)+"</span>":"");
    }else if(sentinel){
      sentinel.remove();
    }

    // Keep the exact position even if images in newly appended rows resolve
    // immediately after insertion.
    scroller.scrollTop=this._catalogScrollTop;
    this.observeCatalogScroll();
  }
  async loadMoreCatalog(){
    if(this._view!=="catalog"||this._catalogLoading||this._catalogLoadingMore)return;
    var chunk=this.catalogChunkSize();
    this._catalogLoadError="";
    if(this._catalogVisibleCount<this._catalogItems.length){
      this._catalogVisibleCount=Math.min(this._catalogItems.length,this._catalogVisibleCount+chunk);
      this.refreshCatalogGrid();
      return;
    }

    this._catalogLoadingMore=true;
    this.refreshCatalogGrid();
    var requestId=this._catalogRequest;
    try{
      if(this._collectionTabs){
        var tabs=this.activeCollectionTabs().filter(t=>t&&t.hasMore&&t.request);
        if(!tabs.length){
          this._catalogLoadingMore=false;
          this.refreshCatalogGrid();
          return;
        }
        await Promise.all(tabs.map(async tab=>{
          try{
            var result=await this.ws({...tab.request,skip:tab.nextSkip||0});
            if(requestId!==this._catalogRequest)return;
            var merged=this.mergeCatalogItems(tab.items,result.items||[]);
            tab.items=merged.items;
            this.updatePagingState(tab,result,merged.added);
          }catch(e){
            tab.error=e.message||"Could not load more titles.";
            tab.hasMore=false;
          }
        }));
        if(requestId!==this._catalogRequest)return;
        var combined=this.collectionItems(this._collectionTab);
        this._catalogItems=this.mergeCatalogItems(this._catalogItems,combined).items;
        this._catalogVisibleCount=Math.min(this._catalogItems.length,this._catalogVisibleCount+chunk);
        var active=this.activeCollectionTabs();
        this._catalogLoadError=active.filter(t=>t.error).map(t=>t.name+": "+t.error).join(" · ");
      }else if(this._catalogPaging&&this._catalogPaging.hasMore){
        var result=await this.ws({...this._catalogPaging.request,skip:this._catalogPaging.nextSkip||0});
        if(requestId!==this._catalogRequest)return;
        var merged=this.mergeCatalogItems(this._catalogItems,result.items||[]);
        this._catalogItems=merged.items;
        this.updatePagingState(this._catalogPaging,result,merged.added);
        this._catalogVisibleCount=Math.min(this._catalogItems.length,this._catalogVisibleCount+chunk);
      }
    }catch(e){
      if(requestId===this._catalogRequest)this._catalogLoadError=e.message||"Could not load more titles.";
    }finally{
      if(requestId===this._catalogRequest){
        this._catalogLoadingMore=false;
        this.refreshCatalogGrid();
      }
    }
  }
  observeCatalogScroll(){
    if(this._catalogObserver){this._catalogObserver.disconnect();this._catalogObserver=null;}
    if(this._view!=="catalog"||!this.shadowRoot||!this.catalogCanGrow())return;
    var scroller=this.shadowRoot.querySelector(".catalog-scroll");
    var sentinel=this.shadowRoot.querySelector(".catalog-sentinel");
    if(!scroller||!sentinel)return;
    if(scroller.dataset.nuvioScrollTrack!=="1"){
      scroller.dataset.nuvioScrollTrack="1";
      scroller.addEventListener("scroll",()=>{this._catalogScrollTop=scroller.scrollTop;},{passive:true});
    }
    if(!window.IntersectionObserver){
      scroller.addEventListener("scroll",()=>{
        if(scroller.scrollHeight-scroller.scrollTop-scroller.clientHeight<500)this.loadMoreCatalog();
      },{passive:true});
      if(scroller.scrollHeight<=scroller.clientHeight+500)this.loadMoreCatalog();
      return;
    }
    this._catalogObserver=new window.IntersectionObserver(entries=>{
      if(entries.some(entry=>entry.isIntersecting))this.loadMoreCatalog();
    },{root:scroller,rootMargin:"500px 0px",threshold:0.01});
    this._catalogObserver.observe(sentinel);
  }
  catalogView(){
    var s=this._catalogSection||{},cols=Number(this._config.columns)||6;
    var title=this.homeRowTitle(s)||s.name||"Catalog";
    var addon=s.addon?' <small>· '+this.esc(s.addon)+'</small>':"";
    var tabs=this._collectionTabs&&this._collectionTabs.length?'<div class="collection-tabs" role="group" aria-label="Catalog sources">'+(s.show_all_tab!==false&&this._collectionTabs.length>1?'<button class="action collection-tab '+(this._collectionTab<0?'primary':'')+'" data-tab="-1">All</button>':'')+this._collectionTabs.map((t,n)=>'<button class="action collection-tab '+(this._collectionTab===n?'primary':'')+'" data-tab="'+n+'">'+this.esc(t.name)+'</button>').join("")+'</div>':"";
    var visible=this._catalogItems.slice(0,Math.max(0,this._catalogVisibleCount||this.catalogChunkSize()));
    var content=this._catalogLoading&&!visible.length
      ? '<div class="status">Loading catalog…</div>'
      : (visible.length
          ? '<div class="grid catalog-grid" style="--cols:'+cols+'">'+visible.map((x,i)=>this.card(x,"catalog",i)).join("")+'</div>'
          : '<div class="status">No titles were returned by this catalog.</div>');
    var more=this.catalogCanGrow()?'<div class="catalog-sentinel" aria-hidden="true">'+(this._catalogLoadingMore?'<span>Loading more…</span>':'')+'</div>':"";
    return '<div class="catalog-view"><div class="catalog-fixed"><div class="top catalog-top"><button class="back" id="back">← Home</button><h3>'+this.esc(title)+addon+'</h3></div>'+tabs+'</div><div class="catalog-scroll">'+content+more+'</div></div>';
  }
  seasons(){var v=(this._details&&this._details.videos)||[];return [...new Set(v.map(x=>Number(x.season)).filter(Number.isFinite))].sort((a,b)=>a-b);}
  playData(ep){
    var i=this._item,d=this._details||i,o={media_type:i.type,content_id:i.id,title:d.name||i.name||i.id};
    var vid=(ep&&ep.id)||i.video_id;if(vid)o.video_id=vid;
    if(d.poster||i.poster)o.poster=d.poster||i.poster;if(d.background||i.background)o.backdrop=d.background||i.background;if(d.logo||i.logo)o.logo=d.logo||i.logo;
    var s=ep?ep.season:i.season,e=ep?ep.episode:i.episode;if(s!=null)o.season=Number(s);if(e!=null)o.episode=Number(e);if(ep&&ep.title)o.episode_title=ep.title;return o;
  }
  async play(openOnly,ep){
    var p=this.player();if(!p){this._error="Select a media player first.";this.render();return;}
    try{
      await this.ensureDisplaySource(p);
      if(openOnly)await this._hass.callService("nuvio","open",{media_type:this._item.type,content_id:this._item.id},{entity_id:p});
      else await this._hass.callService("nuvio","play",this.playData(ep),{entity_id:p});
    }catch(e){this._error=e.message||"Nuvio playback failed.";this.render();}
  }
  streamVideoId(ep){
    if(ep&&ep.id)return ep.id;
    if(this._item&&this._item.video_id)return this._item.video_id;
    if(this._item&&this._item.type==="series"){
      var s=ep?ep.season:this._item.season,e=ep?ep.episode:this._item.episode;
      if(s!=null&&e!=null)return this._item.id+":"+s+":"+e;
    }
    return this._item?this._item.id:"";
  }
  async showSources(ep=null,options={}){
    var videoId=this.streamVideoId(ep);
    if(!videoId){this._error="No video ID is available for this title.";this.render();return;}
    this._sourcesBackView=options.backTo||"details";
    this._streamContext=ep;
    this._addonFilter="all";
    this._view="sources";
    this._error="";
    await this.loadSources({reset:true});
  }
  async refreshSources(){
    await this.loadSources({reset:true});
  }
  async loadSources({reset=true}={}){
    var videoId=this.streamVideoId(this._streamContext);
    if(!videoId){this._error="No video ID is available for this title.";this.render();return;}
    var request=(this._sourceRequest||0)+1;
    this._sourceRequest=request;
    if(reset){
      this._streams=[];
      this._watchProviders=[];
      this._watchProviderMeta={configured:false};
      this._watchProvidersLoading=false;
      this._debridMeta={configured:false,provider:""};
      this._addonFilter="all";
    }
    this._streamLoading=true;
    this._streamLoadingStage="watchhub";
    this._error="";
    this.render();
    var providerPromise=this.loadWatchProviders(request);
    var errors=[];
    try{
      var watchhub=await this.ws({
        type:"nuvio/streams",
        media_type:this._item.type,
        video_id:videoId,
        addon_scope:"watchhub"
      });
      if(request!==this._sourceRequest)return;
      this._streams=watchhub.streams||[];
      this._debridMeta=watchhub.debrid||this._debridMeta;
    }catch(e){
      if(request!==this._sourceRequest)return;
      errors.push("WatchHub: "+(e.message||"Could not load sources."));
    }

    if(request!==this._sourceRequest)return;
    this._streamLoadingStage="other";
    this.render();

    try{
      var other=await this.ws({
        type:"nuvio/streams",
        media_type:this._item.type,
        video_id:videoId,
        addon_scope:"other"
      });
      if(request!==this._sourceRequest)return;
      this._streams=this._streams.concat(other.streams||[]);
      this._debridMeta=other.debrid||this._debridMeta;
    }catch(e){
      if(request!==this._sourceRequest)return;
      errors.push("Other addons: "+(e.message||"Could not load sources."));
    }

    if(request!==this._sourceRequest)return;
    this._streamLoading=false;
    this._streamLoadingStage="";
    this._error=errors.join(" · ");
    this.render();
    await providerPromise;
  }
  async loadWatchProviders(request){
    var ep=this._streamContext||{};
    this._watchProvidersLoading=true;
    try{
      var payload={
        type:"nuvio/watch_providers",
        media_type:this._item.type,
        content_id:this._item.id,
        title:(this._details&&this._details.name)||this._item.name||""
      };
      var season=ep.season==null?this._item.season:ep.season;
      var episode=ep.episode==null?this._item.episode:ep.episode;
      if(season!=null)payload.season=Number(season);
      if(episode!=null)payload.episode=Number(episode);
      var result=await this.ws(payload);
      if(request!==this._sourceRequest)return;
      this._watchProviderMeta=result||{configured:false};
      this._watchProviders=(result&&result.providers)||[];
    }catch(e){
      if(request!==this._sourceRequest)return;
      this._watchProviderMeta={configured:true,error:e.message||"Could not load streaming availability."};
      this._watchProviders=[];
    }finally{
      if(request===this._sourceRequest){
        this._watchProvidersLoading=false;
        this.render();
      }
    }
  }
  async playWatchProvider(provider){
    if(!provider)return;
    if(provider.deep_link){
      var linkSource=String(provider.deep_link_source||"");
      await this.playProviderSource({
        external_url:provider.deep_link,
        name:provider.name||provider.justwatch_provider_name||provider.tvdb_source_name||"",
        title:provider.name||"",
        addon:linkSource==="justwatch"?"JustWatch":(linkSource==="thetvdb"?"TheTVDB":"Provider")
      });
      return;
    }
    if(!(this._watchProviderMeta||{}).justwatch_authenticated){
      var index=this.watchHubSourceIndex(provider);
      if(index>=0){
        await this.playInNuvioIndex(index);
        return;
      }
    }
    this._error=(this._watchProviderMeta||{}).justwatch_authenticated
      ? (provider.name||"This provider")+" is available, but your JustWatch account did not return a usable provider link."
      : (provider.name||"This provider")+" is available for the configured country, but JustWatch, TheTVDB, and WatchHub did not supply a usable provider link.";
    this.render();
  }
  watchHubSourceIndex(provider){
    var key=String((provider||{}).provider_key||"");
    if(!key)return -1;
    return this._streams.findIndex(s=>
      !!s.external_url&&
      String(s.provider_key||"")===key&&
      String(s.addon||"").toLowerCase().includes("watchhub")
    );
  }
  watchProviderRow(){
    var meta=this._watchProviderMeta||{};
    if(!meta.configured&&!this._watchProvidersLoading)return "";
    var providers=this._watchProviders||[];
    if(!providers.length&&!this._watchProvidersLoading)return "";
    var region=meta.region||"";
    var scope=meta.scope==="season"
      ? "Season availability"
      : "Movie availability";
    var cards=providers.map((provider,providerIndex)=>{
      var watchhubIndex=this.watchHubSourceIndex(provider);
      var accountAuthoritative=!!meta.justwatch_authenticated;
      var exact=!!provider.deep_link;
      var playable=exact||(!accountAuthoritative&&watchhubIndex>=0);
      var access=(provider.access||[]).join(" · ");
      var deepSource=String(provider.deep_link_source||"");
      var source=exact
        ? (deepSource==="justwatch"
            ? (provider.justwatch_authenticated?"JustWatch account":"JustWatch offer")
            : (deepSource==="thetvdb"?"TheTVDB exact link":"Provider link"))
        : (!accountAuthoritative&&watchhubIndex>=0?"WatchHub link":"Availability only");
      var hint=playable
        ? "Play with "+provider.name+" · "+source
        : accountAuthoritative
          ? provider.name+" is available here, but your JustWatch account did not return a usable provider link."
          : provider.name+" is available here, but no usable provider link was returned.";
      var logo=provider.logo_url
        ? '<img src="'+this.esc(provider.logo_url)+'" alt="">'
        : '<div class="watch-provider-fallback">'+this.esc(String(provider.name||"?").slice(0,2).toUpperCase())+'</div>';
      return '<button class="watch-provider '+(playable?"linked":"availability-only")+'"'+
        (playable?' data-watch-provider-index="'+providerIndex+'"':" disabled")+
        ' title="'+this.esc(hint)+'">'+
          logo+
          '<span class="watch-provider-name">'+this.esc(provider.name)+'</span>'+
          (access?'<span class="watch-provider-access">'+this.esc(access)+'</span>':"")+
          (playable?'<span class="watch-provider-link-source">'+this.esc(source)+'</span>':"")+
        '</button>';
    }).join("");
    return '<section class="watch-provider-section">'+
      '<div class="watch-provider-heading"><div><h3>Available on</h3><span>'+this.esc(scope)+(region?" · "+this.esc(region):"")+'</span></div></div>'+
      '<div class="watch-provider-rail">'+
        (this._watchProvidersLoading?'<div class="watch-provider-loading">Loading availability…</div>':"")+
        cards+
      '</div>'+
      (meta.attribution?'<div class="watch-provider-attribution">'+this.esc(meta.attribution)+'</div>':"")+
    '</section>';
  }
  sourceAddonNames(){
    var names=[];
    this._streams.forEach(s=>{
      var name=String(s.addon||"Unknown addon");
      if(!names.includes(name))names.push(name);
    });
    return names;
  }
  filteredSourceEntries(){
    var names=this.sourceAddonNames();
    if(this._addonFilter!=="all"&&!names.includes(this._addonFilter))this._addonFilter="all";
    return this._streams
      .map((stream,index)=>({stream,index}))
      .filter(entry=>this._addonFilter==="all"||String(entry.stream.addon||"Unknown addon")===this._addonFilter);
  }
  toggleAddonFilter(){
    this._addonFilterExpanded=!this._addonFilterExpanded;
    this.render();
  }
  setAddonFilter(name){
    this._addonFilter=String(name||"all");
    this.render();
  }
  sourceFilterBar(){
    if(!this._addonFilterExpanded)return "";
    var names=this.sourceAddonNames();
    var chip=(name,label)=>'<button class="source-filter-chip '+(this._addonFilter===name?"active":"")+'" data-addon-filter="'+this.esc(name)+'" aria-pressed="'+(this._addonFilter===name?"true":"false")+'">'+this.esc(label)+'</button>';
    return '<div class="source-filter-bar" role="group" aria-label="Source addons">'+
      chip("all","All")+
      names.map(name=>chip(name,name)).join("")+
    '</div>';
  }
  inferMime(url,filename,declared){
    var d=String(declared||"").trim().toLowerCase();
    if(d&&d.includes("/")&&d!=="video/*"&&d!=="application/octet-stream")return d;
    var u=(String(filename||"")+" "+String(url||"")).toLowerCase();
    if(u.includes(".m3u8")||u.includes("m3u8"))return "application/vnd.apple.mpegurl";
    if(u.includes(".mpd"))return "application/dash+xml";
    if(u.includes(".mkv"))return "video/x-matroska";
    if(u.includes(".webm"))return "video/webm";
    if(u.includes(".mov"))return "video/quicktime";
    if(u.includes(".m2ts")||u.includes(".ts"))return "video/mp2t";
    if(u.includes(".mp4")||u.includes(".m4v"))return "video/mp4";
    return d||"video/*";
  }
  formatBytes(value){
    var n=Number(value||0);if(!Number.isFinite(n)||n<=0)return "";
    var units=["B","KB","MB","GB","TB"],i=0;
    while(n>=1024&&i<units.length-1){n/=1024;i++;}
    return (i>=3?n.toFixed(1):Math.round(n))+ " "+units[i];
  }
  async resolveSource(index,renderAfter=true){
    var s=this._streams[index];if(!s||this._resolving.has(index))return null;
    if(!this._debridMeta.configured){
      this._error="Configure your debrid provider and API key in Settings → Devices & services → Nuvio → Reconfigure.";
      this.render();return null;
    }
    this._resolving.add(index);this._error="";this.render();
    try{
      var ep=this._streamContext||{};
      var payload={
        type:"nuvio/resolve_stream",
        info_hash:s.info_hash||undefined,
        magnet_uri:s.magnet_uri||undefined,
        torrent_sources:s.torrent_sources||[],
        file_idx:s.file_idx==null?undefined:Number(s.file_idx),
        filename:s.filename||undefined,
        resolve_filename:s.resolve_filename||undefined,
        torrent_name:s.torrent_name||undefined,
        resolver_service:s.resolver_service||undefined,
        season:ep.season==null?(s.resolve_season==null?undefined:Number(s.resolve_season)):Number(ep.season),
        episode:ep.episode==null?(s.resolve_episode==null?undefined:Number(s.resolve_episode)):Number(ep.episode)
      };
      Object.keys(payload).forEach(k=>payload[k]===undefined&&delete payload[k]);
      var result=await this.ws(payload);
      s.url=result.url;s.direct=true;s.requires_headers=false;
      if(result.filename)s.filename=result.filename;
      if(result.video_size){
        s.size_bytes=result.video_size;s.size_label=this.formatBytes(result.video_size);
        s.badges=s.badges||[];
        if(!s.badges.some(b=>b.kind==="size"))s.badges.push({kind:"size",label:s.size_label});
      }
      s.resolved_provider=result.provider||this._debridMeta.provider||"";
      return s;
    }catch(e){
      this._error=e.message||"Could not resolve this debrid source.";
    }finally{
      this._resolving.delete(index);if(renderAfter)this.render();
    }
    return null;
  }
  async resolveVisibleSources(){
    if(!this._debridMeta.configured){
      this._error="Configure your debrid provider and API key in Settings → Devices & services → Nuvio → Reconfigure.";
      this.render();return;
    }
    var candidates=this.filteredSourceEntries().map(x=>({s:x.stream,i:x.index})).filter(x=>!x.s.direct&&x.s.resolvable&&!x.s.requires_headers&&(x.s.info_hash||x.s.magnet_uri)).slice(0,6);
    for(var item of candidates)await this.resolveSource(item.i);
  }
  sourcePlaybackData(stream,inNuvio=false){
    var ep=this._streamContext||null;
    var data=this.playData(ep);
    data.stream_url=stream.url;
    data.stream_title=stream.name||stream.title||stream.description||data.title||"Nuvio stream";
    data.mime_type=this.inferMime(stream.url,stream.filename,stream.mime_type||stream.source_type);
    data.in_nuvio=!!inNuvio;
    if(stream.filename)data.filename=stream.filename;
    var videoSize=Number(stream.size_bytes);if(Number.isFinite(videoSize)&&videoSize>0)data.video_size=Math.round(videoSize);
    if(stream.addon)data.addon_name=stream.addon;
    if(stream.addon_logo)data.addon_logo=stream.addon_logo;
    if(stream.description)data.stream_description=stream.description;
    if(stream.info_hash)data.info_hash=stream.info_hash;
    if(stream.file_idx!=null)data.file_idx=Number(stream.file_idx);
    return data;
  }
  async playSource(stream,inNuvio=false){
    var p=this.player();if(!p){this._error="Select a media player first.";this.render();return;}
    if(!stream||!stream.url){this._error="This source does not have a playable URL yet.";this.render();return;}
    try{
      await this.ensureDisplaySource(p);
      await this._hass.callService(
        "nuvio",
        "play_source",
        this.sourcePlaybackData(stream,inNuvio),
        {entity_id:p}
      );
    }catch(e){this._error=e.message||(inNuvio?"Nuvio internal playback failed.":"Direct source playback failed.");this.render();}
  }
  async playProviderSource(stream){
    var p=this.player();if(!p){this._error="Select a media player first.";this.render();return;}
    if(!stream||!stream.external_url){this._error="This streaming source does not include a provider link.";this.render();return;}
    var context=this.playData(this._streamContext||null);
    try{
      await this.ensureDisplaySource(p);
      await this._hass.callService(
        "nuvio",
        "play_provider",
        {
          external_url:stream.external_url,
          provider_name:stream.name||stream.title||stream.addon||"",
          media_type:context.media_type,
          title:context.title,
          content_id:context.content_id,
          video_id:context.video_id,
          season:context.season,
          episode:context.episode,
          episode_title:context.episode_title
        },
        {entity_id:p}
      );
    }catch(e){
      this._error=e.message||"Could not open this title in the streaming app.";
      this.render();
    }
  }
  async playInNuvioIndex(index){
    var s=this._streams[index];if(!s)return;
    if(s.external_url){await this.playProviderSource(s);return;}
    if(s.direct&&s.url){await this.playSource(s,true);return;}
    if(s.resolvable){
      var resolved=await this.resolveSource(index,false);
      if(resolved&&resolved.url){await this.playSource(resolved,true);return;}
      return;
    }
    // No exact URL is available: do NOT substitute a title-open command for Play.
    this._error=s.requires_headers
      ? "This source requires HTTP headers that cannot currently be passed to Nuvio. Choose another source."
      : "This addon did not supply a playable stream URL for this selection. Choose a direct link or configure a supported debrid resolver; opening the title would not play the selected source.";
    this.render();
  }
  async playDirectIndex(index){
    var s=this._streams[index];if(!s)return;
    if(s.direct&&s.url){await this.playSource(s);return;}
    if(!s.resolvable){
      this._error="This source cannot be resolved directly with the debrid providers synced to your Nuvio account.";
      this.render();return;
    }
    var resolved=await this.resolveSource(index,false);
    if(resolved&&resolved.url)await this.playSource(resolved);
  }
  poster(i,preferLandscape=false){
    var u=(preferLandscape&&(i.episode_thumbnail||i.landscapePoster||i.background))||i.poster||i.background;
    return u?'<img loading="lazy" src="'+this.esc(u)+'" alt="">':'<div class="ph"><ha-icon icon="mdi:movie-open"></ha-icon></div>';
  }
  homeTypeLabel(type){
    var t=String(type||"movie").trim().toLowerCase();
    if(t==="movie"||t==="movies")return "Movie";
    if(t==="series"||t==="tv"||t==="shows")return "Series";
    if(t==="channel"||t==="channels"||t==="live"||t==="tvchannel"||t==="tvchannels")return "Channels";
    if(t==="anime")return "Anime";
    return t?t.charAt(0).toUpperCase()+t.slice(1):"Movie";
  }
  homeRowTitle(section){
    var raw=String(section&&section.name||"").trim();
    if(!section||section.kind!=="catalog")return raw;
    var base=raw?raw.charAt(0).toUpperCase()+raw.slice(1):"";
    var typeLabel=this.homeTypeLabel(section.media_type);
    if(!base)return typeLabel;
    if(this._homePrefs.show_catalog_type_suffix===false)return base;
    var rawType=String(section.media_type||"movie").trim();
    var rawLabel=rawType?rawType.charAt(0).toUpperCase()+rawType.slice(1):"Movie";
    var lower=base.toLowerCase();
    if(lower.endsWith(typeLabel.toLowerCase())||lower.endsWith(rawLabel.toLowerCase()))return base;
    return base+" - "+typeLabel;
  }
  card(i,source,index,options={}){
    var progress=i.duration>0?Math.min(100,Math.max(0,(i.position/i.duration)*100)):0;
    var ep=(i.season!=null&&i.episode!=null)?'<span>S'+this.esc(i.season)+' E'+this.esc(i.episode)+'</span>':"";
    var showLabels=options.showLabels!==false;
    var preferLandscape=!!options.preferLandscape;
    var labelHtml=showLabels?'<div class="pt">'+this.esc(i.name)+'</div><div class="meta">'+this.esc(i.releaseInfo||"")+ep+'</div>':"";
    return '<button class="pc '+(preferLandscape?"landscape-card":"")+'" data-source="'+source+'" data-index="'+index+'"><div class="poster">'+this.poster(i,preferLandscape)+(progress?'<div class="prog"><i style="width:'+progress+'%"></i></div>':"")+'</div>'+labelHtml+'</button>';
  }
  collectionCard(i,sectionIndex,index){
    var shape=String(i.posterShape||"SQUARE").toUpperCase();
    var image=i.poster?'<img loading="lazy" src="'+this.esc(i.poster)+'" alt="">':(i.cover_emoji?'<div class="collection-emoji">'+this.esc(i.cover_emoji)+'</div>':'<div class="collection-emoji">'+this.esc(String(i.name||"").slice(0,2).toUpperCase())+'</div>');
    var title=i.hide_title?"":'<div class="collection-title">'+this.esc(i.name)+'</div>';
    return '<button type="button" aria-label="'+this.esc(i.name)+'" data-section-index="'+sectionIndex+'" data-folder-index="'+index+'" class="collection-card shape-'+this.esc(shape.toLowerCase())+'"><div class="collection-art">'+image+title+'</div></button>';
  }
  hero(){
    if(this._homePrefs.hero_section_enabled===false||!this._hero.length)return "";
    var i=this._hero[this._heroIndex]||this._hero[0],bg=i.background||i.landscapePoster||i.poster||"";
    var meta=[i.releaseInfo||"",i.runtime||""].filter(Boolean).join(" · ");
    var genres=(i.genres||[]).slice(0,3).join(" · ");
    var logo=i.logo?'<img class="home-hero-logo" src="'+this.esc(i.logo)+'" alt="'+this.esc(i.name||"")+'">':'<h2>'+this.esc(i.name||"")+'</h2>';
    var start=Math.max(0,Math.min(this._heroIndex-3,this._hero.length-7));
    var dots=this._hero.length>1?'<div class="home-hero-nav"><button class="hero-arrow" data-hero-step="-1" aria-label="Previous featured title">‹</button><div class="home-hero-dots">'+this._hero.slice(start,start+7).map((_,n)=>{n+=start;return '<button class="home-hero-dot '+(n===this._heroIndex?'active':'')+'" data-hero-index="'+n+'" aria-label="Featured title '+(n+1)+'" aria-current="'+(n===this._heroIndex?'true':'false')+'"></button>';}).join("")+'</div><span class="hero-count">'+(this._heroIndex+1)+' / '+this._hero.length+'</span><button class="hero-arrow" data-hero-step="1" aria-label="Next featured title">›</button><button class="hero-pause" aria-label="'+(this._heroPaused?'Resume':'Pause')+' automatic rotation">'+(this._heroPaused?'▶':'Ⅱ')+'</button></div>':"";
    return '<section class="home-hero-stage">'+
      '<button class="home-hero-card" data-hero-open="'+this._heroIndex+'" '+(bg?'style="background-image:url(&quot;'+this.esc(bg)+'&quot;)"':"")+'>'+
        '<div class="home-hero-shade"></div><div class="home-hero-copy">'+logo+
        (meta?'<div class="home-hero-meta">'+this.esc(meta)+'</div>':"")+
        (genres?'<div class="home-hero-meta">'+this.esc(genres)+'</div>':"")+
        (i.description?'<p>'+this.esc(i.description)+'</p>':"")+
        '</div>'+
      '</button>'+dots+
    '</section>';
  }
  advanceHero(step,index){
    if(!this._hero.length)return;
    this._heroIndex=index==null?(this._heroIndex+step+this._hero.length)%this._hero.length:index;
    var stage=this.shadowRoot.querySelector(".home-hero-stage");
    if(stage){
      var active=this.shadowRoot.activeElement;
      var selector=active&&active.matches("[data-hero-step]")?'[data-hero-step="'+active.dataset.heroStep+'"]':active&&active.matches(".hero-pause")?'.hero-pause':active&&active.matches(".home-hero-dot")?'[data-hero-index="'+this._heroIndex+'"]':null;
      stage.outerHTML=this.hero();this.wireHero();
      if(selector)this.shadowRoot.querySelector(selector)?.focus({preventScroll:true});
    }
  }
  wireHero(){
    var r=this.shadowRoot;
    r.querySelectorAll("[data-hero-step]").forEach(b=>b.addEventListener("click",()=>this.advanceHero(Number(b.dataset.heroStep))));
    r.querySelectorAll(".home-hero-dot").forEach(b=>b.addEventListener("click",()=>this.advanceHero(0,Number(b.dataset.heroIndex))));
    r.querySelector(".hero-pause")?.addEventListener("click",()=>{this._heroPaused=!this._heroPaused;this.advanceHero(0);});
    r.querySelector(".home-hero-card")?.addEventListener("click",()=>{var i=this._hero[this._heroIndex];if(i)this.selectItem(i);});
  }
  syncHeroTimer(){
    var enabled=this.isConnected&&this._view==="home"&&this._hero.length>1&&this._homePrefs.hero_section_enabled!==false&&this._config.hero_autorotate!==false;
    var interval=Math.max(3,Number(this._config.hero_interval)||7)*1000;
    if(!enabled||interval!==this._heroInterval){clearInterval(this._heroTimer);this._heroTimer=null;}
    if(enabled&&!this._heroTimer){this._heroInterval=interval;this._heroTimer=setInterval(()=>{
      var stage=this.shadowRoot.querySelector(".home-hero-stage");
      if(!this._heroPaused&&!document.hidden&&stage&&!stage.matches(":hover")&&!stage.contains(this.shadowRoot.activeElement)&&!window.matchMedia("(prefers-reduced-motion: reduce)").matches)this.advanceHero(1);
    },interval);}
  }
  connectedCallback(){this.syncHeroTimer();}
  header(){
    var onHome=this._view==="home";
    var search=onHome&&this._config.show_search!==false
      ? '<div class="search"><ha-icon icon="mdi:magnify"></ha-icon><input id="search" value="'+this.esc(this._query)+'" placeholder="Search Nuvio…"></div>'
      : "";
    var addons=this._view==="sources"
      ? '<button class="ib toolbar-btn source-addon-toggle '+(this._addonFilterExpanded||this._addonFilter!=="all"?"toolbar-active":"")+'" id="addonsToggle" title="Filter sources by addon" aria-pressed="'+(this._addonFilterExpanded?"true":"false")+'"><ha-icon icon="mdi:filter-variant"></ha-icon></button>'
      : "";
    var remote=this._config.show_remote===false
      ? ""
      : '<button class="ib toolbar-btn remote-toggle-button '+(this._remoteExpanded?"remote-active":"")+'" title="Control" aria-label="Control"><ha-icon icon="mdi:remote-tv"></ha-icon></button>';
    var home='<button class="ib toolbar-btn '+(onHome?"toolbar-active":"")+'" id="homeTop" title="Home" aria-label="Home"><ha-icon icon="mdi:home"></ha-icon></button>';
    return '<div class="header"><div class="header-title"><img class="nuvio-wordmark" src="/nuvio/assets/wordmark.png?v=0.4.79" alt="Nuvio" decoding="async" style="display:none;height:38px;max-width:150px;width:auto;object-fit:contain"><h2 class="nuvio-wordmark-fallback">'+this.esc(this._config.title||"Nuvio")+'</h2><span class="card-version">v0.4.79</span></div><div class="tools">'+search+this.roomSelect()+'<label class="toolbar-player" title="Select media player"><ha-icon icon="mdi:television" aria-hidden="true"></ha-icon>'+this.playerSelect()+'</label>'+
      home+
      '<button class="ib toolbar-btn" id="refresh" title="Refresh" aria-label="Refresh"><ha-icon icon="mdi:refresh"></ha-icon></button>'+
      addons+remote+'</div></div>';
  }
  async goHome(){
    this._view="home";
    this._error="";
    this._addonFilterExpanded=false;
    if(!this._loaded){
      await this.loadHome(false);
      return;
    }
    this.render();
  }
  async refreshCurrent(){
    if(this._view==="sources"){
      await this.refreshSources();
      return;
    }
    if(this._view==="search"){
      await this.search();
      return;
    }
    if(this._view==="catalog"&&this._catalogReload){
      await this._catalogReload();
      return;
    }
    if(this._view==="details"&&this._item&&this._item.manifest_url){
      this._loading=true;this._error="";this.render();
      try{
        this._details=await this.ws({
          type:"nuvio/details",
          manifest_url:this._item.manifest_url,
          media_type:this._item.type,
          content_id:this._item.id
        });
        var seasons=this.seasons();
        if(seasons.length&&!seasons.includes(this._season))this._season=seasons[0];
      }catch(e){
        this._error=e.message||"Could not refresh title details.";
      }
      this._loading=false;this.render();
      return;
    }
    await this.loadHome(true);
  }
  home(){
    if(this._homeRetryTimer&&!this._sections.length&&!this._hero.length)return '<div class="status">Nuvio Home is still loading. Retrying automatically…</div>';
    if(this._loading&&!this._loaded)return '<div class="status">Loading Nuvio…</div>';
    if(!this._sections.length&&!this._hero.length)return '<div class="status">Nuvio Home is temporarily unavailable or has no content. Use Refresh to try again.</div>';
    var rows=this._sections.map((s,si)=>{
      var title=this.homeRowTitle(s);
      if(s.kind==="collection"){
        return '<section class="collection-section"><h3>'+this.esc(title)+'</h3><div class="rail collection-rail">'+(s.items||[]).map((x,i)=>this.collectionCard(x,si,i)).join("")+'</div></section>';
      }
      var addon=(s.kind==="catalog"&&this._homePrefs.show_catalog_addon_name!==false&&s.addon)
        ? '<small>from '+this.esc(s.addon)+'</small>'
        : "";
      var showLabels=s.kind!=="catalog"||this._homePrefs.show_poster_labels!==false;
      var landscape=s.kind==="catalog"&&this._homePrefs.layout==="modern"&&this._homePrefs.modern_landscape_posters_enabled===true;
      if(s.kind==="continue"&&this._homePrefs.use_episode_thumbnails_in_cw===true)landscape=true;
      var head=s.kind==="catalog"
        ? '<div class="home-row-head"><button class="catalog-open catalog-title" data-catalog-index="'+si+'"><span>'+this.esc(title)+(addon?' '+addon:"")+'</span></button><button class="catalog-open see-all" data-catalog-index="'+si+'">See all ›</button></div>'
        : '<h3>'+this.esc(title)+(addon?' '+addon:"")+'</h3>';
      if(s.kind==="catalog"&&s.lazy===true){
        var shimmer=Array.from({length:6},()=>'<div class="lazy-card"><div class="lazy-poster"></div><div class="lazy-line"></div></div>').join("");
        return '<section class="lazy-catalog-section" data-lazy-catalog-index="'+si+'">'+head+'<div class="rail lazy-rail">'+shimmer+'</div></section>';
      }
      if(s.kind==="catalog"&&s.load_error&&!s.items.length){
        return '<section>'+head+'<div class="catalog-load-error">'+this.esc(s.load_error)+' · Open the catalog to retry.</div></section>';
      }
      return '<section>'+head+'<div class="rail">'+(s.items||[]).map((x,i)=>this.card(x,"s"+si,i,{showLabels:showLabels,preferLandscape:landscape})).join("")+'</div></section>';
    }).join("");
    return this.hero()+rows;
  }
  searchView(){
    var cols=Number(this._config.columns)||6;
    return '<div class="top"><button class="back" id="back">← Catalog</button><h3>Search results for “'+this.esc(this._query)+'”</h3></div>'+(this._loading?'<div class="status">Searching…</div>':'<div class="grid" style="--cols:'+cols+'">'+this._results.map((x,i)=>this.card(x,"search",i)).join("")+'</div>');
  }
  playerSelect(){
    var selected=this.player();
    return '<select id="player" aria-label="Media player" title="Select media player">'+this.players().map(id=>{var m=this._playersMeta.find(x=>x.entity_id===id),name=m?m.name:(((this._hass.states[id]||{}).attributes||{}).friendly_name||id),platform=m?m.platform:"";return '<option value="'+this.esc(id)+'" data-platform="'+this.esc(platform)+'" '+(id===selected?"selected":"")+'>'+this.esc(name)+(platform==="webostv"?" · LG webOS":platform==="androidtv"?" · Android TV (ADB)":platform==="androidtv_remote"?" · Android TV Remote":"")+'</option>';}).join("")+'</select>';
  }
  async remoteKey(key){
    var p=this.player();
    if(!p){this._error="Select a media player first.";this.render();return;}
    try{
      await this.ensureDisplaySource(p);
      await this._hass.callService("nuvio","remote_key",{key:key},{entity_id:p});
    }catch(e){
      this._error=e.message||"Remote command failed.";
      this.render();
    }
  }
  remotePanel(){ return ""; }
  removeRemotePortal(){
    var portal=document.getElementById("nuvio-remote-portal");
    if(portal)portal.remove();
  }
  updateRemoteButtons(){
    if(!this.shadowRoot)return;
    this.shadowRoot.querySelectorAll(".remote-toggle-button").forEach(b=>{
      b.classList.toggle("remote-active",this._remoteExpanded);
      b.setAttribute("aria-pressed",this._remoteExpanded?"true":"false");
    });
  }
  toggleRemote(){
    this._remoteExpanded=!this._remoteExpanded;
    if(this._remoteExpanded)this.syncRemotePortal();
    else this.removeRemotePortal();
    this.updateRemoteButtons();
  }
  syncRemotePortal(){
    if(this._config.show_remote===false||!this._remoteExpanded){
      this.removeRemotePortal();
      return;
    }

    // Keep the existing controller alive across Home Assistant/card re-renders.
    // This is especially important while the catalog is loading.
    if(document.getElementById("nuvio-remote-portal"))return;

    var side=String(this._config.remote_side||"left").toLowerCase()==="right"?"right":"left";
    var portal=document.createElement("div");
    portal.id="nuvio-remote-portal";
    portal.style.cssText="position:fixed;inset:0;z-index:2147483000;pointer-events:none;";

    var shellSide=side==="right"?"right:12px;left:auto;":"left:12px;right:auto;";
    portal.innerHTML=`
      <style>
        #nuvio-remote-portal .nuvio-remote-backdrop{
          position:fixed;inset:0;background:rgba(0,0,0,.16);pointer-events:auto;
        }
        #nuvio-remote-portal .nuvio-remote-shell{
          position:fixed;
          top:max(180px,calc(env(safe-area-inset-top) + 110px));
          ${shellSide}
          width:176px;box-sizing:border-box;border:1px solid rgba(255,255,255,.14);
          border-radius:24px;padding:12px;background:rgba(28,28,30,.98);color:#fff;
          box-shadow:0 18px 50px rgba(0,0,0,.42);backdrop-filter:blur(18px);
          pointer-events:auto;font-family:Roboto,Arial,sans-serif;
          max-height:calc(100vh - 196px);overflow-y:auto;overscroll-behavior:contain;
        }
        #nuvio-remote-portal .nuvio-remote-head{
          display:flex;align-items:center;justify-content:space-between;
          font-size:13px;font-weight:700;color:#d0d0d0;margin-bottom:10px;
        }
        #nuvio-remote-portal button{font:inherit;box-sizing:border-box}
        #nuvio-remote-portal .nuvio-remote-close{
          width:30px;height:30px;border:0;border-radius:15px;background:#2f2f31;
          color:white;display:grid;place-items:center;cursor:pointer;font-size:20px;padding:0;
        }
        #nuvio-remote-portal .nuvio-wake-btn{
          width:100%;height:36px;border:0;border-radius:18px;background:#303033;color:white;
          display:flex;align-items:center;justify-content:center;gap:7px;font-size:12px;
          cursor:pointer;margin:0 0 12px;padding:0;
        }
        #nuvio-remote-portal .nuvio-remote-ring{
          position:relative;width:132px;height:132px;margin:0 auto 12px;border-radius:50%;
          background:radial-gradient(circle at center,#2c2c2e 0 34%,#35353a 35% 100%);
          box-shadow:inset 0 0 0 1px rgba(255,255,255,.08);
        }
        #nuvio-remote-portal .nuvio-remote-ring button{
          position:absolute;border:0;background:transparent;color:white;
          display:grid;place-items:center;cursor:pointer;padding:0;
        }
        #nuvio-remote-portal .nuvio-ring-btn{width:44px;height:44px;border-radius:50%}
        #nuvio-remote-portal .nuvio-ring-up{top:0;left:0;right:0;margin:auto}
        #nuvio-remote-portal .nuvio-ring-down{bottom:0;left:0;right:0;margin:auto}
        #nuvio-remote-portal .nuvio-ring-left{left:0;top:0;bottom:0;margin:auto}
        #nuvio-remote-portal .nuvio-ring-right{right:0;top:0;bottom:0;margin:auto}
        #nuvio-remote-portal .nuvio-ring-btn ha-icon{--mdc-icon-size:32px;width:32px;height:32px}
        #nuvio-remote-portal .nuvio-ring-up ha-icon{transform:translateY(-6px)}
        #nuvio-remote-portal .nuvio-ring-down ha-icon{transform:translateY(6px)}
        #nuvio-remote-portal .nuvio-ring-left ha-icon{transform:translateX(-6px)}
        #nuvio-remote-portal .nuvio-ring-right ha-icon{transform:translateX(6px)}
        #nuvio-remote-portal .nuvio-ring-ok{
          width:48px;height:48px;left:42px;top:42px;border-radius:50%;
          background:#03a9d9;border:0;color:white;font-size:11px;font-weight:800;
          box-shadow:0 3px 10px rgba(0,0,0,.25);
        }
        #nuvio-remote-portal .nuvio-number-pad{
          display:grid;grid-template-columns:repeat(3,1fr);gap:7px;
          margin:0 0 12px;padding-top:2px;
        }
        #nuvio-remote-portal .nuvio-number-pad button{
          height:36px;border:0;border-radius:12px;background:#303033;color:white;
          display:grid;place-items:center;font-size:16px;font-weight:700;
          cursor:pointer;padding:0;
          box-shadow:inset 0 0 0 1px rgba(255,255,255,.035);
        }
        #nuvio-remote-portal .nuvio-number-pad .nuvio-digit-zero{grid-column:2}
        #nuvio-remote-portal .nuvio-volume-row{
          display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin:0 0 12px;
        }
        #nuvio-remote-portal .nuvio-volume-row button{
          height:36px;border:0;border-radius:12px;background:#303033;color:white;
          display:grid;place-items:center;cursor:pointer;padding:0;
        }
        #nuvio-remote-portal .nuvio-volume-row ha-icon{--mdc-icon-size:23px}
        #nuvio-remote-portal .nuvio-remote-footer{
          display:grid;grid-template-columns:1fr 1fr;gap:8px;
        }
        #nuvio-remote-portal .nuvio-remote-footer button{
          height:40px;border:0;border-radius:14px;background:#303033;color:white;
          display:flex;align-items:center;justify-content:center;gap:6px;font-size:12px;
          cursor:pointer;padding:0;
        }
        #nuvio-remote-portal button:active{transform:scale(.96)}
        @media(max-width:700px){
          #nuvio-remote-portal .nuvio-remote-shell{width:166px;padding:11px}
          #nuvio-remote-portal .nuvio-remote-ring{width:122px;height:122px}
          #nuvio-remote-portal .nuvio-ring-ok{left:37px;top:37px}
        }
      </style>
      <div class="nuvio-remote-backdrop"></div>
      <div class="nuvio-remote-shell" role="dialog" aria-label="TV Remote">
        <div class="nuvio-remote-head">
          <span>TV Remote</span>
          <button class="nuvio-remote-close" title="Close" aria-label="Close">×</button>
        </div>
        <button class="nuvio-wake-btn" data-remote-key="wake"><span>▣</span><span>Wake</span></button>
        <div class="nuvio-remote-ring">
          <button class="nuvio-ring-btn nuvio-ring-up" data-remote-key="up" title="Up" aria-label="Up"><ha-icon icon="mdi:chevron-up"></ha-icon></button>
          <button class="nuvio-ring-btn nuvio-ring-left" data-remote-key="left" title="Left" aria-label="Left"><ha-icon icon="mdi:chevron-left"></ha-icon></button>
          <button class="nuvio-ring-ok" data-remote-key="ok" title="OK">OK</button>
          <button class="nuvio-ring-btn nuvio-ring-right" data-remote-key="right" title="Right" aria-label="Right"><ha-icon icon="mdi:chevron-right"></ha-icon></button>
          <button class="nuvio-ring-btn nuvio-ring-down" data-remote-key="down" title="Down" aria-label="Down"><ha-icon icon="mdi:chevron-down"></ha-icon></button>
        </div>
        <div class="nuvio-number-pad" role="group" aria-label="Number pad">
          <button data-remote-key="1" title="1" aria-label="1">1</button>
          <button data-remote-key="2" title="2" aria-label="2">2</button>
          <button data-remote-key="3" title="3" aria-label="3">3</button>
          <button data-remote-key="4" title="4" aria-label="4">4</button>
          <button data-remote-key="5" title="5" aria-label="5">5</button>
          <button data-remote-key="6" title="6" aria-label="6">6</button>
          <button data-remote-key="7" title="7" aria-label="7">7</button>
          <button data-remote-key="8" title="8" aria-label="8">8</button>
          <button data-remote-key="9" title="9" aria-label="9">9</button>
          <button class="nuvio-digit-zero" data-remote-key="0" title="0" aria-label="0">0</button>
        </div>
        <div class="nuvio-volume-row" role="group" aria-label="Volume controls">
          <button data-volume="down" title="Volume down" aria-label="Volume down"><ha-icon icon="mdi:volume-minus"></ha-icon></button>
          <button data-volume="mute" title="Mute or unmute" aria-label="Mute or unmute"><ha-icon icon="mdi:volume-off"></ha-icon></button>
          <button data-volume="up" title="Volume up" aria-label="Volume up"><ha-icon icon="mdi:volume-plus"></ha-icon></button>
        </div>
        ${this.selectedRoom()?.power_entity?'<button class="nuvio-wake-btn" data-room-power="true" title="Toggle room power"><ha-icon icon="mdi:power"></ha-icon><span>Room power</span></button>':''}
        <div class="nuvio-remote-footer">
          <button data-remote-key="back"><span>←</span><span>Back</span></button>
          <button data-remote-key="home"><span>⌂</span><span>Home</span></button>
        </div>
      </div>
    `;

    portal.querySelectorAll("[data-remote-key]").forEach(
      b=>b.addEventListener("click",()=>this.remoteKey(b.dataset.remoteKey))
    );
    portal.querySelectorAll("[data-volume]").forEach(b=>b.addEventListener("click",()=>this.volumeControl(b.dataset.volume)));
    portal.querySelector("[data-room-power]")?.addEventListener("click",()=>this.toggleRoomPower());
    var close=()=>{
      this._remoteExpanded=false;
      this.removeRemotePortal();
      this.updateRemoteButtons();
    };
    portal.querySelector(".nuvio-remote-close")?.addEventListener("click",close);
    portal.querySelector(".nuvio-remote-backdrop")?.addEventListener("click",close);

    (document.body||document.documentElement).appendChild(portal);
  }
  disconnectedCallback(){
    clearTimeout(this._homeRetryTimer);this._homeRetryTimer=null;
    clearInterval(this._heroTimer);this._heroTimer=null;
    if(this._lazyObserver){this._lazyObserver.disconnect();this._lazyObserver=null;}
    if(this._catalogObserver){this._catalogObserver.disconnect();this._catalogObserver=null;}
    this.removeRemotePortal();
  }
  detailsView(){
    var i=this._item;if(!i)return "";var d=this._details||i,bg=d.background||d.poster||"",videos=(d.videos||[]);
    var seasons=this.seasons(),eps=videos.filter(v=>Number(v.season)===Number(this._season)).sort((a,b)=>(Number(a.episode)||0)-(Number(b.episode)||0));
    var episodeHtml="";
    if(d.type==="series"&&this._details){
      episodeHtml='<div class="seasons">'+seasons.map(s=>'<button class="season '+(Number(this._season)===s?"active":"")+'" data-season="'+s+'">Season '+s+'</button>').join("")+'</div><div class="episodes">'+eps.map((e,n)=>'<button type="button" class="episode sourceep" data-ep="'+n+'" aria-label="Open sources for episode '+this.esc(e.episode||"")+'">'+(e.thumbnail?'<img loading="lazy" src="'+this.esc(e.thumbnail)+'" alt="">':'<div></div>')+'<div><h4>E'+this.esc(e.episode||"")+' · '+this.esc(e.title||("Episode "+(e.episode||"")))+'</h4>'+(e.overview?'<p>'+this.esc(e.overview)+'</p>':"")+'</div><span class="episode-chevron">›</span></button>').join("")+'</div>';
    }
    var platform=this.platform(this.player()),webos=platform==="webostv",remoteOnly=platform==="androidtv_remote";
    var sourceButton=(d.type!=="series"||i.video_id)?'<button class="action primary" id="sources">Sources</button>':"";
    var actions=webos
      ? '<button class="action" id="play">Open Nuvio TV on LG</button>'+sourceButton+'<div class="platform-note">Direct HTTP/HLS sources can be sent to the LG media viewer. Torrent/debrid-only sources still require Nuvio.</div>'
      : remoteOnly
        ? '<button class="action" id="play">Open in Nuvio</button>'+sourceButton+'<div class="platform-note">Direct HTTP/HLS sources can be opened separately. Torrent/debrid-only sources still require Nuvio.</div>'
        : '<button class="action" id="open">Open in Nuvio</button>'+((d.type!=="series"||i.video_id)?'<button class="action" id="play">▶ Play</button>'+sourceButton:"");
    return '<div class="hero" '+(bg?'style="background-image:url(&quot;'+this.esc(bg)+'&quot;)"':"")+'><div class="shade"></div><button class="back heroBack" id="back">← Catalog</button></div><div class="detail"><h2>'+this.esc(d.name||i.name)+'</h2><div class="meta">'+this.esc(d.releaseInfo||"")+(d.genres&&d.genres.length?' · '+this.esc(d.genres.join(", ")):"")+'</div>'+(d.description?'<p class="desc">'+this.esc(d.description)+'</p>':"")+'<div class="controls">'+actions+'</div>'+(this._loading?'<div class="status">Loading details…</div>':episodeHtml)+'</div>';
  }
  async copyText(value){
    try{
      await navigator.clipboard.writeText(String(value||""));
    }catch(e){
      this._error="Could not copy the link to the clipboard.";
      this.render();
    }
  }
  async openSourceLink(stream){
    await this.playSource(stream);
  }
  sourceDetails(){
    var d=this._details||this._item||{},i=this._item||{},ep=this._streamContext;
    var title=d.name||i.name||"Nuvio";
    if(ep){
      var epTitle=ep.title||ep.name||ep.episode_title||("Episode "+(ep.episode||""));
      var thumb=ep.thumbnail||ep.background||ep.poster||d.background||d.poster||i.background||i.poster||"";
      var epMeta=[];
      if(ep.season!=null&&ep.episode!=null)epMeta.push("Season "+this.esc(ep.season)+" · Episode "+this.esc(ep.episode));
      else if(ep.episode!=null)epMeta.push("Episode "+this.esc(ep.episode));
      if(ep.releaseInfo)epMeta.push(this.esc(ep.releaseInfo));
      if(ep.runtime)epMeta.push(this.esc(ep.runtime));
      var overview=ep.overview||ep.description||"";
      return '<section class="source-context source-context-episode">'+
        (thumb?'<div class="source-context-art episode-art"><img loading="lazy" src="'+this.esc(thumb)+'" alt=""></div>':'')+
        '<div class="source-context-copy">'+
          '<div class="source-context-kicker">'+this.esc(title)+'</div>'+
          '<h2>'+this.esc(epTitle)+'</h2>'+
          (epMeta.length?'<div class="source-context-meta">'+epMeta.join(" · ")+'</div>':'')+
          (overview?'<p>'+this.esc(overview)+'</p>':'')+
        '</div>'+
      '</section>';
    }
    var art=d.poster||i.poster||d.background||i.background||"";
    var movieMeta=[];
    if(d.releaseInfo)movieMeta.push(this.esc(d.releaseInfo));
    if(d.runtime)movieMeta.push(this.esc(d.runtime));
    if(d.genres&&d.genres.length)movieMeta.push(this.esc(d.genres.join(", ")));
    var description=d.description||i.description||"";
    return '<section class="source-context source-context-movie">'+
      (art?'<div class="source-context-art movie-art"><img loading="lazy" src="'+this.esc(art)+'" alt=""></div>':'')+
      '<div class="source-context-copy">'+
        '<div class="source-context-kicker">Movie</div>'+
        '<h2>'+this.esc(title)+'</h2>'+
        (movieMeta.length?'<div class="source-context-meta">'+movieMeta.join(" · ")+'</div>':'')+
        (description?'<p>'+this.esc(description)+'</p>':'')+
      '</div>'+
    '</section>';
  }
  sourcesView(){
    var ep=this._streamContext,d=this._details||this._item,title=d.name||this._item.name||"Nuvio";
    var sub=ep?("S"+(ep.season||"")+" E"+(ep.episode||"")+" · "+(ep.title||"Episode")):"Movie";
    var visible=this.filteredSourceEntries();
    var groups=new Map();
    visible.forEach(({stream:s,index:n})=>{
      var key=s.addon||"Unknown addon";
      if(!groups.has(key))groups.set(key,[]);
      groups.get(key).push({stream:s,index:n});
    });
    var badgeHtml=s=>(s.badges||[]).map(b=>'<span class="stream-badge badge-'+this.esc(b.kind||"info")+'">'+this.esc(b.label)+'</span>').join("");
    var groupHtml=[...groups.entries()].map(([addon,items])=>{
      var logo=(items[0].stream.addon_logo||"");
      var directCount=items.filter(x=>x.stream.direct).length;
      var rows=items.map(({stream:s,index:n})=>{
        var label=s.name||s.title||s.description||("Source "+(n+1));
        var secondary=s.description&&s.description!==label?s.description:"";
        var filename=s.filename&&s.filename!==label?s.filename:"";
        var unavailable=s.requires_headers?"Custom headers required":"Nuvio resolver required";
        var externalUrl=s.external_url||"";
        var torrentLink=s.magnet_uri||"";
        var canResolve=!!s.resolvable&&!s.requires_headers&&(s.info_hash||s.magnet_uri);
        var resolving=this._resolving.has(n);
        var externalOnly=!!externalUrl&&!s.direct&&!canResolve;
        var playButton='<button class="action primary nuvioplay" data-source-index="'+n+'">▶ Play</button>';
        var actionHtml=externalOnly
          ? playButton+'<button class="action copyexternal" data-source-index="'+n+'">Copy provider link</button><span class="resolver">Streaming app</span>'
          : s.direct
            ? playButton+'<button class="action copylink" data-source-index="'+n+'">Copy stream link</button>'
            : canResolve
              ? playButton+'<button class="action resolvesource" data-source-index="'+n+'" '+(resolving?"disabled":"")+'">Resolve only</button>'+(torrentLink?'<button class="action copytorrent" data-source-index="'+n+'">Copy magnet</button>':"")
              : playButton+'<span class="resolver">'+this.esc(unavailable)+'</span>'+(torrentLink?'<button class="action copytorrent" data-source-index="'+n+'">Copy magnet</button>':"");
        return '<div class="source-row">'+
          '<div class="source-main">'+
            '<div class="source-label">'+this.esc(label)+'</div>'+
            '<div class="stream-badges">'+badgeHtml(s)+'</div>'+
            (secondary?'<div class="source-description">'+this.esc(secondary)+'</div>':"")+
            (filename?'<div class="source-filename">'+this.esc(filename)+'</div>':"")+
          '</div>'+
          '<div class="source-actions">'+actionHtml+'</div>'+
        '</div>';
      }).join("");
      return '<section class="source-group">'+
        '<div class="source-group-head">'+
          (logo?'<img src="'+this.esc(logo)+'" alt="">':"")+
          '<div><h3>'+this.esc(addon)+'</h3><span>'+items.length+' source'+(items.length===1?"":"s")+' · '+directCount+' direct</span></div>'+
        '</div>'+
        rows+
      '</section>';
    }).join("");

    var unresolved=visible.filter(x=>!x.stream.direct&&x.stream.resolvable&&!x.stream.requires_headers&&(x.stream.info_hash||x.stream.magnet_uri)).length;
    var debridControls=unresolved
      ? (this._debridMeta.configured
          ? '<button class="action resolveall" id="resolveAll">Resolve up to 6 links · '+this.esc((this._debridMeta.providers||[]).join(", ")||this._debridMeta.provider||"Nuvio debrid")+'</button>'
          : '<span class="debrid-note">Play uses Nuvio for the selected source or opens Nuvio\'s source picker when the source cannot be resolved here.</span>')
      : "";
    var filtered=this._addonFilter!=="all";
    var sourceCountLabel=filtered
      ? visible.length+" of "+this._streams.length+" source"+(this._streams.length===1?"":"s")
      : this._streams.length+" source"+(this._streams.length===1?"":"s");
    var summary=sourceCountLabel+" from "+groups.size+" addon"+(groups.size===1?"":"s")+(unresolved?' · '+unresolved+' resolvable':"");
    var loadingText=this._streamLoadingStage==="watchhub"
      ? "Loading WatchHub…"
      : "Loading other addons…";
    var sourceBody=(groupHtml?'<div class="sources">'+groupHtml+'</div>':"")+
      (this._streamLoading?'<div class="status source-loading-status">'+loadingText+'</div>':"");
    if(!this._streamLoading&&!groupHtml)sourceBody='<div class="status">No sources were returned'+(filtered?" for this addon":" by your configured Nuvio addons")+'.</div>';

    return this.sourceFilterBar()+
      '<div class="top source-top"><button class="back" id="backDetails">← '+this.esc(title)+'</button></div>'+
      this.sourceDetails()+
      this.watchProviderRow()+
      '<div class="top source-controls"><div class="source-title-row"><h3>Sources · '+this.esc(sub)+'</h3></div><div class="controls">'+debridControls+'</div><div class="source-summary">'+summary+'</div></div>'+
      sourceBody;
  }
  styles(){
    return '<style>:host{display:block;--pw:min(150px,34vw)}ha-card{overflow:visible;padding:0;color:var(--primary-text-color)}.header{position:sticky;top:0;z-index:20;display:flex;gap:12px;align-items:center;padding:16px 20px 12px;border-bottom:1px solid var(--divider-color);background:var(--card-background-color)}.header-title{flex:1;min-width:0;display:flex;flex-direction:column;gap:1px}.header h2{margin:0;min-width:0;font-size:22px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.card-version{font-size:10px;line-height:1.2;color:var(--secondary-text-color);opacity:.8}.header-title.wordmark-loaded .card-version{margin-left:16px}.tools,.controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.toolbar-btn{display:inline-flex;align-items:center;gap:6px}.toolbar-btn ha-icon{--mdc-icon-size:19px}.toolbar-active{background:color-mix(in srgb,var(--primary-color) 18%,var(--secondary-background-color))!important}.search{display:flex;align-items:center;background:var(--secondary-background-color);border-radius:18px;padding:0 9px;min-width:220px}.search input{border:0;outline:0;background:transparent;color:var(--primary-text-color);padding:9px;width:100%}.ib,.back,.action,.season{border:0;cursor:pointer;background:var(--secondary-background-color);color:var(--primary-text-color);border-radius:18px;padding:9px 13px}.ib.toolbar-btn{width:38px;height:38px;flex:0 0 38px;padding:0;border-radius:50%;display:grid;place-items:center}.toolbar-room{display:flex;align-items:center;gap:6px;min-width:122px;max-width:210px;flex:0 1 160px;border-radius:18px;padding:0 9px;background:var(--secondary-background-color);color:var(--primary-text-color)}.toolbar-room ha-icon{--mdc-icon-size:19px;flex:0 0 auto}.toolbar-room select{width:100%;min-width:0;max-width:100%;padding:9px 0;border:0;outline:0;background:transparent;color:inherit;text-overflow:ellipsis;font:inherit;cursor:pointer}.toolbar-player{display:flex;align-items:center;gap:6px;min-width:155px;max-width:260px;flex:0 1 240px;border-radius:18px;padding:0 9px;background:var(--secondary-background-color);color:var(--primary-text-color)}.toolbar-player ha-icon{--mdc-icon-size:19px;flex:0 0 auto}.toolbar-player select{width:100%;min-width:0;max-width:100%;padding:9px 0;border:0;outline:0;background:transparent;color:inherit;text-overflow:ellipsis;font:inherit;cursor:pointer}section{padding:8px 0 12px}section h3{margin:6px 20px 10px}.home-row-head{display:flex;align-items:center;gap:10px;margin:6px 20px 10px}.catalog-title{flex:1;min-width:0;text-align:left;border:0;background:transparent;color:var(--primary-text-color);font:inherit;font-size:1.17em;font-weight:600;padding:0;cursor:pointer}.catalog-title span{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.catalog-title small{font-size:11px;font-weight:400;color:var(--secondary-text-color)}.see-all{border:0;background:transparent;color:var(--primary-color);font:inherit;font-size:12px;font-weight:600;padding:5px 0 5px 8px;cursor:pointer;white-space:nowrap}.catalog-view{display:flex;flex-direction:column;min-height:0}.catalog-fixed{flex:0 0 auto;background:var(--card-background-color);border-bottom:1px solid var(--divider-color);z-index:2}.catalog-scroll{height:clamp(320px,calc(100dvh - 300px),780px);overflow-y:auto;overscroll-behavior:contain;scrollbar-gutter:stable}.catalog-grid{overflow-anchor:auto}.catalog-sentinel{overflow-anchor:none}.catalog-top h3{margin:12px 0 4px}.catalog-top small{font-weight:400;color:var(--secondary-text-color)}.catalog-sentinel{min-height:72px;display:grid;place-items:center;color:var(--secondary-text-color);font-size:12px;padding:0 20px;text-align:center}.rail{display:flex;gap:12px;overflow:auto;padding:0 20px 10px}.pc{width:var(--pw);min-width:var(--pw);border:0;background:none;color:inherit;text-align:left;padding:0;cursor:pointer}.poster{aspect-ratio:2/3;border-radius:12px;overflow:hidden;background:var(--secondary-background-color);position:relative}.poster img{width:100%;height:100%;object-fit:cover}.ph{height:100%;display:grid;place-items:center}.pt{font-weight:600;font-size:13px;margin-top:7px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.meta{display:flex;justify-content:space-between;gap:5px;color:var(--secondary-text-color);font-size:11px}.prog{position:absolute;left:6px;right:6px;bottom:6px;height:4px;background:#ffffff55}.prog i{display:block;height:100%;background:var(--primary-color)}.home-hero-stage{position:relative;padding:0 0 14px}.home-hero-card{position:relative;display:block;width:100%;height:340px;border:0;padding:0;overflow:hidden;background-size:cover;background-position:center;color:white;text-align:left;cursor:pointer}.home-hero-shade{position:absolute;inset:0;background:linear-gradient(90deg,rgba(0,0,0,.88) 0%,rgba(0,0,0,.60) 37%,rgba(0,0,0,.12) 72%),linear-gradient(0deg,var(--card-background-color) 0%,transparent 38%)}.home-hero-copy{position:absolute;left:22px;bottom:30px;max-width:min(520px,60%);z-index:1}.home-hero-copy h2{margin:0 0 8px;font-size:30px}.home-hero-copy p{margin:10px 0 0;line-height:1.4;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}.home-hero-logo{display:block;max-width:min(360px,75%);max-height:90px;object-fit:contain;object-position:left bottom;margin-bottom:10px}.home-hero-meta{font-size:13px;opacity:.9;margin-top:4px}.home-hero-nav{position:absolute;right:18px;bottom:26px;z-index:2;display:flex;align-items:center;gap:10px;padding:6px 9px;border-radius:24px;background:rgba(0,0,0,.55);color:white}.home-hero-dots{display:flex;gap:7px}.hero-arrow,.hero-pause{display:grid;place-items:center;width:32px;height:32px;padding:0;border:0;border-radius:50%;background:rgba(255,255,255,.12);color:white;cursor:pointer;font-size:26px}.hero-pause{font-size:15px}.hero-count{font-size:11px;white-space:nowrap}.home-hero-dot{width:8px;height:8px;border:0;border-radius:50%;padding:0;background:#ffffff66;cursor:pointer}.home-hero-dot.active{background:white;transform:scale(1.25)}.landscape-card{--pw:min(235px,53vw)}.landscape-card .poster{aspect-ratio:16/9}.collection-rail{align-items:flex-start}.collection-card{width:var(--pw);min-width:var(--pw);border:0;padding:0;background:none;color:inherit;cursor:pointer;font:inherit;text-align:left}.collection-card:focus-visible{outline:2px solid var(--primary-color);outline-offset:3px}.collection-tabs{display:flex;gap:8px;overflow:auto;padding:8px 20px}.collection-art{position:relative;aspect-ratio:1/1;border-radius:12px;overflow:hidden;background:var(--secondary-background-color)}.collection-card.shape-poster .collection-art{aspect-ratio:2/3}.collection-card.shape-landscape{width:min(235px,53vw);min-width:min(235px,53vw)}.collection-card.shape-landscape .collection-art{aspect-ratio:16/9}.collection-art img{width:100%;height:100%;object-fit:fill}.collection-emoji{height:100%;display:grid;place-items:center;font-size:42px;font-weight:700}.collection-title{position:absolute;left:0;right:0;bottom:0;padding:18px 8px 8px;text-align:center;font-size:12px;font-weight:700;color:white;background:linear-gradient(transparent,rgba(0,0,0,.8))}.lazy-rail{overflow:hidden}.lazy-card{width:var(--pw);min-width:var(--pw)}.lazy-poster{aspect-ratio:2/3;border-radius:12px;background:linear-gradient(100deg,var(--secondary-background-color) 25%,color-mix(in srgb,var(--secondary-background-color) 75%,var(--primary-text-color) 25%) 45%,var(--secondary-background-color) 65%);background-size:220% 100%;animation:nuvioShimmer 1.35s linear infinite}.lazy-line{height:12px;width:72%;border-radius:6px;margin-top:8px;background:var(--secondary-background-color)}.catalog-load-error{padding:8px 20px 20px;color:var(--secondary-text-color);font-size:12px}@keyframes nuvioShimmer{0%{background-position:180% 0}100%{background-position:-40% 0}}@media(prefers-reduced-motion:reduce){.lazy-poster{animation:none}}.status{padding:28px;text-align:center;color:var(--secondary-text-color)}.error{margin:10px 20px;padding:12px;border-radius:10px;background:var(--error-color);color:white}.top{padding:8px 20px}.grid{display:grid;grid-template-columns:repeat(var(--cols),minmax(0,1fr));gap:14px;padding:10px 20px 22px}.grid .pc{width:auto;min-width:0}.hero{height:270px;background-size:cover;background-position:center;position:relative}.shade{position:absolute;inset:0;background:linear-gradient(0deg,var(--card-background-color) 0%,transparent 90%)}.heroBack{position:absolute;top:16px;left:16px}.detail{position:relative;margin-top:-82px;padding:0 20px 22px}.detail h2{font-size:28px;margin:0 0 8px}.desc{max-width:850px;color:var(--secondary-text-color);line-height:1.45}.controls{margin:16px 0}.platform-note{flex-basis:100%;font-size:12px;color:var(--secondary-text-color);max-width:760px}.controls select{border:0;border-radius:18px;padding:9px 12px;background:var(--secondary-background-color);color:var(--primary-text-color)}.primary,.season.active{background:var(--primary-color);color:white}.seasons{display:flex;gap:8px;overflow:auto;margin:14px 0}.episodes{display:grid;gap:9px}.episode{display:grid;grid-template-columns:140px 1fr auto;gap:12px;align-items:center;width:100%;border:0;text-align:left;color:inherit;font:inherit;cursor:pointer;background:var(--secondary-background-color);padding:8px;border-radius:12px}.episode:hover,.episode:focus-visible{outline:2px solid color-mix(in srgb,var(--primary-color) 65%,transparent);outline-offset:1px}.episode img{width:140px;aspect-ratio:16/9;object-fit:cover;border-radius:8px}.episode h4,.episode p{margin:0}.episode p{font-size:12px;color:var(--secondary-text-color);margin-top:5px}.episode-chevron{font-size:28px;color:var(--secondary-text-color);padding:0 8px}.sources{display:grid;gap:18px;padding:0 20px 22px}.source-group{padding:0}.source-group-head{display:flex;align-items:center;gap:10px;margin:0 0 8px}.source-group-head img{width:34px;height:34px;object-fit:contain;border-radius:8px;background:var(--secondary-background-color)}.source-group-head h3{margin:0;font-size:16px}.source-group-head span,.source-summary{font-size:12px;color:var(--secondary-text-color)}.source-row{display:flex;gap:12px;align-items:center;justify-content:space-between;background:var(--secondary-background-color);padding:12px;border-radius:12px;margin-bottom:8px}.source-main{min-width:0;display:flex;flex:1;flex-direction:column;gap:6px}.source-label{font-weight:650;white-space:normal;overflow-wrap:anywhere}.source-description,.source-filename,.resolver{font-size:12px;color:var(--secondary-text-color);overflow-wrap:anywhere}.source-filename{opacity:.8}.stream-badges{display:flex;flex-wrap:wrap;gap:5px}.stream-badge{display:inline-flex;align-items:center;min-height:20px;padding:1px 7px;border-radius:10px;font-size:11px;font-weight:650;background:var(--card-background-color);border:1px solid var(--divider-color);white-space:nowrap}.badge-resolution{background:color-mix(in srgb,var(--primary-color) 20%,var(--card-background-color));border-color:color-mix(in srgb,var(--primary-color) 55%,var(--divider-color))}.badge-hdr,.badge-audio{background:color-mix(in srgb,var(--accent-color,var(--primary-color)) 14%,var(--card-background-color))}.badge-size,.badge-language{font-weight:500;color:var(--secondary-text-color)}.source-actions{flex:0 0 auto;max-width:260px;text-align:right;display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}.source-filter-bar{display:flex;gap:8px;overflow:auto;padding:10px 20px 4px;scrollbar-width:thin}.watch-provider-section{padding:4px 20px 12px}.watch-provider-heading{display:flex;align-items:end;justify-content:space-between;margin:0 0 8px}.watch-provider-heading h3{margin:0;font-size:15px}.watch-provider-heading span{font-size:11px;color:var(--secondary-text-color)}.watch-provider-rail{display:flex;gap:10px;overflow-x:auto;padding:2px 0 4px;scrollbar-width:thin}.watch-provider{width:78px;min-width:78px;border:0;border-radius:14px;background:var(--secondary-background-color);color:var(--primary-text-color);padding:8px 6px;display:flex;flex-direction:column;align-items:center;gap:5px;cursor:pointer}.watch-provider img,.watch-provider-fallback{width:44px;height:44px;border-radius:10px;object-fit:cover}.watch-provider-fallback{display:grid;place-items:center;background:var(--card-background-color);font-weight:700}.watch-provider-name{font-size:11px;line-height:1.15;text-align:center}.watch-provider-access{font-size:9px;color:var(--secondary-text-color);text-align:center}.watch-provider-link-source{font-size:8px;color:var(--secondary-text-color);text-align:center}.watch-provider.linked:hover{outline:2px solid var(--primary-color)}.watch-provider.availability-only{opacity:.52;cursor:default}.watch-provider-attribution{font-size:9px;color:var(--secondary-text-color);margin-top:5px}.watch-provider-loading{font-size:12px;color:var(--secondary-text-color);padding:14px 4px;white-space:nowrap}.source-filter-chip{border:0;cursor:pointer;background:var(--secondary-background-color);color:var(--primary-text-color);border-radius:18px;padding:8px 13px;white-space:nowrap;font:inherit;font-size:12px}.source-filter-chip.active{background:var(--primary-color);color:white}.source-top{padding-top:12px;padding-bottom:6px}.source-controls{padding-top:4px}.source-loading-status{padding-top:8px}.source-context{display:grid;grid-template-columns:auto minmax(0,1fr);gap:18px;align-items:center;margin:4px 20px 10px;padding:14px;border-radius:16px;background:linear-gradient(135deg,color-mix(in srgb,var(--secondary-background-color) 92%,transparent),color-mix(in srgb,var(--card-background-color) 96%,transparent));border:1px solid var(--divider-color);overflow:hidden}.source-context-art{overflow:hidden;border-radius:12px;background:var(--secondary-background-color);box-shadow:0 6px 18px rgba(0,0,0,.18)}.source-context-art img{display:block;width:100%;height:100%;object-fit:cover}.source-context-art.movie-art{width:112px;aspect-ratio:2/3}.source-context-art.episode-art{width:min(240px,30vw);aspect-ratio:16/9}.source-context-copy{min-width:0}.source-context-kicker{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--secondary-text-color);margin-bottom:4px}.source-context-copy h2{margin:0 0 7px;font-size:24px;line-height:1.15}.source-context-meta{font-size:12px;color:var(--secondary-text-color);line-height:1.4}.source-context-copy p{margin:10px 0 0;max-width:850px;color:var(--secondary-text-color);line-height:1.45;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}.source-title-row{display:flex;align-items:center;gap:8px;margin:8px 0}.source-title-row h3{margin:0}.remote-active{background:var(--primary-color)!important;color:white!important}.source-summary{margin-top:-8px;margin-bottom:6px}.debrid-note{font-size:12px;color:var(--secondary-text-color);max-width:520px}.resolvesource:disabled{opacity:.65;cursor:wait}.resolveall{font-size:12px}.nuvio-layout{position:relative;display:block;min-width:0}.nuvio-main{width:100%;min-width:0}.remote-shell{width:176px;border:1px solid var(--divider-color);border-radius:24px;padding:12px;background:color-mix(in srgb,var(--card-background-color) 94%,transparent);backdrop-filter:blur(18px);box-shadow:0 12px 36px rgba(0,0,0,.26)}.remote-head{display:flex;align-items:center;justify-content:space-between;font-size:12px;font-weight:700;color:var(--secondary-text-color);margin-bottom:10px}.remote-close{width:26px;height:26px;border:0;border-radius:13px;background:var(--secondary-background-color);color:var(--primary-text-color);display:grid;place-items:center;cursor:pointer}.remote-close ha-icon{--mdc-icon-size:16px}.wake-btn{width:100%;height:34px;border:0;border-radius:17px;background:var(--secondary-background-color);color:var(--primary-text-color);display:flex;align-items:center;justify-content:center;gap:6px;font-size:11px;cursor:pointer;margin-bottom:10px}.wake-btn ha-icon{--mdc-icon-size:18px}.remote-ring{position:relative;width:132px;height:132px;margin:0 auto 10px;border-radius:50%;background:radial-gradient(circle at center,var(--secondary-background-color) 0 34%,color-mix(in srgb,var(--secondary-background-color) 82%,var(--primary-color) 18%) 35% 100%);box-shadow:inset 0 0 0 1px var(--divider-color)}.remote-ring button{position:absolute;border:0;background:transparent;color:var(--primary-text-color);display:grid;place-items:center;cursor:pointer}.ring-btn{width:44px;height:44px;border-radius:50%!important}.ring-btn ha-icon{--mdc-icon-size:28px}.ring-btn.up{top:0;left:0;right:0;margin:auto}.ring-btn.down{bottom:0;left:0;right:0;margin:auto}.ring-btn.left{left:0;top:0;bottom:0;margin:auto}.ring-btn.right{right:0;top:0;bottom:0;margin:auto}.ring-btn.up ha-icon{transform:translateY(-6px)}.ring-btn.down ha-icon{transform:translateY(6px)}.ring-btn.left ha-icon{transform:translateX(-6px)}.ring-btn.right ha-icon{transform:translateX(6px)}.ring-ok{width:48px;height:48px;left:42px;top:42px;border-radius:50%!important;background:var(--primary-color)!important;color:white!important;font-size:11px;font-weight:800;box-shadow:0 3px 10px rgba(0,0,0,.22)}.remote-ring button:active,.wake-btn:active,.remote-footer button:active{transform:scale(.96)}.remote-footer{display:grid;grid-template-columns:1fr 1fr;gap:8px}.remote-footer button{height:38px;border:0;border-radius:14px;background:var(--secondary-background-color);color:var(--primary-text-color);display:flex;align-items:center;justify-content:center;gap:5px;font-size:11px;cursor:pointer}.remote-footer ha-icon{--mdc-icon-size:18px}.resolveall{font-size:12px}@media(max-width:700px){:host{--pw:120px}.catalog-scroll{height:clamp(300px,calc(100dvh - 340px),720px)}.remote-dialog{top:180px}.remote-shell{width:160px;padding:10px}.remote-ring{width:120px;height:120px}.ring-ok{left:36px;top:36px}.header{flex-direction:column;align-items:stretch}.search{min-width:0;flex:1}.grid{grid-template-columns:repeat(3,minmax(0,1fr))}.episode{grid-template-columns:95px 1fr}.episode img{width:95px}.playep{grid-column:2}.source-context{grid-template-columns:92px minmax(0,1fr);gap:12px;margin:4px 12px 10px;padding:10px}.source-context-art.movie-art{width:92px}.source-context-art.episode-art{width:92px;aspect-ratio:16/9}.source-context-copy h2{font-size:19px}.source-context-copy p{font-size:12px;-webkit-line-clamp:3}.source-row{align-items:flex-start;flex-direction:column}.source-actions{max-width:none;width:100%;text-align:left}.source-actions .action{width:100%}.home-hero-card{height:250px}.home-hero-copy{left:16px;bottom:22px;max-width:75%}.home-hero-copy h2{font-size:24px}.home-hero-nav{right:12px;bottom:20px;gap:7px}.home-hero-copy{bottom:80px}.home-hero-copy p{display:none}.hero{height:220px}.tools{width:100%;gap:6px}.toolbar-player{min-width:110px;max-width:none;flex:1 1 130px}.search{min-width:0;flex:1 1 100%;width:100%}}</style>';
  }
  wire(){
    var r=this.shadowRoot,q=r.querySelector("#search");
    var wordmark=r.querySelector(".nuvio-wordmark"),fallback=r.querySelector(".nuvio-wordmark-fallback");
    if(wordmark&&fallback){
      var showWordmark=()=>{
        var loaded=wordmark.complete&&wordmark.naturalWidth>0;
        wordmark.style.display=loaded?"block":"none";
        fallback.style.display=loaded?"none":"";
        wordmark.closest(".header-title")?.classList.toggle("wordmark-loaded",loaded);
      };
      wordmark.addEventListener("load",showWordmark);
      wordmark.addEventListener("error",showWordmark);
      showWordmark();
    }
    if(q){q.addEventListener("input",e=>this._query=e.target.value);q.addEventListener("keydown",e=>{if(e.key==="Enter")this.search();});}
    r.querySelector("#homeTop")?.addEventListener("click",()=>this.goHome());
    r.querySelector("#refresh")?.addEventListener("click",()=>this.refreshCurrent());
    r.querySelector("#addonsToggle")?.addEventListener("click",()=>this.toggleAddonFilter());
    r.querySelectorAll("[data-addon-filter]").forEach(b=>b.addEventListener("click",()=>this.setAddonFilter(b.dataset.addonFilter)));
    r.querySelectorAll("[data-remote-key]").forEach(b=>b.addEventListener("click",()=>this.remoteKey(b.dataset.remoteKey)));
    r.querySelectorAll(".remote-toggle-button").forEach(b=>b.addEventListener("click",()=>this.toggleRemote()));
    r.querySelector("#back")?.addEventListener("click",()=>{this._view=this._view==="details"?(this._returnView||"home"):"home";this._error="";this.render();});
    r.querySelector("#open")?.addEventListener("click",()=>this.play(true,null));
    r.querySelector("#play")?.addEventListener("click",()=>this.play(false,null));
    r.querySelector("#sources")?.addEventListener("click",()=>this.showSources(null));
    r.querySelector("#player")?.addEventListener("change",e=>{this.choosePlayer(e.target.value);});
    r.querySelector("#room")?.addEventListener("change",e=>{this.chooseRoom(e.target.value);});
    r.querySelectorAll(".season").forEach(b=>b.addEventListener("click",()=>{this._season=Number(b.dataset.season);this.render();}));
    r.querySelectorAll(".sourceep").forEach(b=>b.addEventListener("click",()=>{var eps=(this._details.videos||[]).filter(v=>Number(v.season)===Number(this._season)).sort((a,c)=>(Number(a.episode)||0)-(Number(c.episode)||0));this.showSources(eps[Number(b.dataset.ep)],{backTo:"details"});}));
    r.querySelectorAll(".playsource").forEach(b=>b.addEventListener("click",()=>this.playSource(this._streams[Number(b.dataset.sourceIndex)])));
    r.querySelectorAll(".nuvioplay").forEach(b=>b.addEventListener("click",()=>this.playInNuvioIndex(Number(b.dataset.sourceIndex))));
    r.querySelectorAll("[data-watch-provider-index]").forEach(b=>b.addEventListener("click",()=>this.playWatchProvider(this._watchProviders[Number(b.dataset.watchProviderIndex)])));
    r.querySelectorAll(".playdirect").forEach(b=>b.addEventListener("click",()=>this.playDirectIndex(Number(b.dataset.sourceIndex))));
    r.querySelectorAll(".resolvesource").forEach(b=>b.addEventListener("click",()=>this.resolveSource(Number(b.dataset.sourceIndex))));
    r.querySelector("#resolveAll")?.addEventListener("click",()=>this.resolveVisibleSources());
    r.querySelectorAll("button.openlink").forEach(b=>b.addEventListener("click",()=>this.openSourceLink(this._streams[Number(b.dataset.sourceIndex)])));
    r.querySelectorAll(".copylink").forEach(b=>b.addEventListener("click",()=>this.copyText((this._streams[Number(b.dataset.sourceIndex)]||{}).url)));
    r.querySelectorAll(".copyexternal").forEach(b=>b.addEventListener("click",()=>this.copyText((this._streams[Number(b.dataset.sourceIndex)]||{}).external_url)));
    r.querySelectorAll(".copytorrent").forEach(b=>b.addEventListener("click",()=>this.copyText((this._streams[Number(b.dataset.sourceIndex)]||{}).magnet_uri)));
    r.querySelector("#backDetails")?.addEventListener("click",()=>{this._view=this._sourcesBackView||"details";this._error="";this.render();});
    r.querySelectorAll(".collection-card").forEach(b=>b.addEventListener("click",()=>{var s=this._sections[Number(b.dataset.sectionIndex)];if(s)this.openCollection(s.items[Number(b.dataset.folderIndex)],s);}));
    r.querySelectorAll(".collection-tab").forEach(b=>b.addEventListener("click",()=>this.selectCollectionTab(Number(b.dataset.tab))));
    r.querySelectorAll(".catalog-open").forEach(b=>b.addEventListener("click",()=>{var s=this._sections[Number(b.dataset.catalogIndex)];if(s)this.openCatalog(s);}));
    this.wireHero();
    this.wireCatalogCards(r);
    r.querySelectorAll(".pc:not([data-source=\"catalog\"])").forEach(b=>b.addEventListener("click",()=>{var i;if(b.dataset.source==="search")i=this._results[Number(b.dataset.index)];else{var si=Number(b.dataset.source.slice(1));i=this._sections[si].items[Number(b.dataset.index)];}if(i)this.selectItem(i);}));
  }
  render(){
    if(!this.shadowRoot)return;
    var oldScroller=this.shadowRoot.querySelector(".catalog-scroll");
    if(oldScroller)this._catalogScrollTop=oldScroller.scrollTop;
    if(this._resetCatalogScroll)this._catalogScrollTop=0;
    var scrollTop=this._catalogScrollTop||0;
    this._resetCatalogScroll=false;
    var body=this._view==="details"?this.detailsView():(this._view==="sources"?this.sourcesView():(this._view==="search"?this.searchView():(this._view==="catalog"?this.catalogView():this.home())));
    var content=this._config.show_remote===false
      ? body
      : '<div class="nuvio-layout">'+this.remotePanel()+'<main class="nuvio-main">'+body+'</main></div>';
    this.shadowRoot.innerHTML=this.styles()+'<ha-card>'+this.header()+(this._error?'<div class="error">'+this.esc(this._error)+'</div>':"")+content+'</ha-card>';this.wire();
    var newScroller=this.shadowRoot.querySelector(".catalog-scroll");
    if(newScroller)newScroller.scrollTop=scrollTop;
    this.observeLazyCatalogs();
    this.observeCatalogScroll();
    this.syncRemotePortal();
    this.updateRemoteButtons();
    this.syncHeroTimer();
  }
}

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
    return JSON.stringify([...this.routes(),...this.rooms()].map(route=>[route&&route.display,this.displaySources(route&&route.display)]));
  }
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
    const extras=[selected,this._config.default_player,this._config.entity,...routes.flatMap(r=>[r&&r.player,r&&r.display]),...this.rooms().flatMap(r=>[r.player,r.display,r.volume_entity])];
    const empty=includeEmpty?'<option value="">Select a media player</option>':"";
    return empty+this.playerIds(extras).map(id=>'<option value="'+this.esc(id)+'" '+(id===selected?'selected':'')+'>'+this.esc(this.name(id))+' · '+this.esc(id)+'</option>').join("");
  }
  powerOptions(selected){
    const states=(this._hass&&this._hass.states)||{};
    const ids=[...new Set([...Object.keys(states).filter(id=>id.startsWith("switch.")||id.startsWith("input_boolean.")),selected].filter(Boolean))].sort((a,b)=>this.name(a).localeCompare(this.name(b)));
    return '<option value="">No power helper</option>'+ids.map(id=>'<option value="'+this.esc(id)+'" '+(id===selected?'selected':'')+'>'+this.esc(this.name(id))+' · '+this.esc(id)+'</option>').join("");
  }
  rooms(){return Array.isArray(this._config.rooms)?this._config.rooms:[];}
  roomHtml(room,index){
    const r=room||{},wake=r.wake_delay_ms==null?2000:r.wake_delay_ms;
    const settle=r.delay_ms==null?1000:r.delay_ms;
    const powerDelay=r.power_delay_ms==null?2000:r.power_delay_ms;
    return '<section class="route"><div class="route-heading"><strong>Room '+(index+1)+'</strong><button type="button" data-action="remove-room" data-index="'+index+'" aria-label="Remove room '+(index+1)+'">Remove</button></div>'+
      '<div class="fields"><label>Room name<input type="text" data-room="'+index+'" data-key="name" value="'+this.esc(r.name||"")+'" placeholder="Living room"></label>'+
      '<label>Playback device<select data-room="'+index+'" data-key="player">'+this.playerOptions(r.player||"")+'</select></label>'+
      '<label>Physical TV / display (optional)<select data-room="'+index+'" data-key="display">'+this.playerOptions(r.display||"")+'</select></label>'+
      '<label>TV input / HDMI source'+this.sourceOptions(r.display,index,r.source||"","room")+'</label>'+
      '<label>Volume device (optional override)<select data-room="'+index+'" data-key="volume_entity">'+this.playerOptions(r.volume_entity||"")+'</select><small>Defaults to the physical TV, or the playback device if no TV is mapped.</small></label>'+
      '<label>Power helper (optional)<select data-room="'+index+'" data-key="power_entity">'+this.powerOptions(r.power_entity||"")+'</select></label>'+
      '<label class="switch"><input type="checkbox" data-room="'+index+'" data-key="turn_on" '+(r.turn_on!==false?'checked':'')+'>Turn on display when needed</label>'+
      '<label>Power-on delay (ms)<input type="number" min="0" max="30000" step="100" data-room="'+index+'" data-key="power_delay_ms" value="'+this.esc(powerDelay)+'"></label>'+
      '<label>Display wake delay (ms)<input type="number" min="0" max="10000" step="100" data-room="'+index+'" data-key="wake_delay_ms" value="'+this.esc(wake)+'"></label>'+
      '<label>HDMI switch delay (ms)<input type="number" min="0" max="10000" step="100" data-room="'+index+'" data-key="delay_ms" value="'+this.esc(settle)+'"></label></div></section>';
  }
  sourceOptions(display,index,selected="",scope="route"){
    const sources=this.displaySources(display);
    const attrs=' data-'+(scope==="room"?"room":"route")+'="'+index+'" data-key="source"';
    if(sources.length){
      // Source names are TV-provided: HDMI inputs may also have custom names.
      const options='<option value="">Select a TV source</option>'+sources.map(source=>'<option value="'+this.esc(source)+'" '+(source===selected?'selected':'')+'>'+this.esc(source)+'</option>').join("");
      const saved=selected&&!sources.includes(selected)?'<option value="'+this.esc(selected)+'" selected>'+this.esc(selected)+' (saved; not currently reported)</option>':"";
      return '<select'+attrs+'>'+options+saved+'</select><small>Available sources reported by the selected TV in Home Assistant.</small>';
    }
    return '<input'+attrs+' type="text" value="'+this.esc(selected)+'" placeholder="Enter TV input name" autocomplete="off"><small>This TV does not report its sources; enter the exact input name manually.</small>';
  }
  routes(){return Array.isArray(this._config.display_routes)?this._config.display_routes:[];}
  routeHtml(route,index){
    const r=route||{},source=String(r.source||"");
    const on=r.turn_on!==false;
    const wake=r.wake_delay_ms==null?2000:r.wake_delay_ms;
    const settle=r.delay_ms==null?1000:r.delay_ms;
    return '<section class="route"><div class="route-heading"><strong>Connection '+(index+1)+'</strong><button type="button" data-action="remove" data-index="'+index+'" aria-label="Remove connection '+(index+1)+'">Remove</button></div>'+
      '<div class="fields"><label>Playback device<select data-route="'+index+'" data-key="player">'+this.playerOptions(r.player||"")+'</select></label>'+
      '<label>Physical TV / display<select data-route="'+index+'" data-key="display">'+this.playerOptions(r.display||"")+'</select></label>'+
      '<label>TV input / HDMI source'+this.sourceOptions(r.display,index,source)+'</label>'+
      '<label class="switch"><input type="checkbox" data-route="'+index+'" data-key="turn_on" '+(on?'checked':'')+'>Turn on the display if needed</label>'+
      '<label>Wake delay (ms)<input type="number" min="0" max="10000" step="100" data-route="'+index+'" data-key="wake_delay_ms" value="'+this.esc(wake)+'"></label>'+
      '<label>Delay after input change (ms)<input type="number" min="0" max="10000" step="100" data-route="'+index+'" data-key="delay_ms" value="'+this.esc(settle)+'"></label></div></section>';
  }
  emit(config){
    this._config=config;
    this.dispatchEvent(new window.CustomEvent("config-changed",{detail:{config:{...config}},bubbles:true,composed:true}));
    this.render();
  }
  change(event){
    const target=event.target;
    if(!target||!target.getAttribute)return;
    const field=target.getAttribute("data-field");
    const routeIndex=target.getAttribute("data-route");
    const roomIndex=target.getAttribute("data-room");
    const checkbox=target.type==="checkbox";
    if(field){
      let value=checkbox?target.checked:target.value;
      if(field==="columns")value=Math.max(1,Math.min(12,Number(value)||6));
      const config={...this._config,[field]:value};
      if(field==="default_player"&&!value)delete config.default_player;
      this.emit(config);
      return;
    }
    if(roomIndex!=null){
      const index=Number(roomIndex),rooms=this.rooms().map(r=>({...r}));
      const key=target.getAttribute("data-key");
      if(!Number.isInteger(index)||index<0||index>=rooms.length||!key)return;
      let value=checkbox?target.checked:target.value;
      if(["delay_ms","wake_delay_ms","power_delay_ms"].includes(key))value=Math.max(0,Math.min(key==="power_delay_ms"?30000:10000,Math.round(Number(value)||0)));
      if(key==="display"&&rooms[index].display!==value)rooms[index].source="";
      rooms[index][key]=value;
      this.emit({...this._config,rooms});
      return;
    }
    if(routeIndex==null)return;
    const key=target.getAttribute("data-key");
    const index=Number(routeIndex),routes=this.routes().map(r=>({...r}));
    if(!Number.isInteger(index)||index<0||index>=routes.length||!key)return;
    let value=checkbox?target.checked:target.value;
    if(key==="delay_ms"||key==="wake_delay_ms")value=Math.max(0,Math.min(10000,Math.round(Number(value)||0)));
    if(key==="display"&&routes[index].display!==value)routes[index].source="";
    routes[index][key]=value;
    this.emit({...this._config,display_routes:routes});
  }
  clickAction(event){
    const btn=event.target&&event.target.closest&&event.target.closest("button[data-action]");
    if(!btn)return;
    const action=btn.getAttribute("data-action");
    if(action==="add-room"||action==="remove-room"){
      const rooms=this.rooms().map(room=>({...room}));
      if(action==="add-room"){
        let number=rooms.length+1;
        while(rooms.some(room=>room.id==="room-"+number))number++;
        rooms.push({id:"room-"+number,name:"Room "+number,player:"",display:"",source:"",power_entity:"",volume_entity:"",turn_on:true,power_delay_ms:2000,wake_delay_ms:2000,delay_ms:1000});
      }else{
        const index=Number(btn.getAttribute("data-index"));
        if(!Number.isInteger(index)||index<0||index>=rooms.length)return;
        rooms.splice(index,1);
      }
      const default_room=rooms.some(room=>room.id===this._config.default_room)?this._config.default_room:(rooms[0]&&rooms[0].id)||"";
      this.emit({...this._config,rooms,default_room});
      return;
    }
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
    const cfg=this._config,routes=this.routes(),rooms=this.rooms();
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
      <section class="group"><h3>Rooms and device mappings</h3><p>Each room has its own playback player, optional physical TV, TV input, volume device and power helper. Pick a room from the card toolbar to route playback and volume to that room. A room without a mapped display uses its playback device directly.</p>
        <label>Default room<select data-field="default_room"><option value="">First configured room</option>${rooms.map(room=>'<option value="'+this.esc(room.id)+'" '+(room.id===cfg.default_room?'selected':'')+'>'+this.esc(room.name||room.id)+'</option>').join("")}</select></label>
        ${rooms.map((room,index)=>this.roomHtml(room,index)).join("")}
        <button class="add" type="button" data-action="add-room">+ Add room</button>
      </section>
      <section class="group"><h3>Playback device</h3><p>Choose the default device. The player selector remains available in the card’s top toolbar.</p>
        <label>Default player<select data-field="default_player">${this.playerOptions(cfg.default_player||cfg.entity||"")}</select></label>
      </section>
      <section class="group"><h3>Remote control</h3><div class="fields">
        <label class="switch"><input type="checkbox" data-field="show_remote" ${cfg.show_remote!==false?'checked':''}>Show control button</label>
        <label>Remote panel side<select data-field="remote_side"><option value="left" ${cfg.remote_side!=="right"?'selected':''}>Left</option><option value="right" ${cfg.remote_side==="right"?'selected':''}>Right</option></select></label>
      </div></section>
      <section class="group"><h3>HDMI and TV connections</h3><p>When you select a playback device, Nuvio can turn on its physical TV and switch to the connected HDMI input. This mapping is optional, and players without a connection are unchanged. Input choices come from the selected TV’s Home Assistant media sources; TVs without a source list allow manual input.</p>
        ${routes.map((route,index)=>this.routeHtml(route,index)).join("")}
        <button class="add" type="button" data-action="add">+ Add TV connection</button>
      </section>
    </div>`;
    this._rendered=true;
  }
}
if(!customElements.get("nuvio-card-editor"))customElements.define("nuvio-card-editor",NuvioCardEditor);

if(!customElements.get("nuvio-card"))customElements.define("nuvio-card",NuvioCard);
window.customCards=window.customCards||[];
if(!window.customCards.some(c=>c.type==="nuvio-card"))window.customCards.push({type:"nuvio-card",name:"Nuvio",description:"Browse, search and play your Nuvio catalog.",preview:true});
console.info("NUVIO-CARD v0.4.85");

// Nuvio popup button. Bundled after nuvio-card.js so HACS loads both card types
// through the existing versioned Lovelace module resource.
class NuvioPopupCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: "open"});
    this._config = {};
    this._hass = null;
    this._overlay = null;
    this._popupCard = null;
    this._autoCloseTimer = null;
    this._onKeydown = event => {
      if (event.key === "Escape" && this._overlay) {
        event.stopPropagation();
        this.closePopup();
      }
    };
  }
  static getConfigElement() { return document.createElement("nuvio-popup-card-editor"); }
  static getStubConfig() { return {button_label: "Nuvio", button_style: "horizontal", popup_width: "wide", popup_auto_close_minutes: 2}; }
  getCardSize() { return 2; }
  getGridOptions() { const tall = this.launcherStyle() === "vertical"; return {columns: tall ? 4 : 3, rows: tall ? 2 : 1, min_columns: 2, min_rows: tall ? 2 : 1}; }
launcherStyle() {
  // Old cards that saved an icon must keep showing that icon unless
  // their owner explicitly picks a different layout.
  const style = String(this._config.button_style || "").trim();
  if (["vertical", "horizontal", "logo_only", "icon_text"].includes(style)) return style;
  return String(this._config.button_icon || "").trim() ? "icon_text" : "horizontal";
}
  popupSize() { return ["normal", "wide", "fullscreen"].includes(this._config.popup_width) ? this._config.popup_width : "wide"; }
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
    this._config = {...config};
    this.render();
    if (this._overlay) this._overlay.dataset.size = this.popupSize();
    if (this._overlay && previousAutoClose !== this.popupAutoCloseMinutes()) this.startAutoCloseTimer();
    if (this._popupCard) this._popupCard.setConfig({...this._config, type: "custom:nuvio-card"});
  }
  set hass(value) {
    this._hass = value;
    if (this._popupCard) this._popupCard.hass = value;
  }
  render() {
  const label = String(this._config.button_label ?? "Nuvio");
  const icon = String(this._config.button_icon ?? "").trim();
  const style = this.launcherStyle();
  this.shadowRoot.innerHTML = `<style>
    :host{display:block;--popup-button-height:120px;height:120px!important;min-height:120px!important;max-height:120px!important;align-self:stretch;box-sizing:border-box}ha-card{display:block;width:100%;height:120px!important;min-height:120px!important;max-height:120px!important;box-sizing:border-box;border-radius:var(--ha-card-border-radius,14px);overflow:hidden}
    ha-card.launcher-vertical{height:120px!important;min-height:120px!important;max-height:120px!important}
    button{box-sizing:border-box;width:100%;height:120px!important;min-height:120px!important;max-height:120px!important;border:0;border-radius:inherit;padding:8px;display:flex;align-items:center;justify-content:center;gap:10px;cursor:pointer;background:transparent;color:var(--primary-text-color);font:inherit;font-weight:600}
    button:hover{background:var(--secondary-background-color)}button:focus-visible{outline:2px solid var(--primary-color);outline-offset:-3px}
    ha-icon{color:var(--primary-color);--mdc-icon-size:25px}
    .launcher-visual{min-width:0;display:flex;align-items:center;justify-content:center}
    .launcher-logo{display:block;width:120px;max-width:100%;height:auto;max-height:38px;object-fit:contain}
    .launcher-vertical-logo{display:block;width:auto;max-width:100%;height:104px;max-height:104px;object-fit:contain}
    .launcher-mark{display:block;width:auto;height:46px;max-width:100%;object-fit:contain}
    .launcher-caption{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .launcher-vertical button{flex-direction:column;gap:0;padding:8px}
    .launcher-vertical .launcher-caption{font-size:13px;line-height:17px;max-width:100%}
  </style><ha-card class="launcher-${style}"><button type="button" aria-label="Open Nuvio"><span class="launcher-visual"></span><span class="launcher-caption"></span></button></ha-card>`;
  const visual = this.shadowRoot.querySelector(".launcher-visual");
  if (style === "icon_text") {
    const selected = document.createElement("ha-icon");
    selected.setAttribute("icon", icon || "mdi:television-play");
    visual.appendChild(selected);
  } else {
    const logo = document.createElement("img");
    if (style === "vertical") {
      logo.className = "launcher-vertical-logo";
      logo.src = "/nuvio/assets/vertical.png?v=0.4.82";
    } else if (style === "logo_only") {
      logo.className = "launcher-mark";
      logo.src = "/nuvio/assets/icon-only.png?v=0.4.82";
    } else {
      logo.className = "launcher-logo";
      logo.src = "/nuvio/assets/wordmark.png?v=0.4.82";
    }
    logo.alt = "";
    logo.addEventListener("error", () => {
      const fallback = document.createElement("strong");
      fallback.textContent = style === "logo_only" ? "N" : "Nuvio";
      logo.replaceWith(fallback);
    });
    visual.appendChild(logo);
  }
  const caption = this.shadowRoot.querySelector(".launcher-caption");
  caption.textContent = label;
  // The uploaded vertical and logo-only assets already contain the complete
  // visual treatment. The horizontal wordmark also contains the default name.
  caption.style.display = ["vertical", "logo_only"].includes(style) || (style === "horizontal" && label.trim().toLowerCase() === "nuvio") ? "none" : "";
  this.shadowRoot.querySelector("button").addEventListener("click", () => this.openPopup());
}
  openPopup() {
    if (this._overlay) return;
    this._opener = this.shadowRoot.activeElement;
    const overlay = document.createElement("div");
    overlay.className = "nuvio-popup-overlay";
    overlay.dataset.size = this.popupSize();
    overlay.innerHTML = `<style>
      .nuvio-popup-overlay{position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.65);padding:12px;box-sizing:border-box}
      .nuvio-popup-frame{width:min(1440px,calc(100vw - 24px));max-width:calc(100vw - 24px);height:min(900px,calc(100dvh - 24px));max-height:calc(100dvh - 24px);min-width:0;display:flex;flex-direction:column;overflow:hidden;border-radius:18px;background:var(--card-background-color,var(--ha-card-background,#fff));color:var(--primary-text-color);box-shadow:0 20px 75px rgba(0,0,0,.4)}
      .nuvio-popup-overlay[data-size="normal"] .nuvio-popup-frame{width:min(900px,calc(100vw - 24px));height:min(700px,calc(100dvh - 24px))}
      .nuvio-popup-overlay[data-size="fullscreen"]{padding:0}
      .nuvio-popup-overlay[data-size="fullscreen"] .nuvio-popup-frame{width:100%;max-width:100%;height:100%;max-height:100%;border-radius:0}
      .nuvio-popup-top{height:48px;min-height:48px;box-sizing:border-box;flex:0 0 48px;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:0 12px 0 20px;border-bottom:1px solid var(--divider-color);font:600 16px var(--paper-font-body1_-_font-family,inherit)}
      .nuvio-popup-top button{box-sizing:border-box;flex:0 0 36px;width:36px;height:36px;display:grid;place-items:center;padding:0;border:0;border-radius:50%;cursor:pointer;background:var(--secondary-background-color);color:var(--primary-text-color)}
      .nuvio-popup-top button:focus-visible{outline:2px solid var(--primary-color)}
      .nuvio-popup-body{min-height:0;flex:1;overflow:auto;overscroll-behavior:contain}
      .nuvio-popup-body nuvio-card{display:block;min-height:100%}
      @media(max-width:600px){.nuvio-popup-overlay{padding:0}.nuvio-popup-frame,.nuvio-popup-overlay[data-size="normal"] .nuvio-popup-frame,.nuvio-popup-overlay[data-size="wide"] .nuvio-popup-frame{width:100%;max-width:100%;height:100%;max-height:100%;border-radius:0}.nuvio-popup-top{height:44px;min-height:44px;flex-basis:44px;padding:0 8px 0 12px}}
    </style><div class="nuvio-popup-frame" role="dialog" aria-modal="true" aria-label="Nuvio"><div class="nuvio-popup-top"><span>Nuvio</span><button type="button" aria-label="Close Nuvio popup"><ha-icon icon="mdi:close"></ha-icon></button></div><div class="nuvio-popup-body"></div></div>`;
    const content = overlay.querySelector(".nuvio-popup-body");
    const card = document.createElement("nuvio-card");
    this._overlay = overlay;
    this._popupCard = card;
    card.setConfig({...this._config, type: "custom:nuvio-card"});
    content.appendChild(card);
    (document.body || document.documentElement).appendChild(overlay);
    card.hass = this._hass;
    overlay.querySelector(".nuvio-popup-top button").addEventListener("click", () => this.closePopup());
    overlay.addEventListener("click", event => { if (event.target === overlay) this.closePopup(); });
    document.addEventListener("keydown", this._onKeydown, true);
    overlay.querySelector(".nuvio-popup-top button").focus();
    this.startAutoCloseTimer();
  }
  closePopup() {
    if (this._autoCloseTimer !== null) {
      clearTimeout(this._autoCloseTimer);
      this._autoCloseTimer = null;
    }
    document.removeEventListener("keydown", this._onKeydown, true);
    if (this._overlay) this._overlay.remove();
    this._overlay = null;
    this._popupCard = null;
    if (this._opener && this.isConnected) this._opener.focus();
    this._opener = null;
  }
  disconnectedCallback() { this.closePopup(); }
}

class NuvioPopupCardEditor extends HTMLElement {
  constructor() { super(); this.attachShadow({mode:"open"}); this._config={}; this._hass=null; }
  set hass(value) { this._hass=value; const editor=this.shadowRoot.querySelector("nuvio-card-editor"); if(editor) editor.hass=value; }
  setConfig(config) { this._config={...config}; this.render(); }
  emit(config) {
    this._config={...config,type:"custom:nuvio-popup-card"};
    this.dispatchEvent(new CustomEvent("config-changed", {detail:{config:{...this._config}},bubbles:true,composed:true}));
  }
  render() {
    this.shadowRoot.innerHTML=`<style>:host{display:block;color:var(--primary-text-color)}.popup-options{display:flex;gap:12px;flex-wrap:wrap;padding:12px 4px;border-bottom:1px solid var(--divider-color)}label{display:flex;flex:1 1 170px;flex-direction:column;gap:6px;font-size:13px}input{padding:10px;border:1px solid var(--divider-color);border-radius:9px;background:var(--secondary-background-color);color:var(--primary-text-color);font:inherit}</style><div class="popup-options"><label>Button label<input data-field="button_label" type="text"></label><label>Button icon (MDI, optional)<input data-field="button_icon" type="text" placeholder="mdi:television-play"><small>Used for Icon + text; leave blank for the default TV icon.</small></label><label>Button appearance<select data-field="button_style"><option value="vertical">Vertical logo</option><option value="horizontal">Horizontal logo</option><option value="logo_only">Logo only</option><option value="icon_text">Icon + text</option></select></label><label>Popup size<select data-field="popup_width"><option value="normal">Normal</option><option value="wide">Wide</option><option value="fullscreen">Full screen</option></select></label><label>Popup auto-close (minutes)<input data-field="popup_auto_close_minutes" type="number" min="0" step="any" value="2"><small>Default: 2 minutes after opening. Set 0 to disable.</small></label></div><nuvio-card-editor></nuvio-card-editor>`;
    for (const field of ["button_label","button_icon"]) {
      const input=this.shadowRoot.querySelector(`[data-field="${field}"]`);
      input.value=String(this._config[field] ?? (field==="button_label"?"Nuvio":""));
      input.addEventListener("change", () => this.emit({...this._config,[field]:input.value}));
    }
    const buttonStyle=this.shadowRoot.querySelector("select[data-field=button_style]");
  buttonStyle.value=["vertical","horizontal","logo_only","icon_text"].includes(this._config.button_style)
    ? this._config.button_style
    : (String(this._config.button_icon||"").trim()?"icon_text":"horizontal");
  buttonStyle.addEventListener("change",()=>this.emit({...this._config,button_style:buttonStyle.value}));
    const popupSize=this.shadowRoot.querySelector("select[data-field=popup_width]");
    popupSize.value=["normal","wide","fullscreen"].includes(this._config.popup_width)?this._config.popup_width:"wide";
    popupSize.addEventListener("change",()=>this.emit({...this._config,popup_width:popupSize.value}));
    const autoClose=this.shadowRoot.querySelector("input[data-field=popup_auto_close_minutes]");
    autoClose.value=String(this._config.popup_auto_close_minutes ?? 2);
    autoClose.addEventListener("change",()=>{
      const raw=autoClose.value.trim(),minutes=Number(raw);
      this.emit({...this._config,popup_auto_close_minutes:raw === "" || !Number.isFinite(minutes) || minutes < 0 ? 2 : minutes});
    });
    const editor=this.shadowRoot.querySelector("nuvio-card-editor");
    editor.addEventListener("config-changed", event => {event.stopPropagation();this.emit(event.detail.config);});
    editor.setConfig({...this._config,type:"custom:nuvio-card"});
    if(this._hass)editor.hass=this._hass;
  }
}
if(!customElements.get("nuvio-popup-card-editor"))customElements.define("nuvio-popup-card-editor",NuvioPopupCardEditor);
if(!customElements.get("nuvio-popup-card"))customElements.define("nuvio-popup-card",NuvioPopupCard);
window.customCards=window.customCards||[];
if(!window.customCards.some(card=>card.type==="nuvio-popup-card"))window.customCards.push({type:"nuvio-popup-card",name:"Nuvio Popup Button",description:"Open the full Nuvio catalog in a popup from a compact button.",preview:true});
