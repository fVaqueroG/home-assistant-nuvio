from pathlib import Path

card_path = Path('custom_components/nuvio/frontend/nuvio-card.js')
s = card_path.read_text()

def replace_once(old, new):
    global s
    count = s.count(old)
    if count != 1:
        raise SystemExit(f'Expected one occurrence, found {count}: {old[:110]!r}')
    s = s.replace(old, new, 1)

if '  rooms(){ return Array.isArray(this._config.rooms)' not in s:
    replace_once('this._playersMeta=[]; this._playerId=""; this._streams=[];', 'this._playersMeta=[]; this._playerId=""; this._roomId=null; this._streams=[];')
    replace_once('  setConfig(c){ this._config=Object.assign({title:"Nuvio",columns:6,show_search:true,show_remote:true,remote_side:"left"},c||{}); this.render(); }', '''  setConfig(c){
    this._config=Object.assign({title:"Nuvio",columns:6,show_search:true,show_remote:true,remote_side:"left"},c||{});
    var rooms=this.rooms();
    if(this._roomId===null||(this._roomId&&!rooms.some(r=>r.id===this._roomId))){
      var initial=rooms.find(r=>r.id===this._config.default_room)||rooms[0];
      this._roomId=initial?initial.id:"";
    }
    var room=this.selectedRoom();
    if(room&&room.player)this._playerId=room.player;
    this.render();
  }''')
    replace_once('  player(){ var s=this.shadowRoot&&this.shadowRoot.querySelector("#player"); return this._playerId||(s&&s.value)||this._config.default_player||this._config.entity||this.players()[0]||""; }', '''  rooms(){ return Array.isArray(this._config.rooms)?this._config.rooms.filter(r=>r&&typeof r.id==="string"&&r.id&&typeof r.name==="string"&&r.name.trim()):[]; }
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
  }''')
    replace_once('  var routes=Array.isArray(this._config.display_routes)?this._config.display_routes:[];\n  return routes.find(r=>r&&r.player===player&&typeof r.display==="string"&&r.display.startsWith("media_player.")&&String(r.source||"").trim())||null;', '''  var room=this.selectedRoom();
  if(room&&room.player===player){
    return typeof room.display==="string"&&room.display.startsWith("media_player.")&&String(room.source||"").trim()?room:null;
  }
  var routes=Array.isArray(this._config.display_routes)?this._config.display_routes:[];
  return routes.find(r=>r&&r.player===player&&typeof r.display==="string"&&r.display.startsWith("media_player.")&&String(r.source||"").trim())||null;''')
    replace_once('async ensureDisplaySource(player){\n  var route=this.displayRoute(player);', '''async ensureDisplaySource(player){
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
  var route=this.displayRoute(player);''')
    replace_once('  this._playerId=player;\n  try{await this.ensureDisplaySource(player);}', '''  this._playerId=player;
  var active=this.selectedRoom();
  if(!active||active.player!==player){var match=this.rooms().find(r=>r.player===player);this._roomId=match?match.id:"";}
  this.removeRemotePortal();this.render();
  try{await this.ensureDisplaySource(player);}''')
    replace_once('var remote=this._config.show_remote===false', 'var remote=this._config.show_remote===false') if False else None
    replace_once('this.esc(this._config.title||"Nuvio")+\'</h2><span class="card-version">v0.4.63</span></div><div class="tools">\'+search+\'<label class="toolbar-player"', 'this.esc(this._config.title||"Nuvio")+\'</h2><span class="card-version">v0.4.64</span></div><div class="tools">\'+search+this.roomSelect()+\'<label class="toolbar-player"')
    replace_once('    r.querySelector("#player")?.addEventListener("change",e=>{this.choosePlayer(e.target.value);});', '''    r.querySelector("#player")?.addEventListener("change",e=>{this.choosePlayer(e.target.value);});
    r.querySelector("#room")?.addEventListener("change",e=>{this.chooseRoom(e.target.value);});''')
    replace_once('  async remoteKey(key){', '  async remoteKey(key){') if False else None
    replace_once('        #nuvio-remote-portal .nuvio-remote-footer{', '''        #nuvio-remote-portal .nuvio-volume-row{
          display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin:0 0 12px;
        }
        #nuvio-remote-portal .nuvio-volume-row button{
          height:36px;border:0;border-radius:12px;background:#303033;color:white;
          display:grid;place-items:center;cursor:pointer;padding:0;
        }
        #nuvio-remote-portal .nuvio-volume-row ha-icon{--mdc-icon-size:23px}
        #nuvio-remote-portal .nuvio-remote-footer{''')
    replace_once('        <div class="nuvio-remote-footer">', '''        <div class="nuvio-volume-row" role="group" aria-label="Volume controls">
          <button data-volume="down" title="Volume down" aria-label="Volume down"><ha-icon icon="mdi:volume-minus"></ha-icon></button>
          <button data-volume="mute" title="Mute or unmute" aria-label="Mute or unmute"><ha-icon icon="mdi:volume-off"></ha-icon></button>
          <button data-volume="up" title="Volume up" aria-label="Volume up"><ha-icon icon="mdi:volume-plus"></ha-icon></button>
        </div>
        ${this.selectedRoom()?.power_entity?'<button class="nuvio-wake-btn" data-room-power="true" title="Toggle room power"><ha-icon icon="mdi:power"></ha-icon><span>Room power</span></button>':''}
        <div class="nuvio-remote-footer">''')
    replace_once('    var close=()=>{\n      this._remoteExpanded=false;', '''    portal.querySelectorAll("[data-volume]").forEach(b=>b.addEventListener("click",()=>this.volumeControl(b.dataset.volume)));
    portal.querySelector("[data-room-power]")?.addEventListener("click",()=>this.toggleRoomPower());
    var close=()=>{
      this._remoteExpanded=false;''')
    replace_once('}.toolbar-player{display:flex;', '}.toolbar-room{display:flex;align-items:center;gap:6px;min-width:122px;max-width:210px;flex:0 1 160px;border-radius:18px;padding:0 9px;background:var(--secondary-background-color);color:var(--primary-text-color)}.toolbar-room ha-icon{--mdc-icon-size:19px;flex:0 0 auto}.toolbar-room select{width:100%;min-width:0;max-width:100%;padding:9px 0;border:0;outline:0;background:transparent;color:inherit;text-overflow:ellipsis;font:inherit;cursor:pointer}.toolbar-player{display:flex;')
    replace_once('console.info("NUVIO-CARD v0.4.63");', 'console.info("NUVIO-CARD v0.4.64");')

    # Visual editor: room mappings are independent of existing legacy display_routes.
    replace_once('    return JSON.stringify(this.routes().map(route=>[route&&route.display,this.displaySources(route&&route.display)]));', '''    return JSON.stringify([...this.routes(),...this.rooms()].map(route=>[route&&route.display,this.displaySources(route&&route.display)]));''')
    replace_once('    const extras=[selected,this._config.default_player,this._config.entity,...routes.flatMap(r=>[r&&r.player,r&&r.display])];', '''    const extras=[selected,this._config.default_player,this._config.entity,...routes.flatMap(r=>[r&&r.player,r&&r.display]),...this.rooms().flatMap(r=>[r.player,r.display,r.volume_entity])];''')
    replace_once('  sourceOptions(display,index,selected=""){', '''  powerOptions(selected){
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
  sourceOptions(display,index,selected="",scope="route"){''')
    replace_once('    const attrs=\' data-route="\'+index+\'" data-key="source"\';', '''    const attrs=' data-'+(scope==="room"?"room":"route")+'="'+index+'" data-key="source"';''')
    replace_once('    const routeIndex=target.getAttribute("data-route");', '''    const routeIndex=target.getAttribute("data-route");
    const roomIndex=target.getAttribute("data-room");''')
    replace_once('    if(routeIndex==null)return;', '''    if(roomIndex!=null){
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
    if(routeIndex==null)return;''')
    replace_once('    const routes=this.routes().map(route=>({...route}));\n    if(btn.getAttribute("data-action")==="add")', '''    const action=btn.getAttribute("data-action");
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
    if(btn.getAttribute("data-action")==="add")''')
    replace_once('    const cfg=this._config,routes=this.routes();', '''    const cfg=this._config,routes=this.routes(),rooms=this.rooms();''')
    replace_once('      <section class="group"><h3>Playback device</h3>', '''      <section class="group"><h3>Rooms and device mappings</h3><p>Each room has its own playback player, optional physical TV, TV input, volume device and power helper. Pick a room from the card toolbar to route playback and volume to that room. A room without a mapped display uses its playback device directly.</p>
        <label>Default room<select data-field="default_room"><option value="">First configured room</option>${rooms.map(room=>'<option value="'+this.esc(room.id)+'" '+(room.id===cfg.default_room?'selected':'')+'>'+this.esc(room.name||room.id)+'</option>').join("")}</select></label>
        ${rooms.map((room,index)=>this.roomHtml(room,index)).join("")}
        <button class="add" type="button" data-action="add-room">+ Add room</button>
      </section>
      <section class="group"><h3>Playback device</h3>''')
    card_path.write_text(s)

manifest = Path('custom_components/nuvio/manifest.json')
m = manifest.read_text()
if '"version": "0.4.63"' in m:
    manifest.write_text(m.replace('"version": "0.4.63"','"version": "0.4.64"',1))
elif '"version": "0.4.64"' not in m:
    raise SystemExit('Unexpected manifest version')

print('Room selector, per-room routing and power, volume remote, editor and v0.4.64 applied')
