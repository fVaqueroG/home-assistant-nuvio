class NuvioCard extends HTMLElement {
  constructor(){
    super(); this.attachShadow({mode:"open"});
    this._config={}; this._hass=null; this._loaded=false; this._loading=false;
    this._sections=[]; this._hero=[]; this._heroIndex=0; this._homePrefs={}; this._results=[]; this._playersMeta=[]; this._playerId=""; this._streams=[]; this._streamLoading=false; this._streamContext=null; this._debridMeta={configured:false,provider:""}; this._resolving=new Set(); this._remoteExpanded=false; this._view="home"; this._item=null; this._details=null; this._season=null; this._query=""; this._error="";
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
    try{ var r=await this.ws({type:"nuvio/home",refresh:refresh}); this._sections=r.sections||[]; this._hero=((r.hero||{}).enabled===false?[]:((r.hero||{}).items||[])); this._heroIndex=Math.min(this._heroIndex,Math.max(0,this._hero.length-1)); this._homePrefs=r.preferences||{}; this._playersMeta=r.players||[]; if(!this._playerId)this._playerId=this._config.default_player||this._config.entity||this.players()[0]||""; this._loaded=true; }
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
  sourcePlaybackData(stream,inNuvio=false){
    var ep=this._streamContext||null;
    var data=this.playData(ep);
    data.stream_url=stream.url;
    data.stream_title=stream.name||stream.title||stream.description||data.title||"Nuvio stream";
    data.mime_type=this.inferMime(stream.url);
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
  async playInNuvioIndex(index){
    var s=this._streams[index];if(!s)return;
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
  collectionCard(i){
    var shape=String(i.posterShape||"SQUARE").toUpperCase();
    var image=i.poster?'<img loading="lazy" src="'+this.esc(i.poster)+'" alt="">':(i.cover_emoji?'<div class="collection-emoji">'+this.esc(i.cover_emoji)+'</div>':'<div class="collection-emoji">'+this.esc(String(i.name||"").slice(0,2).toUpperCase())+'</div>');
    var title=i.hide_title?"":'<div class="collection-title">'+this.esc(i.name)+'</div>';
    return '<div class="collection-card shape-'+this.esc(shape.toLowerCase())+'"><div class="collection-art">'+image+title+'</div></div>';
  }
  hero(){
    if(this._homePrefs.hero_section_enabled===false||!this._hero.length)return "";
    var i=this._hero[this._heroIndex]||this._hero[0],bg=i.background||i.landscapePoster||i.poster||"";
    var meta=[i.releaseInfo||"",i.runtime||""].filter(Boolean).join(" · ");
    var genres=(i.genres||[]).slice(0,3).join(" · ");
    var logo=i.logo?'<img class="home-hero-logo" src="'+this.esc(i.logo)+'" alt="'+this.esc(i.name||"")+'">':'<h2>'+this.esc(i.name||"")+'</h2>';
    var dots=this._hero.length>1?'<div class="home-hero-dots">'+this._hero.map((_,n)=>'<button class="home-hero-dot '+(n===this._heroIndex?"active":"")+'" data-hero-index="'+n+'" aria-label="Hero '+(n+1)+'"></button>').join("")+'</div>':"";
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
  header(){
    var s=this._config.show_search===false?"":'<div class="search"><ha-icon icon="mdi:magnify"></ha-icon><input id="search" value="'+this.esc(this._query)+'" placeholder="Search Nuvio…"></div>';
    var remote=this._config.show_remote===false?"":'<button class="ib remote-toggle-button '+(this._remoteExpanded?"remote-active":"")+'" title="Remote"><ha-icon icon="mdi:remote-tv"></ha-icon></button>';
    return '<div class="header"><h2>'+this.esc(this._config.title)+'</h2><div class="tools">'+s+'<button class="ib" id="refresh" title="Refresh"><ha-icon icon="mdi:refresh"></ha-icon></button>'+remote+'</div></div>';
  }
  home(){
    if(this._loading&&!this._loaded)return '<div class="status">Loading Nuvio…</div>';
    if(!this._sections.length&&!this._hero.length)return '<div class="status">No Nuvio Home content was returned.</div>';
    var rows=this._sections.map((s,si)=>{
      var title=this.homeRowTitle(s);
      if(s.kind==="collection"){
        return '<section class="collection-section"><h3>'+this.esc(title)+'</h3><div class="rail collection-rail">'+(s.items||[]).map(x=>this.collectionCard(x)).join("")+'</div></section>';
      }
      var addon=(s.kind==="catalog"&&this._homePrefs.show_catalog_addon_name!==false&&s.addon)
        ? '<small>from '+this.esc(s.addon)+'</small>'
        : "";
      var showLabels=s.kind!=="catalog"||this._homePrefs.show_poster_labels!==false;
      var landscape=s.kind==="catalog"&&this._homePrefs.layout==="modern"&&this._homePrefs.modern_landscape_posters_enabled===true;
      if(s.kind==="continue"&&this._homePrefs.use_episode_thumbnails_in_cw===true)landscape=true;
      return '<section><h3>'+this.esc(title)+(addon?' '+addon:"")+'</h3><div class="rail">'+(s.items||[]).map((x,i)=>this.card(x,"s"+si,i,{showLabels:showLabels,preferLandscape:landscape})).join("")+'</div></section>';
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
    this.removeRemotePortal();
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
        var nuvioButton='<button class="action nuvioplay" data-source-index="'+n+'">'+((s.direct||canResolve)?"▶ Play in Nuvio":"Open in Nuvio")+'</button>';
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
    return '<style>:host{display:block;--pw:min(150px,34vw)}ha-card{overflow:hidden;padding:0;color:var(--primary-text-color)}.header{display:flex;gap:12px;align-items:center;padding:18px 20px 8px}.header h2{margin:0;flex:1;font-size:22px}.tools,.controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.search{display:flex;align-items:center;background:var(--secondary-background-color);border-radius:18px;padding:0 9px;min-width:220px}.search input{border:0;outline:0;background:transparent;color:var(--primary-text-color);padding:9px;width:100%}.ib,.back,.action,.season{border:0;cursor:pointer;background:var(--secondary-background-color);color:var(--primary-text-color);border-radius:18px;padding:9px 13px}section{padding:8px 0 12px}section h3{margin:6px 20px 10px}.rail{display:flex;gap:12px;overflow:auto;padding:0 20px 10px}.pc{width:var(--pw);min-width:var(--pw);border:0;background:none;color:inherit;text-align:left;padding:0;cursor:pointer}.poster{aspect-ratio:2/3;border-radius:12px;overflow:hidden;background:var(--secondary-background-color);position:relative}.poster img{width:100%;height:100%;object-fit:cover}.ph{height:100%;display:grid;place-items:center}.pt{font-weight:600;font-size:13px;margin-top:7px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.meta{display:flex;justify-content:space-between;gap:5px;color:var(--secondary-text-color);font-size:11px}.prog{position:absolute;left:6px;right:6px;bottom:6px;height:4px;background:#ffffff55}.prog i{display:block;height:100%;background:var(--primary-color)}.home-hero-stage{position:relative;padding:0 0 14px}.home-hero-card{position:relative;display:block;width:100%;height:340px;border:0;padding:0;overflow:hidden;background-size:cover;background-position:center;color:white;text-align:left;cursor:pointer}.home-hero-shade{position:absolute;inset:0;background:linear-gradient(90deg,rgba(0,0,0,.88) 0%,rgba(0,0,0,.60) 37%,rgba(0,0,0,.12) 72%),linear-gradient(0deg,var(--card-background-color) 0%,transparent 38%)}.home-hero-copy{position:absolute;left:22px;bottom:30px;max-width:min(520px,60%);z-index:1}.home-hero-copy h2{margin:0 0 8px;font-size:30px}.home-hero-copy p{margin:10px 0 0;line-height:1.4;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}.home-hero-logo{display:block;max-width:min(360px,75%);max-height:90px;object-fit:contain;object-position:left bottom;margin-bottom:10px}.home-hero-meta{font-size:13px;opacity:.9;margin-top:4px}.home-hero-dots{position:absolute;right:18px;bottom:26px;z-index:2;display:flex;gap:7px}.home-hero-dot{width:8px;height:8px;border:0;border-radius:50%;padding:0;background:#ffffff66;cursor:pointer}.home-hero-dot.active{background:white;transform:scale(1.25)}.landscape-card{--pw:min(235px,53vw)}.landscape-card .poster{aspect-ratio:16/9}.collection-rail{align-items:flex-start}.collection-card{width:var(--pw);min-width:var(--pw)}.collection-art{position:relative;aspect-ratio:1/1;border-radius:12px;overflow:hidden;background:var(--secondary-background-color)}.collection-card.shape-poster .collection-art{aspect-ratio:2/3}.collection-card.shape-landscape{width:min(235px,53vw);min-width:min(235px,53vw)}.collection-card.shape-landscape .collection-art{aspect-ratio:16/9}.collection-art img{width:100%;height:100%;object-fit:cover}.collection-emoji{height:100%;display:grid;place-items:center;font-size:42px;font-weight:700}.collection-title{position:absolute;left:0;right:0;bottom:0;padding:18px 8px 8px;text-align:center;font-size:12px;font-weight:700;color:white;background:linear-gradient(transparent,rgba(0,0,0,.8))}.status{padding:28px;text-align:center;color:var(--secondary-text-color)}.error{margin:10px 20px;padding:12px;border-radius:10px;background:var(--error-color);color:white}.top{padding:8px 20px}.grid{display:grid;grid-template-columns:repeat(var(--cols),minmax(0,1fr));gap:14px;padding:10px 20px 22px}.grid .pc{width:auto;min-width:0}.hero{height:270px;background-size:cover;background-position:center;position:relative}.shade{position:absolute;inset:0;background:linear-gradient(0deg,var(--card-background-color) 0%,transparent 90%)}.heroBack{position:absolute;top:16px;left:16px}.detail{position:relative;margin-top:-82px;padding:0 20px 22px}.detail h2{font-size:28px;margin:0 0 8px}.desc{max-width:850px;color:var(--secondary-text-color);line-height:1.45}.controls{margin:16px 0}.platform-note{flex-basis:100%;font-size:12px;color:var(--secondary-text-color);max-width:760px}.controls select{border:0;border-radius:18px;padding:9px 12px;background:var(--secondary-background-color);color:var(--primary-text-color)}.primary,.season.active{background:var(--primary-color);color:white}.seasons{display:flex;gap:8px;overflow:auto;margin:14px 0}.episodes{display:grid;gap:9px}.episode{display:grid;grid-template-columns:140px 1fr auto;gap:12px;align-items:center;background:var(--secondary-background-color);padding:8px;border-radius:12px}.episode img{width:140px;aspect-ratio:16/9;object-fit:cover;border-radius:8px}.episode h4,.episode p{margin:0}.episode p{font-size:12px;color:var(--secondary-text-color);margin-top:5px}.episode-actions{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}.sources{display:grid;gap:18px;padding:0 20px 22px}.source-group{padding:0}.source-group-head{display:flex;align-items:center;gap:10px;margin:0 0 8px}.source-group-head img{width:34px;height:34px;object-fit:contain;border-radius:8px;background:var(--secondary-background-color)}.source-group-head h3{margin:0;font-size:16px}.source-group-head span,.source-summary{font-size:12px;color:var(--secondary-text-color)}.source-row{display:flex;gap:12px;align-items:center;justify-content:space-between;background:var(--secondary-background-color);padding:12px;border-radius:12px;margin-bottom:8px}.source-main{min-width:0;display:flex;flex:1;flex-direction:column;gap:6px}.source-label{font-weight:650;white-space:normal;overflow-wrap:anywhere}.source-description,.source-filename,.resolver{font-size:12px;color:var(--secondary-text-color);overflow-wrap:anywhere}.source-filename{opacity:.8}.stream-badges{display:flex;flex-wrap:wrap;gap:5px}.stream-badge{display:inline-flex;align-items:center;min-height:20px;padding:1px 7px;border-radius:10px;font-size:11px;font-weight:650;background:var(--card-background-color);border:1px solid var(--divider-color);white-space:nowrap}.badge-resolution{background:color-mix(in srgb,var(--primary-color) 20%,var(--card-background-color));border-color:color-mix(in srgb,var(--primary-color) 55%,var(--divider-color))}.badge-hdr,.badge-audio{background:color-mix(in srgb,var(--accent-color,var(--primary-color)) 14%,var(--card-background-color))}.badge-size,.badge-language{font-weight:500;color:var(--secondary-text-color)}.source-actions{flex:0 0 auto;max-width:260px;text-align:right;display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}.source-top{padding-top:16px}.source-title-row{display:flex;align-items:center;gap:8px;margin:8px 0}.source-title-row h3{margin:0}.remote-active{background:var(--primary-color)!important;color:white!important}.source-summary{margin-top:-8px;margin-bottom:6px}.debrid-note{font-size:12px;color:var(--secondary-text-color);max-width:520px}.resolvesource:disabled{opacity:.65;cursor:wait}.resolveall{font-size:12px}.nuvio-layout{position:relative;display:block;min-width:0}.nuvio-main{width:100%;min-width:0}.remote-shell{width:176px;border:1px solid var(--divider-color);border-radius:24px;padding:12px;background:color-mix(in srgb,var(--card-background-color) 94%,transparent);backdrop-filter:blur(18px);box-shadow:0 12px 36px rgba(0,0,0,.26)}.remote-head{display:flex;align-items:center;justify-content:space-between;font-size:12px;font-weight:700;color:var(--secondary-text-color);margin-bottom:10px}.remote-close{width:26px;height:26px;border:0;border-radius:13px;background:var(--secondary-background-color);color:var(--primary-text-color);display:grid;place-items:center;cursor:pointer}.remote-close ha-icon{--mdc-icon-size:16px}.wake-btn{width:100%;height:34px;border:0;border-radius:17px;background:var(--secondary-background-color);color:var(--primary-text-color);display:flex;align-items:center;justify-content:center;gap:6px;font-size:11px;cursor:pointer;margin-bottom:10px}.wake-btn ha-icon{--mdc-icon-size:18px}.remote-ring{position:relative;width:132px;height:132px;margin:0 auto 10px;border-radius:50%;background:radial-gradient(circle at center,var(--secondary-background-color) 0 34%,color-mix(in srgb,var(--secondary-background-color) 82%,var(--primary-color) 18%) 35% 100%);box-shadow:inset 0 0 0 1px var(--divider-color)}.remote-ring button{position:absolute;border:0;background:transparent;color:var(--primary-text-color);display:grid;place-items:center;cursor:pointer}.ring-btn{width:44px;height:44px;border-radius:50%!important}.ring-btn ha-icon{--mdc-icon-size:28px}.ring-btn.up{top:2px;left:44px}.ring-btn.down{bottom:2px;left:44px}.ring-btn.left{left:2px;top:44px}.ring-btn.right{right:2px;top:44px}.ring-ok{width:48px;height:48px;left:42px;top:42px;border-radius:50%!important;background:var(--primary-color)!important;color:white!important;font-size:11px;font-weight:800;box-shadow:0 3px 10px rgba(0,0,0,.22)}.remote-ring button:active,.wake-btn:active,.remote-footer button:active{transform:scale(.96)}.remote-footer{display:grid;grid-template-columns:1fr 1fr;gap:8px}.remote-footer button{height:38px;border:0;border-radius:14px;background:var(--secondary-background-color);color:var(--primary-text-color);display:flex;align-items:center;justify-content:center;gap:5px;font-size:11px;cursor:pointer}.remote-footer ha-icon{--mdc-icon-size:18px}.resolveall{font-size:12px}@media(max-width:700px){:host{--pw:120px}.remote-dialog{top:180px}.remote-shell{width:160px;padding:10px}.remote-ring{width:120px;height:120px}.ring-btn.up{left:38px}.ring-btn.down{left:38px}.ring-btn.left{top:38px}.ring-btn.right{top:38px}.ring-ok{left:36px;top:36px}.header{flex-direction:column;align-items:stretch}.search{min-width:0;flex:1}.grid{grid-template-columns:repeat(3,minmax(0,1fr))}.episode{grid-template-columns:95px 1fr}.episode img{width:95px}.playep{grid-column:2}.source-row{align-items:flex-start;flex-direction:column}.source-actions{max-width:none;width:100%;text-align:left}.source-actions .action{width:100%}.home-hero-card{height:250px}.home-hero-copy{left:16px;bottom:22px;max-width:75%}.home-hero-copy h2{font-size:24px}.home-hero-copy p{display:none}.hero{height:220px}}</style>';
  }
  wire(){
    var r=this.shadowRoot,q=r.querySelector("#search");
    if(q){q.addEventListener("input",e=>this._query=e.target.value);q.addEventListener("keydown",e=>{if(e.key==="Enter")this.search();});}
    r.querySelector("#refresh")?.addEventListener("click",()=>{this._loaded=false;this.loadHome(true);});
    r.querySelectorAll("[data-remote-key]").forEach(b=>b.addEventListener("click",()=>this.remoteKey(b.dataset.remoteKey)));
    r.querySelectorAll(".remote-toggle-button").forEach(b=>b.addEventListener("click",()=>this.toggleRemote()));
    r.querySelector("#back")?.addEventListener("click",()=>{this._view="home";this._error="";this.render();});
    r.querySelector("#open")?.addEventListener("click",()=>this.play(true,null));
    r.querySelector("#play")?.addEventListener("click",()=>this.play(false,null));
    r.querySelector("#sources")?.addEventListener("click",()=>this.showSources(null));
    r.querySelector("#player")?.addEventListener("change",e=>{this._playerId=e.target.value;this.render();});
    r.querySelectorAll(".season").forEach(b=>b.addEventListener("click",()=>{this._season=Number(b.dataset.season);this.render();}));
    r.querySelectorAll(".playep").forEach(b=>b.addEventListener("click",()=>{var eps=(this._details.videos||[]).filter(v=>Number(v.season)===Number(this._season)).sort((a,c)=>(Number(a.episode)||0)-(Number(c.episode)||0));this.play(false,eps[Number(b.dataset.ep)]);}));
    r.querySelectorAll(".sourceep").forEach(b=>b.addEventListener("click",()=>{var eps=(this._details.videos||[]).filter(v=>Number(v.season)===Number(this._season)).sort((a,c)=>(Number(a.episode)||0)-(Number(c.episode)||0));this.showSources(eps[Number(b.dataset.ep)]);}));
    r.querySelectorAll(".playsource").forEach(b=>b.addEventListener("click",()=>this.playSource(this._streams[Number(b.dataset.sourceIndex)])));
    r.querySelectorAll(".nuvioplay").forEach(b=>b.addEventListener("click",()=>this.playInNuvioIndex(Number(b.dataset.sourceIndex))));
    r.querySelectorAll(".playdirect").forEach(b=>b.addEventListener("click",()=>this.playDirectIndex(Number(b.dataset.sourceIndex))));
    r.querySelectorAll(".resolvesource").forEach(b=>b.addEventListener("click",()=>this.resolveSource(Number(b.dataset.sourceIndex))));
    r.querySelector("#resolveAll")?.addEventListener("click",()=>this.resolveVisibleSources());
    r.querySelectorAll("button.openlink").forEach(b=>b.addEventListener("click",()=>this.openSourceLink(this._streams[Number(b.dataset.sourceIndex)])));
    r.querySelectorAll(".copylink").forEach(b=>b.addEventListener("click",()=>this.copyText((this._streams[Number(b.dataset.sourceIndex)]||{}).url)));
    r.querySelectorAll(".copytorrent").forEach(b=>b.addEventListener("click",()=>this.copyText((this._streams[Number(b.dataset.sourceIndex)]||{}).magnet_uri)));
    r.querySelector("#backDetails")?.addEventListener("click",()=>{this._view="details";this._error="";this.render();});
    r.querySelectorAll(".home-hero-dot").forEach(b=>b.addEventListener("click",e=>{e.stopPropagation();this._heroIndex=Number(b.dataset.heroIndex)||0;this.render();}));
    r.querySelector(".home-hero-card")?.addEventListener("click",()=>{var i=this._hero[this._heroIndex];if(i)this.selectItem(i);});
    r.querySelectorAll(".pc").forEach(b=>b.addEventListener("click",()=>{var i;if(b.dataset.source==="search")i=this._results[Number(b.dataset.index)];else{var si=Number(b.dataset.source.slice(1));i=this._sections[si].items[Number(b.dataset.index)];}if(i)this.selectItem(i);}));
  }
  render(){
    if(!this.shadowRoot)return;var body=this._view==="details"?this.detailsView():(this._view==="sources"?this.sourcesView():(this._view==="search"?this.searchView():this.home()));
    var content=this._config.show_remote===false
      ? body
      : '<div class="nuvio-layout">'+this.remotePanel()+'<main class="nuvio-main">'+body+'</main></div>';
    this.shadowRoot.innerHTML=this.styles()+'<ha-card>'+(this._view==="home"?this.header():"")+(this._error?'<div class="error">'+this.esc(this._error)+'</div>':"")+content+'</ha-card>';this.wire();
    this.syncRemotePortal();
    this.updateRemoteButtons();
  }
}
if(!customElements.get("nuvio-card"))customElements.define("nuvio-card",NuvioCard);
window.customCards=window.customCards||[];
if(!window.customCards.some(c=>c.type==="nuvio-card"))window.customCards.push({type:"nuvio-card",name:"Nuvio",description:"Browse, search and play your Nuvio catalog.",preview:true});
console.info("NUVIO-CARD v0.4.14");
