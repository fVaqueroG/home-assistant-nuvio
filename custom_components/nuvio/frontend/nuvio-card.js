class NuvioCard extends HTMLElement {
  constructor(){
    super(); this.attachShadow({mode:"open"});
    this._config={}; this._hass=null; this._loaded=false; this._loading=false;
    this._sections=[]; this._results=[]; this._playersMeta=[]; this._playerId=""; this._view="home"; this._item=null; this._details=null; this._season=null; this._query=""; this._error="";
  }
  static getStubConfig(){ return {title:"Nuvio",columns:6}; }
  setConfig(c){ this._config=Object.assign({title:"Nuvio",columns:6,show_search:true},c||{}); this.render(); }
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
    return '<div class="header"><h2>'+this.esc(this._config.title)+'</h2><div class="tools">'+s+'<button class="ib" id="refresh"><ha-icon icon="mdi:refresh"></ha-icon></button></div></div>';
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
  detailsView(){
    var i=this._item;if(!i)return "";var d=this._details||i,bg=d.background||d.poster||"",videos=(d.videos||[]);
    var seasons=this.seasons(),eps=videos.filter(v=>Number(v.season)===Number(this._season)).sort((a,b)=>(Number(a.episode)||0)-(Number(b.episode)||0));
    var episodeHtml="";
    if(d.type==="series"&&this._details){
      episodeHtml='<div class="seasons">'+seasons.map(s=>'<button class="season '+(Number(this._season)===s?"active":"")+'" data-season="'+s+'">Season '+s+'</button>').join("")+'</div><div class="episodes">'+eps.map((e,n)=>'<div class="episode">'+(e.thumbnail?'<img loading="lazy" src="'+this.esc(e.thumbnail)+'" alt="">':'<div></div>')+'<div><h4>E'+this.esc(e.episode||"")+' · '+this.esc(e.title||("Episode "+(e.episode||"")))+'</h4>'+(e.overview?'<p>'+this.esc(e.overview)+'</p>':"")+'</div><button class="action primary playep" data-ep="'+n+'">▶ Play</button></div>').join("")+'</div>';
    }
    var platform=this.platform(this.player()),webos=platform==="webostv",remoteOnly=platform==="androidtv_remote";
    var actions=webos
      ? '<button class="action primary" id="play">Open Nuvio TV on LG</button><div class="platform-note">LG webOS can launch Nuvio TV from Home Assistant. Direct title/episode routing will activate when the Nuvio webOS app supports launch parameters.</div>'
      : remoteOnly
        ? '<button class="action primary" id="play">Open in Nuvio</button><div class="platform-note">Android TV Remote can open the selected Nuvio title. Direct stream playback requires a separate ADB-based Android TV entity.</div>'
        : '<button class="action" id="open">Open in Nuvio</button>'+((d.type!=="series"||i.video_id)?'<button class="action primary" id="play">▶ Play</button>':"");
    return '<div class="hero" '+(bg?'style="background-image:url(&quot;'+this.esc(bg)+'&quot;)"':"")+'><div class="shade"></div><button class="back heroBack" id="back">← Catalog</button></div><div class="detail"><h2>'+this.esc(d.name||i.name)+'</h2><div class="meta">'+this.esc(d.releaseInfo||"")+(d.genres&&d.genres.length?' · '+this.esc(d.genres.join(", ")):"")+'</div>'+(d.description?'<p class="desc">'+this.esc(d.description)+'</p>':"")+'<div class="controls">'+this.playerSelect()+actions+'</div>'+(this._loading?'<div class="status">Loading details…</div>':episodeHtml)+'</div>';
  }
  styles(){
    return '<style>:host{display:block;--pw:min(150px,34vw)}ha-card{overflow:hidden;padding:0;color:var(--primary-text-color)}.header{display:flex;gap:12px;align-items:center;padding:18px 20px 8px}.header h2{margin:0;flex:1;font-size:22px}.tools,.controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.search{display:flex;align-items:center;background:var(--secondary-background-color);border-radius:18px;padding:0 9px;min-width:220px}.search input{border:0;outline:0;background:transparent;color:var(--primary-text-color);padding:9px;width:100%}.ib,.back,.action,.season{border:0;cursor:pointer;background:var(--secondary-background-color);color:var(--primary-text-color);border-radius:18px;padding:9px 13px}section{padding:8px 0 12px}section h3{margin:6px 20px 10px}.rail{display:flex;gap:12px;overflow:auto;padding:0 20px 10px}.pc{width:var(--pw);min-width:var(--pw);border:0;background:none;color:inherit;text-align:left;padding:0;cursor:pointer}.poster{aspect-ratio:2/3;border-radius:12px;overflow:hidden;background:var(--secondary-background-color);position:relative}.poster img{width:100%;height:100%;object-fit:cover}.ph{height:100%;display:grid;place-items:center}.pt{font-weight:600;font-size:13px;margin-top:7px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.meta{display:flex;justify-content:space-between;gap:5px;color:var(--secondary-text-color);font-size:11px}.prog{position:absolute;left:6px;right:6px;bottom:6px;height:4px;background:#ffffff55}.prog i{display:block;height:100%;background:var(--primary-color)}.status{padding:28px;text-align:center;color:var(--secondary-text-color)}.error{margin:10px 20px;padding:12px;border-radius:10px;background:var(--error-color);color:white}.top{padding:8px 20px}.grid{display:grid;grid-template-columns:repeat(var(--cols),minmax(0,1fr));gap:14px;padding:10px 20px 22px}.grid .pc{width:auto;min-width:0}.hero{height:270px;background-size:cover;background-position:center;position:relative}.shade{position:absolute;inset:0;background:linear-gradient(0deg,var(--card-background-color) 0%,transparent 90%)}.heroBack{position:absolute;top:16px;left:16px}.detail{position:relative;margin-top:-82px;padding:0 20px 22px}.detail h2{font-size:28px;margin:0 0 8px}.desc{max-width:850px;color:var(--secondary-text-color);line-height:1.45}.controls{margin:16px 0}.platform-note{flex-basis:100%;font-size:12px;color:var(--secondary-text-color);max-width:760px}.controls select{border:0;border-radius:18px;padding:9px 12px;background:var(--secondary-background-color);color:var(--primary-text-color)}.primary,.season.active{background:var(--primary-color);color:white}.seasons{display:flex;gap:8px;overflow:auto;margin:14px 0}.episodes{display:grid;gap:9px}.episode{display:grid;grid-template-columns:140px 1fr auto;gap:12px;align-items:center;background:var(--secondary-background-color);padding:8px;border-radius:12px}.episode img{width:140px;aspect-ratio:16/9;object-fit:cover;border-radius:8px}.episode h4,.episode p{margin:0}.episode p{font-size:12px;color:var(--secondary-text-color);margin-top:5px}@media(max-width:700px){:host{--pw:120px}.header{flex-direction:column;align-items:stretch}.search{min-width:0;flex:1}.grid{grid-template-columns:repeat(3,minmax(0,1fr))}.episode{grid-template-columns:95px 1fr}.episode img{width:95px}.playep{grid-column:2}.hero{height:220px}}</style>';
  }
  wire(){
    var r=this.shadowRoot,q=r.querySelector("#search");
    if(q){q.addEventListener("input",e=>this._query=e.target.value);q.addEventListener("keydown",e=>{if(e.key==="Enter")this.search();});}
    r.querySelector("#refresh")?.addEventListener("click",()=>{this._loaded=false;this.loadHome(true);});
    r.querySelector("#back")?.addEventListener("click",()=>{this._view="home";this._error="";this.render();});
    r.querySelector("#open")?.addEventListener("click",()=>this.play(true,null));
    r.querySelector("#play")?.addEventListener("click",()=>this.play(false,null));
    r.querySelector("#player")?.addEventListener("change",e=>{this._playerId=e.target.value;this.render();});
    r.querySelectorAll(".season").forEach(b=>b.addEventListener("click",()=>{this._season=Number(b.dataset.season);this.render();}));
    r.querySelectorAll(".playep").forEach(b=>b.addEventListener("click",()=>{var eps=(this._details.videos||[]).filter(v=>Number(v.season)===Number(this._season)).sort((a,c)=>(Number(a.episode)||0)-(Number(c.episode)||0));this.play(false,eps[Number(b.dataset.ep)]);}));
    r.querySelectorAll(".pc").forEach(b=>b.addEventListener("click",()=>{var i;if(b.dataset.source==="search")i=this._results[Number(b.dataset.index)];else{var si=Number(b.dataset.source.slice(1));i=this._sections[si].items[Number(b.dataset.index)];}if(i)this.selectItem(i);}));
  }
  render(){
    if(!this.shadowRoot)return;var body=this._view==="details"?this.detailsView():(this._view==="search"?this.searchView():this.home());
    this.shadowRoot.innerHTML=this.styles()+'<ha-card>'+(this._view==="home"?this.header():"")+(this._error?'<div class="error">'+this.esc(this._error)+'</div>':"")+body+'</ha-card>';this.wire();
  }
}
if(!customElements.get("nuvio-card"))customElements.define("nuvio-card",NuvioCard);
window.customCards=window.customCards||[];
if(!window.customCards.some(c=>c.type==="nuvio-card"))window.customCards.push({type:"nuvio-card",name:"Nuvio",description:"Browse, search and play your Nuvio catalog.",preview:true});
console.info("NUVIO-CARD v0.3.5");
