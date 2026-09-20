from pathlib import Path
p = Path('tests/test_card.cjs')
s = p.read_text()
if '// Room mapping and TV volume regressions.' not in s:
    anchor = 'const flush=()=>new Promise(r=>setImmediate(r));'
    assert s.count(anchor) == 1
    editor = r'''// Room mapping and TV volume regressions.
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
'''
    s = s.replace(anchor, editor + '\n' + anchor, 1)
    async_anchor = ' // An addon row without an exact URL must not silently open the title.'
    assert s.count(async_anchor) == 1
    async_tests = r''' // Room selection controls playback, HDMI switching and the physical TV's volume.
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
'''
    s = s.replace(async_anchor, async_tests + async_anchor, 1)
    p.write_text(s)
print('Room and volume regression tests applied')
