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
 const landing=select('#app').innerHTML;
 for(const title of ['Why do we need this service?','How it works','How can we take it further?','Google Maps Routes API','0.65','DRIVER EARNINGS PER RIDE'])assert(landing.includes(title));
 assert(!landing.includes('PRODUCT EXAMPLE'));
 await as('yelyn');
 const initial=app.rides.find(r=>r.trip_id===app.config.demo_start_trip_id);assert(initial);
 assert(select('#app').innerHTML.includes('View ride offer →'));
 await click(button({openRide:String(initial.id)}));assert(select('#modal-content').innerHTML.includes('request-form'));
 assert.equal(app.applications.length,0);
 await as('kate');app.boardKind='regular';await run('refresh')();
 assert(!select('#app').innerHTML.includes('Ride example'));assert(!select('#app').innerHTML.includes('Example A'));
 const origin=input.places[0],dest=input.places[4];
 const post=form('post-form',{role:'driver',kind:'regular',start_date:input.date,end_date:new Date(new Date(input.date+'T12:00:00Z').getTime()+21*86400000).toISOString().slice(0,10),departure_hour:13,weekdays:[1],seats:2,price_mode:'automatic',price:'',detour_minutes:10,note:'Tuesday class commute. Meet at the station entrance.',return_hour:17,...locationFields('origin',origin,'area',.5),...locationFields('dest',dest,'exact',0)});
 await run('updateQuote')(post);assert(post.querySelector('#price-quote').innerHTML.includes('Estimated Earnings'));
 assert.equal(post.elements.price.value,'12.00');
 await submit(post);
 // Later recurring dates are quoted independently in the background.
 for(let i=0;i<200&&app.priceState.pending;i++){await new Promise(resolve=>setTimeout(resolve,20));await run('refresh')()}
 const owned=app.rides.find(r=>r.note==='Tuesday class commute. Meet at the station entrance.');assert(owned);
 const tid=owned.trip_id,dates=app.rides.filter(r=>r.trip_id===tid).sort((a,b)=>a.trip_date.localeCompare(b.trip_date));assert.equal(dates.length,4);
 for(const r of dates){assert.equal(r.price_meta.model,'google_shared_v1');assert.equal(r.pricing.price_min_cents,990);assert.equal(r.pricing.price_max_cents,1200)}
 const ids={};
 for(const ride of dates.slice(0,2)){
  for(const who of ['yelyn','hannah','emily']){
   await as(who);const current=app.rides.find(r=>r.id===ride.id);assert(current);assert(!current.identity_revealed);
   const request=form('request-form',{scope:'date',party_size:1,auto_confirm:'on',...locationFields('origin',current.origin,'exact',0),...locationFields('dest',current.destination,'exact',0)});request.dataset.occurrence=String(ride.id);
   const path=`/api/occurrences/${ride.id}/request`,before=traffic.filter(t=>t.path===path).length;
   await Promise.all([submit(request),submit(request)]);assert.equal(traffic.filter(t=>t.path===path).length-before,1);
   const a=app.applications.find(a=>a.occurrence_id===ride.id);assert(a);ids[ride.id+who]=a.id;assert.equal(a.status,'pending');
   await as('kate','requests','incoming');await click(button({application:String(a.id),action:'accept'}));
   const markup=select('#modal-content').innerHTML;assert(markup.includes('Current price / rider'));
   const count=markup.match(/data-rider-count="(\d+)"/)[1];
   await click(button({application:String(a.id),action:'accept',riderCount:count},['data-confirmed']));
   assert.equal(app.applications.find(x=>x.id===a.id).status,who==='emily'?'waitlisted':'confirmed');
  }
 }
 await as('emily','requests','waitlist');
 const marker=`data-request-id="${ids[dates[0].id+'emily']}"`;
 assert.equal(select('#app').innerHTML.split(marker).length-1,1);await click(button({requestTab:'sent'}));assert(!select('#app').innerHTML.includes(marker));
 await as('yelyn','rides');app.myRole='rider';await run('refresh')();const first=app.myRides.find(r=>r.id===dates[0].id);assert.equal(first.agreed_price_cents,990);
 const cancel=button({skipWeek:String(first.id)},['data-confirmed']);const path=`/api/occurrences/${first.id}/skip-week`,before=traffic.filter(t=>t.path===path).length;
 await Promise.all([click(cancel),click(cancel)]);assert.equal(traffic.filter(t=>t.path===path).length-before,1);
 await as('emily','rides');app.myRole='rider';await run('refresh')();const promoted=app.myRides.find(r=>r.id===first.id);assert(promoted);assert.equal(promoted.driver.name,'Kate');assert.equal(promoted.agreed_price_cents,990);assert.equal(promoted.pricing.driver_earnings_cents,1980);
 const later=app.applications.find(a=>a.id===ids[dates[1].id+'emily']);assert.equal(later.status,'waitlisted');
 await as('kate','rides');app.myRole='driver';await run('refresh')();await click(button({skipWeek:String(dates[1].id)},['data-confirmed']));
 await as('emily','requests','sent');assert.equal(app.applications.find(a=>a.id===ids[dates[1].id+'emily']).status,'canceled');assert.equal(app.applications.find(a=>a.id===ids[dates[0].id+'emily']).status,'confirmed');
 const unavailable={pricing_status:{ready:false},price_cents:0};assert.equal(run('displayPrice')(unavailable,0),'Google price unavailable');
 console.log('PASS: ordinary UI post with Google HTTP quote, two weeks of actual requests/acceptance, Hannah second seat, Emily waitlist, single submissions, disjoint tabs, week-only promotion, Google-based shared prices, driver cancellation and landing content.');
})().catch(e=>{console.error(e);process.exitCode=1});
