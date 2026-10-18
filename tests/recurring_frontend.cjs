/* Production JS handlers against a real Python HTTP fixture, with a minimal
   document/form adapter. This checks logic and rendered HTML, not browser layout. */
'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
let principal='yelyn';const traffic=[];
function node(){return {innerHTML:'',textContent:'',hidden:false,disabled:false,open:false,children:[],handlers:{},scrollIntoView(){},focus(){},classList:{add(){},remove(){},toggle(){}},addEventListener(k,fn){this.handlers[k]=fn},append(...children){this.children.push(...children)},replaceChildren(...children){this.children=children},showModal(){this.open=true},close(){this.open=false},setAttribute(){}}}
const nodes=new Map();const select=s=>{if(!nodes.has(s))nodes.set(s,node());return nodes.get(s)};
const document={querySelector:select,querySelectorAll(){return []},addEventListener(){},createElement:node};
class FormAdapter{
 constructor(form){this.entriesList=[];for(const [name,element] of Object.entries(form.elements||{})){if(element.disabled||element.value===null||element.value===undefined)continue;for(const value of Array.isArray(element.value)?element.value:[element.value])this.entriesList.push([name,String(value)])}}
 get(name){return this.entriesList.find(([key])=>key===name)?.[1]??null}
 getAll(name){return this.entriesList.filter(([key])=>key===name).map(([,value])=>value)}
 has(name){return this.entriesList.some(([key])=>key===name)}
 [Symbol.iterator](){return this.entriesList[Symbol.iterator]()}
}
const runtime=vm.createContext({document,window:{scrollTo(){}},navigator:{},FormData:FormAdapter,structuredClone,setTimeout,clearTimeout,console,fetch:(path,options={})=>{traffic.push({path,method:options.method||'GET'});return fetch(input.base+path,{...options,headers:{...options.headers,Cookie:input.sessions[principal].cookie}})}});
vm.runInContext(fs.readFileSync(input.js.replace(/app\.js$/, 'landing.js'),'utf8'),runtime);
const source=fs.readFileSync(input.js,'utf8').replace(/\nboot\(\);\s*$/,'');vm.runInContext(source,runtime);
const run=code=>vm.runInContext(code,runtime),app=run('app'),clean=value=>JSON.parse(JSON.stringify(value));
function form(id,fields){const elements=Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,{value:v,disabled:false}]));const parts=new Map();return {id,elements,isConnected:true,dataset:{},querySelector(s){if(!parts.has(s))parts.set(s,node());return parts.get(s)},querySelectorAll(){return []}}}
const submit=async f=>run('handleSubmit')({preventDefault(){},target:f});
function locationFields(prefix,point,mode='area',radius=1){return {[prefix+'_resolved']:JSON.stringify(point),[prefix+'_label']:point.label,[prefix+'_mode']:mode,[prefix+'_radius']:radius}}
const button=(dataset,attributes=[])=>({dataset,hasAttribute:name=>attributes.includes(name)});
const click=async b=>run('handleClick')({target:{closest(){return b}}});
async function as(who,page='browse',tab='incoming'){principal=who;app.user=input.sessions[who].user;app.csrf=input.sessions[who].csrf;app.page=page;app.requestTab=tab;app.criteria={};app.boardRole='all';await run('refresh')()}
(async()=>{
 await run('boot')();assert.equal(app.config.version,'2.5.0');
 await as('yelyn');app.boardKind='regular';await run('refresh')();
 const rides=app.rides.filter(r=>r.trip_id===app.config.demo_start_trip_id).sort((a,b)=>a.trip_date.localeCompare(b.trip_date));assert.equal(rides.length,4);
 assert(select('#app').innerHTML.includes('Recurring period:'));
 assert.equal((select('#app').innerHTML.match(/class="ride-card"/g)||[]).length,new Set(app.rides.filter(r=>r.kind==='regular').map(r=>r.trip_id)).size);
 const first=rides[0],ids={};
 for(const who of ['yelyn','hannah','emily']){
  await as(who);await click(button({openRide:String(first.id)}));
  const detail=select('#modal-content').innerHTML;assert(detail.includes('Request recurring period'));assert(detail.includes('4 remaining date(s)'));assert(detail.includes('Recurring period:'));
  const request=form('request-form',{party_size:1,auto_confirm:'on',...locationFields('origin',first.origin,'exact',0),...locationFields('dest',first.destination,'exact',0)});request.dataset.occurrence=String(first.id);
  const path=`/api/occurrences/${first.id}/request`,before=traffic.filter(t=>t.path===path).length;
  await Promise.all([submit(request),submit(request)]);assert.equal(traffic.filter(t=>t.path===path).length-before,1);
  const apps=app.applications.filter(a=>a.trip_id===first.trip_id);assert.equal(apps.length,4);assert(apps.every(a=>a.status==='pending'));
  assert.equal((select('#app').innerHTML.match(/class="request"/g)||[]).length,1);ids[who]=apps.find(a=>a.occurrence_id===first.id).id;
  await as('kate','requests','incoming');await click(button({application:String(ids[who]),action:'accept'}));
  const review=select('#modal-content').innerHTML;assert(review.includes('Review recurring period')||review.includes('One approval applies'));assert(review.includes('Confirm recurring period'));
  const token=review.match(/data-series-token="([a-f0-9]+)"/)[1];
  await click(button({application:String(ids[who]),action:'accept',seriesToken:token},['data-confirmed']));
  const approved=app.applications.filter(a=>a.requester_id===input.sessions[who].user.id&&a.trip_id===first.trip_id);
  assert.equal(approved.length,4);assert(approved.every(a=>a.status===(who==='emily'?'waitlisted':'confirmed')));
 }
 await as('emily','requests','waitlist');assert.equal((select('#app').innerHTML.match(/class="request"/g)||[]).length,1);
 await as('yelyn','rides');app.myRole='rider';await run('refresh')();assert.equal(app.myRides.filter(r=>r.trip_id===first.trip_id).length,4);
 await click(button({skipWeek:String(first.id)},['data-confirmed']));
 await as('emily','rides');assert(app.myRides.some(r=>r.id===first.id&&r.driver.name==='Kate'));assert.equal(app.applications.filter(a=>a.status==='waitlisted').length,3);
 await as('yelyn','requests','sent');assert.equal(app.applications.filter(a=>a.status==='confirmed').length,3);
 app.requestDate=rides[1].trip_date;await run('refresh')();assert.equal((select('#app').innerHTML.match(/class="request"/g)||[]).length,1);
 const sid=app.applications.find(a=>a.id===ids.yelyn).recurring_id;
 await click(button({withdrawSeries:String(sid)}));assert(select('#modal-content').innerHTML.includes('Cancel the remaining recurring period?'));
 await click(button({withdrawSeries:String(sid)},['data-confirmed']));assert(app.applications.filter(a=>a.trip_id===first.trip_id).every(a=>a.status==='canceled'));
 console.log('PASS: period labels, one board offer per series, one request, one approval, four bookings, waitlists, weekly exception, date filters, recurring withdrawal');
})().catch(error=>{console.error(error);process.exitCode=1});
