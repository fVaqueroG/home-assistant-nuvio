class NuvioCard extends HTMLElement {
  constructor(){
    super(); this.attachShadow({mode:"open"});
    this._config={}; this._hass=null; this._loaded=false; this._loading=false;
    this._sections=[]; this._hero=[]; this._heroIndex=0; this._homePrefs={}; this._results=[]; this._catalogSection=null; this._catalogItems=[]; this._catalogLoading=false; this._catalogReload=null; this._returnView="home"; this._playersMeta=[]; this._playerId=""; this._streams=[]; this._streamLoading=false; this._streamLoadingStage=""; this._streamContext=null; this._sourceRequest=0; this._addonFilter="all"; this._addonFilterExpanded=false; this._watchProviders=[]; this._watchProviderMeta={configured:false}; this._watchProvidersLoading=false; this._debridMeta={configured:false,provider:""}; this._resolving=new Set(); this._lazyCatalogLoads=new Set(); this._lazyObserver=null; this._remoteExpanded=false; this._view="home"; this._item=null; this._details=null; this._season=null; this._query=""; this._error="";
  }
  static getStubConfig(){ return {title:"Nuvio",columns:6,show_remote:true,remote_side:"left"}; }
  setConfig(c){ this._config=Object.assign({title:"Nuvio",columns:6,show_search:true,show_remote:true,remote_side:"left"},c||{}); this.render(); }
  set hass(h){ this._hass=h; if(!this._loaded&&!this._loading&&!this._homeRetryTimer&&(this._homeRetryCount||0)<3)this.loadHome(); }
  getCardSize(){ return 8; }
  ws(m){ return this._hass.connection.sendMessagePromise(m); }
  esc(v){ return String(v==null?"":v).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;"); }
  players(){ return this._playersMeta.length?this._playersMeta.map(x=>x.entity_id):(this._hass?Object.keys(this._hass.states).filter(x=>x.startsWith("media_player.")).sort():[]); }
  platform(id){ var p=this._playersMeta.find(x=>x.entity_id===id); return p?p.platform:""; }
  player(){ var s=this.shadowRoot&&this.shadowRoot.querySelector("#player"); return this._playerId||(s&&s.value)||this._config.default_player||this._config.entity||this.players()[0]||""; }
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
  async openCollection(folder,section){
    if(!folder)return;
    this._catalogReload=()=>this.openCollection(folder,section);
    var request=(this._catalogRequest||0)+1;this._catalogRequest=request;
    this._catalogSection={kind:"collection",name:folder.name,show_all_tab:section.show_all_tab};
    this._catalogItems=[];this._collectionTabs=[];this._collectionTab=section.show_all_tab===false?0:-1;
    this._catalogLoading=true;this._view="catalog";this._error="";this.render();
    var sources=Array.isArray(folder.sources)?folder.sources:[];
    var tabs=await Promise.all(sources.map(async source=>{
      var type=source.type||source.apiType||source.api_type||"movie";
      var tab={name:source.title||source.catalogName||source.catalog_name||this.homeTypeLabel(type),items:[],error:""};
      try{
        if(source.provider&&source.provider!=="addon")throw new Error("This folder source is not an addon catalog.");
        var base=source.addonBaseUrl||source.addon_base_url||source.baseUrl||source.base_url||source.addonUrl||source.url||"";
        var manifest=base?(base.replace(/\/+$/,"").endsWith("manifest.json")?base:base.replace(/\/+$/,"")+"/manifest.json"):"";
        var result=await this.ws({type:"nuvio/catalog",manifest_url:manifest,addon_id:source.addonId||source.addon_id||"",media_type:type,catalog_id:source.catalogId||source.catalog_id||"",genre:source.genre||"",hide_unreleased:this._homePrefs.hide_unreleased_content===true});
        tab.items=result.items||[];
      }catch(e){tab.error=e.message||"Could not load this catalog.";}
      return tab;
    }));
    if(request!==this._catalogRequest)return;
    this._collectionTabs=tabs;this._catalogLoading=false;
    if(!sources.length)this._error="This folder has no saved catalog sources.";
    this.selectCollectionTab(this._collectionTab);
  }
  selectCollectionTab(index){
    this._collectionTab=index;
    var tabs=index<0?(this._collectionTabs||[]):[(this._collectionTabs||[])[index]].filter(Boolean);
    var seen=new Set(),items=[];
    // Interleave movie/series sources in the All tab without duplicate titles.
    for(var n=0;n<Math.max(0,...tabs.map(t=>t.items.length));n++)for(var tab of tabs){
      var item=tab.items[n];if(!item)continue;var key=item.type+":"+item.id;
      if(!seen.has(key)){seen.add(key);items.push(item);}
    }
    this._catalogItems=items;
    if(tabs.length)this._error=tabs.filter(t=>t.error).map(t=>t.name+": "+t.error).join(" · ");
    this.render();
  }
  async openCatalog(section){
    if(!section||section.kind!=="catalog")return;
    this._catalogReload=()=>this.openCatalog(section);
    this._catalogRequest=(this._catalogRequest||0)+1;var request=this._catalogRequest;
    this._collectionTabs=null;this._catalogSection=section;
    this._catalogItems=Array.isArray(section.items)?section.items.slice():[];
    this._catalogLoading=true;
    this._view="catalog";
    this._error="";
    this.render();
    try{
      if(!section.manifest_url)throw new Error("This catalog is missing its addon reference. Refresh the card once after updating Nuvio.");
      var r=await this.ws({
        type:"nuvio/catalog",
        manifest_url:section.manifest_url,
        media_type:section.media_type||"movie",
        catalog_id:section.catalog_id,
        hide_unreleased:this._homePrefs.hide_unreleased_content===true
      });
      if(request!==this._catalogRequest)return;
      this._catalogItems=r.items||[];
      if(section.lazy===true){
        var limit=this._homePrefs.layout==="modern"?15:24;
        section.items=this._catalogItems.slice(0,limit);
        section.lazy=false;
        section.load_error="";
      }
    }catch(e){
      if(request!==this._catalogRequest)return;
      this._error=e.message||"Could not open this catalog.";
    }
    this._catalogLoading=false;
    this.render();
  }
  catalogView(){
    var s=this._catalogSection||{},cols=Number(this._config.columns)||6;
    var title=this.homeRowTitle(s)||s.name||"Catalog";
    var addon=s.addon?' <small>· '+this.esc(s.addon)+'</small>':"";
    return '<div class="top catalog-top"><button class="back" id="back">← Home</button><h3>'+this.esc(title)+addon+'</h3></div>'+
      (this._collectionTabs&&this._collectionTabs.length?'<div class="collection-tabs" role="group" aria-label="Catalog sources">'+(s.show_all_tab!==false&&this._collectionTabs.length>1?'<button class="action collection-tab '+(this._collectionTab<0?'primary':'')+'" data-tab="-1">All</button>':'')+this._collectionTabs.map((t,n)=>'<button class="action collection-tab '+(this._collectionTab===n?'primary':'')+'" data-tab="'+n+'">'+this.esc(t.name)+'</button>').join("")+'</div>':'')+
      (this._catalogLoading?'<div class="status">Loading catalog…</div>':
        (this._catalogItems.length?
          '<div class="grid catalog-grid" style="--cols:'+cols+'">'+this._catalogItems.map((x,i)=>this.card(x,"catalog",i)).join("")+'</div>':
          '<div class="status">No titles were returned by this catalog.</div>'));
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
    // No exact URL is available to Home Assistant for this row. Keep the
    // legacy behavior as a fallback: open Nuvio's source screen for the title.
    await this.play(false,this._streamContext||null);
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
      ? '<button class="ib toolbar-btn source-addon-toggle '+(this._addonFilterExpanded||this._addonFilter!=="all"?"toolbar-active":"")+'" id="addonsToggle" title="Filter sources by addon" aria-pressed="'+(this._addonFilterExpanded?"true":"false")+'"><ha-icon icon="mdi:filter-variant"></ha-icon><span>Addons</span></button>'
      : "";
    var remote=this._config.show_remote===false
      ? ""
      : '<button class="ib toolbar-btn remote-toggle-button '+(this._remoteExpanded?"remote-active":"")+'" title="Control" aria-label="Control"><ha-icon icon="mdi:remote-tv"></ha-icon><span>Control</span></button>';
    var home='<button class="ib toolbar-btn '+(onHome?"toolbar-active":"")+'" id="homeTop" title="Home" aria-label="Home"><ha-icon icon="mdi:home"></ha-icon><span>Home</span></button>';
    return '<div class="header"><h2>'+this.esc(this._config.title||"Nuvio")+'</h2><div class="tools">'+search+
      home+
      '<button class="ib toolbar-btn" id="refresh" title="Refresh" aria-label="Refresh"><ha-icon icon="mdi:refresh"></ha-icon><span>Refresh</span></button>'+
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
    return '<select id="player">'+this.players().map(id=>{var m=this._playersMeta.find(x=>x.entity_id===id),name=m?m.name:(((this._hass.states[id]||{}).attributes||{}).friendly_name||id),platform=m?m.platform:"";return '<option value="'+this.esc(id)+'" data-platform="'+this.esc(platform)+'" '+(id===selected?"selected":"")+'>'+this.esc(name)+(platform==="webostv"?" · LG webOS":platform==="androidtv"?" · Android TV (ADB)":platform==="androidtv_remote"?" · Android TV Remote":"")+'</option>';}).join("")+'</select>';
  }
  async remoteKey(key){
    var p=this.player();
    if(!p){this._error="Select a media player first.";this.render();return;}
    try{
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
        #nuvio-remote-portal .nuvio-ring-up{top:2px;left:44px}
        #nuvio-remote-portal .nuvio-ring-down{bottom:2px;left:44px}
        #nuvio-remote-portal .nuvio-ring-left{left:2px;top:44px}
        #nuvio-remote-portal .nuvio-ring-right{right:2px;top:44px}
        #nuvio-remote-portal .nuvio-ring-btn span{font-size:28px;line-height:1}
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
          #nuvio-remote-portal .nuvio-ring-up,
          #nuvio-remote-portal .nuvio-ring-down{left:39px}
          #nuvio-remote-portal .nuvio-ring-left,
          #nuvio-remote-portal .nuvio-ring-right{top:39px}
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
          <button class="nuvio-ring-btn nuvio-ring-up" data-remote-key="up" title="Up"><span>⌃</span></button>
          <button class="nuvio-ring-btn nuvio-ring-left" data-remote-key="left" title="Left"><span>‹</span></button>
          <button class="nuvio-ring-ok" data-remote-key="ok" title="OK">OK</button>
          <button class="nuvio-ring-btn nuvio-ring-right" data-remote-key="right" title="Right"><span>›</span></button>
          <button class="nuvio-ring-btn nuvio-ring-down" data-remote-key="down" title="Down"><span>⌄</span></button>
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
        <div class="nuvio-remote-footer">
          <button data-remote-key="back"><span>←</span><span>Back</span></button>
          <button data-remote-key="home"><span>⌂</span><span>Home</span></button>
        </div>
      </div>
    `;

    portal.querySelectorAll("[data-remote-key]").forEach(
      b=>b.addEventListener("click",()=>this.remoteKey(b.dataset.remoteKey))
    );
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
    return '<div class="hero" '+(bg?'style="background-image:url(&quot;'+this.esc(bg)+'&quot;)"':"")+'><div class="shade"></div><button class="back heroBack" id="back">← Catalog</button></div><div class="detail"><h2>'+this.esc(d.name||i.name)+'</h2><div class="meta">'+this.esc(d.releaseInfo||"")+(d.genres&&d.genres.length?' · '+this.esc(d.genres.join(", ")):"")+'</div>'+(d.description?'<p class="desc">'+this.esc(d.description)+'</p>':"")+'<div class="controls">'+this.playerSelect()+actions+'</div>'+(this._loading?'<div class="status">Loading details…</div>':episodeHtml)+'</div>';
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
      '<div class="top source-controls"><div class="source-title-row"><h3>Sources · '+this.esc(sub)+'</h3></div><div class="controls">'+this.playerSelect()+debridControls+'</div><div class="source-summary">'+summary+'</div></div>'+
      sourceBody;
  }
  styles(){
    return '<style>:host{display:block;--pw:min(150px,34vw)}ha-card{overflow:hidden;padding:0;color:var(--primary-text-color)}.header{display:flex;gap:12px;align-items:center;padding:16px 20px 12px;border-bottom:1px solid var(--divider-color);background:var(--card-background-color)}.header h2{margin:0;flex:1;min-width:0;font-size:22px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.tools,.controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.toolbar-btn{display:inline-flex;align-items:center;gap:6px}.toolbar-btn ha-icon{--mdc-icon-size:19px}.toolbar-active{background:color-mix(in srgb,var(--primary-color) 18%,var(--secondary-background-color))!important}.search{display:flex;align-items:center;background:var(--secondary-background-color);border-radius:18px;padding:0 9px;min-width:220px}.search input{border:0;outline:0;background:transparent;color:var(--primary-text-color);padding:9px;width:100%}.ib,.back,.action,.season{border:0;cursor:pointer;background:var(--secondary-background-color);color:var(--primary-text-color);border-radius:18px;padding:9px 13px}section{padding:8px 0 12px}section h3{margin:6px 20px 10px}.home-row-head{display:flex;align-items:center;gap:10px;margin:6px 20px 10px}.catalog-title{flex:1;min-width:0;text-align:left;border:0;background:transparent;color:var(--primary-text-color);font:inherit;font-size:1.17em;font-weight:600;padding:0;cursor:pointer}.catalog-title span{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.catalog-title small{font-size:11px;font-weight:400;color:var(--secondary-text-color)}.see-all{border:0;background:transparent;color:var(--primary-color);font:inherit;font-size:12px;font-weight:600;padding:5px 0 5px 8px;cursor:pointer;white-space:nowrap}.catalog-top h3{margin:12px 0 4px}.catalog-top small{font-weight:400;color:var(--secondary-text-color)}.rail{display:flex;gap:12px;overflow:auto;padding:0 20px 10px}.pc{width:var(--pw);min-width:var(--pw);border:0;background:none;color:inherit;text-align:left;padding:0;cursor:pointer}.poster{aspect-ratio:2/3;border-radius:12px;overflow:hidden;background:var(--secondary-background-color);position:relative}.poster img{width:100%;height:100%;object-fit:cover}.ph{height:100%;display:grid;place-items:center}.pt{font-weight:600;font-size:13px;margin-top:7px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.meta{display:flex;justify-content:space-between;gap:5px;color:var(--secondary-text-color);font-size:11px}.prog{position:absolute;left:6px;right:6px;bottom:6px;height:4px;background:#ffffff55}.prog i{display:block;height:100%;background:var(--primary-color)}.home-hero-stage{position:relative;padding:0 0 14px}.home-hero-card{position:relative;display:block;width:100%;height:340px;border:0;padding:0;overflow:hidden;background-size:cover;background-position:center;color:white;text-align:left;cursor:pointer}.home-hero-shade{position:absolute;inset:0;background:linear-gradient(90deg,rgba(0,0,0,.88) 0%,rgba(0,0,0,.60) 37%,rgba(0,0,0,.12) 72%),linear-gradient(0deg,var(--card-background-color) 0%,transparent 38%)}.home-hero-copy{position:absolute;left:22px;bottom:30px;max-width:min(520px,60%);z-index:1}.home-hero-copy h2{margin:0 0 8px;font-size:30px}.home-hero-copy p{margin:10px 0 0;line-height:1.4;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}.home-hero-logo{display:block;max-width:min(360px,75%);max-height:90px;object-fit:contain;object-position:left bottom;margin-bottom:10px}.home-hero-meta{font-size:13px;opacity:.9;margin-top:4px}.home-hero-nav{position:absolute;right:18px;bottom:26px;z-index:2;display:flex;align-items:center;gap:10px;padding:6px 9px;border-radius:24px;background:rgba(0,0,0,.55);color:white}.home-hero-dots{display:flex;gap:7px}.hero-arrow,.hero-pause{display:grid;place-items:center;width:32px;height:32px;padding:0;border:0;border-radius:50%;background:rgba(255,255,255,.12);color:white;cursor:pointer;font-size:26px}.hero-pause{font-size:15px}.hero-count{font-size:11px;white-space:nowrap}.home-hero-dot{width:8px;height:8px;border:0;border-radius:50%;padding:0;background:#ffffff66;cursor:pointer}.home-hero-dot.active{background:white;transform:scale(1.25)}.landscape-card{--pw:min(235px,53vw)}.landscape-card .poster{aspect-ratio:16/9}.collection-rail{align-items:flex-start}.collection-card{width:var(--pw);min-width:var(--pw);border:0;padding:0;background:none;color:inherit;cursor:pointer;font:inherit;text-align:left}.collection-card:focus-visible{outline:2px solid var(--primary-color);outline-offset:3px}.collection-tabs{display:flex;gap:8px;overflow:auto;padding:8px 20px}.collection-art{position:relative;aspect-ratio:1/1;border-radius:12px;overflow:hidden;background:var(--secondary-background-color)}.collection-card.shape-poster .collection-art{aspect-ratio:2/3}.collection-card.shape-landscape{width:min(235px,53vw);min-width:min(235px,53vw)}.collection-card.shape-landscape .collection-art{aspect-ratio:16/9}.collection-art img{width:100%;height:100%;object-fit:fill}.collection-emoji{height:100%;display:grid;place-items:center;font-size:42px;font-weight:700}.collection-title{position:absolute;left:0;right:0;bottom:0;padding:18px 8px 8px;text-align:center;font-size:12px;font-weight:700;color:white;background:linear-gradient(transparent,rgba(0,0,0,.8))}.lazy-rail{overflow:hidden}.lazy-card{width:var(--pw);min-width:var(--pw)}.lazy-poster{aspect-ratio:2/3;border-radius:12px;background:linear-gradient(100deg,var(--secondary-background-color) 25%,color-mix(in srgb,var(--secondary-background-color) 75%,var(--primary-text-color) 25%) 45%,var(--secondary-background-color) 65%);background-size:220% 100%;animation:nuvioShimmer 1.35s linear infinite}.lazy-line{height:12px;width:72%;border-radius:6px;margin-top:8px;background:var(--secondary-background-color)}.catalog-load-error{padding:8px 20px 20px;color:var(--secondary-text-color);font-size:12px}@keyframes nuvioShimmer{0%{background-position:180% 0}100%{background-position:-40% 0}}@media(prefers-reduced-motion:reduce){.lazy-poster{animation:none}}.status{padding:28px;text-align:center;color:var(--secondary-text-color)}.error{margin:10px 20px;padding:12px;border-radius:10px;background:var(--error-color);color:white}.top{padding:8px 20px}.grid{display:grid;grid-template-columns:repeat(var(--cols),minmax(0,1fr));gap:14px;padding:10px 20px 22px}.grid .pc{width:auto;min-width:0}.hero{height:270px;background-size:cover;background-position:center;position:relative}.shade{position:absolute;inset:0;background:linear-gradient(0deg,var(--card-background-color) 0%,transparent 90%)}.heroBack{position:absolute;top:16px;left:16px}.detail{position:relative;margin-top:-82px;padding:0 20px 22px}.detail h2{font-size:28px;margin:0 0 8px}.desc{max-width:850px;color:var(--secondary-text-color);line-height:1.45}.controls{margin:16px 0}.platform-note{flex-basis:100%;font-size:12px;color:var(--secondary-text-color);max-width:760px}.controls select{border:0;border-radius:18px;padding:9px 12px;background:var(--secondary-background-color);color:var(--primary-text-color)}.primary,.season.active{background:var(--primary-color);color:white}.seasons{display:flex;gap:8px;overflow:auto;margin:14px 0}.episodes{display:grid;gap:9px}.episode{display:grid;grid-template-columns:140px 1fr auto;gap:12px;align-items:center;width:100%;border:0;text-align:left;color:inherit;font:inherit;cursor:pointer;background:var(--secondary-background-color);padding:8px;border-radius:12px}.episode:hover,.episode:focus-visible{outline:2px solid color-mix(in srgb,var(--primary-color) 65%,transparent);outline-offset:1px}.episode img{width:140px;aspect-ratio:16/9;object-fit:cover;border-radius:8px}.episode h4,.episode p{margin:0}.episode p{font-size:12px;color:var(--secondary-text-color);margin-top:5px}.episode-chevron{font-size:28px;color:var(--secondary-text-color);padding:0 8px}.sources{display:grid;gap:18px;padding:0 20px 22px}.source-group{padding:0}.source-group-head{display:flex;align-items:center;gap:10px;margin:0 0 8px}.source-group-head img{width:34px;height:34px;object-fit:contain;border-radius:8px;background:var(--secondary-background-color)}.source-group-head h3{margin:0;font-size:16px}.source-group-head span,.source-summary{font-size:12px;color:var(--secondary-text-color)}.source-row{display:flex;gap:12px;align-items:center;justify-content:space-between;background:var(--secondary-background-color);padding:12px;border-radius:12px;margin-bottom:8px}.source-main{min-width:0;display:flex;flex:1;flex-direction:column;gap:6px}.source-label{font-weight:650;white-space:normal;overflow-wrap:anywhere}.source-description,.source-filename,.resolver{font-size:12px;color:var(--secondary-text-color);overflow-wrap:anywhere}.source-filename{opacity:.8}.stream-badges{display:flex;flex-wrap:wrap;gap:5px}.stream-badge{display:inline-flex;align-items:center;min-height:20px;padding:1px 7px;border-radius:10px;font-size:11px;font-weight:650;background:var(--card-background-color);border:1px solid var(--divider-color);white-space:nowrap}.badge-resolution{background:color-mix(in srgb,var(--primary-color) 20%,var(--card-background-color));border-color:color-mix(in srgb,var(--primary-color) 55%,var(--divider-color))}.badge-hdr,.badge-audio{background:color-mix(in srgb,var(--accent-color,var(--primary-color)) 14%,var(--card-background-color))}.badge-size,.badge-language{font-weight:500;color:var(--secondary-text-color)}.source-actions{flex:0 0 auto;max-width:260px;text-align:right;display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}.source-filter-bar{display:flex;gap:8px;overflow:auto;padding:10px 20px 4px;scrollbar-width:thin}.watch-provider-section{padding:4px 20px 12px}.watch-provider-heading{display:flex;align-items:end;justify-content:space-between;margin:0 0 8px}.watch-provider-heading h3{margin:0;font-size:15px}.watch-provider-heading span{font-size:11px;color:var(--secondary-text-color)}.watch-provider-rail{display:flex;gap:10px;overflow-x:auto;padding:2px 0 4px;scrollbar-width:thin}.watch-provider{width:78px;min-width:78px;border:0;border-radius:14px;background:var(--secondary-background-color);color:var(--primary-text-color);padding:8px 6px;display:flex;flex-direction:column;align-items:center;gap:5px;cursor:pointer}.watch-provider img,.watch-provider-fallback{width:44px;height:44px;border-radius:10px;object-fit:cover}.watch-provider-fallback{display:grid;place-items:center;background:var(--card-background-color);font-weight:700}.watch-provider-name{font-size:11px;line-height:1.15;text-align:center}.watch-provider-access{font-size:9px;color:var(--secondary-text-color);text-align:center}.watch-provider-link-source{font-size:8px;color:var(--secondary-text-color);text-align:center}.watch-provider.linked:hover{outline:2px solid var(--primary-color)}.watch-provider.availability-only{opacity:.52;cursor:default}.watch-provider-attribution{font-size:9px;color:var(--secondary-text-color);margin-top:5px}.watch-provider-loading{font-size:12px;color:var(--secondary-text-color);padding:14px 4px;white-space:nowrap}.source-filter-chip{border:0;cursor:pointer;background:var(--secondary-background-color);color:var(--primary-text-color);border-radius:18px;padding:8px 13px;white-space:nowrap;font:inherit;font-size:12px}.source-filter-chip.active{background:var(--primary-color);color:white}.source-top{padding-top:12px;padding-bottom:6px}.source-controls{padding-top:4px}.source-loading-status{padding-top:8px}.source-context{display:grid;grid-template-columns:auto minmax(0,1fr);gap:18px;align-items:center;margin:4px 20px 10px;padding:14px;border-radius:16px;background:linear-gradient(135deg,color-mix(in srgb,var(--secondary-background-color) 92%,transparent),color-mix(in srgb,var(--card-background-color) 96%,transparent));border:1px solid var(--divider-color);overflow:hidden}.source-context-art{overflow:hidden;border-radius:12px;background:var(--secondary-background-color);box-shadow:0 6px 18px rgba(0,0,0,.18)}.source-context-art img{display:block;width:100%;height:100%;object-fit:cover}.source-context-art.movie-art{width:112px;aspect-ratio:2/3}.source-context-art.episode-art{width:min(240px,30vw);aspect-ratio:16/9}.source-context-copy{min-width:0}.source-context-kicker{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--secondary-text-color);margin-bottom:4px}.source-context-copy h2{margin:0 0 7px;font-size:24px;line-height:1.15}.source-context-meta{font-size:12px;color:var(--secondary-text-color);line-height:1.4}.source-context-copy p{margin:10px 0 0;max-width:850px;color:var(--secondary-text-color);line-height:1.45;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}.source-title-row{display:flex;align-items:center;gap:8px;margin:8px 0}.source-title-row h3{margin:0}.remote-active{background:var(--primary-color)!important;color:white!important}.source-summary{margin-top:-8px;margin-bottom:6px}.debrid-note{font-size:12px;color:var(--secondary-text-color);max-width:520px}.resolvesource:disabled{opacity:.65;cursor:wait}.resolveall{font-size:12px}.nuvio-layout{position:relative;display:block;min-width:0}.nuvio-main{width:100%;min-width:0}.remote-shell{width:176px;border:1px solid var(--divider-color);border-radius:24px;padding:12px;background:color-mix(in srgb,var(--card-background-color) 94%,transparent);backdrop-filter:blur(18px);box-shadow:0 12px 36px rgba(0,0,0,.26)}.remote-head{display:flex;align-items:center;justify-content:space-between;font-size:12px;font-weight:700;color:var(--secondary-text-color);margin-bottom:10px}.remote-close{width:26px;height:26px;border:0;border-radius:13px;background:var(--secondary-background-color);color:var(--primary-text-color);display:grid;place-items:center;cursor:pointer}.remote-close ha-icon{--mdc-icon-size:16px}.wake-btn{width:100%;height:34px;border:0;border-radius:17px;background:var(--secondary-background-color);color:var(--primary-text-color);display:flex;align-items:center;justify-content:center;gap:6px;font-size:11px;cursor:pointer;margin-bottom:10px}.wake-btn ha-icon{--mdc-icon-size:18px}.remote-ring{position:relative;width:132px;height:132px;margin:0 auto 10px;border-radius:50%;background:radial-gradient(circle at center,var(--secondary-background-color) 0 34%,color-mix(in srgb,var(--secondary-background-color) 82%,var(--primary-color) 18%) 35% 100%);box-shadow:inset 0 0 0 1px var(--divider-color)}.remote-ring button{position:absolute;border:0;background:transparent;color:var(--primary-text-color);display:grid;place-items:center;cursor:pointer}.ring-btn{width:44px;height:44px;border-radius:50%!important}.ring-btn ha-icon{--mdc-icon-size:28px}.ring-btn.up{top:2px;left:44px}.ring-btn.down{bottom:2px;left:44px}.ring-btn.left{left:2px;top:44px}.ring-btn.right{right:2px;top:44px}.ring-ok{width:48px;height:48px;left:42px;top:42px;border-radius:50%!important;background:var(--primary-color)!important;color:white!important;font-size:11px;font-weight:800;box-shadow:0 3px 10px rgba(0,0,0,.22)}.remote-ring button:active,.wake-btn:active,.remote-footer button:active{transform:scale(.96)}.remote-footer{display:grid;grid-template-columns:1fr 1fr;gap:8px}.remote-footer button{height:38px;border:0;border-radius:14px;background:var(--secondary-background-color);color:var(--primary-text-color);display:flex;align-items:center;justify-content:center;gap:5px;font-size:11px;cursor:pointer}.remote-footer ha-icon{--mdc-icon-size:18px}.resolveall{font-size:12px}@media(max-width:700px){:host{--pw:120px}.remote-dialog{top:180px}.remote-shell{width:160px;padding:10px}.remote-ring{width:120px;height:120px}.ring-btn.up{left:38px}.ring-btn.down{left:38px}.ring-btn.left{top:38px}.ring-btn.right{top:38px}.ring-ok{left:36px;top:36px}.header{flex-direction:column;align-items:stretch}.search{min-width:0;flex:1}.grid{grid-template-columns:repeat(3,minmax(0,1fr))}.episode{grid-template-columns:95px 1fr}.episode img{width:95px}.playep{grid-column:2}.source-context{grid-template-columns:92px minmax(0,1fr);gap:12px;margin:4px 12px 10px;padding:10px}.source-context-art.movie-art{width:92px}.source-context-art.episode-art{width:92px;aspect-ratio:16/9}.source-context-copy h2{font-size:19px}.source-context-copy p{font-size:12px;-webkit-line-clamp:3}.source-row{align-items:flex-start;flex-direction:column}.source-actions{max-width:none;width:100%;text-align:left}.source-actions .action{width:100%}.home-hero-card{height:250px}.home-hero-copy{left:16px;bottom:22px;max-width:75%}.home-hero-copy h2{font-size:24px}.home-hero-nav{right:12px;bottom:20px;gap:7px}.home-hero-copy{bottom:80px}.home-hero-copy p{display:none}.hero{height:220px}}</style>';
  }
  wire(){
    var r=this.shadowRoot,q=r.querySelector("#search");
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
    r.querySelector("#player")?.addEventListener("change",e=>{this._playerId=e.target.value;this.render();});
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
    r.querySelectorAll(".pc").forEach(b=>b.addEventListener("click",()=>{var i;if(b.dataset.source==="search")i=this._results[Number(b.dataset.index)];else if(b.dataset.source==="catalog")i=this._catalogItems[Number(b.dataset.index)];else{var si=Number(b.dataset.source.slice(1));i=this._sections[si].items[Number(b.dataset.index)];}if(i)this.selectItem(i);}));
  }
  render(){
    if(!this.shadowRoot)return;var body=this._view==="details"?this.detailsView():(this._view==="sources"?this.sourcesView():(this._view==="search"?this.searchView():(this._view==="catalog"?this.catalogView():this.home())));
    var content=this._config.show_remote===false
      ? body
      : '<div class="nuvio-layout">'+this.remotePanel()+'<main class="nuvio-main">'+body+'</main></div>';
    this.shadowRoot.innerHTML=this.styles()+'<ha-card>'+this.header()+(this._error?'<div class="error">'+this.esc(this._error)+'</div>':"")+content+'</ha-card>';this.wire();
    this.observeLazyCatalogs();
    this.syncRemotePortal();
    this.updateRemoteButtons();
    this.syncHeroTimer();
  }
}
if(!customElements.get("nuvio-card"))customElements.define("nuvio-card",NuvioCard);
window.customCards=window.customCards||[];
if(!window.customCards.some(c=>c.type==="nuvio-card"))window.customCards.push({type:"nuvio-card",name:"Nuvio",description:"Browse, search and play your Nuvio catalog.",preview:true});
console.info("NUVIO-CARD v0.4.45");
