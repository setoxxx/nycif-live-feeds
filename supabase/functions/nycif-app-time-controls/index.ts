const JS = String.raw`(function(){
'use strict';
var NIGHT='https://oggwpvdirkrnzoolparx.supabase.co/functions/v1/nycif-night-layers';
var SPECIAL='https://oggwpvdirkrnzoolparx.supabase.co/functions/v1/nycif-special-calendars';
var APIKEY='sb_publishable_V5PfbUnBmRxlVVS6TtOHHQ_av0Fzo3Z';
var root=document.getElementById('nycifUnifiedApp');
var chips=root&&root.querySelector('.u-chips');
if(!root||!chips)return;

['nycif-time-controls-v7-style','nycif-time-controls-v8-style','nycif-time-controls-v9-style','nycif-time-controls-v10-style','nycif-time-controls-v11-style','nycif-time-controls-v12-style','nycif-time-controls-v13-style','nycif-time-controls-v14-style','nycif-time-controls-v15-style','nycif-time-controls-v16-style','nycif-time-controls-v17-style'].forEach(function(id){var n=document.getElementById(id);if(n)n.remove();});
var css=document.createElement('style');css.id='nycif-time-controls-v17-style';css.textContent=[
'#nycifUnifiedApp .u-topbar{z-index:40!important}',
'#nycifUnifiedApp .u-chips{position:absolute!important;z-index:9100!important;top:108px!important;left:50%!important;transform:translateX(-50%)!important;width:min(94vw,720px)!important;height:52px!important;display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:8px!important;padding:0!important;border-radius:0!important;background:transparent!important;box-shadow:none!important}',
'#nycifUnifiedApp .u-chip{height:50px!important;border:1px solid rgba(255,255,255,.28)!important;border-radius:999px!important;background:#09090a!important;color:#fff!important;font-size:13px!important;font-weight:650!important;padding:0 8px!important;box-shadow:none!important}',
'#nycifUnifiedApp .u-chip .round{display:none!important}',
'#nycifUnifiedApp .u-chip.is-active{background:#f7f7f8!important;color:#080809!important;border-color:#f7f7f8!important;font-weight:850!important}',
'#nycifUnifiedApp .u-aux-chips{position:absolute!important;z-index:9100!important;top:166px!important;left:50%!important;transform:translateX(-50%)!important;width:min(94vw,720px)!important;display:none;gap:7px;padding:0;pointer-events:auto}',
'#nycifUnifiedApp .u-aux-chips.is-night{display:grid;grid-template-columns:repeat(3,minmax(0,1fr))}',
'#nycifUnifiedApp .u-aux-chips.is-seven{display:grid;grid-template-columns:repeat(7,minmax(0,1fr))}',
'#nycifUnifiedApp .u-aux-chips .u-chip{height:46px!important;font-size:11px!important;line-height:1.15;flex-direction:column}',
'#nycifUnifiedApp .u-aux-chips .u-chip small{display:block;font-size:9px;font-weight:600;letter-spacing:.03em;opacity:.8}',
'#nycifUnifiedApp .u-special-calendars{position:absolute;z-index:9090;top:220px;left:50%;transform:translateX(-50%);width:min(94vw,720px);display:none;gap:7px;pointer-events:auto}',
'#nycifUnifiedApp .u-special-calendars.on{display:grid}',
'#nycifUnifiedApp.nycif-hide-special .u-special-calendars{display:none!important}',
'#nycifUnifiedApp.nycif-mode-tonight .u-special-calendars,#nycifUnifiedApp.nycif-mode-seven .u-special-calendars{display:none!important}',
'#nycifUnifiedApp.nycif-special-active .u-aux-chips{display:none!important}',
'#nycifUnifiedApp.nycif-special-active .u-special-calendars{display:grid!important}',
'#nycifUnifiedApp .u-special-card{background:#050506;color:#fff;border:1px solid rgba(255,255,255,.17);border-radius:18px;box-shadow:0 8px 24px rgba(0,0,0,.28);overflow:hidden}',
'#nycifUnifiedApp .u-special-titlebar{appearance:none;border:0;background:transparent;color:#fff;width:100%;height:46px;padding:0 18px;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:720;letter-spacing:.22em;text-transform:uppercase;cursor:pointer;position:relative}',
'#nycifUnifiedApp .u-special-titlebar:after{content:"";position:absolute;left:10px;right:10px;bottom:0;height:3px;background:#ef233c;border-radius:3px}',
'#nycifUnifiedApp .u-special-days{display:flex;align-items:stretch;gap:3px;overflow-x:auto;scrollbar-width:none;padding:8px 10px 10px}',
'#nycifUnifiedApp .u-special-day{appearance:none;border:0;flex:0 0 auto;min-width:61px;height:50px;border-radius:10px;background:transparent;color:#e8e8ea;display:grid;align-content:center;gap:2px;text-align:center;cursor:pointer;padding:3px 7px}',
'#nycifUnifiedApp .u-special-day .date{font-size:10px}.u-special-day .dow{font-size:8px;letter-spacing:.09em;color:#aeb0b6}.u-special-day.is-active{background:#e91f37;color:#fff}.u-special-day.is-active .dow{color:#fff}',
'#nycifUnifiedApp .nycif-night-pin-icon{background:transparent!important;border:0!important}',
'#nycifUnifiedApp .nycif-night-pin-shell{width:28px;height:28px;border-radius:50%;background:#09090b;border:2px solid #fff;box-shadow:0 0 0 2px var(--night-tone);display:grid;place-items:center;font-size:14px}',
'#nycifUnifiedApp.nycif-context-open .u-list{top:228px!important}',
'@media(max-width:782px){#nycifUnifiedApp .u-chips{top:100px!important;width:94vw!important}#nycifUnifiedApp .u-chip{height:46px!important;font-size:12px!important}#nycifUnifiedApp .u-aux-chips{top:154px;width:94vw}#nycifUnifiedApp .u-aux-chips .u-chip{height:42px!important;font-size:10px!important}#nycifUnifiedApp .u-special-calendars{top:204px;width:94vw}#nycifUnifiedApp.nycif-context-open .u-list{top:216px!important}}'
].join('');document.head.appendChild(css);

var oldNow=chips.querySelector('[data-mode="NOW"]');
var todayChip=chips.querySelector('[data-mode="TODAY"]');
var coming=chips.querySelector('[data-mode="COMING"]');
var seven=chips.querySelector('[data-mode="7D"]');
var tonight=chips.querySelector('[data-mode="TONIGHT"]');
if(oldNow)oldNow.remove();
if(coming)coming.remove();
if(todayChip){todayChip.innerHTML='<span>Now</span>';todayChip.setAttribute('data-public-mode','NOW');}
if(tonight)tonight.innerHTML='<span>Tonight</span>';
if(seven)seven.innerHTML='<span>7 Days</span>';

document.querySelectorAll('.u-night-subfilters,.u-seven-preview,.u-aux-chips').forEach(function(n){n.remove();});
var aux=document.createElement('div');
aux.className='u-aux-chips';
aux.setAttribute('data-nycif-aux','v17');
chips.insertAdjacentElement('afterend',aux);

var oldSpecial=document.querySelector('.u-special-calendars');
if(oldSpecial)oldSpecial.remove();
var specialHost=document.createElement('div');
specialHost.className='u-special-calendars';
aux.insertAdjacentElement('afterend',specialHost);

var nightKey=null,nightCache={},nightOverlay=null,specialState=null,sevenState=null,ourMode='NOW',collections=[];

function adapter(){return window.NYCIF_MAPS&&window.NYCIF_MAPS.uEventMap||null;}
function map(){var a=adapter();return a&&a.map||null;}
function source(){var a=adapter();return a&&(a.getSource?a.getSource('eventsSrc'):a.sources&&a.sources.eventsSrc)||null;}
function group(){var a=adapter();return a&&a.layerGroups&&a.layerGroups.eventsPins;}
function hideEvents(){var m=map(),g=group();if(m&&g&&m.hasLayer(g))m.removeLayer(g);var s=source();if(s){var empty={type:'FeatureCollection',features:[]};if(s.setData)s.setData(empty);else s.data=empty;}}
function showEvents(){var m=map(),g=group();if(m&&g&&!m.hasLayer(g))g.addTo(m);}
function clearNight(){var m=map();if(m&&nightOverlay&&m.hasLayer(nightOverlay))m.removeLayer(nightOverlay);nightOverlay=null;}
function allEvents(){return root.__nycifAllEvents&&root.__nycifAllEvents.features||[];}
function setSource(features){var s=source(),d={type:'FeatureCollection',features:features||[]};if(s){if(s.setData)s.setData(d);else s.data=d;}showEvents();}
function applyPins(features){setSource(features);}
function nyDate(d){return new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).format(d);}
function nyAddDays(day,offset){var p=String(day).split('-').map(Number);return nyDate(new Date(Date.UTC(p[0],p[1]-1,p[2]+offset,16,0,0)));}
function nyHour(d){return Number(new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',hour:'2-digit',hour12:false}).format(d));}
function eventStart(f){var p=f&&f.properties||{},v=p.start_date_time||p.start_at||p.event_date;var d=v?new Date(v):null;return d&&Number.isFinite(d.getTime())?d:null;}
function nextSevenKeys(){var today=nyDate(new Date()),out=[];for(var i=1;i<=7;i++)out.push(nyAddDays(today,i));return out;}
function mapped(rows){return (rows||[]).filter(function(f){return !!f.geometry;});}
function nowRows(){var today=nyDate(new Date());return allEvents().filter(function(f){var x=eventStart(f);return x&&nyDate(x)===today;});}
function strictTonightRows(){var today=nyDate(new Date());return allEvents().filter(function(f){var x=eventStart(f);if(!x||nyDate(x)!==today)return false;var h=nyHour(x);return h>=18&&h<=23;});}
function sevenDayRows(day){return allEvents().filter(function(f){var x=eventStart(f);return x&&nyDate(x)===day;});}
function closeList(){var h=document.getElementById('uHappeningList');if(h)h.classList.remove('is-active');}
function nowChip(){return chips.querySelector('[data-mode="TODAY"]')||chips.querySelector('[data-public-mode="NOW"]');}
function sevenChip(){return chips.querySelector('[data-mode="7D"]');}
function tonightChip(){return chips.querySelector('[data-mode="TONIGHT"]');}
function activateChip(target){Array.prototype.forEach.call(chips.querySelectorAll('.u-chip[data-mode]'),function(c){c.classList.toggle('is-active',c===target);});}
function nightCfg(k){return k==='dispensary'?{tone:'#2f9e5b',emoji:'🌿'}:k==='liquor'?{tone:'#c47a18',emoji:'🍸'}:{tone:'#c026d3',emoji:'🍹'};}
function nightIcon(k){var c=nightCfg(k);return L.divIcon({className:'nycif-night-pin-icon',html:'<div class="nycif-night-pin-shell" style="--night-tone:'+c.tone+'">'+c.emoji+'</div>',iconSize:[28,28],iconAnchor:[14,14]});}
function labelDate(key){var p=String(key).split('-').map(Number);return new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',month:'short',day:'numeric'}).format(new Date(Date.UTC(p[0],p[1]-1,p[2],16,0,0)));}
function labelDow(key){var p=String(key).split('-').map(Number);return new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',weekday:'short'}).format(new Date(Date.UTC(p[0],p[1]-1,p[2],16,0,0)));}

function showNow(){nightKey=null;clearNight();applyPins(mapped(nowRows()));closeList();}
function showTonightEvents(){nightKey=null;clearNight();applyPins(mapped(strictTonightRows()));closeList();}
function showSevenEvents(day){nightKey=null;clearNight();var keys=nextSevenKeys();if(!day)day=keys[0];sevenState=day;applyPins(mapped(sevenDayRows(day)));closeList();}
function restoreModeEvents(){if(ourMode==='TONIGHT')showTonightEvents();else if(ourMode==='7D')showSevenEvents(sevenState);else showNow();}

async function loadNight(k,b){if(nightCache[k])return nightCache[k];if(b)b.classList.add('is-loading');try{var r=await fetch(NIGHT+'?layer='+encodeURIComponent(k),{cache:'no-store'});if(!r.ok)throw new Error('Layer unavailable');return nightCache[k]=await r.json();}finally{if(b)b.classList.remove('is-loading');}}
function renderNight(k,d){var m=map();if(!m||typeof L==='undefined')return;clearNight();nightOverlay=L.layerGroup().addTo(m);(d.features||[]).filter(function(f){var c=f&&f.geometry&&f.geometry.coordinates||[];return Number.isFinite(+c[0])&&Number.isFinite(+c[1]);}).slice(0,250).forEach(function(f){var c=f.geometry.coordinates,p=f.properties||{};L.marker([+c[1],+c[0]],{icon:nightIcon(k),title:String(p.title||'Location')}).bindPopup('<strong>'+String(p.title||'Location').replace(/[<>&]/g,'')+'</strong>').addTo(nightOverlay);});}
async function activateNight(k,b){hideEvents();try{renderNight(k,await loadNight(k,b));}catch(e){console.error(e);nightKey=null;if(b)b.classList.remove('is-active');restoreModeEvents();}}

function renderAux(){
  aux.innerHTML='';
  aux.classList.remove('is-night','is-seven');
  if(specialState)return;
  if(ourMode==='7D'){
    aux.classList.add('is-seven');
    var keys=nextSevenKeys();
    if(!sevenState)sevenState=keys[0];
    keys.forEach(function(key,idx){
      var b=document.createElement('button');
      b.type='button';
      b.className='u-chip'+(sevenState===key?' is-active':'');
      b.setAttribute('data-seven-day',key);
      b.setAttribute('data-day-index',String(idx+1));
      b.innerHTML='<span>'+labelDow(key)+'</span><small>'+labelDate(key)+'</small>';
      b.addEventListener('click',function(ev){
        ev.preventDefault();
        ev.stopPropagation();
        sevenState=key;
        nightKey=null;
        clearNight();
        renderAux();
        showSevenEvents(key);
      });
      aux.appendChild(b);
    });
    return;
  }
  aux.classList.add('is-night');
  [{id:'5pm',label:'5 P.M. Somewhere',emoji:'🍹'},{id:'dispensary',label:'Dispensaries',emoji:'🌿'},{id:'liquor',label:'Liquor Stores',emoji:'🍸'}].forEach(function(layer){
    var b=document.createElement('button');
    b.type='button';
    b.className='u-chip'+(nightKey===layer.id?' is-active':'');
    b.setAttribute('data-night-layer',layer.id);
    b.innerHTML='<span>'+layer.emoji+' '+layer.label+'</span>';
    b.addEventListener('click',function(ev){
      ev.preventDefault();
      ev.stopPropagation();
      if(nightKey===layer.id){nightKey=null;renderAux();restoreModeEvents();return;}
      nightKey=layer.id;
      sevenState=null;
      renderAux();
      activateNight(layer.id,b);
    });
    aux.appendChild(b);
  });
}

function applyModePins(){
  if(specialState)return;
  if(ourMode==='7D'){specialHost.classList.remove('on');if(!nightKey)showSevenEvents(sevenState);}
  else if(ourMode==='TONIGHT'){specialHost.classList.remove('on');if(!nightKey)showTonightEvents();}
  else{if(collections.length&&!root.classList.contains('nycif-hide-special'))specialHost.classList.add('on');if(!nightKey)showNow();}
}
function syncContext(){
  root.classList.toggle('nycif-mode-now',ourMode==='NOW');
  root.classList.toggle('nycif-mode-tonight',ourMode==='TONIGHT');
  root.classList.toggle('nycif-mode-seven',ourMode==='7D');
  root.classList.toggle('nycif-context-open',ourMode!=='NOW'||specialHost.classList.contains('on')||!!nightKey);
  renderAux();
  requestAnimationFrame(function(){setTimeout(applyModePins,0);});
}

function setPrimary(mode){
  ourMode=mode;
  specialState=null;
  root.classList.remove('nycif-special-active');
  nightKey=null;
  clearNight();
  closeList();
  if(mode==='TONIGHT'){sevenState=null;activateChip(tonightChip());}
  else if(mode==='7D'){if(!sevenState)sevenState=nextSevenKeys()[0];activateChip(sevenChip());}
  else{sevenState=null;activateChip(nowChip());}
  syncContext();
}

function turnOffContext(){sevenState=null;nightKey=null;clearNight();setPrimary('NOW');}

function clearSpecialButtons(){Array.prototype.forEach.call(specialHost.querySelectorAll('.u-special-titlebar,.u-special-day'),function(b){b.classList.remove('is-active');});}
function renderList(rows,title){var h=document.getElementById('uHappeningList');if(!h)return;h.innerHTML='';rows.forEach(function(f){var p=f.properties||{},b=document.createElement('button'),s=document.createElement('strong'),sm=document.createElement('small');b.className='u-list-item';s.textContent=p.title||'Event';sm.textContent=[p.day_bucket,p.start_time&&p.start_time!=='TBA'?p.start_time:null,p.location||p.venue_name||p.borough,p.access].filter(Boolean).join(' · ');b.appendChild(s);b.appendChild(sm);if(f.geometry)b.addEventListener('click',function(){var a=adapter();if(a)a.flyTo({center:f.geometry.coordinates,zoom:14});closeList();});h.appendChild(b);});h.classList.add('is-active');var st=document.getElementById('uStat');if(st)st.textContent=(title||'Events')+' · '+rows.length;}
function bucketWeekday(c,key){if(key==='MISC/TBA')return'TBD';var f=(c.features||[]).find(function(x){return (x.properties||{}).day_bucket===key;});var p=f&&f.properties||{},v=p.event_date||p.start_at||p.start_date_time;if(!v)return'';var d=new Date(v);if(!Number.isFinite(d.getTime()))return'';return new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',weekday:'short'}).format(d).toUpperCase();}
function dayLabel(key){return key==='MISC/TBA'?'TBD':String(key).replace(/^SEP\s+/i,'Sep ');}
function applySpecial(c,bucket){specialState={id:c.collection_id,bucket:bucket||'*'};sevenState=null;nightKey=null;clearNight();root.classList.add('nycif-special-active');specialHost.classList.add('on');aux.classList.remove('is-night','is-seven');var rows=(c.features||[]).filter(function(f){return !bucket||(f.properties||{}).day_bucket===bucket;}),mappedRows=mapped(rows);applyPins(mappedRows);clearSpecialButtons();var target=bucket?specialHost.querySelector('[data-special-day="'+bucket+'"]'):specialHost.querySelector('[data-special-title="'+c.collection_id+'"]');if(target)target.classList.add('is-active');if(bucket==='MISC/TBA'||!mappedRows.length)renderList(rows,c.display_name+' · TBD');else closeList();}
function leaveSpecial(){if(!specialState)return;specialState=null;root.classList.remove('nycif-special-active');clearSpecialButtons();closeList();syncContext();}
function renderCollections(data){collections=data&&data.collections||[];specialHost.innerHTML='';if(!collections.length){specialHost.classList.remove('on');syncContext();return;}collections.forEach(function(c){var card=document.createElement('div'),title=document.createElement('button'),days=document.createElement('div');card.className='u-special-card';card.style.position='relative';title.type='button';title.className='u-special-titlebar';title.setAttribute('data-special-title',c.collection_id);title.textContent=c.display_name||c.short_label||'Special Collection';title.addEventListener('click',function(){if(specialState&&specialState.id===c.collection_id&&specialState.bucket==='*')leaveSpecial();else applySpecial(c,null);});days.className='u-special-days';(c.buckets||[]).forEach(function(x){var b=document.createElement('button');b.type='button';b.className='u-special-day';b.setAttribute('data-special-day',x.key);b.innerHTML='<span class="date">'+dayLabel(x.key)+'</span><span class="dow">'+bucketWeekday(c,x.key)+'</span>';b.addEventListener('click',function(){applySpecial(c,x.key);});days.appendChild(b);});card.appendChild(title);card.appendChild(days);specialHost.appendChild(card);});syncContext();}
async function loadSpecial(){try{var r=await fetch(SPECIAL,{cache:'no-store',headers:{apikey:APIKEY}});if(!r.ok)throw new Error('Special calendar unavailable');renderCollections(await r.json());}catch(e){console.error(e);collections=[];specialHost.classList.remove('on');syncContext();}}

root.addEventListener('click',function(ev){
  var b=ev.target.closest&&ev.target.closest('#nycifUnifiedApp .u-chips .u-chip[data-mode]');
  if(!b||!chips.contains(b))return;
  var requested=b.getAttribute('data-mode');
  if(requested!=='TONIGHT'&&requested!=='7D'&&requested!=='TODAY'&&requested!=='NOW')return;
  ev.preventDefault();
  ev.stopImmediatePropagation();
  if(requested==='7D'&&ourMode==='7D'){turnOffContext();return;}
  if(requested==='TONIGHT'&&ourMode==='TONIGHT'){turnOffContext();return;}
  if(requested==='7D'){setPrimary('7D');return;}
  if(requested==='TONIGHT'){setPrimary('TONIGHT');return;}
  turnOffContext();
},true);

root.addEventListener('nycif:events-ready',function(){syncContext();});
syncContext();
loadSpecial();
})();`;

Deno.serve((req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET,HEAD,OPTIONS" },
    });
  }
  if (req.method !== "GET" && req.method !== "HEAD") {
    return new Response("method_not_allowed", { status: 405 });
  }
  return new Response(req.method === "HEAD" ? null : JS, {
    status: 200,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Content-Type": "application/javascript; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
});
