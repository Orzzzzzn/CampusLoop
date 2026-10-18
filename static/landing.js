'use strict';

function campusPricingSlide(){
 return `<section class="cl-slide cl-price-slide" id="pricing-model">
  <div class="landing-shell">
   <div class="cl-slide-top"><span>◆ BEHIND THE MATCH</span><span>CAMPUSLOOP / PRICING MODEL</span></div>
   <h2>Share the ride. Share the cost.</h2>
   <p class="cl-intro">A transparent cost-sharing algorithm that rewards drivers for filling seats while reducing each rider's contribution.</p>
   <article class="cl-base-card">
    <div class="cl-step">01 / BASE PRICE</div>
    <h3>Base Price = Distance × Rate per mile + Time × Rate per minute</h3>
    <p>Google Maps Routes API provides distance and traffic-aware estimated travel time for the scheduled departure.</p>
    <div class="cl-base-divider"></div>
    <h4>The fixed pricing parameters are:</h4>
    <div class="cl-parameters">
     <div><span>Rate per mile</span><strong>$0.60/mi</strong></div>
     <div><span>Rate per minute</span><strong>$0.30/min</strong></div>
     <div><span>Service fee</span><strong>None</strong><small>Potential future fee as the platform scales</small></div>
    </div>
   </article>
   <div class="cl-formula-grid">
    <article><div class="cl-step">02 / DRIVER EARNINGS</div><h3>Base × [1 + 0.65(n − 1)]</h3><p>Each additional rider increases driver earnings by 65% of the base price.</p></article>
    <article><div class="cl-step">03 / RIDER CONTRIBUTION</div><h3>Driver earnings ÷ n</h3><p>The total is shared equally among confirmed riders. Here, n is the rider count.</p></article>
   </div>
   <article class="cl-demo-card" data-pricing-demo>
    <div class="cl-demo-head"><h3>See how sharing changes the price</h3><span>EXAMPLE TRIP</span></div>
    <p class="cl-demo-meta">18 miles · 41 minutes · $23.10 base price · Up to 4 riders</p>
    <div class="cl-demo-controls"><strong>Confirmed riders</strong><div><button type="button" data-rider-delta="-1" aria-label="Remove one rider">−</button><output data-rider-count aria-live="polite">3</output><button type="button" data-rider-delta="1" aria-label="Add one rider">+</button></div></div>
    <div class="cl-demo-results"><div><span>Driver earns</span><strong data-driver-earnings>$53.13</strong><small>Total trip earnings</small></div><div><span>Each rider pays</span><strong data-rider-payment>$17.71</strong><small>Equal contribution</small></div></div>
    <div class="cl-table-wrap"><table><thead><tr><th>Riders</th><th>Driver earns</th><th>Per rider</th></tr></thead><tbody>${[1,2,3,4].map(n=>{const total=23.1*(1+.65*(n-1));return `<tr data-rider-row="${n}" ${n===3?'class="is-selected"':''}><td>${n}</td><td>$${total.toFixed(2)}</td><td>$${(total/n).toFixed(2)}</td></tr>`}).join('')}</tbody></table></div>
   </article>
   <div class="cl-price-process"><h3>From estimate to confirmed price</h3><div><article><span>01 · POST</span><strong>Show a range</strong><p>Estimate from one rider through full capacity.</p></article><article><span>02 · MATCH</span><strong>Confirm riders</strong><p>Count accepted participants sharing the trip.</p></article><article><span>03 · UPDATE</span><strong>Recalculate</strong><p>Keep route data; update pricing using the confirmed count.</p></article></div></div>
   <p class="cl-price-foot">✓ Fixed rates · Traffic-aware route estimates · No current service fee · No surge multiplier</p>
  </div>
 </section>`;
}
function campusNextSlide(){
 return `<section class="cl-slide cl-next-slide" id="whats-next"><div class="landing-shell">
  <div class="cl-slide-top"><span>◆ THE ROAD AHEAD</span><span>CAMPUSLOOP / FUTURE VISION</span></div>
  <h2>Starting at USC.<br>Going everywhere.</h2>
  <p class="cl-intro">Launch with one trusted campus community. Then grow into a connected network that makes student travel easier, more social, and more affordable.</p>
  <div class="cl-current-focus"><div class="cl-step">PHASE 01 / INITIAL SCOPE</div><h3>Built for Trojans.</h3><p>Focus on USC students, with university email signup and a single account for offering or requesting one-time and recurring rides.</p><small>Planned verification: confirm email ownership and restrict USC access to approved university domains. A generic .edu address alone does not prove USC enrollment.</small></div>
  <div class="cl-roadmap-grid">
   <article><div class="cl-step">02 / EXPAND</div><div class="cl-roadmap-icon">◎</div><h3>More campuses.</h3><p>Extend to UCLA, nearby universities, and eventually student networks across the country.</p></article>
   <article><div class="cl-step">03 / TRUST</div><div class="cl-roadmap-icon">◇</div><h3>Safer coordination.</h3><p>Develop identity checks, trip reviews, ratings, and ride-sharing safety features.</p></article>
   <article><div class="cl-step">04 / CONNECT</div><div class="cl-roadmap-icon">↗</div><h3>More ways to travel.</h3><p>Connect shared rides with campus shuttles and public transit, including first- and last-mile trips.</p></article>
   <article><div class="cl-step">05 / OPTIMIZE</div><div class="cl-roadmap-icon">⌁</div><h3>Smarter matching.</h3><p>Explore flexible meeting points, event and airport ride pools, and demand-based recommendations.</p></article>
  </div>
  <div class="cl-next-closing">One campus today. <em>A connected student network tomorrow.</em></div>
 </div></section>`;
}
function updateCampusPricingDemo(demo){
 const n=Math.max(1,Math.min(4,Number(demo.dataset.riders||3)));
 demo.dataset.riders=String(n);
 const total=23.1*(1+.65*(n-1));
 demo.querySelector('[data-rider-count]').textContent=String(n);
 demo.querySelector('[data-driver-earnings]').textContent='$'+total.toFixed(2);
 demo.querySelector('[data-rider-payment]').textContent='$'+(total/n).toFixed(2);
 demo.querySelectorAll('[data-rider-row]').forEach(r=>r.classList.toggle('is-selected',Number(r.dataset.riderRow)===n));
 demo.querySelector('[data-rider-delta="-1"]').disabled=n===1;
 demo.querySelector('[data-rider-delta="1"]').disabled=n===4;
}
document.addEventListener('click',event=>{
 const button=event.target.closest('[data-rider-delta]');
 if(!button)return;
 const demo=button.closest('[data-pricing-demo]');
 if(!demo)return;
 demo.dataset.riders=String(Math.max(1,Math.min(4,Number(demo.dataset.riders||3)+Number(button.dataset.riderDelta))));
 updateCampusPricingDemo(demo);
});



function landing(){
 const link=(label,page,cls='')=>`<button type="button" class="${cls}" data-nav="${page}">${label}</button>`;
 return `<div class="landing" id="landing-top">
 <section class="landing-hero landing-shell"><div class="landing-hero-copy"><div class="landing-kicker">✳ GOOD PLANS. BETTER COMPANY.</div><h1>Share the route.<br>Split the cost.<br><em>Ride together.</em></h1><p>Campus plans. Weekend plans. Going-home plans. Share trips with students headed your way, and make getting there work for your budget.</p><div class="landing-actions">${link('Find your ride ↗','browse','landing-button lime')}${link('Post a trip ↗','post','landing-button ghost')}</div><span class="landing-small">↗ One account. Ride, drive, or do a little of both.</span></div><div class="landing-hero-image"><img src="/static/landing-photo-3.jpeg" alt="Students sharing a ride next to a car on campus"><span class="landing-image-tag">↗ Same direction. New connections.</span><div class="landing-float"><strong>✳ Campus</strong><span>⇄ Your next plan</span><small>Less “how do I get there?” More “let’s go.”</small></div></div></section>
 <div class="landing-banner"><div class="landing-shell landing-banner-inner"><h3>↗ Not a cab. A connection.</h3><p>Unlike Uber or Lyft, CampusLoop doesn't dispatch professional drivers. It connects students with similar routes and schedules, sharing journeys they're already planning to take.</p></div></div>
 <section class="landing-section landing-shell" id="ways-to-ride"><div class="landing-kicker">✳ TWO WAYS TO GET GOING</div><div class="landing-section-heading"><h2>For the everyday.<br>And the out-of-the-ordinary.</h2><p>A one-off adventure or your Monday routine.<br>Find a shared ride that fits the way you move.</p></div><div class="landing-trip-grid"><article class="landing-trip-card"><span class="landing-type">ONE PLAN, ONE GREAT TRIP</span><h3>One-Time Trips</h3><p>A ride for that thing on your calendar. Post or find a shared trip for a specific day, time, and destination.</p><div class="landing-tags"><span>✈ Airport runs</span><span>♫ Concert nights</span><span>☀ Weekend plans</span></div><small>Example: campus → airport · Friday, 2:00 PM</small></article><article class="landing-trip-card green"><span class="landing-type">YOUR WEEK, ON REPEAT</span><h3>Recurring Trips</h3><p>Make your regular route less of a regular expense. Match with students who share your daily or weekly schedule.</p><div class="landing-tags"><span>▦ Classes</span><span>⌘ Internships</span><span>↗ Daily commutes</span></div><small>Example: home → campus · Mon–Thu, 8:30 AM</small></article></div></section>
 <section class="landing-match" id="matching"><div class="landing-shell landing-match-inner"><div><div class="landing-kicker">✳ A LITTLE MORE IN COMMON</div><h2>Your route.<br>Your schedule.<br>Your kind of ride.</h2><p>Not just the same destination. Intelligent matching looks at the details that make a shared trip actually make sense.</p><ul><li>✓ Location & departure time</li><li>✓ Route overlap & available seats</li><li>✓ Cost-sharing preferences</li></ul>${link('Find your shared route ↗','browse','landing-text-link')}</div><div class="landing-demo-card"><div class="landing-demo-title"><strong>Find a shared route</strong><small>PRODUCT EXAMPLE</small></div><div class="landing-demo-fields"><span>FROM <strong>North campus</strong></span><span>TO <strong>Airport</strong></span><span>WHEN <strong>Fri, Oct 23 · 2 PM</strong></span></div><img src="/static/landing-photo-0.jpeg" alt="Illustrative shared ride listing with route map"><p>Illustrative trips and contributions only. Not live availability or quoted fares.</p></div></div></section>
 <section class="landing-section landing-shell" id="how-it-works"><div class="landing-kicker">✳ FROM PLANNING TO PASSENGER SEAT</div><div class="landing-section-heading"><h2>A few steps. A shared journey.</h2><p>You don't need to pick a side.<br>Be a rider today, a driver tomorrow.</p></div><div class="landing-steps"><article><span>01</span><h3>Put your plans out there.</h3><p>Need a ride or have seats to share? Either riders or drivers can post a one-time or recurring trip. Add your route, time, seats, and cost-sharing preferences.</p><small>I need a ride / I'm driving</small></article><article><span>02</span><h3>Find your overlap.</h3><p>Explore matching trip postings from students with a similar route and schedule. Compare the details and find a trip that fits your plans.</p><small>Similar routes. Compatible schedules.</small></article><article><span>03</span><h3>Connect. Agree. Go.</h3><p>Coordinate the pickup, confirm the timing, and agree on the shared contribution before setting off. Then get where you're going, together.</p><small>A shared plan before a shared ride.</small></article></div></section>
 <section class="landing-section landing-shell" id="destinations"><div class="landing-kicker">✳ MORE OF THE PLACES YOU WANT TO BE</div><div class="landing-section-heading"><h2>Life doesn't stop at<br>the campus gates.</h2>${link('Where are you headed? ↗','browse','landing-text-link')}</div><div class="landing-dest-grid"><article><img src="/static/landing-photo-5.jpeg" alt="Friends sharing a ride to the airport"><span>AIRPORTS & TRIPS HOME</span><h3>Catch flights, not pricey rides.</h3><p>Split the airport run. Save your budget for the trip.</p></article><article><img src="/static/landing-photo-6.jpeg" alt="Students enjoying an outdoor concert"><span>CONCERTS & WEEKEND OUTINGS</span><h3>Make the group chat plans real.</h3><p>Concert nights and weekend escapes start here.</p></article><article><img src="/static/landing-photo-4.jpeg" alt="Students walking on campus"><span>CAMPUS & INTERNSHIPS</span><h3>Give your routine a plus-one.</h3><p>Campus, classes, internships. Share the usual route.</p></article></div><p class="landing-also">Also on the itinerary <span>Shopping runs</span><span>Amusement park days</span><span>Weekend getaways</span><span>Your next idea ↗</span></p></section>
 <section class="landing-benefits" id="why-campusloop"><div class="landing-shell"><div class="landing-kicker">✳ GOOD FOR YOU. GOOD FOR THE JOURNEY.</div><h2>Small change in how you travel.<br>More room for what matters.</h2><div class="landing-benefit-grid"><article><b>♧</b><h3>Less cost. More possibility.</h3><p>Share transportation costs and keep more of your budget for student life.</p></article><article><b>↗</b><h3>Empty seats, put to use.</h3><p>Already going? Turn the space in your car into someone else's way there.</p></article><article><b>⌁</b><h3>More ways to get there.</h3><p>Connect the dots between campus and the places your day takes you.</p></article><article><b>♧</b><h3>A little lighter on the planet.</h3><p>More people in one car can mean fewer separate car journeys.</p></article></div></div></section>
 <section class="landing-section landing-shell landing-faq" id="faqs"><div><div class="landing-kicker">✳ BEFORE YOU HEAD OUT</div><h2>Good questions.<br>Straight answers.</h2><p>A little clarity before your next shared journey.</p></div><div class="landing-faq-grid"><details open><summary>Is this like Uber or Lyft?</summary><p>Not quite. CampusLoop connects students who already plan to travel similar routes. It's shared trip planning, not on-demand professional driver dispatch.</p></details><details open><summary>Can I be both a rider and a driver?</summary><p>Yes. One account covers both. Look for a seat when you need one, or offer your empty seats when you're the one driving.</p></details><details open><summary>Can I post a trip if I need a ride?</summary><p>Absolutely. Both riders and drivers can create postings. Share where and when you need to go so students with compatible plans can connect.</p></details><details open><summary>What about my regular commute?</summary><p>Use a recurring trip for daily or weekly routes to campus, classes, internships, and other regular destinations. One-time trips are for occasional plans.</p></details><details open><summary>How does splitting the cost work?</summary><p>Include your cost-sharing preferences in your posting. Compare contributions when matching, then agree on the amount and details together before the trip.</p></details><details open><summary>What should we confirm before leaving?</summary><p>Agree on pickup and drop-off points, departure time, seats, luggage space, and shared costs. Review the plan together and use your judgment before committing.</p></details></div></section>
 ${campusPricingSlide()}
 <section class="landing-cta"><div class="landing-shell landing-cta-inner"><div><div class="landing-kicker">✳ YOUR NEXT TRIP STARTS HERE</div><h2>Going somewhere?<br>Don't go it alone.</h2><p>Find a seat. Fill a seat. Make your next plan a shared one.</p><div class="landing-actions">${link('Get started with CampusLoop ↗','browse','landing-button lime')}${link('Post a trip ↗','post','landing-button ghost')}</div></div><div class="landing-cta-art">↗ <span>See you on the way.</span></div></div></section>
 ${campusNextSlide()}
 <footer class="landing-footer"><div class="landing-shell"><div><strong>↗ CampusLoop.</strong><p>Student plans. Shared journeys.<br>A better way to get there, together.</p></div><div><b>HIT THE ROAD</b>${link('Find a ride','browse')}${link('Post a trip','post')}<a href="#ways-to-ride">One-time trips</a><a href="#ways-to-ride">Recurring trips</a></div><div><b>GET TO KNOW US</b><a href="#how-it-works">How it works</a><a href="#why-campusloop">Why CampusLoop</a><a href="#faqs">FAQs</a></div><h3>Same direction.<br>Better together.</h3></div><div class="landing-shell landing-copyright">© 2026 CampusLoop. Share the journey.</div></footer>
 </div>`;
}
