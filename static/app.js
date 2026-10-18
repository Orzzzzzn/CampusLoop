'use strict';
const CLIENT_VERSION='2.5.0';
const $=s=>document.querySelector(s);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const app={config:null,user:null,csrf:'',page:'home',afterAuth:'browse',boardRole:'all',boardKind:'one',authTab:'login',requestTab:'incoming',criteria:{},rides:[],myRides:[],applications:[],notifications:[],unread:0,bellOpen:false,myDate:'',myRole:'driver',myScope:'upcoming',myKind:'one',myFrom:'',myTo:'',requestDate:'',rag:null,ratingPrompted:false};
let map=null,mapLayers=[],activePin='origin',mapForm=null;
const submittingForms=new WeakSet(),pendingActions=new Set();
const hour=n=>String(n).padStart(2,'0')+':00';
const money=n=>'$'+(n/100).toFixed(2);
const fmt=d=>new Date(d+'T12:00:00').toLocaleDateString('en-US',{month:'short',day:'numeric',weekday:'short'});
const SORT_OPTIONS=[['recommended','Recommended'],['soonest','Earliest departure'],['nearest','Nearest places'],['price','Lowest price']];
const sortLabel=v=>(SORT_OPTIONS.find(([k])=>k===v)||[v,v])[1];
function tripWhen(r){
 const date=r.trip_date?fmt(r.trip_date):'';
 const out=hour(r.departure_hour);
 if(r.kind==='round'&&r.return_hour!=null&&r.return_hour!=='')return `${date} · out ${out} · back ${hour(r.return_hour)}`;
 return date?`${date} · ${out}`:out;
}

const weekday=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
function toast(message){$('#toast').textContent=message;$('#toast').classList.add('show');clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('#toast').classList.remove('show'),4500)}
async function api(path,body,method){
 const response=await fetch(path,{method:method||(body===undefined?'GET':'POST'),credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json',...(app.csrf?{'X-CSRF-Token':app.csrf}:{})},...(body===undefined?{}:{body:JSON.stringify(body)})});
 if(!(response.headers.get('content-type')||'').includes('application/json'))throw Error('This address did not return the CampusLoop API. Open http://127.0.0.1:8010.');
 const data=await response.json();
 if(!response.ok){if(response.status===401&&app.user){app.user=null;app.csrf='';render()}throw Error(data.error||`Request failed (HTTP ${response.status}).`)}
 return data;
}

function modal(title,body,wide=false){closeModal();$('#modal').classList.toggle('dialog-wide',wide);$('#modal-content').innerHTML=`<div class="modal-head"><h2 id="modal-title">${esc(title)}</h2><button class="close" data-close aria-label="Close dialog">×</button></div><div class="modal-body">${body}</div>`;$('#modal').showModal();observeRoutePreviews()}
function closeModal(){if(map){map.remove();map=null;mapLayers=[]}mapForm=null;if($('#modal').open)$('#modal').close()}
function roleButton(value,label){return `<button type="button" role="tab" aria-selected="${app.boardRole===value}" class="${app.boardRole===value?'active':''}" data-board-role="${value}">${label}</button>`}

function header(){
 $('#navigation').innerHTML=app.page==='home'?`<a href="#ways-to-ride">Ways to ride</a>
<a href="#how-it-works">How it works</a>
<a href="#why-campusloop">Why CampusLoop</a>
<a href="#faqs">FAQs</a>`:app.user?`<button data-nav="browse" class="${app.page==='browse'?'active':''}">Find a ride</button><button data-nav="rides" class="${app.page==='rides'?'active':''}">My rides</button><button data-nav="requests" class="${app.page==='requests'?'active':''}">Requests <span class="count">${app.applications.filter(a=>a.incoming&&a.status==='pending').length}</span></button>`:'';
 $('#account').innerHTML=app.page==='home'&&!app.user?`<button data-nav="auth" class="landing-header-login">Log in</button><button data-nav="browse" class="landing-header-start">Get started ↗</button>`:app.user?`<span class="server-status">● Connected</span><div class="bell-wrap"><button type="button" class="bell-btn" data-bell aria-label="Notifications"${app.unread?` title="${app.unread} unread"`:''}>${bellIcon()}${app.unread?`<span class="bell-dot" aria-hidden="true"></span>`:''}</button>${app.bellOpen?bellPanel():''}</div><button data-profile class="row"><span class="account-name" style="font-size:11px">${esc(app.user.name)}</span><span class="avatar sage">${esc(app.user.name.split(' ').map(s=>s[0]).join('').slice(0,2))}</span></button>`:'<span class="campus-pill">USC student community</span>';
}
function bellIcon(){return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M6 9a6 6 0 0 1 12 0c0 7 3 7 3 9H3c0-2 3-2 3-9" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M10 20a2 2 0 0 0 4 0" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>`}
function bellPanel(){
 const items=app.notifications.slice(0,20);
 return `<div class="bell-panel" role="menu"><h3>Notifications</h3>${items.length?items.map(n=>`<button type="button" class="bell-item${!n.read?' unread':''}" data-open-notification="${n.id}" data-kind="${esc(n.kind)}" data-occurrence="${n.occurrence_id||''}" data-application="${n.application_id||''}"><strong>${esc(n.title)}</strong><small>${esc(n.body)}</small></button>`).join(''):'<p class="help-text" style="padding:8px">No notifications yet.</p>'}${app.unread?`<button type="button" class="link" data-mark-all-read style="margin:8px;font-size:11px">Mark all as read</button>`:''}</div>`;
}
function render(){if(mapForm?.id==='search-form'){if(map)map.remove();map=null;mapForm=null;mapLayers=[]}header();$('#app').innerHTML=(app.page==='home'?landing():app.user?(app.page==='browse'?browse():app.page==='rides'?myRides():requests()):auth())+`<footer class="app-footer"><span>CampusLoop v${esc(app.config?.version||CLIENT_VERSION)} · Student to student. Your campus, connected.</span><span>USC community · ${app.config?.demo_mode?'Local development accounts':'Student email verification'} · America/Los_Angeles</span></footer>`;observeRoutePreviews()}
function auth(){return `<div class="auth-layout"><div class="auth-story"><div class="eyebrow demo-label"><span class="dot"></span> YOUR CAMPUS. YOUR LOOP.</div><h1>Your commute.<br>Your people.<br>Your CampusLoop.</h1><p>Find nearby rides, share a weekly routine, and meet students going your way. Your name stays private until a ride is confirmed.</p><span class="badge green">Anonymous before matching · Real names after confirmation</span></div><section class="auth-card"><div class="tabs-small"><button type="button" data-auth-tab="login" class="${app.authTab==='login'?'active':''}">Sign in</button><button type="button" data-auth-tab="register" class="${app.authTab==='register'?'active':''}">Create account</button></div><h2>${app.authTab==='login'?'Welcome back.':'Find your campus loop.'}</h2><form id="auth-form"><div data-form-error role="alert" hidden></div>${app.authTab==='register'?'<label class="form-field">Full name<input name="name" required minlength="2" maxlength="80" autocomplete="name"><small>Shared only with confirmed ride participants.</small></label>':''}<label class="form-field">Student email<input name="email" type="email" required autocomplete="username" placeholder="you@usc.edu" ></label><label class="form-field">Password<input name="password" type="password" required minlength="10" maxlength="200" autocomplete="${app.authTab==='login'?'current-password':'new-password'}"></label><button type="submit" class="btn primary">${app.authTab==='login'?'Sign in →':'Create student account →'}</button></form>${app.config?.demo_mode?'<div class="notice" style="margin-top:20px"><strong>Local test accounts</strong><br>'+Object.values(app.config.accounts||{}).map(esc).join(' · ')+'<br>Password: <code>heky-local-2026</code><br><small>Existing test passwords are kept for compatibility. Use separate browser profiles to sign in as each person. Requests, approvals, waitlists and cancellations change actual saved bookings. No booking is preconfirmed.</small></div>':''}</section></div>`}

function hourOptions(value='',any=true,max=23){return (any?'<option value="">Any hour</option>':'')+Array.from({length:max+1},(_,i)=>`<option value="${i}" ${String(value)===String(i)?'selected':''}>${hour(i)}</option>`).join('')}
function placeDefault(side){return (side==='origin'?app.criteria.origin:app.criteria.destination)||null}

function locationFields(side,loc,optional=false,enabled=true,fixed=false){
 const point=loc||placeDefault(side),label=point?.label||'',mode=fixed?'exact':point?.mode||'area',radius=point?.radius_miles||1,pickup=side==='origin';
 return `<fieldset class="location-input" data-location="${side}"><legend>${pickup?'Pickup':'Drop-off'} ${fixed?'meeting point':'place and range'}</legend><input type="hidden" name="${side}_resolved" value="${point?esc(JSON.stringify(point)):''}"><div class="place-search-row"><label class="form-field grow">${pickup?'Pickup':'Drop-off'} place or address<input type="search" name="${side}_label" value="${esc(label)}" ${optional?'':'required'} minlength="3" maxlength="180" autocomplete="off" placeholder="Enter your ${pickup?'pickup':'drop-off'} place or address" data-place-input="${side}"></label><button type="button" class="btn outline" data-find-place="${side}">Find place</button></div><div data-place-results="${side}" class="place-results" aria-live="polite"></div>${fixed?`<input type="hidden" name="${side}_mode" value="exact"><p class="help-text">This exact point is proposed to the other student for confirmation.</p>`:`<div class="coords"><label class="form-field">Meeting flexibility<select name="${side}_mode" data-location-mode="${side}"><option value="exact" ${mode==='exact'?'selected':''}>Exact place</option><option value="area" ${mode==='area'?'selected':''}>Nearby area</option></select></label><label class="form-field">Allowed range <output data-radius-value="${side}">${mode==='area'?radius+' mi':'Exact point'}</output><input name="${side}_radius" type="range" min="0.1" max="10" step="0.05" value="${radius}" data-radius-side="${side}" ${mode==='exact'?'disabled':''}></label></div><div class="radius-presets">${[.25,.5,1,2,3,5].map(n=>`<button type="button" data-set-radius="${n}" data-side="${side}" ${mode==='exact'?'disabled':''}>${n} mi</button>`).join('')}</div>`}<div class="location-feedback" data-place-feedback="${side}">${label?esc(mode==='area'?'Within '+radius+' mi of '+label:'Exact place: '+label):optional?'Any '+(pickup?'pickup':'drop-off')+' location · choose a place to apply this filter.':'Choose the place you want. No location has been selected.'}</div><div class="map-toolbar" style="margin-top:9px"><button type="button" class="link" data-pick-map="${side}">Choose on map</button>${pickup?`<button type="button" class="link" data-current-location="${side}">Use my location</button>`:''}${optional?`<button type="button" class="link" data-clear-place="${side}">Clear ${pickup?'pickup':'drop-off'}</button>`:''}</div></fieldset>`;
}

function resolvedPlace(form,side){try{return JSON.parse(form.elements[side+'_resolved'].value)}catch{return null}}
function setPlace(form,side,place){
 const label=place.label;const loc={...place,label};form.elements[side+'_resolved'].value=JSON.stringify(loc);form.elements[side+'_label'].value=label;
 const result=form.querySelector(`[data-place-results="${side}"]`);if(result)result.replaceChildren();
 updateLocationFeedback(form,side);if(map&&mapForm===form)map.panTo([loc.lat,loc.lon]);drawPins();if(form.id==='search-form')autoSearch(form);if(form.id==='post-form')updateQuote(form);
}
function updateLocationFeedback(form,side){
 const mode=form.elements[side+'_mode'].value,radius=form.elements[side+'_radius'],value=radius?.value||1,label=form.elements[side+'_label'].value.trim(),point=resolvedPlace(form,side);
 if(radius)radius.disabled=mode==='exact';
 form.querySelectorAll(`[data-side="${side}"][data-set-radius]`).forEach(b=>b.disabled=mode==='exact');
 const out=form.querySelector(`[data-radius-value="${side}"]`);if(out)out.textContent=mode==='exact'?'Exact point':value+' mi';
 const feedback=form.querySelector(`[data-place-feedback="${side}"]`);if(feedback)feedback.textContent=!label?'No place selected.':!point||point.label!==label?'Select a search result or a point on the map to apply this place.':mode==='exact'?'Exact place: '+label:'Within '+value+' mi of '+label;
}

async function searchPlace(form,side){
 const input=form.elements[side+'_label'],value=input.value.trim(),result=form.querySelector(`[data-place-results="${side}"]`);if(value.length<2){toast('Enter a place name or an address.');return}
 result.textContent='Finding places…';const center=resolvedPlace(form,side);
 try{
  const data=await api('/api/places/search',{query:value,...(center?{bias:{lat:center.lat,lon:center.lon}}:{})});
  if(!form.isConnected||input.value.trim()!==value)return;
  result.replaceChildren();if(!data.places.length){result.textContent='No places found. Try a more specific address or choose on the map.';return}
  for(const place of data.places){const b=document.createElement('button');b.type='button';b.className='place-result';b.textContent=place.label;b.addEventListener('click',()=>setPlace(form,side,place));result.append(b)}
  const note=document.createElement('small');note.textContent=data.attribution;result.append(note);
 }catch(error){if(form.isConnected)result.textContent=error.message;throw error}
}

function autoSearch(form){if(form.id!=='search-form')return;try{app.criteria=readCriteria(form,true);app.rag=null;refresh().catch(e=>toast(e.message))}catch(e){toast(e.message)}}

async function submitRideSearch(form){
 app.criteria=readCriteria(form);app.rag=null;
 const button=form.querySelector('button[type="submit"]'),label=button?.textContent;
 if(button)button.textContent='Searching…';
 try{
  const sequence=refreshSequence+1;
  await refresh();
  if(app.page!=='browse'||sequence!==refreshSequence)return;
  const results=$('#ride-results');
  if(results){results.scrollIntoView({behavior:'smooth',block:'start'});results.focus({preventScroll:true})}
 }finally{if(button)button.textContent=label}
}

function readLocation(form,side,exact=false){
 const f=new FormData(form),point=resolvedPlace(form,side),label=(f.get(side+'_label')||'').trim();
 if(!point||!label||label!==point.label)throw Error('Choose '+(side==='origin'?'a pickup':'a drop-off')+' place from the results, or select it on the map.');
 const mode=exact?'exact':f.get(side+'_mode');return {label,lat:point.lat,lon:point.lon,mode,radius_miles:mode==='area'?Number(f.get(side+'_radius')):0};
}

function readCriteria(form,allowUnresolved=false){
 const f=new FormData(form),c={};if(app.boardRole!=='all')c.role=app.boardRole;if(f.get('date'))c.date=f.get('date');
 for(const k of ['departure_hour'])if(f.get(k)!==null&&f.get(k)!=='')c[k]=Number(f.get(k));
 if(f.get('sort'))c.sort=f.get('sort');else if(app.criteria.sort)c.sort=app.criteria.sort;

 for(const [field,key] of [['origin','origin'],['dest','destination']]){
  const label=(f.get(field+'_label')||'').trim(),point=resolvedPlace(form,field);
  if(label&&point?.label===label)c[key]=readLocation(form,field);
  else if(label&&!allowUnresolved)throw Error('Choose your '+(field==='origin'?'pickup':'drop-off')+' place from the search results or the map.');
 }
 return c;
}

function route(r){const a=r.origin,b=r.destination;return `<div class="route-with-map"><div class="ride-route"><div class="time">${hour(r.departure_hour)}</div><div class="route-point start"></div><div class="place">${esc(a.label)}<small>${a.mode==='area'?'Within '+a.radius_miles+' mi of center':'Exact pickup point'}</small></div><div class="time" style="grid-column:1">${r.pricing?.duration_minutes?'~'+Math.round(r.pricing.duration_minutes)+'m':'Arrival'}</div><div class="route-point end"></div><div class="place">${esc(b.label)}<small>${b.mode==='area'?'Within '+b.radius_miles+' mi of center':'Exact drop-off point'}</small></div>${r.kind==='round'&&r.return_hour!=null?`<p class="help-text">Return departure · ${hour(r.return_hour)}</p>`:''}${r.pricing?`<p class="help-text pricing-route-info">${routeEstimate(r.pricing)}</p>`:''}</div>${routePreview(r)}</div>${recurringPeriod(r)}`}
function seatSummary(r){
 if(r.role==='rider'){
  if(r.driver_id)return 'Driver confirmed';
  const n=r.capacity;
  return 'Party of '+n+' · looking for a driver';
 }
 const booked=r.confirmed_seats||0, open=r.available_seats, cap=r.capacity;
 if(open===0)return booked+' / '+cap+' seats filled · waitlist open';
 return booked+' riding · '+open+' of '+cap+' seats open';
}
function card(r){const full=r.role==='driver'&&r.available_seats===0;return `<article class="ride-card"><div class="row between"><div class="person">${avatar(r.owner_name,r.identity_revealed,r.owner_rating)}<div><strong>${esc(r.is_owner?'You':r.owner_name)}</strong><small>${r.is_owner?'Your post':r.identity_revealed?'Matched · real name shared':'Anonymous until a ride is confirmed'}</small></div></div><span class="badge ${r.role==='rider'?'amber':'green'}">${r.role==='rider'?'Looking for a driver':'Offering seats'}</span></div>${route(r)}${recommendation(r)}${r.match_type?`<div class="match-summary"><strong>${r.match_type==='both_locations'?'Both ends match your route':r.match_type==='pickup'?'Pickup matches your area':'Drop-off matches your area'}</strong>${r.pickup_distance_miles!==null?`<span>Pickup center · ${r.pickup_distance_miles.toFixed(1)} mi from ${esc(r.search_origin)}</span>`:''}${r.dropoff_distance_miles!==null?`<span>Drop-off center · ${r.dropoff_distance_miles.toFixed(1)} mi from ${esc(r.search_destination)}</span>`:''}</div>`:''}<div class="ride-meta"><span>${tripWhen(r)}</span><span>${r.kind==='regular'?'Recurring · '+r.weekdays.map(n=>weekday[n]).join('/'):r.kind==='round'?'Round trip':'One-time'}</span><span>Detour limit +${r.detour_minutes} min</span></div><div class="card-bottom"><span class="price">${r.pricing?priceRange(r.pricing):displayPrice(r,r.price_cents)} ${r.pricing_status?.ready===false?'<small>Waiting for route data</small>':r.pricing?`<small class="pricing-caption">Final price depends on confirmed rider count${r.kind==='round'?' · Both legs included':''}</small>`:`<small>/ passenger · ${r.kind==='round'?'both legs':'this date'}${r.role==='rider'?' budget':''} · Manual</small>`}</span><span class="seat ${full?'full':''}">${seatSummary(r)}</span><button type="button" class="btn ${full?'outline':'primary'}" data-open-ride="${r.id}">${r.is_owner?'Manage date':r.application&&!['canceled','declined'].includes(r.application.status)?'View request':r.role==='rider'?'Offer a ride':full?'Join waitlist':'View ride'} →</button></div></article>`}

function browse(){
 const c=app.criteria;
 const recurringCount=new Set(app.rides.filter(r=>r.kind==='regular').map(r=>r.trip_id)).size;
 const otherCount=app.rides.filter(r=>r.kind!=='regular').length;
 return `<section class="hero"><div><div class="eyebrow demo-label"><span class="dot"></span> YOUR CAMPUS. YOUR LOOP.</div><h1>Find your people.<br>Share your CampusLoop.</h1><p>All upcoming rides in one place. Search your route to find nearby pickup and drop-off areas.</p></div><button type="button" class="btn primary" data-post>＋ Post a ride</button></section>${priceNotice()}${startOffer()}<form id="search-form" class="app-search"><label class="form-field">Date · leave blank for all dates<input name="date" type="date" value="${esc(c.date||'')}"></label><label class="form-field">Departure time<select name="departure_hour">${hourOptions(c.departure_hour)}</select></label><button type="submit" class="btn lime">Find my loop →</button><div class="location-details"><div class="row between"><strong style="font-size:12px">Match to the places you choose</strong><span class="help-text">Choose either end or both · both ends must match when selected</span></div><div class="location-grid">${locationFields('origin',c.origin,true,!!c.origin)}${locationFields('dest',c.destination,true,!!c.destination)}</div><div id="search-map" class="mapbox" hidden></div><p class="help-text">Pick a place and a range. Matching updates automatically. Use Sort below the ride tabs to choose recommended, earliest, nearest, or lowest price. Names stay anonymous until confirmation.</p></div></form><div id="ride-results" class="controls board-title" tabindex="-1" role="region" aria-label="Ride search results"><div class="segmented" role="tablist" aria-label="Ride board">${roleButton('all','All rides')}${roleButton('driver','Rides offered')}${roleButton('rider','Riders looking')}</div><button type="button" class="link" data-clear-search>Clear all filters</button><span class="muted" style="font-size:11px">${recurringCount+otherCount} offers / requests · ${c.date?fmt(c.date):'All upcoming dates'} · ${esc(sortLabel(c.sort||'recommended'))} order</span></div>
 <div class="trip-kind-tabs" role="tablist" aria-label="Ride schedule">${[['one',`One-time & round trips (${otherCount})`],['regular',`Recurring rides (${recurringCount})`]].map(([v,l])=>`<button type="button" role="tab" aria-selected="${app.boardKind===v}" data-board-kind="${v}" class="${app.boardKind===v?'active':''}">${l}</button>`).join('')}</div>
 <div class="board-sort row between"><label class="form-field">Sort by<select data-board-sort>${SORT_OPTIONS.map(([v,l])=>`<option value="${v}" ${(c.sort||'recommended')===v?'selected':''}>${l}</option>`).join('')}</select></label></div>
 <div class="layout"><section class="ride-list">${app.rides.length?browseRideList():`<div class="empty"><h3>No rides match these filters</h3><p>Widen the pickup or drop-off range, or choose more dates and hours.</p><button type="button" class="btn outline" data-clear-search>Show all rides</button></div>`}</section><aside>${ragPanel()}</aside></div>`;
}

function browseRideList(){
 const kind=app.boardKind==='regular'?'regular':'one';
 let list=app.rides.filter(r=>(r.kind==='regular')===(kind==='regular'));
 if(kind==='regular'){
  const seen=new Set();
  list=list.filter(r=>{if(seen.has(r.trip_id))return false;seen.add(r.trip_id);return true});
  // Recommended keeps API order. Earliest first orders series by next upcoming date.
  if((app.criteria.sort||'recommended')==='soonest'){
   list=[...list].sort((a,b)=>a.trip_date.localeCompare(b.trip_date)||a.departure_hour-b.departure_hour||a.id-b.id);
  }
 }
 return `<section class="board-group"><div class="stack">${list.map(card).join('')||`<p class="empty">No matching rides in this section.${app.rides.length?` Try the ${app.boardKind==='regular'?'One-time & round trips':'Recurring rides'} tab.`:''}</p>`}</div></section>`;
}

function ragPanel(){const r=app.rag;return `<section class="rag-card"><span class="eyebrow demo-label">YOUR CAMPUS COPILOT</span><h3 style="margin-top:8px">Ask CampusLoop.</h3><p class="help-text" style="margin-top:8px">Find answers in current ride posts and community guidance. Uses the applied date and location filters.</p><form id="rag-form"><label class="screen-reader" for="rag-question">Ask about rides or policies</label><textarea id="rag-question" name="question" required minlength="2" maxlength="2000" placeholder="What happens to the waitlist if someone cancels?">${esc(r?.question||'')}</textarea><button class="btn primary full-width">Ask with sources ↗</button></form><div id="rag-result">${r?ragResult(r):'<div class="notice" style="margin-top:16px">The assistant reads sources. Bookings and seat changes always use the application buttons.</div>'}</div></section>`}
function ragResult(r){return `${r.warning?`<div class="notice alert" style="margin-top:15px">${esc(r.warning)}</div>`:''}${r.answer?`<div class="rag-answer">${esc(r.answer)}</div>`:'<p class="help-text" style="margin-top:15px">No AI answer was generated. Retrieved documents are available below.</p>'}<span class="badge gray">${esc(r.mode==='rag'?'Grounded answer · '+r.retrieval:r.mode)}</span>${(r.sources||[]).map(s=>`<details class="source"><summary>[${esc(s.citation)}] ${esc(s.title)}</summary><p>${esc(s.text)}</p>${s.occurrence_id?`<button class="link" data-open-ride="${s.occurrence_id}">View this ride</button>`:''}</details>`).join('')}`}
let refreshSequence=0;
async function refresh(){
 if(!app.user)return;const seq=++refreshSequence,page=app.page,criteria=structuredClone(app.criteria);
 if(page==='browse'&&!criteria.sort)criteria.sort='recommended';
 const [requests,notes,result,prices]=await Promise.all([
  api('/api/applications'),
  api('/api/notifications'),
  page==='browse'?api('/api/rides/search',criteria):page==='rides'?api('/api/my-rides/search',{date:app.myDate,scope:app.myScope,departure_from:app.myFrom===''?null:Number(app.myFrom)}):Promise.resolve(null),
  api('/api/pricing/status')
 ]);
 if(seq!==refreshSequence||!app.user||app.page!==page)return;
 app.applications=requests.applications;app.priceState=prices;
 app.notifications=notes.notifications||[];
 app.unread=notes.unread||0;
 if(page==='browse')app.rides=result.rides;if(page==='rides')app.myRides=result.rides;
 if(page==='browse')preferBoardKind();
 if(page==='rides')preferMyRideKind();
 render();
 if(page==='rides')maybePromptRatings();clearTimeout(refresh.priceTimer);const priceRows=page==='browse'?app.rides:page==='rides'?app.myRides:app.applications;const stalePrices=!prices.pending&&priceRows.some(r=>r.pricing_status?.state==='pending'&&!r.departed&&!r.closed);if((prices.running||stalePrices)&&['browse','rides','requests'].includes(page))refresh.priceTimer=setTimeout(()=>refresh().catch(e=>toast(e.message)),1500);
}
function preferBoardKind(){
 if(!app.rides.length)return;
 const onTab=app.rides.some(r=>(r.kind==='regular')===(app.boardKind==='regular'));
 if(!onTab)app.boardKind=app.rides.some(r=>r.kind==='regular')?'regular':'one';
}
function preferMyRideKind(){
 const roleRides=app.myRides.filter(r=>r.my_role===app.myRole);
 if(!roleRides.length)return;
 const onTab=roleRides.some(r=>(r.kind==='regular')===(app.myKind==='regular'));
 if(!onTab)app.myKind=roleRides.some(r=>r.kind==='regular')?'regular':'one';
}
function resetAccountFilters(){app.criteria={};app.requestDate='';app.myDate='';app.myFrom='';app.myTo='';app.boardKind='regular';app.myKind='regular';app.myRole=app.user?.vehicle?'driver':'rider'}
function displayPrice(ride,value){return ride.pricing_status?.ready===false?'Google price unavailable':money(value)}
function priceNotice(){const p=app.priceState||app.config?.pricing;if(!p?.pending)return '';return `<div class="notice" role="status"><strong>${p.running?'Loading Google Maps prices…':'Google Maps prices unavailable'}</strong><span> ${p.ready||0} / ${p.total||p.pending} scheduled rides priced</span><p>${p.running?'Route distance and traffic-aware travel time are being calculated. Booking opens when the route price is ready.':p.configured?'Some route quotes could not be loaded. Retry to calculate their prices.':'The app owner must enable Google route pricing before these rides can be booked.'}</p>${p.configured&&!p.running?'<button type="button" class="btn outline" data-retry-prices>Retry route prices</button>':''}</div>`}

function arrivalWindow(departure,minutes=60){return Math.min(23,Math.max(departure+1,Math.ceil(departure+(Number(minutes)||60)/60)))}
async function finishSignIn(){const next=app.afterAuth;app.afterAuth='browse';app.page='browse';resetAccountFilters();await refresh();if(next==='post')postRide()}
async function navigate(page){
 if(page==='home'){app.page='home';app.bellOpen=false;render();window.scrollTo(0,0);return}
 if(!app.user){app.afterAuth=page==='post'?'post':'browse';app.page='auth';app.authTab='login';render();window.scrollTo(0,0);return}
 app.page=page==='post'?'browse':['browse','rides','requests'].includes(page)?page:'browse';app.bellOpen=false;await refresh();if(page==='post')postRide();window.scrollTo(0,0);
}
function weekdayInputs(selected=[0,2,4]){return `<div class="weekdays">${weekday.map((name,n)=>`<label><input name="weekdays" type="checkbox" value="${n}" ${selected.includes(n)?'checked':''}><span>${name}</span></label>`).join('')}</div>`}
function applyTripKind(form,kind){
 const field=form.elements.kind;if(field)field.value=kind;
 form.querySelectorAll('[data-kind-tab]').forEach(b=>b.classList.toggle('active',b.dataset.kindTab===kind));
 form.querySelectorAll('[data-repeat-field]').forEach(x=>{x.hidden=kind!=='regular';x.querySelectorAll('input').forEach(input=>{input.disabled=kind!=='regular'})});
 const ret=form.querySelector('[data-return-field]');if(ret)ret.hidden=kind!=='round';
 updateQuote(form);
}
function postRide(){
 const first=app.criteria.date||app.config.default_date;
 const endDefault=new Date(new Date(first+'T12:00:00').getTime()+27*86400000).toISOString().slice(0,10);
 modal('Create your CampusLoop',`<p>Choose a route, a departure time, and whether your trip repeats.</p>
 <form id="post-form"><div data-form-error role="alert" hidden></div>
 <div class="trip-kind-tabs" role="tablist" aria-label="Trip type">
  <button type="button" data-kind-tab="one" class="active">One-time</button>
  <button type="button" data-kind-tab="round">Round trip</button>
  <button type="button" data-kind-tab="regular">Recurring</button>
 </div>
 <input type="hidden" name="kind" value="one" data-trip-type>
 <div class="form-grid">
  <label class="form-field">I am a<select name="role"><option value="driver">Driver · offering seats</option><option value="rider">Rider · looking for a driver</option></select></label>
  <div class="location-grid span2">${locationFields('origin')}${locationFields('dest')}</div>
  <div class="span2"><div class="map-toolbar">Click the map to set: <button type="button" class="chip active" data-pin-side="origin">Pickup</button><button type="button" class="chip" data-pin-side="dest">Drop-off</button></div><div id="location-map" class="mapbox">Loading map…</div><p class="help-text">Map tiles © OpenStreetMap contributors. Check the actual meeting entrance.</p><p id="quote-route-info" class="help-text" hidden></p></div>
  <label class="form-field">Travel date<input name="start_date" type="date" value="${first}" required></label>
  <label class="form-field" data-repeat-field hidden>Repeat through<input name="end_date" type="date" value="${endDefault}" required disabled></label>
  <label class="form-field">Departure hour<select name="departure_hour">${hourOptions(8,false,22)}</select></label>
  <label class="form-field" data-return-field hidden>Return departure<select name="return_hour">${hourOptions(17,false)}</select></label>
  <p class="help-text">Travel time is an estimate and can change with traffic. No arrival deadline is required.</p>
  <div class="form-field span2" data-repeat-field hidden>Weekdays${weekdayInputs()}</div>
  <label class="form-field">Passenger capacity / rider party size<input name="seats" type="number" min="1" max="4" value="2" required></label>
  <input type="hidden" name="price_mode" value="automatic"><p class="help-text">Google Maps pricing · distance, scheduled traffic and confirmed passengers.</p>
  <label class="form-field">Google base price / rider ($)<input name="price" type="number" min="0" step="0.01" value="" disabled readonly></label>
  <div class="notice span2" id="price-quote" aria-live="polite">Choose both places and a departure time to see your estimate.</div>
  <label class="form-field">Driver detour limit (minutes)<input name="detour_minutes" type="number" min="0" max="60" value="10" required></label>
  <label class="form-field span2">Meeting notes & preferences<textarea name="note" maxlength="1000" placeholder="Pickup notes, luggage, or timing flexibility. Keep your name private until matching."></textarea></label>
 </div>
 <div class="notice">Round trips cover both legs on that date. A recurring request covers all remaining scheduled dates. Approve once for the period; seats, Google prices and weekly cancellations stay date-specific.</div>
 <div class="modal-actions post-submit"><button type="button" class="btn outline" data-close>Cancel</button><button type="submit" class="btn primary">Publish ride →</button></div>
 </form>`,true);
 const form=$('#post-form');applyTripKind(form,'one');initMap(form);updateQuote(form);
}

function initMap(form,side='origin'){
 if(map){map.remove();map=null}mapForm=form;activePin=side;const container=form.querySelector('.mapbox');container.hidden=false;
 if(!window.L){container.textContent='The online map is unavailable. Use Find place to search a place or address.';return}
 map=L.map(container).setView([34.025,-118.29],12);L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(map);
 const point=resolvedPlace(form,side);if(point)map.setView([point.lat,point.lon],13);
 map.on('click',e=>setPlace(form,activePin,{label:activePin==='origin'?'Selected pickup location':'Selected drop-off location',lat:e.latlng.lat,lon:e.latlng.lng,source:'map'}));drawPins();setTimeout(()=>map?.invalidateSize(),0);
}

function drawPins(){if(!map||!mapForm)return;mapLayers.forEach(l=>map.removeLayer(l));mapLayers=[];for(const side of ['origin','dest']){const enabled=mapForm.elements[side+'_enabled'];if(enabled&&!enabled.checked)continue;const point=resolvedPlace(mapForm,side);if(!point)continue;const mode=mapForm.elements[side+'_mode']?.value||'exact';const radius=Number(mapForm.elements[side+'_radius']?.value||0);const color=side==='origin'?'#325e3b':'#326e83';mapLayers.push(L.circleMarker([point.lat,point.lon],{radius:7,color,fillOpacity:1}).bindTooltip(side==='origin'?'Your pickup center':'Your drop-off center').addTo(map));if(mode==='area'&&radius)mapLayers.push(L.circle([point.lat,point.lon],{radius:radius*1609.344,color,fillOpacity:.12}).addTo(map))}}

function allRides(){return [...app.rides,...app.myRides]}
async function showRide(id){
 const r=allRides().find(r=>r.id===id);if(!r){toast('Open the corresponding ride list to view this ride.');return}
 if(r.is_owner){
  if(r.role==='rider'&&!r.driver_id){modal('Your rider request',`${route(r)}${r.pricing?`<div class="notice">${pricingEstimate(r.pricing,false,r.kind)}</div>`:`<p class="agreed-price">Budget: ${displayPrice(r,r.price_cents)} / passenger · ${r.kind==='round'?'both legs':'this date'}</p>`}<p>Waiting for a driver. Confirmed passenger rides appear in My rides after you accept a driver’s offer.</p><div class="request-actions"><button class="btn outline" data-review-offers>Review incoming offers</button>${!r.departed&&!r.price_meta?.retired_setup?`<button class="btn danger" data-cancel-occurrence="${r.id}">Cancel this date</button>`:''}</div>`,true);return}
  app.myDate=r.trip_date;app.myScope='all';app.myRole=r.role==='driver'?'driver':(r.role==='rider'&&!r.driver_id?'pending':'rider');app.myKind=r.kind==='regular'?'regular':'one';await navigate('rides');return
 }
 const existing=r.application&&((!['canceled','declined'].includes(r.application.status)&&!(r.kind==='regular'&&!r.application.recurring_id))||['pending','approved'].includes(r.application.recurring_status));
 modal(r.role==='rider'?'Offer a ride':r.available_seats===0?'Request a waitlist spot':'Join this CampusLoop',`<div class="person">${avatar(r.owner_name,r.identity_revealed,r.owner_rating)}<div><strong>${esc(r.owner_name)}</strong><small>${r.identity_revealed?'Matched · real name shared':'Anonymous · identity shared after confirmation'}</small></div></div>${route(r)}<div class="notice">${esc(r.note)}</div><div class="summary-box"><div class="summary-line"><span>When</span><strong>${tripWhen(r)}</strong></div><div class="summary-line"><span>${r.role==='rider'?'Rider party size':'Seats available'}</span><strong>${r.role==='rider'?r.capacity:r.available_seats}</strong></div>${r.pricing?`<div class="notice">${ridePricing(r)}</div>`:`<div class="summary-line"><span>Price / passenger · this date</span><strong>${displayPrice(r,r.price_cents)}</strong></div>`}</div>${existing?`<div class="notice">Your request is ${esc(r.application.status)}. Manage it under Requests → ${r.application.status==='waitlisted'?'My waitlist':'Sent'}.</div>`:(r.pricing_status?.ready===false||(r.kind==='regular'&&r.recurring_schedule?.ready===false))?`<div class="notice">${esc(r.pricing_status.notice||'Waiting for Google quotes for the recurring period.')} All requested dates must have a route price before you can join.</div>`:r.departed?'<div class="notice">This ride has departed.</div>':r.role==='rider'&&r.driver_id?'<div class="notice">This student already accepted a driver.</div>':`<form id="request-form" data-occurrence="${r.id}"><input type="hidden" name="scope" value="${r.kind==='regular'?'series':'date'}">${r.kind==='regular'?seriesJoin(r):''}<div data-form-error role="alert" hidden></div>${r.role==='driver'&&r.available_seats===0?'<p class="notice">This ride is full. Your request needs driver approval before it joins My waitlist.</p>':''}<p class="help-text">The suggested meeting points fall in the shared area between your requested places and this ride. Both sides agree to these points when the request is accepted.</p><div class="location-grid">${locationFields('origin',r.suggested_meeting_origin,false,true,true)}${locationFields('dest',r.suggested_meeting_destination,false,true,true)}</div><div id="location-map" class="mapbox" hidden></div>${r.role==='driver'?'<label class="form-field" style="margin-top:15px">Passengers in your party<input name="party_size" type="number" min="1" max="4" value="${r.application?.party_size||1}" required></label><label class="check" style="margin-top:15px"><input name="auto_confirm" type="checkbox" checked>After driver approval, automatically confirm my party if enough seats open at these exact terms.</label>':''}<div class="modal-actions"><button type="submit" class="btn primary">${r.kind==='regular'?'Request recurring period':r.role==='rider'?'Send ride offer':r.available_seats===0?'Request waitlist spot':'Send seat request'} →</button></div></form>`}`,true);
}

function proposal(a){
 const nameNote=a.identity_revealed
  ?(a.was_matched&&a.status==='canceled'?'You were matched · real names stay shared':a.status==='confirmed'?'Ride confirmed · real names shared':'Real names shared for this request')
  :'Names stay anonymous until confirmation';
 return `<div class="party-proposal"><strong>Agreed meeting proposal</strong><span>↑ ${esc(a.meeting_origin.label)}</span><span>↓ ${esc(a.meeting_destination.label)}</span><small>${nameNote}</small></div>`;
}

function requestStatusLabel(a){
 if(a.series&&!app.requestDate){const c=a.series.counts;if(c.pending)return 'Recurring request';if(c.confirmed&&c.waitlisted)return 'Partially confirmed';if(c.waitlisted)return 'Recurring waitlist';if(c.confirmed)return 'Recurring confirmed'}
 if(a.owner_canceled)return 'driver canceled';
 return a.status;
}
function incomingPendingCount(){
 const seen=new Set();let n=0;
 for(const a of app.applications){
  if(!a.incoming||a.closed)continue;
  const pending=a.status==='pending'||(a.series&&a.series.counts.pending>0);
  if(!pending)continue;
  if(a.recurring_id){if(seen.has(a.recurring_id))continue;seen.add(a.recurring_id)}
  n+=1;
 }
 return n;
}
function requests(){
 const filtered=app.applications.filter(a=>(!app.requestDate||a.trip_date===app.requestDate)&&(app.requestTab==='incoming'?a.incoming:app.requestTab==='waitlist'?!a.incoming&&a.status==='waitlisted':!a.incoming&&a.status!=='waitlisted'));const list=sortByEarliest(groupSeriesRequests(filtered));
 return `<div class="page-top"><span class="eyebrow demo-label">YOUR SHARED PLANS</span><h1>Good company starts here.</h1><p>The post owner accepts requests. Only confirmed bookings occupy passenger seats.</p></div>
 <div class="row wrap"><label class="form-field">Travel date · blank for all<input type="date" value="${esc(app.requestDate)}" data-request-date="1"></label></div><div class="tabs-small">${[['incoming','Incoming'],['sent','Sent'],['waitlist','My waitlist']].map(([k,v])=>`<button data-request-tab="${k}" class="${app.requestTab===k?'active':''}">${v}</button>`).join('')}</div>
 <div class="stack">${list.length?list.map(a=>`<article class="request" data-request-id="${a.id}"><div class="row between"><div class="person">${avatar(a.incoming?a.requester_name:a.owner_name,a.identity_revealed,a.counterparty_rating)}<strong>${esc(a.incoming?a.requester_name:a.owner_name)}</strong></div><span class="badge ${a.status==='confirmed'?'green':a.owner_canceled?'amber':'gray'}">${esc(requestStatusLabel(a))}</span></div>
 <p>${esc(a.origin.label)} → ${esc(a.destination.label)}<br>${tripWhen(a)} · ${a.party_size} passenger${a.party_size===1?'':'s'} ${a.role==='rider'?'· driver offer':''}</p>
 ${a.owner_canceled?`<div class="owner-canceled-note">The driver canceled this ride date. Your request is listed here again so you can find another CampusLoop.</div>`:''}
 ${proposal(a)}${a.series?seriesStatus(a.series):''}${a.pricing?currentPricing(a.pricing,(a.incoming&&a.role==='driver')||(!a.incoming&&a.role==='rider')):''}<p class="agreed-price">${a.pricing?'Estimated price':a.status==='confirmed'?'Agreed':'Proposed'}: <strong>${displayPrice(a,a.agreed_price_cents)} / passenger</strong> · ${displayPrice(a,a.total_price_cents)} for ${a.party_size} · ${a.kind==='round'?'both legs':'this date'}</p>
 <div class="request-actions">${a.incoming&&(a.status==='pending'||(a.series&&a.series.counts.pending>0))?`<button class="btn primary" data-application="${a.id}" data-action="accept">${a.series?'Accept recurring period':'Accept request'}</button><button class="btn outline" data-application="${a.id}" data-action="decline">${a.series?'Decline remaining requests':'Decline'}</button>`:''}${!a.incoming&&a.series&&['pending','approved'].includes(a.series.status)?`<button class="btn outline" data-withdraw-series="${a.series.id}">Cancel remaining recurring dates</button>`:''}${!a.incoming&&!a.closed&&['pending','waitlisted','confirmed'].includes(a.status)?`<button class="btn ${a.status==='confirmed'?'danger':'outline'}" data-application="${a.id}" data-action="cancel">${a.status==='confirmed'?'Cancel this date':'Withdraw request'}</button>`:''}${!a.incoming&&!a.closed&&a.status==='waitlisted'&&!a.auto_confirm?`<button class="btn primary" data-application="${a.id}" data-action="claim">Confirm open seat</button>`:''}${a.status==='confirmed'?`<button class="btn outline" data-chat="${a.occurrence_id}">Ride chat</button>`:''}${a.owner_canceled?`<button class="btn primary" data-republish="${a.id}">Find another ride</button>`:''}</div>
 ${a.status==='waitlisted'?`<p class="help-text">Approved waitlist · position ${a.waitlist_position} · ${a.auto_confirm?'Auto-confirm enabled; promotion requires enough seats for your whole party.':'You must confirm an open seat manually.'}</p>`:''}</article>`).join(''):'<div class="empty"><h3>No requests here yet</h3><p>Find a ride or post your route to get started.</p><button class="btn primary" data-nav="browse">Find your people →</button></div>'}</div>`;
}
function myRides(){
 const rides=app.myRides.filter(r=>r.my_role===app.myRole);
 const kind=app.myKind==='regular'?'regular':'one';
 const list=sortByEarliest(rides.filter(r=>(r.kind==='regular')===(kind==='regular')));
 const recurringCount=rides.filter(r=>r.kind==='regular').length;
 const otherCount=rides.length-recurringCount;
 return `<div class="page-top row between"><div><span class="eyebrow demo-label">YOUR TRAVEL PLANS</span><h1>My rides.</h1><p>Driving and confirmed passenger bookings, with independent changes for each recurring date.</p></div><button class="btn primary" data-post>＋ Post a ride</button></div>
 <div class="tabs-small" role="tablist" aria-label="Your role">${[['driver','You’re driving'],['rider','Confirmed passenger'],['pending','Still pending']].map(([v,l])=>`<button role="tab" aria-selected="${app.myRole===v}" data-my-role="${v}" class="${app.myRole===v?'active':''}">${l}</button>`).join('')}</div>
 <div class="trip-kind-tabs" role="tablist" aria-label="Ride schedule">${[['one',`One-time & round trips (${otherCount})`],['regular',`Recurring rides (${recurringCount})`]].map(([v,l])=>`<button type="button" role="tab" aria-selected="${app.myKind===v}" data-my-kind="${v}" class="${app.myKind===v?'active':''}">${l}</button>`).join('')}</div>
 <form id="my-filter-form" class="my-filters"><label class="form-field">Travel date · blank for all<input id="my-date" name="date" type="date" value="${esc(app.myDate)}"></label><label class="form-field">Show<select name="scope">${[['upcoming','Upcoming'],['past','Past · rate ride partners'],['all','All dates']].map(([v,l])=>`<option value="${v}" ${app.myScope===v?'selected':''}>${l}</option>`).join('')}</select></label><label class="form-field">Departure from<select name="departure_from">${hourOptions(app.myFrom)}</select></label><button class="btn primary" type="submit">Apply filters</button><button class="btn outline" type="button" data-clear-my>Clear filters</button></form>
 <section class="ride-group"><div class="stack">${list.map(myRideCard).join('')||`<p class="empty">No rides in this section for the selected filters.${rides.length?` Try the ${app.myKind==='regular'?'One-time & round trips':'Recurring rides'} tab.`:''}</p>`}</div></section>`;
}
function myRideCard(r){
 const passenger=r.my_role==='rider', pending=r.my_role==='pending';
 const badge=pending?'amber': 'green';
 const badgeLabel=pending?'Still pending':passenger?'Confirmed passenger':'You’re driving';
 return `<article class="panel"><div class="row between"><strong>${tripWhen(r)} · ${r.kind==='regular'?'Recurring':r.kind==='round'?'Round trip':'One-time'}${r.has_exception?' · Date exception':''}</strong><span class="badge ${badge}">${badgeLabel}</span></div>${route(r)}
 ${r.price_meta?.retired_setup?'<p class="help-text">Archived agreement.</p>':''}${pending?`<div class="notice">Your rider request is open. Drivers can offer a ride; accept one under Requests → Incoming.</div>`:''}
 ${passenger&&r.driver?`<div class="matched-person person">${avatar(r.driver.name,r.driver.identity_revealed,r.driver.rating)}<div><small>Your confirmed driver</small><strong>${esc(r.driver.name)}</strong><p>${esc(r.driver.vehicle)}</p></div></div>`:''}
 ${!passenger&&!pending&&r.pending_requests?`<div class="notice"><strong>${r.pending_requests} request${r.pending_requests===1?'':'s'} awaiting approval</strong><p>Accept under Requests → Incoming. Waitlist spots appear only after you accept.</p><button type="button" class="btn primary" data-review-offers>Review Incoming →</button></div>`:''}${!passenger&&!pending&&r.passengers.length?`<div class="passenger-list">${r.passengers.map(p=>`<div class="person">${avatar(p.name,p.identity_revealed,p.rating)}<div><strong>${esc(p.name)}</strong><small>${p.party_size} passenger${p.party_size===1?'':'s'}</small></div></div>`).join('')}</div>`:''}
 ${r.meeting_origin?`<div class="party-proposal"><strong>Confirmed meeting points</strong><span>↑ ${esc(r.meeting_origin.label)}</span><span>↓ ${esc(r.meeting_destination.label)}</span></div>`:''}
 ${r.pricing?(pending?`<div class="notice">${pricingEstimate(r.pricing,false,r.kind)}</div>`:currentPricing(r.pricing,!passenger)):''}<p class="agreed-price">${r.pricing?(pending?'Estimated price':'Current price'):passenger||r.application?'Agreed cost share':pending?'Posted budget':'Posted cost share'}: <strong>${displayPrice(r,r.agreed_price_cents)} / passenger</strong>${r.party_size?` · ${displayPrice(r,r.total_price_cents)} for your party of ${r.party_size}`:''} · ${r.kind==='round'?'both legs included':'this date'}</p>
 <div class="row wrap between"><small class="muted">${pending?(r.pending_offers?r.pending_offers+' driver offer'+(r.pending_offers===1?'':'s')+' waiting':'Waiting for driver offers'):r.completed?'Completed':r.departed?'In progress':(r.pending_requests?r.pending_requests+' awaiting approval · ':'')+(r.waitlisted_parties?r.waitlisted_parties+' on waitlist · ':'')+r.confirmed_seats+' / '+r.capacity+' passenger seats booked'}</small><div class="request-actions">
 ${pending?`<button class="btn outline" data-review-offers>Review incoming offers</button>`:`<button class="btn outline" data-chat="${r.id}">Ride chat</button><button class="btn outline" data-activity="${r.id}">Seats & activity</button>`}
 ${r.rating_targets.map(t=>`<button class="btn lime" data-rate="${r.id}" data-subject="${t.id}">${t.stars?'Edit '+t.stars+'★ rating':'Rate '+esc(t.name)}</button>`).join('')}
 ${r.can_edit_date?`<button class="btn outline" data-edit-date="${r.id}">Change this date only</button>`:''}
 ${!r.departed&&r.application?.recurring_id?`<button class="btn outline" data-withdraw-series="${r.application.recurring_id}">Cancel remaining recurring dates</button>`:''}${!r.departed&&!r.price_meta?.retired_setup&&r.kind==='regular'?`<button class="btn outline" data-skip-week="${r.id}">Can’t make this week</button>`:''}
 ${!r.departed&&!r.price_meta?.retired_setup?(r.is_owner?`<button class="btn danger" data-cancel-occurrence="${r.id}">Skip / cancel this date</button>`:r.application?`<button class="btn danger" data-application="${r.application.id}" data-action="cancel">Cancel my seat · this date</button>`:''):''}</div></div></article>`;
}
function openRatingModal(rideId,subjectId){
 const r=allRides().find(x=>x.id===Number(rideId))||app.myRides.find(x=>x.id===Number(rideId));
 const t=r?.rating_targets?.find(x=>x.id===Number(subjectId));
 if(!t||!r){toast('Open Past rides to rate after a completed trip.');return}
 modal('How was this ride?',`<p>Rate ${esc(t.name)} (${esc(t.role)}) for ${fmt(r.trip_date)}. Riders rate the driver; drivers rate each passenger.</p>
 <form id="rating-form" data-occurrence="${r.id}" data-subject="${t.id}">
 <div class="rating-stars">${[5,4,3,2,1].map(n=>`<label><input type="radio" name="stars" value="${n}" ${t.stars===n||(!t.stars&&n===5)?'checked':''} required><span>${'★'.repeat(n)} ${n}</span></label>`).join('')}</div>
 <p class="help-text">One rating per person per confirmed ride. Saving again updates your existing rating.</p>
 <div class="modal-actions"><button type="button" class="btn outline" data-close>Later</button><button class="btn primary" type="submit">Save rating</button></div>
 </form>`);
}
function maybePromptRatings(){
 if(app.ratingPrompted||app.myScope!=='past')return;
 const pending=app.myRides.filter(r=>r.my_role===app.myRole&&r.completed).flatMap(r=>(r.rating_targets||[]).filter(t=>!t.stars).map(t=>({ride:r,target:t})));
 if(!pending.length)return;
 app.ratingPrompted=true;
 const first=pending[0];
 openRatingModal(first.ride.id,first.target.id);
 if(pending.length>1)toast(`${pending.length} completed rides are ready to rate.`);
}
async function activity(id){const data=await api(`/api/occurrences/${id}/activity`);const pending=data.members.filter(m=>m.status==='pending');modal('Seats & ride activity',`${pending.length?`<div class="notice"><strong>${pending.length} request${pending.length===1?'':'s'} awaiting your approval</strong><p>Accept under Requests → Incoming. Until you accept, they are not on the waitlist and do not hold a seat.</p><button type="button" class="btn primary" data-review-offers>Review Incoming →</button></div>`:''}${data.members.map(m=>`<div class="member"><strong>${esc(m.name)} · ${m.party_size} passenger${m.party_size===1?'':'s'}</strong><span class="badge ${m.status==='confirmed'?'green':m.status==='pending'?'amber':'gray'}">${esc(m.status==='pending'?'Awaiting approval':m.status)}${m.status==='waitlisted'&&m.auto_confirm?' · auto':''}</span></div>`).join('')||'<p class="help-text">No passengers or requests on this date yet.</p>'}<div class="timeline">${data.events.map(e=>`<p>${esc(e.message)}</p>`).join('')}</div>`)}
async function chat(id){const data=await api(`/api/occurrences/${id}/messages`);modal('Ride chat',`<p>Visible only to the post owner and confirmed participants.</p><div class="messages" aria-live="polite">${data.messages.map(m=>`<div class="message"><strong>${esc(m.name)}</strong>${esc(m.body)}</div>`).join('')||'<p class="help-text">Start with a meeting point or a quick hello.</p>'}</div><form id="chat-form" data-occurrence="${id}" class="row"><label class="form-field grow">Message<input name="body" maxlength="1000" required placeholder="See you at the entrance…"></label><button class="btn primary">Send</button></form><button class="link" data-chat="${id}" style="margin-top:15px;font-size:11px">Refresh messages</button>`)}
function profile(){modal('Your campus profile',`<div class="notice">${app.config.demo_mode?'Local development mode · verification codes are shown on-screen.':'Student email verification enabled.'}</div><div class="summary-line"><span>Email</span><strong>${esc(app.user.email)}</strong></div><div class="summary-line"><span>Status</span><strong>${app.user.verified?'Email verified':'Email verification required'}</strong></div><form id="profile-form"><label class="form-field" style="margin-top:15px">Full name<input name="name" value="${esc(app.user.name)}" required minlength="2" maxlength="80"></label><label class="form-field" style="margin-top:15px">Vehicle · required before driving<input name="vehicle" value="${esc(app.user.vehicle)}" maxlength="120" placeholder="Model, color, meeting details"></label><div class="modal-actions"><button type="button" class="btn outline" data-logout>Sign out</button><button class="btn primary">Save profile</button></div></form>${!app.user.verified?'<form id="resend-form" style="margin-top:15px"><label class="form-field">Password to request a new email code<input name="password" type="password" required></label><button class="btn outline" style="margin-top:10px">Send verification code</button></form>':''}`)}
function verification(email,developmentCode){modal('Verify your student email',`<p>Enter the six-digit code sent to ${esc(email)}.</p>${developmentCode?`<div class="notice">Development mode: no email was sent. Your test code is <strong>${esc(developmentCode)}</strong>.</div>`:''}<form id="verify-form"><input name="email" type="hidden" value="${esc(email)}"><label class="form-field" style="margin-top:15px">Verification code<input name="code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" required autocomplete="one-time-code"></label><div class="modal-actions"><button class="btn primary">Verify and continue</button></div></form>`)}
function confirmAction(title,message,attributes){modal(title,`<p>${esc(message)}</p><div class="modal-actions"><button class="btn outline" data-close>Keep it</button><button class="btn danger" ${attributes}>Confirm cancellation</button></div>`)}
function confirmRepublish(a){
 modal('Publish your ride again?',
  `<p>Post this route as your own rider request so drivers can find you on <strong>Find a ride</strong> and under <strong>My rides → Still pending</strong>. The canceled request will leave Sent.</p>
   <div class="summary-box">
    <div class="summary-line"><span>Route</span><strong>${esc(a.meeting_origin.label)} → ${esc(a.meeting_destination.label)}</strong></div>
    <div class="summary-line"><span>When</span><strong>${tripWhen(a)}</strong></div>
    <div class="summary-line"><span>Party</span><strong>${a.party_size} passenger${a.party_size===1?'':'s'}</strong></div>
    <div class="summary-line"><span>Budget / passenger</span><strong>${displayPrice(a,a.agreed_price_cents)}</strong></div>
   </div>
   <div class="modal-actions"><button type="button" class="btn outline" data-close>Not now</button><button type="button" class="btn primary" data-republish="${a.id}" data-confirmed>Yes, publish my ride</button></div>`);
}
async function handleClick(e){
 const b=e.target.closest('button');if(!b)return;
 const key=b.dataset.application?`application:${b.dataset.application}:${b.dataset.action}`:b.dataset.skipWeek?`week:${b.dataset.skipWeek}`:b.dataset.cancelOccurrence?`cancel:${b.dataset.cancelOccurrence}`:b.dataset.republish?`republish:${b.dataset.republish}`:null;
 if(!key)return dispatchClick(e);
 if(pendingActions.has(key))return;pendingActions.add(key);const disabled=b.disabled;b.disabled=true;
 try{return await dispatchClick(e)}finally{pendingActions.delete(key);b.disabled=disabled}
}
async function dispatchClick(e){const b=e.target.closest('button');if(!b)return;if(await featureClick(b))return;if(b.hasAttribute('data-close'))return closeModal();if(b.dataset.findPlace)return searchPlace(b.form,b.dataset.findPlace);if(b.dataset.clearPlace){const side=b.dataset.clearPlace;b.form.elements[side+'_resolved'].value='';b.form.elements[side+'_label'].value='';updateLocationFeedback(b.form,side);drawPins();if(b.form.id==='post-form')updateQuote(b.form);return autoSearch(b.form)}if(b.dataset.pickMap)return initMap(b.form,b.dataset.pickMap);if(b.dataset.setRadius){const side=b.dataset.side;b.form.elements[side+'_radius'].value=b.dataset.setRadius;updateLocationFeedback(b.form,side);drawPins();return hasResolvedPlace(b.form,side)?autoSearch(b.form):undefined}if(b.dataset.currentLocation){if(!navigator.geolocation)throw Error('Location access is unavailable in this browser.');const form=b.form,side=b.dataset.currentLocation;navigator.geolocation.getCurrentPosition(pos=>setPlace(form,side,{label:'Your current location',lat:pos.coords.latitude,lon:pos.coords.longitude,source:'map'}),()=>toast('Location access was not granted. Search a place or choose on the map.'));return}if(b.dataset.nav)return navigate(b.dataset.nav);if(b.dataset.authTab){app.authTab=b.dataset.authTab;return render()}if(b.dataset.boardRole){const form=$('#search-form');if(form)app.criteria=readCriteria(form);app.boardRole=b.dataset.boardRole;app.criteria.role=app.boardRole;app.rag=null;return refresh()}if(b.hasAttribute('data-post'))return postRide();if(b.hasAttribute('data-profile'))return profile();if(b.dataset.openRide)return showRide(Number(b.dataset.openRide));if(b.dataset.requestTab){app.requestTab=b.dataset.requestTab;return refresh()}if(b.hasAttribute('data-clear-search')){app.boardRole='all';app.boardKind='one';app.criteria={};app.rag=null;return refresh()}if(b.dataset.pinSide){activePin=b.dataset.pinSide;document.querySelectorAll('[data-pin-side]').forEach(x=>x.classList.toggle('active',x===b));return}if(b.dataset.chat)return chat(Number(b.dataset.chat));if(b.dataset.activity)return activity(Number(b.dataset.activity));if(b.hasAttribute('data-logout')){await api('/api/auth/logout',{});closeModal();app.user=null;app.csrf='';return render()}if(b.dataset.republish){const id=Number(b.dataset.republish);if(!b.hasAttribute('data-confirmed')){const a=app.applications.find(x=>x.id===id);if(!a)throw Error('That request is no longer available.');return confirmRepublish(a)}const result=await api(`/api/applications/${id}/republish`,{});closeModal();app.myRole='pending';app.myDate=result.trip_date||'';app.myScope='upcoming';app.myKind=result.kind==='regular'?'regular':'one';await navigate('rides');return toast('Your ride is posted again. Drivers can find it on Find a ride and under Still pending.')}if(b.dataset.application){const id=Number(b.dataset.application),action=b.dataset.action;if(action==='cancel'&&!b.hasAttribute('data-confirmed'))return confirmAction('Cancel only this date?','Your recurring trips on other dates stay unchanged. A released seat may go to an approved waitlisted party, and others on the waitlist get a notification to claim it.',`data-application="${id}" data-action="cancel" data-confirmed`);const result=await api(`/api/applications/${id}/${action}`,{expected_rider_count:Number(b.dataset.riderCount),expected_series_token:b.dataset.seriesToken});closeModal();await refresh();if(result.series&&['accept','decline'].includes(action))return toast(`Recurring period updated: ${result.series.counts.confirmed} confirmed, ${result.series.counts.waitlisted} waitlisted, ${result.series.counts.pending} pending.`);if(result.pricing&&['accept','claim'].includes(action))return toast(`Request ${result.status}. Current price: ${money(result.pricing.rider_price_cents)} / rider · Earnings: ${money(result.pricing.driver_earnings_cents)}`);return toast(result.promoted_application_ids?.length?'Canceled. The next eligible waitlisted party is confirmed.':'Request '+(result.status||'canceled')+'.')}if(b.dataset.cancelOccurrence&&!b.hasAttribute('data-confirmed'))return confirmAction('Cancel the whole ride date?','All requests and bookings for this single date will be canceled. Riders are notified and see the request again under Requests → Sent. Other recurring dates stay active.',`data-cancel-occurrence="${b.dataset.cancelOccurrence}" data-confirmed`);if(b.dataset.cancelOccurrence){await api(`/api/occurrences/${b.dataset.cancelOccurrence}/cancel`,{});closeModal();await refresh();toast('Ride canceled for this date. Riders were notified.')}}
async function handleSubmit(e){e.preventDefault();const form=e.target;if(submittingForms.has(form))return;submittingForms.add(form);const button=form.querySelector('button[type="submit"]');if(button)button.disabled=true;try{const f=new FormData(form);if(await featureSubmit(form,f))return;if(form.id==='auth-form'){if(app.authTab==='register'){const r=await api('/api/auth/register',Object.fromEntries(f));return verification(r.email,r.development_code)}const r=await api('/api/auth/login',Object.fromEntries(f));app.user=r.user;app.csrf=r.csrf;const session=await api('/api/me');app.user=session.user;app.csrf=session.csrf;await finishSignIn()}else if(form.id==='verify-form'){const r=await api('/api/auth/verify',Object.fromEntries(f));app.user=r.user;app.csrf=r.csrf;closeModal();await finishSignIn();toast('Student email verified.')}else if(form.id==='search-form'){await submitRideSearch(form)}else if(form.id==='post-form'){const d=Object.fromEntries(f),payload={role:d.role,kind:d.kind,origin:readLocation(form,'origin'),destination:readLocation(form,'dest'),start_date:d.start_date,end_date:d.end_date,departure_hour:Number(d.departure_hour),arrive_by:arrivalWindow(Number(d.departure_hour),form.quotedDurationMinutes),weekdays:f.getAll('weekdays').map(Number),seats:Number(d.seats),price_mode:'automatic',price_cents:Math.round(Number(d.price)*100),detour_minutes:Number(d.detour_minutes),note:d.note,return_hour:Number(d.return_hour)};const created=await api('/api/trips',payload);closeModal();app.boardRole='all';app.page='browse';app.criteria={};await refresh();toast('Ride published. It is now visible to other students.')}else if(form.id==='request-form'){const requested=await api(`/api/occurrences/${form.dataset.occurrence}/request`,{scope:f.get('scope')||(allRides().find(r=>r.id===Number(form.dataset.occurrence))?.kind==='regular'?'series':'date'),party_size:Number(f.get('party_size')||1),auto_confirm:f.has('auto_confirm'),meeting_origin:readLocation(form,'origin',true),meeting_destination:readLocation(form,'dest',true)});closeModal();app.requestDate='';app.requestTab=requested.status==='waitlisted'?'waitlist':'sent';await navigate('requests');toast(requested.already_requested?'Your existing request is shown. No additional request was created.':requested.recurring_id?'Recurring request sent for all remaining dates. The owner approves the period once.':'Sent. The post owner can now accept your request.')}else if(form.id==='profile-form'){await api('/api/me',Object.fromEntries(f),'PUT');const me=await api('/api/me');app.user=me.user;closeModal();render();toast('Profile saved.')}else if(form.id==='resend-form'){const r=await api('/api/auth/resend',{email:app.user.email,password:f.get('password')});verification(app.user.email,r.development_code)}else if(form.id==='chat-form'){await api(`/api/occurrences/${form.dataset.occurrence}/messages`,{body:f.get('body')});await chat(Number(form.dataset.occurrence))}else if(form.id==='rag-form'){const question=f.get('question');$('#rag-result').innerHTML='<div class="notice" style="margin-top:15px">Finding sources, then asking the local model… Later asks are usually faster once the model is warm.</div>';const r=await api('/api/rag/ask',{question,filters:app.criteria});app.rag={...r,question};const output=$('#rag-result');if(output)output.innerHTML=ragResult(app.rag)}}finally{submittingForms.delete(form);if(button)button.disabled=false}}
function hasResolvedPlace(form,side){
 const point=resolvedPlace(form,side),label=(form.elements[side+'_label']?.value||'').trim();
 return !!(point&&label&&point.label===label);
}
function handleChange(e){
 const t=e.target,form=t.form;if(t.dataset?.boardSort){app.criteria={...app.criteria,sort:t.value};app.rag=null;return refresh().catch(err=>toast(err.message))}if(t.dataset?.requestDate){app.requestDate=t.value;return refresh().catch(e=>toast(e.message))}if(t.id==='my-date'&&!form){app.myDate=t.value;return refresh()}if(!form)return;
 if(form.id==='my-filter-form'){readMyFilters(form);return refresh().catch(e=>toast(e.message))}
 if(t.dataset.locationEnable){t.closest('fieldset').disabled=!t.checked;if(!t.checked)return autoSearch(form);return}
 // Only re-search after a place is actually selected; typing must not wipe the field via refresh().
 if(t.dataset.locationMode){updateLocationFeedback(form,t.dataset.locationMode);drawPins();return hasResolvedPlace(form,t.dataset.locationMode)?autoSearch(form):undefined}
 if(t.dataset.radiusSide){updateLocationFeedback(form,t.dataset.radiusSide);drawPins();return hasResolvedPlace(form,t.dataset.radiusSide)?autoSearch(form):undefined}
 if(t.dataset.placeInput){
  const side=t.dataset.placeInput,p=resolvedPlace(form,side);
  if(p?.source==='map'&&t.value.trim()){p.label=t.value.trim();form.elements[side+'_resolved'].value=JSON.stringify(p)}
  if(!t.value.trim()){form.elements[side+'_resolved'].value='';updateLocationFeedback(form,side);return autoSearch(form)}
  if(p&&p.label!==t.value.trim())form.elements[side+'_resolved'].value='';
  updateLocationFeedback(form,side);
  return;
 }
 if(t.hasAttribute('data-trip-type')||t.dataset.kindTab){applyTripKind(form,t.dataset.kindTab||t.value);return}
 
 if(form.id==='search-form')autoSearch(form);if(form.id==='post-form')updateQuote(form);
}

document.addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.dataset.placeInput){e.preventDefault();searchPlace(e.target.form,e.target.dataset.placeInput).catch(err=>toast(err.message))}});
document.addEventListener('click',e=>{Promise.resolve(handleClick(e)).catch(err=>toast(err.message))});document.addEventListener('submit',e=>{handleSubmit(e).catch(err=>{const form=document.getElementById(e.target.id);let box=form?.querySelector('[data-form-error]');if(!box&&form){box=document.createElement('div');box.dataset.formError='';box.setAttribute('role','alert');form.prepend(box)}if(box){box.hidden=false;box.className='error-box';box.textContent=err.message}if(e.target.id==='rag-form'&&$('#rag-result'))$('#rag-result').textContent=err.message;toast(err.message)})});document.addEventListener('change',handleChange);document.addEventListener('input',e=>{if(e.target.dataset.radiusSide&&e.target.form){updateLocationFeedback(e.target.form,e.target.dataset.radiusSide);drawPins()}});$('#modal').addEventListener('close',()=>{if(!$('#modal').open){if(map){map.remove();map=null}mapForm=null}});
async function boot(){try{app.config=await api('/api/config');if(app.config.app_name!=='CampusLoop'||app.config.version!==CLIENT_VERSION)throw Error('This page requires CampusLoop '+CLIENT_VERSION+', but the connected server reports '+(app.config.version||'an older version')+'. Run python3 upgrade.py from the new release folder to update the running service.');app.criteria={};try{const me=await api('/api/me');app.user=me.user;app.csrf=me.csrf;resetAccountFilters()}catch{}render()}catch(err){$('#app').innerHTML=`<section class="panel"><h1>Could not connect to CampusLoop</h1><p>${esc(err.message)}</p><p>Run <code>python3 upgrade.py</code> from the new release folder, or start <code>python3 -m app.server</code> there when using native Python. The page and server must use the same release.</p></section>`}}

function avatar(name,revealed,rating){
 const face=revealed?esc(String(name).split(/\s+/).map(w=>w[0]).join('').slice(0,2)):'<svg viewBox="0 0 24 24" width="22" height="22" aria-label="Anonymous member" role="img"><circle cx="12" cy="8" r="4" fill="currentColor"/><path d="M4 22v-3a8 8 0 0 1 16 0v3" fill="currentColor"/></svg>';
 return `<div class="identity-mark"><span class="avatar sage" aria-label="${esc(revealed?name:'Anonymous member')}">${face}</span><small class="rating" title="${esc(rating?.role||'Member')} ratings">${rating?.count?'★ '+Number(rating.average).toFixed(1)+' / 5 ('+rating.count+')':'☆ No ratings'}</small></div>`;
}
function recommendation(r){const score=r.recommendation;if(!score)return '';return `<details class="recommendation"><summary>${score.score} / 100 relevance · Why this ride?</summary><p>${esc(score.reasons.join(' · '))}</p><small>${esc(score.explanation)}</small></details>`}
function readMyFilters(form){const f=new FormData(form);app.myDate=f.get('date')||'';app.myScope=f.get('scope')||'upcoming';app.myFrom=f.get('departure_from')||'';app.myTo=''}
async function updateQuote(form){
 if(!form||form.id!=='post-form'||!form.elements.price_mode)return;
 const box=form.querySelector('#price-quote'),seq=(form.quoteSequence||0)+1;form.quoteSequence=seq;
 const routeInfo=form.querySelector('#quote-route-info');
 if(routeInfo){routeInfo.hidden=true;routeInfo.textContent=''}
 form.elements.price.value='';
 let origin,destination;try{origin=readLocation(form,'origin');destination=readLocation(form,'dest')}catch{box.textContent='Choose both places to calculate the suggested cost share.';return}
 box.textContent='Calculating estimate…';
 const fields=new FormData(form);
 try{
  const q=await api('/api/pricing/quote',{origin,destination,kind:fields.get('kind'),seats:Number(fields.get('seats')),
   start_date:fields.get('start_date'),departure_hour:Number(fields.get('departure_hour')),
   return_hour:Number(fields.get('return_hour')),weekdays:fields.getAll('weekdays').map(Number)});
  if(seq!==form.quoteSequence||!form.isConnected)return;form.quotedDurationMinutes=q.duration_minutes;
  form.elements.price.value=(q.price_cents/100).toFixed(2);
  box.innerHTML=pricingEstimate(q.pricing,fields.get('role')==='driver',fields.get('kind'));
  if(routeInfo){routeInfo.textContent=routeEstimate(q.pricing);routeInfo.hidden=false}
 }catch(e){if(seq===form.quoteSequence)box.textContent=e.message}
}

function priceRange(p,driver=false){
 return driver?`Estimated Earnings: ${money(p.earnings_min_cents)} – ${money(p.earnings_max_cents)}`:
  `Estimated Price: ${money(p.price_min_cents)} – ${money(p.price_max_cents)} / rider`;
}
function pricingDetails(p){
 return `${p.distance_miles} mi · ~${p.duration_minutes} min · Google Maps traffic-aware estimate · No service fee`;
}
function routeEstimate(p){
 return `${p.distance_miles} mi · ~${p.duration_minutes} min · Google Maps`;
}
function pricingHelp(kind){
 return `<details class="pricing-explanation"><summary>How pricing works</summary><p>Base price = $0.60 × miles + $0.30 × minutes.<br>Driver earnings = base × [1 + 0.65 × (riders − 1)].<br>Price per rider = earnings ÷ riders.</p><p>Distance and traffic-aware travel time come from Google Maps for the scheduled departure. The estimate is saved when the ride is posted; prices update with confirmed rider count. No service fee or payment collection.${kind==='round'?' Both directions are included.':''}${kind==='regular'?' Each recurring date has its own scheduled Google traffic estimate. Changing its departure requests a new quote.':''}</p></details>`;
}
function pricingEstimate(p,driver=false,kind='one'){
 const riders=p.capacity===1?'1 rider':`1–${p.capacity} riders`;
 return `<strong>${priceRange(p,driver)}</strong><div class="help-text">${driver?riders+' · Based on estimated traffic':'Final price depends on confirmed rider count'}${kind==='round'?' · Both legs included':''}</div>${pricingHelp(kind)}`;
}
function ridePricing(r){
 if(r.role==='rider')return `<strong>Estimated Earnings: ${money(r.pricing.earnings_max_cents)}</strong><div class="help-text">${r.capacity} rider${r.capacity===1?'':'s'} · Based on estimated traffic${r.kind==='round'?' · Both legs included':''}</div>${pricingHelp(r.kind)}`;
 return pricingEstimate(r.pricing,false,r.kind);
}
function currentPricing(p,driver=false){
 return `<p class="agreed-price">Current ${driver?'estimated earnings':'price / rider'}: <strong>${money(driver?p.driver_earnings_cents:p.rider_price_cents)}</strong> · ${p.rider_count} rider${p.rider_count===1?'':'s'}${p.would_waitlist?' · Waitlist; your party is not counted':''}</p><p class="help-text">${pricingDetails(p)}. Price changes with confirmed rider count; estimate saved at posting.</p>`;
}
async function confirmPricing(b){
 const q=await api(`/api/applications/${b.dataset.application}/price`,{}),p=q.pricing;
 if(q.series&&b.dataset.action==='accept'){
  modal('Review recurring period',`${seriesReview(q.series)}<p>One approval applies to every pending future date shown. Full dates join the approved waitlist. Weekly cancellations stay canceled; later weeks remain booked.</p><div class="modal-actions"><button class="btn outline" data-close>Go back</button><button class="btn primary" data-application="${Number(b.dataset.application)}" data-action="accept" data-series-token="${esc(q.series.review_token)}" data-rider-count="${p?.rider_count||0}" data-confirmed>Confirm recurring period</button></div>`,true);return true;
 }
 if(!p)return false;
 modal('Review current price',`${currentPricing(p,true)}${currentPricing(p)}<p>${p.would_waitlist?'Your party will remain waitlisted until enough seats open.':'This estimate includes the party being confirmed.'} Prices update if riders join or cancel.</p><div class="modal-actions"><button class="btn outline" data-close>Go back</button><button class="btn primary" data-application="${Number(b.dataset.application)}" data-action="${esc(b.dataset.action)}" data-rider-count="${p.rider_count}" data-confirmed>Confirm ${b.dataset.action==='claim'?'open seat':'request'}</button></div>`);
 return true;
}
async function featureClick(b){
 if(b.dataset.withdrawSeries){
  if(!b.hasAttribute('data-confirmed')){confirmAction('Cancel the remaining recurring period?','All your pending, confirmed and waitlisted future dates on this post will be canceled. Past rides stay recorded. For a single week, use Can’t make this week instead.',`data-withdraw-series="${b.dataset.withdrawSeries}" data-confirmed`);return true}
  await api(`/api/recurring/${b.dataset.withdrawSeries}/withdraw`,{});closeModal();await refresh();toast('Remaining recurring dates canceled.');return true;
 }
 if(b.dataset.application&&b.dataset.action==='decline'&&!b.hasAttribute('data-confirmed')){
  const a=app.applications.find(x=>x.id===Number(b.dataset.application));if(a?.series){confirmAction('Decline this recurring request?','This declines every pending date in the period. Previously confirmed dates and weekly exceptions stay unchanged.',`data-application="${a.id}" data-action="decline" data-confirmed`);return true}
 }
 if(b.hasAttribute('data-retry-prices')){await api('/api/pricing/retry',{});await refresh();return true}
 if(b.dataset.application&&['accept','claim'].includes(b.dataset.action)&&!b.hasAttribute('data-confirmed')){const a=app.applications.find(x=>x.id===Number(b.dataset.application));if(a?.series||a?.pricing)return confirmPricing(b)}
 if(b.hasAttribute('data-review-offers')){closeModal();app.requestTab='incoming';await navigate('requests');return true}
 if(b.dataset.myRole){app.myRole=b.dataset.myRole;preferMyRideKind();render();return true}
 if(b.dataset.myKind){app.myKind=b.dataset.myKind;render();return true}
 if(b.dataset.boardKind){app.boardKind=b.dataset.boardKind;render();return true}
 if(b.hasAttribute('data-clear-my')){app.myDate='';app.myFrom='';app.myTo='';app.myScope='upcoming';await refresh();return true}
 if(b.dataset.editDate){const r=allRides().find(x=>x.id===Number(b.dataset.editDate));if(!r)return true;modal('Change this recurring date only',`<p>${fmt(r.trip_date)} · Other dates keep their usual schedule. Dates with active requests must be skipped and reposted to get new agreement.</p><form id="exception-form" data-occurrence="${r.id}"><label class="form-field">Departure<select name="departure_hour">${hourOptions(r.departure_hour,false,22)}</select></label><label class="form-field">Notes for this date<textarea name="note" maxlength="1000">${esc(r.note)}</textarea></label><div class="modal-actions"><button class="btn primary" type="submit">Save this date</button></div></form>`);return true}
 if(b.dataset.skipWeek){if(!b.hasAttribute('data-confirmed')){confirmAction('Skip this week only?','This skips future dates for this recurring ride in the Monday–Sunday week of the selected date. Your other weeks stay unchanged. As a passenger, only your bookings are canceled.',`data-skip-week="${b.dataset.skipWeek}" data-confirmed`);return true}const result=await api(`/api/occurrences/${b.dataset.skipWeek}/skip-week`,{});closeModal();await refresh();toast(`Skipped ${result.skipped_occurrence_ids.length} date(s) in this week.`);return true}
 if(b.dataset.rate){openRatingModal(Number(b.dataset.rate),Number(b.dataset.subject));return true}
 if(b.hasAttribute('data-bell')){app.bellOpen=!app.bellOpen;header();return true}
 if(b.hasAttribute('data-mark-all-read')){await api('/api/notifications/read',{});app.notifications.forEach(n=>n.read=1);app.unread=0;app.bellOpen=true;header();return true}
 if(b.dataset.openNotification){
  const id=Number(b.dataset.openNotification);
  await api('/api/notifications/read',{ids:[id]});
  const note=app.notifications.find(n=>n.id===id);if(note)note.read=1;
  const related=note&&app.applications.find(a=>a.id===note.application_id||a.occurrence_id===note.occurrence_id);if(related)app.requestDate=related.trip_date;
  app.unread=app.notifications.filter(n=>!n.read).length;app.bellOpen=false;header();
  if(note?.kind==='waitlist_open'&&note.application_id){
   app.requestTab='waitlist';await navigate('requests');toast('Confirm the open seat from My waitlist.');return true;
  }
  if(note?.kind==='driver_canceled'){app.requestTab='sent';await navigate('requests');return true}
  if(note?.kind==='waitlist_promoted'||note?.kind==='seat_freed'){app.myScope='upcoming';await navigate('rides');return true}
  return true;
 }
 if(b.dataset.kindTab){applyTripKind(b.form,b.dataset.kindTab);return true}
 return false;
}
async function featureSubmit(form,f){
 if(form.id==='my-filter-form'){readMyFilters(form);await refresh();return true}
 if(form.id==='exception-form'){await api(`/api/occurrences/${form.dataset.occurrence}/edit-date`,{departure_hour:Number(f.get('departure_hour')),arrive_by:arrivalWindow(Number(f.get('departure_hour'))),note:f.get('note')});closeModal();await refresh();toast('This date updated. Other dates keep their usual schedule.');return true}
 if(form.id==='rating-form'){await api(`/api/occurrences/${form.dataset.occurrence}/rating`,{subject_id:Number(form.dataset.subject),stars:Number(f.get('stars'))});closeModal();await refresh();toast('Rating saved.');return true}
 return false;
}

function routePreview(r){return `<figure class="route-preview" data-route-preview="${r.id}"><div class="route-image">${routeSVG({coordinates:[[r.origin.lon,r.origin.lat],[r.destination.lon,r.destination.lat]],is_road_route:false},false)}</div><figcaption>Approximate connection · loading road route</figcaption><small>© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a></small></figure>`}
function routeSVG(data,tiles){
 const W=232,H=142,pad=25;
 const project=([lon,lat])=>{const s=Math.sin(Math.max(-85.05,Math.min(85.05,lat))*Math.PI/180);return [(lon+180)/360,.5-Math.log((1+s)/(1-s))/(4*Math.PI)]};
 const points=data.coordinates.map(project),xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
 const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
 const z=Math.max(1,Math.min(17,Math.floor(Math.log2(Math.min((W-2*pad)/(Math.max(maxX-minX,1e-7)*256),(H-2*pad)/(Math.max(maxY-minY,1e-7)*256))))));
 const world=256*2**z,left=(minX+maxX)/2*world-W/2,top=(minY+maxY)/2*world-H/2;
 const xy=p=>[p[0]*world-left,p[1]*world-top],path=points.map((p,i)=>(i?'L':'M')+xy(p).map(n=>n.toFixed(1)).join(',')).join(' ');
 let images='';if(tiles)for(let x=Math.floor(left/256);x<=Math.floor((left+W)/256);x++)for(let y=Math.floor(top/256);y<=Math.floor((top+H)/256);y++)if(y>=0&&y<2**z)images+=`<image x="${x*256-left}" y="${y*256-top}" width="256" height="256" href="https://tile.openstreetmap.org/${z}/${((x%2**z)+2**z)%2**z}/${y}.png"/>`;
 const endpoints=[xy(points[0]),xy(points[points.length-1])];
 return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${data.is_road_route?'Road route':'Approximate connection; not a road route'}"><rect width="${W}" height="${H}" fill="#eaf0e6"/>${images}<path d="${path}" fill="none" stroke="white" stroke-width="7"/><path d="${path}" fill="none" stroke="#326344" stroke-width="4" ${data.is_road_route?'':'stroke-dasharray="6 5"'}/>${endpoints.map(([x,y],i)=>`<circle cx="${x}" cy="${y}" r="9" fill="${i?'#326e83':'#325e3b'}" stroke="white" stroke-width="2"/><text x="${x}" y="${y+3}" fill="white" text-anchor="middle" font-size="9" font-family="sans-serif">${i?'D':'P'}</text>`).join('')}</svg>`;
}
let routeObserver=null;
const previewCache=new Map();
function observeRoutePreviews(){
 if(typeof IntersectionObserver==='undefined')return;
 if(routeObserver)routeObserver.disconnect();
 routeObserver=new IntersectionObserver(entries=>{for(const entry of entries)if(entry.isIntersecting){routeObserver.unobserve(entry.target);loadPreview(entry.target)}},{rootMargin:'0px'});
 document.querySelectorAll('[data-route-preview]').forEach(el=>routeObserver.observe(el));
}
async function loadPreview(el){
 const id=Number(el.dataset.routePreview);
 try{let promise=previewCache.get(id);if(!promise){promise=api('/api/routes/preview',{occurrence_id:id});previewCache.set(id,promise)}const data=await promise;if(!el.isConnected)return;el.querySelector('.route-image').innerHTML=routeSVG(data,true);el.querySelector('figcaption').textContent=data.is_road_route?`${data.distance_miles} mi · ~${data.duration_minutes} min · OSRM map preview`:`${data.distance_miles} mi estimate · approximate connection`;el.title=data.notice}catch(e){previewCache.delete(id);if(el.isConnected)el.querySelector('figcaption').textContent='Approximate connection · road map unavailable'}
}


function startOffer(){
 const id=app.config?.demo_start_trip_id;
 const rides=(app.rides||[]).filter(r=>r.trip_id===id).sort((a,b)=>a.trip_date.localeCompare(b.trip_date));
 const ride=rides[0];
 return ride?`<div class="notice row between"><span><strong>Tuesday class commute · 1 PM</strong><br>${esc(ride.origin.label)} → ${esc(ride.destination.label)} · 2 passenger seats</span><button class="btn outline" data-open-ride="${ride.id}">View ride offer →</button></div>`:'';
}

function recurringPeriod(r){
 if(r.kind!=='regular'&&!r.series)return '';
 const period=r.recurring_schedule||r.series||r,days=(period.weekdays||[]).map(d=>['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][d]).join(', ');
 return period.start_date?`<div class="recurring-period"><strong>Recurring period: ${fmt(period.start_date)} – ${fmt(period.end_date)}</strong><span>${esc(days)} · Join once for all remaining dates · Skip individual weeks when needed</span></div>`:'';
}
function seriesJoin(r){
 const s=r.recurring_schedule;if(!s)return '';
 return `<div class="notice"><strong>Join the recurring period</strong><p>${s.date_count} remaining date(s), from ${s.dates.length?fmt(s.dates[0].trip_date):'now'} through ${fmt(s.end_date)}. Request once; the owner approves all dates once. Full dates are waitlisted separately. All future dates in this published period are included, regardless of the date filter.</p>${dateTable(s.dates,false)}</div>`;
}
function dateTable(dates,review){
 return `<table class="series-dates"><thead><tr><th>Date / departure</th><th>${review?'Status / after approval':'Price per rider'}</th><th>${review?'Current price / rider':'Google estimate'}</th></tr></thead><tbody>${dates.map(d=>`<tr><td>${fmt(d.trip_date)} · ${hour(d.departure_hour)}</td><td>${review?esc(d.status==='pending'&&d.upcoming?(d.pricing?.would_waitlist?'Waitlist':'Confirm'):d.status):d.pricing?priceRange(d.pricing):d.price_cents!=null?money(d.price_cents):'Unavailable'}</td><td>${d.pricing?(review?money(d.pricing.rider_price_cents):`${d.pricing.distance_miles} mi · ${d.pricing.duration_minutes} min`):d.price_cents!=null?money(d.price_cents):'Unavailable'}</td></tr>`).join('')}</tbody></table>`;
}
function seriesStatus(s){return `${recurringPeriod({kind:'regular',series:s})}<p class="help-text">${s.counts.confirmed} confirmed · ${s.counts.waitlisted} waitlisted · ${s.counts.pending} pending upcoming dates. Prices and seats apply separately to each date.</p><details><summary>View dates in this recurring request (${s.date_count})</summary>${dateTable(s.dates,true)}</details>`}
function seriesReview(s){return `${recurringPeriod({kind:'regular',series:s})}${dateTable(s.dates,true)}<p class="help-text">Prices use each date’s Google quote and confirmed passenger count. Pending and waitlisted parties do not occupy seats. Quotes and capacity are checked again when you confirm.</p>`}
function sortByEarliest(rows){
 return [...rows].sort((a,b)=>(a.trip_date||'').localeCompare(b.trip_date||'')||(a.departure_hour||0)-(b.departure_hour||0)||(a.id||0)-(b.id||0));
}
function groupSeriesRequests(rows){
 if(app.requestDate)return sortByEarliest(rows);
 const grouped=new Map(),result=[];
 for(const a of rows){if(!a.recurring_id){result.push(a);continue}const previous=grouped.get(a.recurring_id);const rank=x=>x.closed?9:x.status==='pending'&&x.incoming?0:['confirmed','waitlisted','pending'].includes(x.status)?1:8;
  if(!previous||rank(a)<rank(previous)||(rank(a)===rank(previous)&&a.trip_date<previous.trip_date))grouped.set(a.recurring_id,a);
 }
 return sortByEarliest([...result,...grouped.values()]);
}

boot();
