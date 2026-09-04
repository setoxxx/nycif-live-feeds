const JS = String.raw`(function(){
'use strict';
var NIGHT='https://oggwpvdirkrnzoolparx.supabase.co/functions/v1/nycif-night-layers';
var SPECIAL='https://oggwpvdirkrnzoolparx.supabase.co/functions/v1/nycif-special-calendars';
var APIKEY='sb_publishable_V5PfbUnBmRxlVVS6TtOHHQ_av0Fzo3Z';
var root=document.getElementById('nycifUnifiedApp'),chips=root&&root.querySelector('.u-chips');
if(!root||!chips)return;
['nycif-time-controls-v7-style','nycif-time-controls-v8-style','nycif-time-controls-v9-style','nycif-time-controls-v10-style','nycif-time-controls-v11-style','nycif-time-controls-v12-style','nycif-time-controls-v13-style','nycif-time-controls-v14-style','nycif-time-controls-v15-style'].forEach(function(id){var n=document.getElementById(id);if(n)n.remove();});
var css=document.createElement('style');css.id='nycif-time-controls-v15-style';css.textContent=[
'.u-topbar{position:absolute!important;z-index:9000!important}',
'.u-chips{position:absolute!important;z-index:8990!important;top:84px!important;width:min(94vw,720px)!important;height:50px!important;grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:9px!important;padding:0!important;border-radius:0!important;background:transparent!important;box-shadow:none!important}',
'.u-chip{height:48px!important;border:1px solid rgba(255,255,255,.28)!important;border-radius:999px!important;background:#09090a!important;color:#fff!important;font-size:13px!important;font-weight:650!important;padding:0 10px!important;box-shadow:none!important}',
'.u-chip .round{display:none!important}.u-chip.is-active{background:#f7f7f8!important;color:#080809!important;border-color:#f7f7f8!important;font-weight:850!important}',
'.u-aux-chips{position:absolute;z-index:8988;top:140px;left:50%;transform:translateX(-50%);width:min(94vw,720px);display:none;gap:7px;padding:0;pointer-events:auto}',
'.u-aux-chips.is-night{display:grid;grid-template-columns:repeat(3,minmax(0,1fr))}',
'.u-aux-chips.is-seven{display:flex;overflow-x:auto;scrollbar-width:none}',
'.u-aux-chips.is-seven::-webkit-scrollbar{display:none}',
'.u-aux-chips .u-chip{height:46px!important;font-size:11px!important;line-height:1.1}',
'.u-aux-chips.is-seven .u-chip{flex:0 0 auto;min-width:78px}',
'.u-aux-chips .u-chip small{display:block;font-size:9px;font-weight:600;letter-spacing:.04em;opacity:.8}',
'.u-special-calendars{position:absolute;z-index:8985;top:196px;left:50%;transform:translateX(-50%);width:min(94vw,720px);display:none;gap:7px;pointer-events:auto}',
'.u-special-calendars.on{display:grid}.nycif-hide-special .u-special-calendars{display:none!important}',
'.u-special-card{background:#050506;color:#fff;border:1px solid rgba(255,255,255,.17);border-radius:18px;box-shadow:0 8px 24px rgba(0,0,0,.28);overflow:hidden}',
'.u-special-titlebar{appearance:none;border:0;background:transparent;color:#fff;width:100%;height:46px;padding:0 18px;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:720;letter-spacing:.22em;text-transform:uppercase;cursor:pointer;position:relative}',
'.u-special-titlebar:after{content:"";position:absolute;left:10px;right:10px;bottom:0;height:3px;background:#ef233c;border-radius:3px}',
'.u-special-days{display:flex;align-items:stretch;gap:3px;overflow-x:auto;scrollbar-width:none;padding:8px 10px 10px}.u-special-days::-webkit-scrollbar{display:none}',
'.u-special-day{appearance:none;border:0;flex:0 0 auto;min-width:61px;height:50px;border-radius:10px;background:transparent;color:#e8e8ea;display:grid;align-content:center;gap:2px;text-align:center;cursor:pointer;padding:3px 7px}',
'.u-special-day .date{font-size:10px}.u-special-day .dow{font-size:8px;letter-spacing:.09em;color:#aeb0b6}.u-special-day.is-active{background:#e91f37;color:#fff}.u-special-day.is-active .dow{color:#fff}',
'.u-special-scroll{position:absolute;top:58px;width:26px;height:38px;border:0;background:linear-gradient(90deg,#050506 50%,transparent);color:#fff;z-index:3;font-size:24px;display:grid;place-items:center;cursor:pointer}.u-special-scroll.left{left:2px}.u-special-scroll.right{right:2px;transform:scaleX(-1)}',
'.nycif-context-open .u-list{top:248px!important}.nycif-mode-seven.nycif-context-open .u-list{top:248px!important}',
'.nycif-special-active .u-aux-chips{display:none!important}.nycif-special-active .u-special-calendars{display:grid!important}',
'.nycif-mode-tonight .u-special-calendars,.nycif-mode-seven .u-special-calendars{display:none!important}',
'.nycif-night-pin-icon{background:transparent!important;border:0!important}.nycif-night-pin-shell{width:42px;height:52px;position:relative;display:grid;place-items:start center}.nycif-night-pin-face{width:35px;height:35px;border-radius:50%;background:#09090b;border:2px solid #fff;box-shadow:0 0 0 3px var(--night-tone),0 0 14px color-mix(in srgb,var(--night-tone) 70%,transparent);display:grid;place-items:center;font-size:18px}.nycif-night-pin-tail{position:absolute;top:34px;width:2px;height:12px;background:var(--night-tone)}.nycif-night-pin-dot{position:absolute;top:44px;width:7px;height:7px;border-radius:50%;background:#09090b;border:2px solid var(--night-tone)}',
'@media(max-width:782px){.u-chips{top:78px!important;width:94vw!important}.u-chip{height:46px!important;font-size:12px!important}.u-aux-chips{top:132px;width:94vw}.u-aux-chips .u-chip{height:44px!important;font-size:10px!important}.u-aux-chips.is-seven .u-chip{min-width:70px}.u-special-calendars{top:186px;width:94vw}.nycif-context-open .u-list{top:236px!important}}'
].join('');document.head.appendChild(css);

var oldNow=chips.querySelector('[data-mode="NOW"]'),todayChip=chips.querySelector('[data-mode="TODAY"]'),coming=chips.querySelector('[data-mode="COMING"]'),seven=chips.querySelector('[data-mode="7D"]');
if(oldNow)oldNow.remove();if(coming)coming.remove();
if(todayChip){todayChip.innerHTML='<span>Now</span>';todayChip.setAttribute('data-public-mode','NOW');}
var tonight=chips.querySelector('[data-mode="TONIGHT"]');if(tonight)tonight.innerHTML='<span>Tonight</span>';
if(seven)seven.innerHTML='<span>7 Days</span>';

document.querySelectorAll('.u-night-subfilters,.u-seven-preview,.u-aux-chips').forEach(function(n){n.remove();});
var aux=document.createElement('div');aux.className='u-aux-chips';aux.setAttribute('data-nycif-aux','v15');
chips.insertAdjacentElement('afterend',aux);

var oldSpecial=document.querySelector('.u-special-calendars');if(oldSpecial)oldSpecial.remove();
var specialHost=document.createElement('div');specialHost.className='u-special-calendars';
aux.insertAdjacentElement('afterend',specialHost);

var nightKey=null,nightCache={},nightOverlay=null,specialState=null,sevenState=null,collections=[];

function adapter(){return window.NYCIF_MAPS&&window.NYCIF_MAPS.uEventMap||null;}
function map(){var a=adapter();return a&&a.map||null;}
function source(){var a=adapter();return a&&(a.getSource?a.getSource('eventsSrc'):a.sources&&a.sources.eventsSrc)||null;}
function group(){var a=adapter();return a&&a.layerGroups&&a.layerGroups.eventsPins;}
function hideEvents(){var m=map(),g=group();if(m&&g&&m.hasLayer(g))m.removeLayer(g);var s=source();if(s){var empty={type:'FeatureCollection',features:[]};if(s.setData)s.setData(empty);else s.data=empty;}}
function showEvents(){var m=map(),g=group();if(m&&g&&!m.hasLayer(g))g.addTo(m);}
function clearNight(){var m=map();if(m&&nightOverlay&&m.hasLayer(nightOverlay))m.removeLayer(nightOverlay);nightOverlay=null;}
function allEvents(){return root.__nycifAllEvents&&root.__nycifAllEvents.features||[];}
function setSource(features){var s=source(),d={type:'FeatureCollection',features:features||[]};if(s){if(s.setData)s.setData(d);else s.data=d;}showEvents();}
function fit(features){var a=adapter();if(a&&typeof a.fitFeatures==='function')a.fitFeatures(features||[]);}
function nyDate(d){return new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).format(d);}
function nyAddDays(day,offset){var p=String(day).split('-').map(Number);return nyDate(new Date(Date.UTC(p[0],p[1]-1,p[2]+offset,16,0,0)));}
function nyHour(d){return Number(new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',hour:'2-digit',hour12:false}).format(d));}
function eventStart(f){var p=f&&f.properties||{},v=p.start_date_time||p.start_at||p.event_date;var d=v?new Date(v):null;return d&&Number.isFinite(d.getTime())?d:null;}
function nextSevenKeys(){var today=nyDate(new Date()),out=[];for(var i=1;i<=7;i++)out.push(nyAddDays(today,i));return out;}
function mapped(rows){return (rows||[]).filter(function(f){return !!f.geometry;});}
function nowRows(){var today=nyDate(new Date());return allEvents().filter(function(f){var x=eventStart(f);return x&&nyDate(x)===today;});}
function strictTonightRows(){var today=nyDate(new Date());return allEvents().filter(function(f){var x=eventStart(f);if(!x||nyDate(x)!==today)return false;var h=nyHour(x);return h>=18&&h<=23;});}
function sevenWindowRows(){var keys=nextSevenKeys();return allEvents().filter(function(f){var x=eventStart(f);return x&&keys.indexOf(nyDate(x))>=0;});}
function closeList(){var h=document.getElementById('uHappeningList');if(h)h.classList.remove('is-active');}
function showNow(){nightKey=null;clearNight();var rows=mapped(nowRows());setSource(rows);fit(rows);closeList();}
function showTonightEvents(){nightKey=null;clearNight();var rows=mapped(strictTonightRows());setSource(rows);fit(rows);closeList();}
function showSevenEvents(day){nightKey=null;clearNight();var rows;if(day){rows=allEvents().filter(function(f){var x=eventStart(f);return x&&nyDate(x)===day;});}else rows=sevenWindowRows();var pins=mapped(rows);setSource(pins);fit(pins);closeList();}
function nowChip(){return chips.querySelector('[data-mode="TODAY"]')||chips.querySelector('[data-public-mode="NOW"]');}
function sevenChip(){return chips.querySelector('[data-mode="7D"]');}
function tonightChip(){return chips.querySelector('[data-mode="TONIGHT"]');}
function activateChip(target){Array.prototype.forEach.call(chips.querySelectorAll('.u-chip'),function(c){c.classList.toggle('is-active',c===target);});}
function mode(){var a=chips.querySelector('.u-chip.is-active');if(!a)return'NOW';var m=a.getAttribute('data-mode');return m==='TONIGHT'?'TONIGHT':m==='7D'?'7D':'NOW';}
function nightCfg(k){return k==='dispensary'?{tone:'#2f9e5b',emoji:'🌿'}:k==='liquor'?{tone:'#c47a18',emoji:'🍸'}:{tone:'#c026d3',emoji:'🍹'};}
function nightIcon(k){var c=nightCfg(k);return L.divIcon({className:'nycif-night-pin-icon',html:'<div class="nycif-night-pin-shell" style="--night-tone:'+c.tone+'"><div class="nycif-night-pin-face">'+c.emoji+'</div><span class="nycif-night-pin-tail"></span><span class="nycif-night-pin-dot"></span></div>',iconSize:[42,52],iconAnchor:[21,50]});}
async function loadNight(k,b){if(nightCache[k])return nightCache[k];if(b)b.classList.add('is-loading');try{var r=await fetch(NIGHT+'?layer='+encodeURIComponent(k),{cache:'no-store'});if(!r.ok)throw new Error('Layer unavailable');return nightCache[k]=await r.json();}finally{if(b)b.classList.remove('is-loading');}}
function renderNight(k,d){var m=map();if(!m||typeof L==='undefined')return;clearNight();nightOverlay=L.layerGroup().addTo(m);(d.features||[]).filter(function(f){var c=f&&f.geometry&&f.geometry.coordinates||[];return Number.isFinite(+c[0])&&Number.isFinite(+c[1]);}).slice(0,1000).forEach(function(f){var c=f.geometry.coordinates,p=f.properties||{};L.marker([+c[1],+c[0]],{icon:nightIcon(k),title:String(p.title||'Location')}).bindPopup('<strong>'+String(p.title||'Location').replace(/[<>&]/g,'')+'</strong>').addTo(nightOverlay);});}
async function activateNight(k,b){hideEvents();try{renderNight(k,await loadNight(k,b));}catch(e){console.error(e);nightKey=null;if(b)b.classList.remove('is-active');restoreModeEvents();}}
function restoreModeEvents(){var m=mode();if(m==='TONIGHT')showTonightEvents();else if(m==='7D')showSevenEvents(sevenState);else showNow();}
function turnOffContext(){sevenState=null;nightKey=null;clearNight();activateChip(nowChip());syncContext();showNow();}
function labelDate(key){var p=String(key).split('-').map(Number);return new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',month:'short',day:'numeric'}).format(new Date(Date.UTC(p[0],p[1]-1,p[2],16,0,0)));}
function labelDow(key){var p=String(key).split('-').map(Number);return new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',weekday:'short'}).format(new Date(Date.UTC(p[0],p[1]-1,p[2],16,0,0)));}
function renderAux(){var m=mode();aux.innerHTML='';aux.classList.remove('is-night','is-seven');if(specialState){aux.classList.remove('is-night','is-seven');return;}if(m==='7D'){aux.classList.add('is-seven');nextSevenKeys().forEach(function(key){var b=document.createElement('button');b.type='button';b.className='u-chip'+(sevenState===key?' is-active':'');b.setAttribute('data-seven-day',key);b.innerHTML='<span>'+labelDow(key)+'</span><small>'+labelDate(key)+'</small>';b.addEventListener('click',function(){if(sevenState===key){sevenState=null;renderAux();showSevenEvents(null);return;}sevenState=key;renderAux();showSevenEvents(key);});aux.appendChild(b);});return;}aux.classList.add('is-night');[{id:'5pm',label:'5 P.M. Somewhere',emoji:'🍹'},{id:'dispensary',label:'Dispensaries',emoji:'🌿'},{id:'liquor',label:'Liquor Stores',emoji:'🍸'}].forEach(function(layer){var b=document.createElement('button');b.type='button';b.className='u-chip'+(nightKey===layer.id?' is-active':'');b.setAttribute('data-night-layer',layer.id);b.innerHTML='<span>'+layer.emoji+' '+layer.label+'</span>';b.addEventListener('click',function(){if(nightKey===layer.id){nightKey=null;renderAux();restoreModeEvents();return;}nightKey=layer.id;renderAux();activateNight(layer.id,b);});aux.appendChild(b);});}
function syncContext(){var m=mode();root.classList.toggle('nycif-mode-now',m==='NOW');root.classList.toggle('nycif-mode-tonight',m==='TONIGHT');root.classList.toggle('nycif-mode-seven',m==='7D');root.classList.toggle('nycif-context-open',m!=='NOW'||specialHost.classList.contains('on')||!!nightKey);renderAux();if(specialState)return;if(m==='7D'){specialHost.classList.remove('on');if(!nightKey)showSevenEvents(sevenState);}else if(m==='TONIGHT'){specialHost.classList.remove('on');if(!nightKey)showTonightEvents();}else{if(collections.length&&!root.classList.contains('nycif-hide-special'))specialHost.classList.add('on');if(!nightKey)showNow();}}
function clearSpecialButtons(){Array.prototype.forEach.call(specialHost.querySelectorAll('.u-special-titlebar,.u-special-day'),function(b){b.classList.remove('is-active');});}
function renderList(rows,title){var h=document.getElementById('uHappeningList');if(!h)return;h.innerHTML='';rows.forEach(function(f){var p=f.properties||{},b=document.createElement('button'),s=document.createElement('strong'),sm=document.createElement('small');b.className='u-list-item';s.textContent=p.title||'Event';sm.textContent=[p.day_bucket,p.start_time&&p.start_time!=='TBA'?p.start_time:null,p.location||p.venue_name||p.borough,p.access].filter(Boolean).join(' · ');b.appendChild(s);b.appendChild(sm);if(f.geometry)b.addEventListener('click',function(){var a=adapter();if(a)a.flyTo({center:f.geometry.coordinates,zoom:14});closeList();});h.appendChild(b);});h.classList.add('is-active');var st=document.getElementById('uStat');if(st)st.textContent=(title||'Events')+' · '+rows.length;}
function bucketWeekday(c,key){if(key==='MISC/TBA')return'TBD';var f=(c.features||[]).find(function(x){return (x.properties||{}).day_bucket===key;});var p=f&&f.properties||{},v=p.event_date||p.start_at||p.start_date_time;if(!v)return'';var d=new Date(v);if(!Number.isFinite(d.getTime()))return'';return new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',weekday:'short'}).format(d).toUpperCase();}
function dayLabel(key){return key==='MISC/TBA'?'TBD':String(key).replace(/^SEP\s+/i,'Sep ');}
function applySpecial(c,bucket){specialState={id:c.collection_id,bucket:bucket||'*'};sevenState=null;nightKey=null;clearNight();root.classList.add('nycif-special-active');specialHost.classList.add('on');aux.classList.remove('is-night','is-seven');var rows=(c.features||[]).filter(function(f){return !bucket||(f.properties||{}).day_bucket===bucket;}),mappedRows=mapped(rows);setSource(mappedRows);fit(mappedRows);clearSpecialButtons();var target=bucket?specialHost.querySelector('[data-special-day="'+bucket+'"]'):specialHost.querySelector('[data-special-title="'+c.collection_id+'"]');if(target)target.classList.add('is-active');if(bucket==='MISC/TBA'||!mappedRows.length)renderList(rows,c.display_name+' · TBD');else closeList();}
function leaveSpecial(){if(!specialState)return;specialState=null;root.classList.remove('nycif-special-active');clearSpecialButtons();closeList();syncContext();}
function renderCollections(data){collections=data&&data.collections||[];specialHost.innerHTML='';if(!collections.length){specialHost.classList.remove('on');syncContext();return;}collections.forEach(function(c){var card=document.createElement('div'),title=document.createElement('button'),days=document.createElement('div');card.className='u-special-card';card.style.position='relative';title.type='button';title.className='u-special-titlebar';title.setAttribute('data-special-title',c.collection_id);title.textContent=c.display_name||c.short_label||'Special Collection';title.addEventListener('click',function(){if(specialState&&specialState.id===c.collection_id&&specialState.bucket==='*')leaveSpecial();else applySpecial(c,null);});days.className='u-special-days';(c.buckets||[]).forEach(function(x){var b=document.createElement('button');b.type='button';b.className='u-special-day';b.setAttribute('data-special-day',x.key);b.innerHTML='<span class="date">'+dayLabel(x.key)+'</span><span class="dow">'+bucketWeekday(c,x.key)+'</span>';b.addEventListener('click',function(){applySpecial(c,x.key);});days.appendChild(b);});var left=document.createElement('button'),right=document.createElement('button');left.type=right.type='button';left.className='u-special-scroll left';right.className='u-special-scroll right';left.textContent=right.textContent='‹';left.addEventListener('click',function(){days.scrollBy({left:-220,behavior:'smooth'});});right.addEventListener('click',function(){days.scrollBy({left:220,behavior:'smooth'});});card.appendChild(title);card.appendChild(days);card.appendChild(left);card.appendChild(right);specialHost.appendChild(card);});syncContext();}
async function loadSpecial(){try{var r=await fetch(SPECIAL,{cache:'no-store',headers:{apikey:APIKEY}});if(!r.ok)throw new Error('Special calendar unavailable');renderCollections(await r.json());}catch(e){console.error(e);collections=[];specialHost.classList.remove('on');syncContext();}}

chips.addEventListener('click',function(ev){var b=ev.target.closest('.u-chip');if(!b||!chips.contains(b))return;var requested=b.getAttribute('data-mode');if(requested!=='TONIGHT'&&requested!=='7D'&&requested!=='TODAY'&&requested!=='NOW')return;if((requested==='TONIGHT'||requested==='7D')&&b.classList.contains('is-active')){ev.preventDefault();ev.stopImmediatePropagation();turnOffContext();return;}ev.preventDefault();ev.stopImmediatePropagation();specialState=null;root.classList.remove('nycif-special-active');clearSpecialButtons();closeList();if(requested==='TONIGHT'){sevenState=null;nightKey=null;clearNight();activateChip(tonightChip());syncContext();return;}if(requested==='7D'){sevenState=null;nightKey=null;clearNight();activateChip(sevenChip());syncContext();return;}turnOffContext();},true);

root.addEventListener('nycif:events-ready',function(){syncContext();});
var m=map();if(m)m.on('moveend',function(){if(nightKey&&nightCache[nightKey]&&!specialState)renderNight(nightKey,nightCache[nightKey]);});
syncContext();loadSpecial();
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
