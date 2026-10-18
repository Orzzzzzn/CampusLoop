/* Production JS handlers against a real Python HTTP fixture, with a minimal
   document/form adapter. This checks logic and rendered HTML, not browser layout. */
'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
let principal='viewer';
function node(){return {innerHTML:'',textContent:'',hidden:false,disabled:false,open:false,children:[],handlers:{},classList:{add(){},remove(){},toggle(){}},addEventListener(k,fn){this.handlers[k]=fn},append(...children){this.children.push(...children)},replaceChildren(...children){this.children=children},showModal(){this.open=true},close(){this.open=false},setAttribute(){}}}
const nodes=new Map();const select=s=>{if(!nodes.has(s))nodes.set(s,node());return nodes.get(s)};
const document={querySelector:select,querySelectorAll(){return []},addEventListener(){},createElement:node};
class FormAdapter{
 constructor(form){this.entriesList=[];for(const [name,element] of Object.entries(form.elements||{})){if(element.disabled||element.value===null||element.value===undefined)continue;for(const value of Array.isArray(element.value)?element.value:[element.value])this.entriesList.push([name,String(value)])}}
 get(name){return this.entriesList.find(([key])=>key===name)?.[1]??null}
 getAll(name){return this.entriesList.filter(([key])=>key===name).map(([,value])=>value)}
 has(name){return this.entriesList.some(([key])=>key===name)}
 [Symbol.iterator](){return this.entriesList[Symbol.iterator]()}
}
const runtime=vm.createContext({document,window:{},navigator:{},FormData:FormAdapter,structuredClone,setTimeout,clearTimeout,console,fetch:(path,options={})=>fetch(input.base+path,{...options,headers:{...options.headers,Cookie:input.sessions[principal].cookie}})});
const source=fs.readFileSync(input.js,'utf8').replace(/\nboot\(\);\s*$/,'');vm.runInContext(source,runtime);
const run=code=>vm.runInContext(code,runtime),app=run('app'),clean=value=>JSON.parse(JSON.stringify(value));
function form(id,fields){const elements=Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,{value:v,disabled:false}]));const parts=new Map();return {id,elements,isConnected:true,dataset:{},querySelector(s){if(!parts.has(s))parts.set(s,node());return parts.get(s)},querySelectorAll(){return []}}}
const submit=async f=>run('handleSubmit')({preventDefault(){},target:f});
function locationFields(prefix,point,mode='area',radius=1){return {[prefix+'_resolved']:JSON.stringify(point),[prefix+'_label']:point.label,[prefix+'_mode']:mode,[prefix+'_radius']:radius}}
const button=(dataset,attributes=[])=>({dataset,hasAttribute:name=>attributes.includes(name)});
const click=async b=>run('handleClick')({target:{closest(){return b}}});
async function as(who,page='browse',tab='incoming'){principal=who;app.user=input.sessions[who].user;app.csrf=input.sessions[who].csrf;app.page=page;app.requestTab=tab;app.criteria={};app.boardRole='all';await run('refresh')()}
(async()=>{
 await run('boot')();assert(app.user,'Boot must retain the authenticated API session');
 assert.equal(app.config.version,'2.2.2');assert.equal(app.boardRole,'all');assert.equal(new Set(app.rides.map(r=>r.role)).size,2);assert(new Set(app.rides.map(r=>r.trip_date)).size>1);
 assert(app.rides.every(r=>!r.identity_revealed&&r.owner_name.startsWith('Loop Member ')),'A fresh student sees only aliases');
 let html=select('#app').innerHTML;assert(html.includes('Ask CampusLoop.'));assert(html.includes('Recurring rides'));assert(html.includes('One-time & round trips'));assert(!/[\uac00-\ud7a3]/.test(html));assert(!/sample pin|latitude|longitude/i.test(html));
 const blank=run('locationFields')('origin',null,true,false);assert(blank.includes('value=""'));assert(!blank.includes('Wilshire'));assert(!blank.includes('disabled'));assert(!/name="origin_(lat|lon)"/.test(blank));
 const postForm=form('post-form',{origin_label:'USC',origin_resolved:'',origin_mode:'area',origin_radius:1});
 await run('searchPlace')(postForm,'origin');assert.equal(postForm.elements.origin_resolved.value,'','Searching does not select a place automatically');
 const results=postForm.querySelector('[data-place-results="origin"]');const chosen=results.children.find(n=>n.textContent==='USC Leavey Library');assert(chosen);chosen.handlers.click();assert.equal(JSON.parse(postForm.elements.origin_resolved.value).label,'USC Leavey Library');
 const origin=input.places[0],dest=input.places[4];
 const searchForm=form('search-form',{date:'',departure_from:'',departure_to:'',...locationFields('origin',origin,'area',.25),...locationFields('dest',dest,'area',1)});
 await submit(searchForm);assert(app.rides.length>0);assert(app.rides.every(r=>r.match_type==='both_locations'));assert.equal(app.criteria.origin.label,origin.label);assert.equal(app.criteria.destination.label,dest.label);assert.equal(app.criteria.origin.radius_miles,.25);
 searchForm.elements.date.value=input.date;searchForm.elements.departure_from.value='8';searchForm.elements.departure_to.value='8';await submit(searchForm);assert(app.rides.every(r=>r.trip_date===input.date&&r.departure_hour===8));
 searchForm.elements.origin_label.value='An unresolved new address';assert.throws(()=>run('readCriteria')(searchForm),/Choose your pickup/);assert(!run('readCriteria')(searchForm,true).origin,'Typing another place must not reuse the old coordinates');
 await click(button({},['data-clear-search']));assert.equal(Object.keys(app.criteria).length,0);assert(new Set(app.rides.map(r=>r.trip_date)).size>1);
 await as('owner');
 const post=form('post-form',{role:'driver',kind:'one',start_date:input.date,end_date:input.date,departure_hour:8,arrive_by:9,weekdays:[],seats:2,price:4,detour_minutes:10,note:'Node handler integration ride',return_hour:17,...locationFields('origin',origin,'area',1),...locationFields('dest',input.places[6],'area',1)});
 await submit(post);const ride=app.rides.find(r=>r.note==='Node handler integration ride');assert(ride);assert.equal(app.boardRole,'all');
 await as('viewer');const publicRide=app.rides.find(r=>r.id===ride.id);assert(publicRide.owner_name.startsWith('Loop Member '));assert(!publicRide.identity_revealed);
 const request=form('request-form',{party_size:1,auto_confirm:'on',...locationFields('origin',publicRide.suggested_meeting_origin,'exact',0),...locationFields('dest',publicRide.suggested_meeting_destination,'exact',0)});request.dataset.occurrence=String(ride.id);
 await submit(request);const pending=app.applications.find(a=>a.occurrence_id===ride.id);assert.equal(pending.status,'pending');assert(pending.owner_name.startsWith('Loop Member '));assert(!select('#app').innerHTML.includes('Mina Park'));
 await as('owner','requests','incoming');const incoming=app.applications.find(a=>a.id===pending.id);assert(incoming.requester_name.startsWith('Loop Member '));
 await click(button({application:String(pending.id),action:'accept'}));assert.equal(app.applications.find(a=>a.id===pending.id).requester_name,'Riley Taylor');
 await as('viewer','requests','sent');const confirmed=app.applications.find(a=>a.id===pending.id);assert.equal(confirmed.status,'confirmed');assert.equal(confirmed.owner_name,'Mina Park');assert(confirmed.identity_revealed);assert(select('#app').innerHTML.includes('Mina Park'));
 // My rides must preserve selected dates, distinguish the actual driving role, and render agreed terms.
 await as('viewer','rides');await click(button({myRole:'rider'}));
 let rideHtml=select('#app').innerHTML;assert(rideHtml.includes('Your confirmed driver'));assert(rideHtml.includes('Mina Park'));assert(rideHtml.includes('Toyota Prius'));assert(rideHtml.includes('Agreed cost share'));assert(rideHtml.includes('>MP</span>'));assert(!rideHtml.includes('>CL<'));
 assert(rideHtml.includes('Recurring rides'));assert(rideHtml.includes('One-time &amp; round trips')||rideHtml.includes('One-time & round trips'));
 const myFilter=form('my-filter-form',{date:'2000-01-01',scope:'all',departure_from:'',departure_to:''});
 await run('handleChange')({target:{form:myFilter,id:'my-date'}});assert.equal(app.myDate,'2000-01-01');assert.equal(app.myRides.length,0);
 myFilter.elements.date.value=input.date;myFilter.elements.scope.value='upcoming';myFilter.elements.departure_from.value=8;myFilter.elements.departure_to.value=8;await submit(myFilter);assert(app.myRides.some(r=>r.id===ride.id));assert(app.myRides.every(r=>r.trip_date===input.date&&r.departure_hour===8));
 await click(button({myRole:'driver'}));assert(!select('#app').innerHTML.includes('Your confirmed driver'));
 const anonymous=run('avatar')('Loop Member 000001',false,{count:2,average:4.5,role:'driver'});assert(anonymous.includes('Anonymous member'));assert(anonymous.includes('4.5 / 5 (2)'));assert(!anonymous.includes('>CL<'));
 const picture=run('routePreview')(publicRide);assert(picture.includes('data-route-preview'));assert(picture.includes('<svg'));assert(picture.includes('OpenStreetMap'));
 const roadPicture=run('routeSVG')({coordinates:[[origin.lon,origin.lat],[-118.3,34.04],[dest.lon,dest.lat]],is_road_route:true},true);assert(roadPicture.includes('tile.openstreetmap.org/'));assert(roadPicture.includes('Road route'));assert(!roadPicture.includes('stroke-dasharray'));
 // Demo Lab buttons execute the same real seat, claim, cancellation and rating APIs.
 await as('owner','lab');await click(button({},['data-create-demo']));assert.equal(app.scenarios.length,6);assert(select('#app').innerHTML.includes('Whole-party fit'));
 const manual=app.scenarios.find(s=>s.title.startsWith('2.')),release=manual.members.find(m=>m.can_release),waiting=manual.members.find(m=>m.is_you);
 await click(button({demoRelease:String(manual.id),aid:String(release.id)}));assert.equal(app.scenarios.find(s=>s.id===manual.id).members.find(m=>m.is_you).status,'waitlisted');
 await click(button({application:String(waiting.id),action:'claim'}));assert.equal(app.scenarios.find(s=>s.id===manual.id).members.find(m=>m.is_you).status,'confirmed');
 const history=app.scenarios.find(s=>s.title.startsWith('5.'));await click(button({labRides:history.trip_date}));
 const past=app.myRides.find(r=>r.id===history.occurrence_id);assert(past.completed);assert.equal(app.myRole,'rider');assert(past.rating_targets.length);
 await click(button({rate:String(past.id),subject:String(past.rating_targets[0].id)}));assert(select('#modal-content').innerHTML.includes('How was this ride?'));
 const ratingForm=form('rating-form',{stars:5});ratingForm.dataset={occurrence:String(past.id),subject:String(past.rating_targets[0].id)};await submit(ratingForm);assert.equal(app.myRides.find(r=>r.id===past.id).rating_targets[0].stars,5);
 // Owner controls must submit one-date and one-week exceptions through the visible handlers.
 await as('owner');post.elements.kind.value='regular';post.elements.end_date.value=new Date(new Date(input.date+'T12:00:00Z').getTime()+14*86400000).toISOString().slice(0,10);post.elements.weekdays.value=[0,1,2,3,4,5,6];post.elements.note.value='Node recurring exception example';await submit(post);
 const regular=app.rides.find(r=>r.note==='Node recurring exception example');assert(regular);
 app.myDate=regular.trip_date;app.myRole='driver';app.myScope='all';app.myKind='regular';app.myFrom='';app.myTo='';await run('navigate')('rides');assert(select('#app').innerHTML.includes('Change this date only'));
 await click(button({editDate:String(regular.id)}));assert(select('#modal-content').innerHTML.includes('Change this recurring date only'));
 const exception=form('exception-form',{departure_hour:10,arrive_by:11,note:'Changed this date'});exception.dataset.occurrence=String(regular.id);await submit(exception);assert.equal(app.myRides.find(r=>r.id===regular.id).departure_hour,10);
 await click(button({skipWeek:String(regular.id)}));assert(select('#modal-content').innerHTML.includes('Skip this week only?'));await click(button({skipWeek:String(regular.id)},['data-confirmed']));assert(!app.myRides.some(r=>r.id===regular.id));
 app.myDate='';await run('refresh')();assert(app.myRides.some(r=>r.trip_id===regular.trip_id),'Other weeks of the recurring schedule must remain');
 console.log('PASS: boot/session, blank locations, explicit place selection, both-end range matching, all dates/roles, date/hour filtering, unresolved-place validation, reset, post, pending aliases, accept, confirmed real names/initials, role tabs, My rides date/hour filters, driver info, agreed prices, route SVGs, Demo Lab manual claims, completed-ride ratings, one-date edits, and week-only skips.');
})().catch(error=>{console.error(error);process.exitCode=1});
