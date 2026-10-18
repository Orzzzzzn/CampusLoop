"""Show the initial Kate offer; run the full sequence only when explicitly requested."""
import argparse
import datetime as dt
import hashlib
import http.cookiejar
import json
import math
import os
from pathlib import Path
from urllib.parse import urlsplit
import urllib.error
import urllib.request
from app.domain import ZONE


class Client:
    def __init__(self,base):
        self.base=base;self.csrf=''
        self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def call(self,path,data=None):
        request=urllib.request.Request(self.base+path,data=None if data is None else json.dumps(data).encode(),
            headers={'Content-Type':'application/json',**({'X-CSRF-Token':self.csrf} if self.csrf else {})})
        try:
            with self.opener.open(request,timeout=120) as response:return json.load(response)
        except urllib.error.HTTPError as exc:
            try:message=json.load(exc).get('error','Request failed.')
            except Exception:message='Request failed.'
            raise RuntimeError(message) from None
    def login(self,email,password):
        result=self.call('/api/auth/login',dict(email=email,password=password));self.csrf=result['csrf'];self.user=result['user']


def save(path,state):
    temporary=path.with_suffix('.new')
    with open(temporary,'w',opener=lambda name,flags:os.open(name,flags,0o600)) as stream:json.dump(state,stream,indent=2)
    os.replace(temporary,path)


def perform(base,state_path=None,new=False):
    base=base.rstrip('/');url=urlsplit(base)
    if url.scheme not in ('http','https') or url.hostname not in ('localhost','127.0.0.1','::1'):
        raise RuntimeError('Use a local CampusLoop server address.')
    public=Client(base);config=public.call('/api/config')
    if not config.get('demo_mode') or not all(name in config.get('accounts',{}) for name in ('kate','yelyn','hannah','emily')):
        raise RuntimeError('This command requires the local testing accounts in DEMO_MODE=1.')
    if not config.get('pricing',{}).get('configured'):
        raise RuntimeError('Google pricing is not configured. Set the server key and restart before running this flow.')
    clients={};password=os.getenv('CAMPUSLOOP_TEST_PASSWORD',os.getenv('DEMO_PASSWORD','heky-local-2026'))
    for name in ('kate','yelyn','hannah','emily'):
        client=Client(base);client.login(config['accounts'][name],password);clients[name]=client
    kate=clients['kate']
    if not kate.user.get('vehicle'):raise RuntimeError('Kate needs a vehicle in her profile before posting.')
    token=hashlib.sha256((base+':recurring-v1:'+str(kate.user['id'])).encode()).hexdigest()[:20]
    path=Path(state_path).expanduser() if state_path else Path.home()/'.campusloop'/'live-flows'/(token+'.json')
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    # macOS/Linux advisory lock keeps two simultaneous invocations from posting twice.
    import fcntl
    with open(path.with_suffix('.lock'),'a',opener=lambda name,flags:os.open(name,flags,0o600)) as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        state=json.loads(path.read_text()) if path.exists() and not new else None
        if state and (state.get('base')!=base or state.get('owner_id')!=kate.user['id']):
            raise RuntimeError('This state file belongs to a different local app/account.')
        if not state:
            moment=dt.datetime.now(ZONE);day=moment.date()+dt.timedelta(days=(1-moment.weekday())%7)
            if dt.datetime.combine(day,dt.time(13),ZONE)<=moment:day+=dt.timedelta(days=7)
            origin={**config['places'][0],'mode':'area','radius_miles':.5}
            destination={**config['places'][4],'mode':'exact','radius_miles':0}
            print('Posting a Tuesday 13:00 ride with two seats; requesting a real Google route quote…',flush=True)
            post=dict(role='driver',kind='regular',origin=origin,destination=destination,
                departure_hour=13,start_date=str(day),end_date=str(day+dt.timedelta(days=21)),weekdays=[1],seats=2,
                price_mode='automatic',detour_minutes=10,note='Tuesday class commute. Meet at the station entrance; two passenger seats.')
            quote=kate.call('/api/pricing/quote',post)
            post['arrive_by']=min(23,max(14,math.ceil(13+quote['duration_minutes']/60)))
            print('Google Maps: '+str(quote['distance_miles'])+' miles, '+str(quote['duration_minutes'])+' minutes; base $%.2f.' % (quote['price_cents']/100),flush=True)
            created=kate.call('/api/trips',post)
            state=dict(base=base,owner_id=kate.user['id'],trip_id=created['trip_id'],setup_complete=False,completed=False)
            save(path,state)
        if not state['completed']:
            rides=kate.call('/api/rides/search',dict(trip_id=state['trip_id']))['rides']
            rides=sorted(rides,key=lambda ride:ride['trip_date'])
            if len(rides)<2:raise RuntimeError('This saved flow no longer has two future ride dates. Continue in the app, or use --new to start another post.')
            if not state['setup_complete']:
                import time
                for _ in range(160):
                    if all(r.get('pricing_status',{}).get('ready') for r in rides):break
                    time.sleep(.25)
                    rides=sorted(kate.call('/api/rides/search',dict(trip_id=state['trip_id']))['rides'],key=lambda ride:ride['trip_date'])
                if not all(r.get('pricing_status',{}).get('ready') for r in rides):raise RuntimeError('Some recurring dates have no Google price. Retry pricing in the app before continuing.')
                for ride in rides[:1]:
                    for name in ('yelyn','hannah','emily'):
                        client=clients[name]
                        existing=next((a for a in client.call('/api/applications')['applications'] if a['occurrence_id']==ride['id']),None)
                        if existing and existing['status'] not in ('pending','confirmed','waitlisted'):
                            raise RuntimeError('A participant changed this in-progress flow. Continue in the app, or use --new.')
                        if not existing:
                            requested=client.call(f"/api/occurrences/{ride['id']}/request",dict(party_size=1,auto_confirm=True,
                                meeting_origin={**ride['origin'],'mode':'exact','radius_miles':0},meeting_destination={**ride['destination'],'mode':'exact','radius_miles':0}))
                            existing=dict(id=requested['application_id'],status=requested['status'])
                        if existing['status']=='pending':
                            quote=kate.call(f"/api/applications/{existing['id']}/price",{})
                            result=kate.call(f"/api/applications/{existing['id']}/accept",dict(expected_rider_count=quote['pricing']['rider_count'],expected_series_token=quote.get('series',{}).get('review_token')))
                            print(ride['trip_date']+' · '+name.title()+': '+result['status'],flush=True)
                state['setup_complete']=True;state['first_occurrence_id']=rides[0]['id'];save(path,state)
            first=next((a for a in clients['yelyn'].call('/api/applications')['applications'] if a['occurrence_id']==state['first_occurrence_id']),None)
            if first and first['status']=='confirmed':clients['yelyn'].call(f"/api/occurrences/{first['occurrence_id']}/skip-week",{})
            elif not first or first['status']!='canceled':raise RuntimeError('The first Yelyn booking changed. Continue in the app, or use --new.')
            state['completed']=True;save(path,state)
        print('Saved ride state in the app:',flush=True)
        for name in ('yelyn','hannah','emily'):
            records=[a for a in clients[name].call('/api/applications')['applications'] if a['trip_id']==state['trip_id']]
            for a in sorted(records,key=lambda a:a['trip_date']):
                price=(' · $%.2f per rider' % (a['agreed_price_cents']/100)) if a['status']=='confirmed' else ''
                print(a['trip_date']+' · '+name.title()+': '+a['status']+price,flush=True)
        print('Open '+base+' and use My rides / Requests in each account. Kate can cancel the second week there.',flush=True)
        return state


def show_start(base):
    base=base.rstrip('/');url=urlsplit(base)
    if url.scheme not in ('http','https') or url.hostname not in ('localhost','127.0.0.1','::1'):
        raise RuntimeError('Use a local CampusLoop server address.')
    client=Client(base);config=client.call('/api/config')
    if not config.get('demo_mode') or not config.get('demo_start_trip_id'):
        raise RuntimeError('The initial offer is available in DEMO_MODE=1 after updating the app.')
    client.login(config['accounts']['kate'],os.getenv('CAMPUSLOOP_TEST_PASSWORD',os.getenv('DEMO_PASSWORD','heky-local-2026')))
    rides=sorted(client.call('/api/rides/search',dict(trip_id=config['demo_start_trip_id']))['rides'],key=lambda r:r['trip_date'])
    if not rides:raise RuntimeError('The initial post has no future active dates. Post a new recurring ride in the app.')
    first=rides[0]
    print('Kate’s ride offer: '+first['origin']['label']+' → '+first['destination']['label'])
    print(first['trip_date']+' at 13:00 · two passenger seats · four Tuesdays')
    if first.get('pricing'):
        p=first['pricing'];print('Google Maps: '+str(p['distance_miles'])+' miles, '+str(p['duration_minutes'])+' minutes; base $%.2f.' % (first['price_cents']/100))
    else:print('Google price unavailable: configure the server key and wait for route calculation.')
    applications=[a for a in client.call('/api/applications')['applications'] if a['trip_id']==first['trip_id']]
    print('Applications on this post: '+str(len(applications)))
    print('Open '+base+' → Find a ride → Tuesday class commute → View ride offer.')
    print('Next: Yelyn requests, Kate accepts, then Hannah and Emily can join. No bookings were created by this command.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',default='http://127.0.0.1:8010')
    parser.add_argument('--perform-sequence',action='store_true',help='Explicitly post, request, confirm and cancel using all four testing accounts')
    parser.add_argument('--new',action='store_true',help='With --perform-sequence, create another post instead of resuming the saved sequence')
    parser.add_argument('--state-file',type=Path,help='State path for --perform-sequence only')
    args=parser.parse_args()
    if not args.perform_sequence and (args.new or args.state_file):parser.error('--new and --state-file require --perform-sequence')
    try:
        if args.perform_sequence:perform(args.base,args.state_file,args.new)
        else:show_start(args.base)
    except (RuntimeError,OSError,ValueError) as exc:parser.exit(1,'Flow stopped: '+str(exc)+'\n')


if __name__=='__main__':main()
