(() => {
  const VERSION = 'all-source-data-explorer-v01-schema';
  const SCHEMA = window.NYCIF_EVENT_FEED_SCHEMA_V1;
  const PRIMARY_SCHEMA = 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/events_schema_v1_staged.json';
  const SUPPLEMENTAL_SCHEMA = 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/events_schema_v1_supplemental_review.json';
  const PRIMARY_FALLBACK = 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/nycif_staged_live_events.json';
  const SUPPLEMENTAL_FALLBACK = 'https://raw.githubusercontent.com/setoxxx/nycif-live-feeds/main/data/supplemental_events_staging_feed.json';
  const PAGE = 100;
  const CATEGORIES = {
    sports:['🏟️','Sports'], fitness:['💪','Fitness / wellness'], parks:['🌳','Parks / recreation'], arts:['🎭','Arts / culture'], market:['🛍️','Markets / fairs'], civic:['📣','Civic / neighborhood'], government:['🏛️','Government / hearings'], education:['📚','Education / training'], family:['👨‍👩‍👧','Kids / family'], services:['🤝','Benefits / services'], environment:['🌎','Environment'], volunteer:['🙋','Volunteer'], jobs:['💼','Jobs / careers'], housing:['🏠','Housing / tenant help'], general:['📍','General']
  };
  const state = { rows:[], filtered:[], shown:PAGE, query:'', category:'all', borough:'all', source:'all', date:'next7', marker:null, feedMeta:{} };
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const norm = v => String(v ?? '').toLowerCase().replace(/\s+/g,' ').trim();
  const dateKey = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  const today = () => dateKey(new Date());
  const plusDays = n => { const d=new Date(); d.setDate(d.getDate()+n); return dateKey(d); };
  const rowDate = r => {
    const direct=String(r.date||'').slice(0,10);
    if(/^\d{4}-\d{2}-\d{2}$/.test(direct)) return direct;
    const start = r.start_date_time || '';
    if(/^\d{4}-\d{2}-\d{2}/.test(start)) return start.slice(0,10);
    const t=Date.parse(start);
    return Number.isFinite(t)?dateKey(new Date(t)):'';
  };
  function toUiRow(schemaEvent, source){
    const mapReady = schemaEvent?.nycif?.coordinate_status === 'map_ready'
      && Number.isFinite(schemaEvent.latitude)
      && Number.isFinite(schemaEvent.longitude);
    const title = schemaEvent.title || 'Untitled event';
    const location = schemaEvent.location || '';
    const category = schemaEvent.category || 'general';
    const borough = schemaEvent.borough || '';
    const agency = schemaEvent.source?.dataset || '';
    return {
      ...schemaEvent,
      _id: `${source}:${schemaEvent.id}`,
      _source: source,
      _category: CATEGORIES[category] ? category : 'general',
      _date: rowDate(schemaEvent),
      _borough: borough,
      _title: title,
      _location: location,
      _lat: schemaEvent.latitude,
      _lng: schemaEvent.longitude,
      _mapReady: !!mapReady,
      _schema_version: SCHEMA?.SCHEMA_VERSION || '1.0',
      _search: norm([title, location, borough, category, agency, schemaEvent.id].filter(Boolean).join(' '))
    };
  }
  async function loadProjected(urls, label, dataLayer){
    let lastError = null;
    for (const url of urls) {
      try {
        const res = await fetch(`${url}?cache=${Date.now()}`, { cache:'no-store', headers:{ Accept:'application/json' } });
        if (!res.ok) throw new Error(`${label} HTTP ${res.status}`);
        const json = await res.json();
        const envelope = SCHEMA.projectEnvelope(json, dataLayer, json.generated_at_utc);
        if (envelope.schema_version !== '1.0') throw new Error(`${label} schema_version mismatch`);
        return { envelope, url };
      } catch (err) {
        lastError = err;
      }
    }
    throw lastError || new Error(`${label} failed`);
  }
  function install(){
    if(document.getElementById('nycifExplorerBtn'))return;
    const btn=document.createElement('button'); btn.id='nycifExplorerBtn'; btn.className='desk-btn nycif-explorer-btn'; btn.type='button'; btn.textContent='All Data'; btn.setAttribute('aria-controls','nycifExplorer'); btn.setAttribute('aria-expanded','false');
    const shell=document.querySelector('.map-shell'); shell?.appendChild(btn);
    const drawer=document.createElement('aside'); drawer.id='nycifExplorer'; drawer.className='desk-drawer nycif-explorer'; drawer.hidden=true; drawer.innerHTML=`<header class="desk-header"><div><p>NYC In Focus</p><h1>All-Source Data Explorer</h1></div><button id="nycifExplorerClose" class="close-btn" type="button">×</button></header><p id="nycifExplorerSummary" class="list-meta">Loading schema v1 data…</p><label class="search"><span class="sr-only">Search all loaded records</span><input id="nycifExplorerSearch" type="search" placeholder="Search titles, places, agencies and categories"></label><div class="nycif-explorer-filters"><select id="nycifExplorerSource"><option value="all">All sources</option><option value="primary">Approved / staged</option><option value="supplemental">Expanded review</option></select><select id="nycifExplorerCategory"><option value="all">All categories</option>${Object.entries(CATEGORIES).map(([k,v])=>`<option value="${k}">${v[0]} ${v[1]}</option>`).join('')}</select><select id="nycifExplorerBorough"><option value="all">All boroughs</option>${['Manhattan','Brooklyn','Queens','Bronx','Staten Island'].map(v=>`<option>${v}</option>`).join('')}</select><select id="nycifExplorerDate"><option value="next7">Next 7 days</option><option value="today">Today</option><option value="all">All upcoming</option></select></div><p class="nycif-explorer-note">Explorer rows are projected to event feed schema v1.0 (<code>latitude</code>/<code>longitude</code>, nested <code>source</code>). Expanded review records stay labeled REVIEW and are not promoted into the approved production feed. Records without usable coordinates remain LIST ONLY.</p><div id="nycifExplorerList" class="event-list"></div><button id="nycifExplorerMore" class="load-all" type="button" hidden>Load more</button>`;
    shell?.appendChild(drawer);
    const style=document.createElement('style'); style.id='nycifExplorerStyle'; style.textContent=`.nycif-explorer-btn{right:118px}.nycif-explorer{z-index:1600}.nycif-explorer-filters{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin:8px 0}.nycif-explorer-filters select{min-width:0;padding:9px;border-radius:9px}.nycif-explorer-note{font-size:11px;line-height:1.35;color:rgba(255,255,255,.72)}.nycif-explorer .event-item{display:block;width:100%;text-align:left}.nycif-source-review{color:#f59e0b;font-weight:800}.nycif-list-only{color:#ef4444;font-weight:800}.nycif-explorer .load-all{margin-top:10px}@media(max-width:600px){.nycif-explorer-btn{right:104px;bottom:20px}.nycif-explorer-filters{grid-template-columns:1fr}}`;
    document.head.appendChild(style);
    btn.addEventListener('click',()=>toggle(true)); document.getElementById('nycifExplorerClose').addEventListener('click',()=>toggle(false));
    document.getElementById('nycifExplorerSearch').addEventListener('input',e=>{state.query=norm(e.target.value);state.shown=PAGE;render();});
    [['nycifExplorerSource','source'],['nycifExplorerCategory','category'],['nycifExplorerBorough','borough'],['nycifExplorerDate','date']].forEach(([id,key])=>document.getElementById(id).addEventListener('change',e=>{state[key]=e.target.value;state.shown=PAGE;render();}));
    document.getElementById('nycifExplorerMore').addEventListener('click',()=>{state.shown+=PAGE;render();});
  }
  function toggle(open){ const d=document.getElementById('nycifExplorer'),b=document.getElementById('nycifExplorerBtn'); d.hidden=!open;b.setAttribute('aria-expanded',String(open));setTimeout(()=>window.NYCIF_MAIN_MAP?.invalidateSize(),80); }
  function matches(r){
    if(state.source!=='all'&&r._source!==state.source)return false; if(state.category!=='all'&&r._category!==state.category)return false; if(state.borough!=='all'&&r._borough!==state.borough)return false; if(state.query&&!r._search.includes(state.query))return false;
    const t=today(), end=plusDays(7); if(state.date==='today'&&r._date!==t)return false; if(state.date==='next7'&&(!r._date||r._date<t||r._date>end))return false; if(state.date==='all'&&r._date&&r._date<t)return false; return true;
  }
  function card(r){ const cat=CATEGORIES[r._category]||CATEGORIES.general, review=r._source==='supplemental'; return `<article class="event-item" data-explorer-id="${esc(r._id)}" tabindex="0"><span class="item-top"><span class="item-source">${cat[0]} ${esc(cat[1])}</span><span class="item-tags"><span class="item-tag ${review?'nycif-source-review':''}">${review?'REVIEW':'LIVE'}</span>${r._mapReady?'':'<span class="item-tag nycif-list-only">LIST ONLY</span>'}</span></span><strong>${esc(r._title)}</strong><span>${esc(r._date||'Date unavailable')}</span><small>${esc([r._borough,r._location,r.source?.dataset].filter(Boolean).join(' • '))}</small>${review?'<small>Expanded source intake; manual review pending.</small>':''}</article>`; }
  function render(){
    state.filtered=state.rows.filter(matches).sort((a,b)=>(a._date||'9999').localeCompare(b._date||'9999')||a._title.localeCompare(b._title)); const shown=Math.min(state.shown,state.filtered.length), primary=state.rows.filter(r=>r._source==='primary').length,supp=state.rows.length-primary,mapReady=state.rows.filter(r=>r._mapReady).length;
    document.getElementById('nycifExplorerSummary').textContent=`schema ${SCHEMA?.SCHEMA_VERSION||'1.0'} · ${state.rows.length.toLocaleString()} loaded · ${primary.toLocaleString()} approved/staged · ${supp.toLocaleString()} expanded review · ${mapReady.toLocaleString()} map-ready · showing ${shown.toLocaleString()} of ${state.filtered.length.toLocaleString()} matches`;
    const list=document.getElementById('nycifExplorerList'); list.innerHTML=state.filtered.slice(0,shown).map(card).join('')||'<div class="empty">No records match this view.</div>';
    list.querySelectorAll('[data-explorer-id]').forEach(el=>{const open=()=>focus(state.rows.find(r=>r._id===el.dataset.explorerId));el.addEventListener('click',open);el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();open();}});});
    const more=document.getElementById('nycifExplorerMore'); more.hidden=shown>=state.filtered.length; more.textContent=`Load 100 more (${Math.max(0,state.filtered.length-shown).toLocaleString()} remaining)`;
  }
  function focus(r){ if(!r)return; if(!r._mapReady){document.getElementById('status').textContent=`${r._title}: coordinate pending; list-only record.`;return;} const map=window.NYCIF_MAIN_MAP;if(!map)return; if(state.marker)map.removeLayer(state.marker); state.marker=L.marker([r._lat,r._lng]).addTo(map).bindPopup(`<strong>${esc(r._title)}</strong><br>${esc(r._location)}<br>${r._source==='supplemental'?'Expanded review record':'Approved/staged record'}`).openPopup();map.flyTo([r._lat,r._lng],15,{duration:.5}); }
  async function boot(){
    install();
    if (!SCHEMA) {
      document.getElementById('nycifExplorerSummary').textContent = 'All-source explorer failed: schema v1 helper missing';
      return;
    }
    try{
      const [primary,supp]=await Promise.all([
        loadProjected([PRIMARY_SCHEMA, PRIMARY_FALLBACK], 'staged feed', 'approved_staged'),
        loadProjected([SUPPLEMENTAL_SCHEMA, SUPPLEMENTAL_FALLBACK], 'supplemental feed', 'review_supplemental')
      ]);
      state.feedMeta = {
        primaryUrl: primary.url,
        supplementalUrl: supp.url,
        primaryTotal: primary.envelope.total,
        supplementalTotal: supp.envelope.total,
        primaryCursor: primary.envelope.next_cursor,
        supplementalCursor: supp.envelope.next_cursor
      };
      state.rows=[
        ...primary.envelope.events.map(r=>toUiRow(r,'primary')),
        ...supp.envelope.events.map(r=>toUiRow(r,'supplemental'))
      ];
      render();
      window.NYCIF_ALL_SOURCE_EXPLORER={
        version:VERSION,
        schemaVersion: SCHEMA.SCHEMA_VERSION,
        getSummary:()=>({
          total:state.rows.length,
          primary:state.rows.filter(r=>r._source==='primary').length,
          supplemental:state.rows.filter(r=>r._source==='supplemental').length,
          mapReady:state.rows.filter(r=>r._mapReady).length,
          feedMeta: state.feedMeta,
          categories:Object.fromEntries(Object.keys(CATEGORIES).map(k=>[k,state.rows.filter(r=>r._category===k).length]))
        }),
        getSchemaSample:()=>state.rows[0] || null
      };
    }catch(e){
      document.getElementById('nycifExplorerSummary').textContent=`All-source explorer failed: ${e.message}`;
    }
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
