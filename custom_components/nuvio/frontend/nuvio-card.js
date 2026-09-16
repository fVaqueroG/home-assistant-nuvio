class NuvioCard extends HTMLElement {
  constructor(){
    super(); this.attachShadow({mode:"open"});
    this._config={}; this._hass=null; this._loaded=false; this._loading=false;
    this._sections=[]; this._results=[]; this._playersMeta=[]; this._playerId=""; this._streams=[]; this._streamLoading=false; this._streamContext=null; this._debridMeta={configured:false,provider:""}; this._resolving=new Set(); this._remoteExpanded=false; this._view="home"; this._item=null; this._details=null; this._season=null; this._query=""; this._error="";
  }
  static getStubConfig(){ return {title:"Nuvio",columns:6,show_remote:true,remote_side:"left"}; }
  setConfig(c){ this._config=Object.assign({title:"Nuvio",columns:6,show_search:true,show_remote:true,remote_side:"left"},c||{}); this.render(); }
  set hass(h){ this._hass=h; if(!this._loaded&&!this._loading)this.loadHome(); else this.render(); }
  getCardSize(){ return 8; }
  ws(m){ return this._hass.connection.sendMessagePromise(m); }
  esc(v){ return String(v==null?"":v).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;"); }
  players(){ return this._playersMeta.length?this._playersMeta.map(x=>x.entity_id):(this._hass?Object.keys(this._hass.states).filter(x=>x.startsWith("media_player.")).sort():[]); }
  platform(id){ var p=this._playersMeta.find(x=>x.entity_id===id); return p?p.platform:""; }
  player(){ var s=this.shadowRoot&&this.shadowRoot.querySelector("#player"); return this._playerId||(s&&s.value)||this._config.default_player||this._config.entity||this.players()[0]||""; }
  async loadHome(refresh=false){
    if(!this._hass)return; this._loading=true; this._error=""; this.render();
    try{ var r=await this.ws({type:"nuvio/home",refresh:refresh}); this._sections=r.sections||[]; this._playersMeta=r.players||[]; if(!this._playerId)this._playerId=this._config.default_player||this._config.entity||this.players()[0]||""; this._loaded=true; }
    catch(e){ this._error=e.message||"Could not load Nuvio."; }
    this._loading=false; this.render();
  }
  async search(){
    var q=this._query.trim(); if(!q){this._view="home";this.render();return;}
    this._view="search";this._loading=true;this._error="";this.render();
    try{var r=await this.ws({type:"nuvio/search",query:q});this._results=r.items||[];}
    catch(e){this._error=e.message||"Search failed.";}
    this._loading=false;this.render();
  }
  async selectItem(item){
    this._item=item;this._details=null;this._season=item.season==null?null:Number(item.season);this._view="details";this._error="";this.render();
    if(!item.manifest_url)return;
    this._loading=true;this.render();
    try{
      this._details=await this.ws({type:"nuvio/details",manifest_url:item.manifest_url,media_type:item.type,content_id:item.id});
      var ss=this.seasons(); if(ss.length&&!ss.includes(this._season))this._season=ss[0];
    }catch(e){this._error=e.message||"Could not load title details.";}
    this._loading=false;this.render();
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
  async showSources(ep=null){
    var videoId=this.streamVideoId(ep);
    if(!videoId){this._error="No video ID is available for this title.";this.render();return;}
    this._streamContext=ep;this._streams=[];this._streamLoading=true;this._view="sources";this._error="";this.render();
    try{
      var r=await this.ws({type:"nuvio/streams",media_type:this._item.type,video_id:videoId});
      this._streams=r.streams||[];this._debridMeta=r.debrid||{configured:false,provider:""};
    }catch(e){this._error=e.message||"Could not load stream sources.";}
    this._streamLoading=false;this.render();
  }
  inferMime(url){
    var u=String(url||"").toLowerCase();
    if(u.includes(".m3u8")||u.includes("m3u8"))return "application/vnd.apple.mpegurl";
    if(u.includes(".mpd"))return "application/dash+xml";
    if(u.includes(".mp4"))return "video/mp4";
    if(u.includes(".mkv"))return "video/x-matroska";
    return "video/*";
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
    var candidates=this._streams.map((s,i)=>({s,i})).filter(x=>!x.s.direct&&x.s.resolvable&&!x.s.requires_headers&&(x.s.info_hash||x.s.magnet_uri)).slice(0,6);
    for(var item of candidates)await this.resolveSource(item.i);
  }
  async playSource(stream){
    var p=this.player();if(!p){this._error="Select a media player first.";this.render();return;}
    if(!stream||!stream.url){this._error="This source needs Nuvio's internal torrent/debrid resolver and cannot be sent as a direct URL.";this.render();return;}
    try{
      await this._hass.callService("nuvio","play_source",{
        stream_url:stream.url,
        stream_title:stream.name||stream.title||stream.description||this._item.name||"Nuvio stream",
        mime_type:this.inferMime(stream.url)
      },{entity_id:p});
    }catch(e){this._error=e.message||"Direct source playback failed.";this.render();}
  }
  async playInNuvio(){
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
  poster(i){
    var u=i.poster||i.background;
    return u?'<img loading="lazy" src="'+this.esc(u)+'" alt="">':'<div class="ph"><ha-icon icon="mdi:movie-open"></ha-icon></div>';
  }
  card(i,source,index){
    var progress=i.duration>0?Math.min(100,Math.max(0,(i.position/i.duration)*100)):0;
    var ep=(i.season!=null&&i.episode!=null)?'<span>S'+this.esc(i.season)+' E'+this.esc(i.episode)+'</span>':"";
    return '<button class="pc" data-source="'+source+'" data-index="'+index+'"><div class="poster">'+this.poster(i)+(progress?'<div class="prog"><i style="width:'+progress+'%"></i></div>':"")+'</div><div class="pt">'+this.esc(i.name)+'</div><div class="meta">'+this.esc(i.releaseInfo||"")+ep+'</div></button>';
  }
  header(){
    var s=this._config.show_search===false?"":'<div class="search"><ha-icon icon="mdi:magnify"></ha-icon><input id="search" value="'+this.esc(this._query)+'" placeholder="Search Nuvio…"></div>';
    var remote=this._config.show_remote===false?"":'<button class="ib remote-toggle-button '+(this._remoteExpanded?"remote-active":"")+'" title="Remote"><ha-icon icon="mdi:remote-tv"></ha-icon></button>';
    return '<div class="header"><h2>'+this.esc(this._config.title)+'</h2><div class="tools">'+s+'<button class="ib" id="refresh" title="Refresh"><ha-icon icon="mdi:refresh"></ha-icon></button>'+remote+'</div></div>';
  }
  home(){
    if(this._loading&&!this._loaded)return '<div class="status">Loading Nuvio…</div>';
    if(!this._sections.length)return '<div class="status">No Nuvio catalogs were returned.</div>';
    return this._sections.map((s,si)=>'<section><h3>'+this.esc(s.name)+(s.addon?' <small>· '+this.esc(s.addon)+'</small>':"")+'</h3><div class="rail">'+(s.items||[]).map((x,i)=>this.card(x,"s"+si,i)).join("")+'</div></section>').join("");
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
  remotePanel(){
    if(this._config.show_remote===false||!this._remoteExpanded)return "";
    var side=String(this._config.remote_side||"left").toLowerCase()==="right"?"right":"left";
    return '<dialog class="remote-dialog remote-dialog-'+side+'" id="remoteDialog">'+
      '<div class="remote-shell">'+
        '<div class="remote-head"><span>TV Remote</span><button class="remote-close" id="remoteClose" title="Close"><ha-icon icon="mdi:close"></ha-icon></button></div>'+
        '<button class="wake-btn" data-remote-key="wake"><ha-icon icon="mdi:television"></ha-icon><span>Wake</span></button>'+
        '<div class="remote-ring">'+
          '<button class="ring-btn up" data-remote-key="up" title="Up"><ha-icon icon="mdi:chevron-up"></ha-icon></button>'+
          '<button class="ring-btn left" data-remote-key="left" title="Left"><ha-icon icon="mdi:chevron-left"></ha-icon></button>'+
          '<button class="ring-ok" data-remote-key="ok" title="OK">OK</button>'+
          '<button class="ring-btn right" data-remote-key="right" title="Right"><ha-icon icon="mdi:chevron-right"></ha-icon></button>'+
          '<button class="ring-btn down" data-remote-key="down" title="Down"><ha-icon icon="mdi:chevron-down"></ha-icon></button>'+
        '</div>'+
        '<div class="remote-footer">'+
          '<button data-remote-key="back" title="Back"><ha-icon icon="mdi:arrow-left"></ha-icon><span>Back</span></button>'+
          '<button data-remote-key="home" title="Home"><ha-icon icon="mdi:home"></ha-icon><span>Home</span></button>'+
        '</div>'+
      '</div>'+
    '</dialog>';
  }
  detailsView(){
    var i=this._item;if(!i)return "";var d=this._details||i,bg=d.background||d.poster||"",videos=(d.videos||[]);
    var seasons=this.seasons(),eps=videos.filter(v=>Number(v.season)===Number(this._season)).sort((a,b)=>(Number(a.episode)||0)-(Number(b.episode)||0));
    var episodeHtml="";
    if(d.type==="series"&&this._details){
      episodeHtml='<div class="seasons">'+seasons.map(s=>'<button class="season '+(Number(this._season)===s?"active":"")+'" data-season="'+s+'">Season '+s+'</button>').join("")+'</div><div class="episodes">'+eps.map((e,n)=>'<div class="episode">'+(e.thumbnail?'<img loading="lazy" src="'+this.esc(e.thumbnail)+'" alt="">':'<div></div>')+'<div><h4>E'+this.esc(e.episode||"")+' · '+this.esc(e.title||("Episode "+(e.episode||"")))+'</h4>'+(e.overview?'<p>'+this.esc(e.overview)+'</p>':"")+'</div><div class="episode-actions"><button class="action playep" data-ep="'+n+'">▶ Play</button><button class="action primary sourceep" data-ep="'+n+'">Sources</button></div></div>').join("")+'</div>';
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
  sourcesView(){
    var ep=this._streamContext,d=this._details||this._item,title=d.name||this._item.name||"Nuvio";
    var sub=ep?("S"+(ep.season||"")+" E"+(ep.episode||"")+" · "+(ep.title||"Episode")):"Movie";
    var groups=new Map();
    this._streams.forEach((s,n)=>{
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
        var directUrl=s.url||"";
        var torrentLink=s.magnet_uri||"";
        var linkHtml="";
        var canResolve=!!s.resolvable&&!s.requires_headers&&(s.info_hash||s.magnet_uri);
        var resolving=this._resolving.has(n);
        var nuvioButton='<button class="action nuvioplay" data-source-index="'+n+'">Open in Nuvio</button>';
        var actionHtml=s.direct
          ? '<button class="action primary playsource" data-source-index="'+n+'">▶ Play on TV</button>'+nuvioButton+'<button class="action copylink" data-source-index="'+n+'">Copy link</button>'
          : canResolve
            ? '<button class="action primary playdirect" data-source-index="'+n+'" '+(resolving?"disabled":"")+'>'+(resolving?"Resolving…":"▶ Play on TV")+'</button>'+nuvioButton+'<button class="action resolvesource" data-source-index="'+n+'" '+(resolving?"disabled":"")+'">Resolve only</button>'+(torrentLink?'<button class="action copytorrent" data-source-index="'+n+'">Copy magnet</button>':"")
            : nuvioButton+'<span class="resolver">'+this.esc(unavailable)+'</span>'+(torrentLink?'<button class="action copytorrent" data-source-index="'+n+'">Copy magnet</button>':"");
        return '<div class="source-row">'+
          '<div class="source-main">'+
            '<div class="source-label">'+this.esc(label)+'</div>'+
            '<div class="stream-badges">'+badgeHtml(s)+'</div>'+
            (secondary?'<div class="source-description">'+this.esc(secondary)+'</div>':"")+
            (filename?'<div class="source-filename">'+this.esc(filename)+'</div>':"")+
            linkHtml+
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
    var unresolved=this._streams.filter(s=>!s.direct&&s.resolvable&&!s.requires_headers&&(s.info_hash||s.magnet_uri)).length;
    var debridControls=unresolved
      ? (this._debridMeta.configured
          ? '<button class="action resolveall" id="resolveAll">Resolve up to 6 links · '+this.esc((this._debridMeta.providers||[]).join(", ")||this._debridMeta.provider||"Nuvio debrid")+'</button>'
          : '<span class="debrid-note">Open in Nuvio opens Nuvio\'s source picker for this title/episode. Play direct plays the exact source selected here.</span>')
      : "";
    var remoteButton=this._config.show_remote===false?"":'<button class="ib remote-toggle-button '+(this._remoteExpanded?"remote-active":"")+'" title="Remote"><ha-icon icon="mdi:remote-tv"></ha-icon></button>';
    return '<div class="top source-top"><button class="back" id="backDetails">← '+this.esc(title)+'</button><div class="source-title-row"><h3>Sources · '+this.esc(sub)+'</h3>'+remoteButton+'</div><div class="controls">'+this.playerSelect()+debridControls+'</div><div class="source-summary">'+this._streams.length+' source'+(this._streams.length===1?"":"s")+' from '+groups.size+' addon'+(groups.size===1?"":"s")+(unresolved?' · '+unresolved+' resolvable':"")+'</div></div>'+
      (this._streamLoading?'<div class="status">Loading sources…</div>':(groupHtml?'<div class="sources">'+groupHtml+'</div>':'<div class="status">No sources were returned by your configured Nuvio addons.</div>'));
  }
  styles(){
    return '<style>:host{display:block;--pw:min(150px,34vw)}ha-card{overflow:hidden;padding:0;color:var(--primary-text-color)}.header{display:flex;gap:12px;align-items:center;padding:18px 20px 8px}.header h2{margin:0;flex:1;font-size:22px}.tools,.controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.search{display:flex;align-items:center;background:var(--secondary-background-color);border-radius:18px;padding:0 9px;min-width:220px}.search input{border:0;outline:0;background:transparent;color:var(--primary-text-color);padding:9px;width:100%}.ib,.back,.action,.season{border:0;cursor:pointer;background:var(--secondary-background-color);color:var(--primary-text-color);border-radius:18px;padding:9px 13px}section{padding:8px 0 12px}section h3{margin:6px 20px 10px}.rail{display:flex;gap:12px;overflow:auto;padding:0 20px 10px}.pc{width:var(--pw);min-width:var(--pw);border:0;background:none;color:inherit;text-align:left;padding:0;cursor:pointer}.poster{aspect-ratio:2/3;border-radius:12px;overflow:hidden;background:var(--secondary-background-color);position:relative}.poster img{width:100%;height:100%;object-fit:cover}.ph{height:100%;display:grid;place-items:center}.pt{font-weight:600;font-size:13px;margin-top:7px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.meta{display:flex;justify-content:space-between;gap:5px;color:var(--secondary-text-color);font-size:11px}.prog{position:absolute;left:6px;right:6px;bottom:6px;height:4px;background:#ffffff55}.prog i{display:block;height:100%;background:var(--primary-color)}.status{padding:28px;text-align:center;color:var(--secondary-text-color)}.error{margin:10px 20px;padding:12px;border-radius:10px;background:var(--error-color);color:white}.top{padding:8px 20px}.grid{display:grid;grid-template-columns:repeat(var(--cols),minmax(0,1fr));gap:14px;padding:10px 20px 22px}.grid .pc{width:auto;min-width:0}.hero{height:270px;background-size:cover;background-position:center;position:relative}.shade{position:absolute;inset:0;background:linear-gradient(0deg,var(--card-background-color) 0%,transparent 90%)}.heroBack{position:absolute;top:16px;left:16px}.detail{position:relative;margin-top:-82px;padding:0 20px 22px}.detail h2{font-size:28px;margin:0 0 8px}.desc{max-width:850px;color:var(--secondary-text-color);line-height:1.45}.controls{margin:16px 0}.platform-note{flex-basis:100%;font-size:12px;color:var(--secondary-text-color);max-width:760px}.controls select{border:0;border-radius:18px;padding:9px 12px;background:var(--secondary-background-color);color:var(--primary-text-color)}.primary,.season.active{background:var(--primary-color);color:white}.seasons{display:flex;gap:8px;overflow:auto;margin:14px 0}.episodes{display:grid;gap:9px}.episode{display:grid;grid-template-columns:140px 1fr auto;gap:12px;align-items:center;background:var(--secondary-background-color);padding:8px;border-radius:12px}.episode img{width:140px;aspect-ratio:16/9;object-fit:cover;border-radius:8px}.episode h4,.episode p{margin:0}.episode p{font-size:12px;color:var(--secondary-text-color);margin-top:5px}.episode-actions{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}.sources{display:grid;gap:18px;padding:0 20px 22px}.source-group{padding:0}.source-group-head{display:flex;align-items:center;gap:10px;margin:0 0 8px}.source-group-head img{width:34px;height:34px;object-fit:contain;border-radius:8px;background:var(--secondary-background-color)}.source-group-head h3{margin:0;font-size:16px}.source-group-head span,.source-summary{font-size:12px;color:var(--secondary-text-color)}.source-row{display:flex;gap:12px;align-items:center;justify-content:space-between;background:var(--secondary-background-color);padding:12px;border-radius:12px;margin-bottom:8px}.source-main{min-width:0;display:flex;flex:1;flex-direction:column;gap:6px}.source-label{font-weight:650;white-space:normal;overflow-wrap:anywhere}.source-description,.source-filename,.resolver{font-size:12px;color:var(--secondary-text-color);overflow-wrap:anywhere}.source-filename{opacity:.8}.stream-badges{display:flex;flex-wrap:wrap;gap:5px}.stream-badge{display:inline-flex;align-items:center;min-height:20px;padding:1px 7px;border-radius:10px;font-size:11px;font-weight:650;background:var(--card-background-color);border:1px solid var(--divider-color);white-space:nowrap}.badge-resolution{background:color-mix(in srgb,var(--primary-color) 20%,var(--card-background-color));border-color:color-mix(in srgb,var(--primary-color) 55%,var(--divider-color))}.badge-hdr,.badge-audio{background:color-mix(in srgb,var(--accent-color,var(--primary-color)) 14%,var(--card-background-color))}.badge-size,.badge-language{font-weight:500;color:var(--secondary-text-color)}.source-actions{flex:0 0 auto;max-width:260px;text-align:right;display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}.source-top{padding-top:16px}.source-title-row{display:flex;align-items:center;gap:8px;margin:8px 0}.source-title-row h3{margin:0}.remote-active{background:var(--primary-color)!important;color:white!important}.source-summary{margin-top:-8px;margin-bottom:6px}.debrid-note{font-size:12px;color:var(--secondary-text-color);max-width:520px}.resolvesource:disabled{opacity:.65;cursor:wait}.resolveall{font-size:12px}.nuvio-layout{position:relative;display:block;min-width:0}.nuvio-main{width:100%;min-width:0}.remote-dialog{position:fixed;top:96px;margin:0;border:0;padding:0;background:transparent;color:inherit;max-width:none;max-height:none;overflow:visible}.remote-dialog-left{left:12px;right:auto}.remote-dialog-right{right:12px;left:auto}.remote-dialog::backdrop{background:rgba(0,0,0,.18)}.remote-shell{width:176px;border:1px solid var(--divider-color);border-radius:24px;padding:12px;background:color-mix(in srgb,var(--card-background-color) 94%,transparent);backdrop-filter:blur(18px);box-shadow:0 12px 36px rgba(0,0,0,.26)}.remote-head{display:flex;align-items:center;justify-content:space-between;font-size:12px;font-weight:700;color:var(--secondary-text-color);margin-bottom:10px}.remote-close{width:26px;height:26px;border:0;border-radius:13px;background:var(--secondary-background-color);color:var(--primary-text-color);display:grid;place-items:center;cursor:pointer}.remote-close ha-icon{--mdc-icon-size:16px}.wake-btn{width:100%;height:34px;border:0;border-radius:17px;background:var(--secondary-background-color);color:var(--primary-text-color);display:flex;align-items:center;justify-content:center;gap:6px;font-size:11px;cursor:pointer;margin-bottom:10px}.wake-btn ha-icon{--mdc-icon-size:18px}.remote-ring{position:relative;width:132px;height:132px;margin:0 auto 10px;border-radius:50%;background:radial-gradient(circle at center,var(--secondary-background-color) 0 34%,color-mix(in srgb,var(--secondary-background-color) 82%,var(--primary-color) 18%) 35% 100%);box-shadow:inset 0 0 0 1px var(--divider-color)}.remote-ring button{position:absolute;border:0;background:transparent;color:var(--primary-text-color);display:grid;place-items:center;cursor:pointer}.ring-btn{width:44px;height:44px;border-radius:50%!important}.ring-btn ha-icon{--mdc-icon-size:28px}.ring-btn.up{top:2px;left:44px}.ring-btn.down{bottom:2px;left:44px}.ring-btn.left{left:2px;top:44px}.ring-btn.right{right:2px;top:44px}.ring-ok{width:48px;height:48px;left:42px;top:42px;border-radius:50%!important;background:var(--primary-color)!important;color:white!important;font-size:11px;font-weight:800;box-shadow:0 3px 10px rgba(0,0,0,.22)}.remote-ring button:active,.wake-btn:active,.remote-footer button:active{transform:scale(.96)}.remote-footer{display:grid;grid-template-columns:1fr 1fr;gap:8px}.remote-footer button{height:38px;border:0;border-radius:14px;background:var(--secondary-background-color);color:var(--primary-text-color);display:flex;align-items:center;justify-content:center;gap:5px;font-size:11px;cursor:pointer}.remote-footer ha-icon{--mdc-icon-size:18px}.resolveall{font-size:12px}@media(max-width:700px){:host{--pw:120px}.remote-shell{width:160px;padding:10px}.remote-ring{width:120px;height:120px}.ring-btn.up{left:38px}.ring-btn.down{left:38px}.ring-btn.left{top:38px}.ring-btn.right{top:38px}.ring-ok{left:36px;top:36px}.header{flex-direction:column;align-items:stretch}.search{min-width:0;flex:1}.grid{grid-template-columns:repeat(3,minmax(0,1fr))}.episode{grid-template-columns:95px 1fr}.episode img{width:95px}.playep{grid-column:2}.source-row{align-items:flex-start;flex-direction:column}.source-actions{max-width:none;width:100%;text-align:left}.source-actions .action{width:100%}.hero{height:220px}}</style>';
  }
  wire(){
    var r=this.shadowRoot,q=r.querySelector("#search");
    if(q){q.addEventListener("input",e=>this._query=e.target.value);q.addEventListener("keydown",e=>{if(e.key==="Enter")this.search();});}
    r.querySelector("#refresh")?.addEventListener("click",()=>{this._loaded=false;this.loadHome(true);});
    r.querySelectorAll("[data-remote-key]").forEach(b=>b.addEventListener("click",()=>this.remoteKey(b.dataset.remoteKey)));
    r.querySelectorAll(".remote-toggle-button").forEach(b=>b.addEventListener("click",()=>{this._remoteExpanded=!this._remoteExpanded;this.render();}));
    r.querySelector("#remoteClose")?.addEventListener("click",()=>{this._remoteExpanded=false;this.render();});
    r.querySelector("#back")?.addEventListener("click",()=>{this._view="home";this._error="";this.render();});
    r.querySelector("#open")?.addEventListener("click",()=>this.play(true,null));
    r.querySelector("#play")?.addEventListener("click",()=>this.play(false,null));
    r.querySelector("#sources")?.addEventListener("click",()=>this.showSources(null));
    r.querySelector("#player")?.addEventListener("change",e=>{this._playerId=e.target.value;this.render();});
    r.querySelectorAll(".season").forEach(b=>b.addEventListener("click",()=>{this._season=Number(b.dataset.season);this.render();}));
    r.querySelectorAll(".playep").forEach(b=>b.addEventListener("click",()=>{var eps=(this._details.videos||[]).filter(v=>Number(v.season)===Number(this._season)).sort((a,c)=>(Number(a.episode)||0)-(Number(c.episode)||0));this.play(false,eps[Number(b.dataset.ep)]);}));
    r.querySelectorAll(".sourceep").forEach(b=>b.addEventListener("click",()=>{var eps=(this._details.videos||[]).filter(v=>Number(v.season)===Number(this._season)).sort((a,c)=>(Number(a.episode)||0)-(Number(c.episode)||0));this.showSources(eps[Number(b.dataset.ep)]);}));
    r.querySelectorAll(".playsource").forEach(b=>b.addEventListener("click",()=>this.playSource(this._streams[Number(b.dataset.sourceIndex)])));
    r.querySelectorAll(".nuvioplay").forEach(b=>b.addEventListener("click",()=>this.playInNuvio()));
    r.querySelectorAll(".playdirect").forEach(b=>b.addEventListener("click",()=>this.playDirectIndex(Number(b.dataset.sourceIndex))));
    r.querySelectorAll(".resolvesource").forEach(b=>b.addEventListener("click",()=>this.resolveSource(Number(b.dataset.sourceIndex))));
    r.querySelector("#resolveAll")?.addEventListener("click",()=>this.resolveVisibleSources());
    r.querySelectorAll("button.openlink").forEach(b=>b.addEventListener("click",()=>this.openSourceLink(this._streams[Number(b.dataset.sourceIndex)])));
    r.querySelectorAll(".copylink").forEach(b=>b.addEventListener("click",()=>this.copyText((this._streams[Number(b.dataset.sourceIndex)]||{}).url)));
    r.querySelectorAll(".copytorrent").forEach(b=>b.addEventListener("click",()=>this.copyText((this._streams[Number(b.dataset.sourceIndex)]||{}).magnet_uri)));
    r.querySelector("#backDetails")?.addEventListener("click",()=>{this._view="details";this._error="";this.render();});
    r.querySelectorAll(".pc").forEach(b=>b.addEventListener("click",()=>{var i;if(b.dataset.source==="search")i=this._results[Number(b.dataset.index)];else{var si=Number(b.dataset.source.slice(1));i=this._sections[si].items[Number(b.dataset.index)];}if(i)this.selectItem(i);}));
  }
  render(){
    if(!this.shadowRoot)return;var body=this._view==="details"?this.detailsView():(this._view==="sources"?this.sourcesView():(this._view==="search"?this.searchView():this.home()));
    var content=this._config.show_remote===false
      ? body
      : '<div class="nuvio-layout">'+this.remotePanel()+'<main class="nuvio-main">'+body+'</main></div>';
    this.shadowRoot.innerHTML=this.styles()+'<ha-card>'+(this._view==="home"?this.header():"")+(this._error?'<div class="error">'+this.esc(this._error)+'</div>':"")+content+'</ha-card>';this.wire();
    var dlg=this.shadowRoot.querySelector("#remoteDialog");
    if(dlg&&!dlg.open){
      try{dlg.showModal();}catch(e){try{dlg.show();}catch(_e){}}
      dlg.addEventListener("click",e=>{if(e.target===dlg){this._remoteExpanded=false;this.render();}});
      dlg.addEventListener("cancel",e=>{e.preventDefault();this._remoteExpanded=false;this.render();});
    }
  }
}
if(!customElements.get("nuvio-card"))customElements.define("nuvio-card",NuvioCard);
window.customCards=window.customCards||[];
if(!window.customCards.some(c=>c.type==="nuvio-card"))window.customCards.push({type:"nuvio-card",name:"Nuvio",description:"Browse, search and play your Nuvio catalog.",preview:true});
console.info("NUVIO-CARD v0.4.9");
