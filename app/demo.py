"""A repeatable Tuesday-class walkthrough using ordinary accounts and ride APIs."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
from .domain import (ROOT, ZONE, Store, PLACES, hash_password, now, today,
                     trip_create, cancel_occurrence, joined_occurrence, ensure_open, Problem, request_ride, decide)

KEY='walkthrough:tuesday-class:v1'
SCENARIO_KEY='walkthrough:waitlists:v1'


def next_tuesday():
    day=today()+dt.timedelta(days=(1-today().weekday())%7)
    if dt.datetime.combine(day,dt.time(13),ZONE)<=now():day+=dt.timedelta(days=7)
    return day


def seed_walkthrough(store,reset=False):
    """Add once to either a new or existing DB; never reset account passwords."""
    with store.tx() as db:
        row=db.execute('SELECT value FROM app_settings WHERE key=?',(KEY,)).fetchone()
        previous=json.loads(row['value']) if row else None
        if previous and not reset:return previous
        password=hash_password(os.getenv('DEMO_PASSWORD','heky-local-2026'))
        ids={};emails={}
        for name,email,vehicle in [('Kate','kate@usc.edu','Honda Civic · Blue'),('Yelyn','yelyn@usc.edu','')]:
            key=name.lower()
            if previous:
                ids[key]=previous[key+'_id']
                emails[key]=db.execute('SELECT email FROM users WHERE id=?',(ids[key],)).fetchone()['email']
                continue
            # Do not take over a pre-existing account with the same display name/email.
            candidate=email;number=1
            while db.execute('SELECT 1 FROM users WHERE email=?',(candidate,)).fetchone():
                candidate=key+'.demo'+(str(number) if number>1 else '')+'@usc.edu';number+=1
            ids[key]=db.execute('INSERT INTO users(name,email,password_hash,verified,vehicle) VALUES(?,?,?,1,?)',(name,candidate,password,vehicle)).lastrowid
            emails[key]=candidate
        kate=dict(db.execute('SELECT * FROM users WHERE id=?',(ids['kate'],)).fetchone())
        # Only an explicitly requested restart cancels the generated offer.
        if previous and reset:
            for row in db.execute("SELECT id FROM occurrences WHERE trip_id=? AND status='active'",(previous['trip_id'],)).fetchall():
                o=joined_occurrence(db,row['id'])
                if o['owner_id']!=kate['id']:continue
                try:ensure_open(o)
                except Problem:continue
                cancel_occurrence(db,kate,row['id'])
        start=next_tuesday();end=start+dt.timedelta(days=21)
        origin={**{k:v for k,v in PLACES[0].items() if k!='id'},'mode':'area','radius_miles':.5}
        destination={**{k:v for k,v in PLACES[4].items() if k!='id'},'mode':'exact','radius_miles':0}
        data=dict(role='driver',kind='regular',origin=origin,destination=destination,
                  departure_hour=13,arrive_by=14,start_date=str(start),end_date=str(end),
                  weekdays=[1],seats=2,price_cents=400,detour_minutes=10,
                  note='Tuesday class commute. Sharing gas costs; meet at the station entrance.')
        # A real manually posted cost share: no synthetic Google quote or traffic data.
        trip_id=trip_create(db,kate,data)
        result=dict(trip_id=trip_id,kate_id=ids['kate'],yelyn_id=ids['yelyn'],kate_email=emails['kate'],yelyn_email=emails['yelyn'],
                    first_date=str(start),end_date=str(end),origin=origin,destination=destination,
                    departure_hour=13,weekdays=[1],price_cents=400,seats=2)
        db.execute('INSERT OR REPLACE INTO app_settings(key,value) VALUES(?,?)',(KEY,json.dumps(result)))
        return result


# Each offer has a distinct route and its own ordinary bookings. Nothing is reset on boot.
SCENARIOS=[
    ('B','Auto replacement',5,4,'regular',13,2,[('yelyn',1,True,True),('hannah',1,True,True),('emily',1,True,True)]),
    ('C','Manual claim',1,6,'one',9,2,[('yelyn',1,True,True),('hannah',1,True,True),('emily',1,False,True)]),
    ('D','Approval required',0,5,'one',11,2,[('yelyn',1,True,True),('hannah',1,True,True),('emily',1,True,False)]),
    ('E','Queue order',2,5,'one',14,1,[('yelyn',1,True,True),('hannah',1,True,True),('emily',1,True,True)]),
    ('F','Whole party fits',3,6,'one',10,2,[('yelyn',1,True,True),('hannah',1,True,True),('emily',2,True,True),('noah',1,True,True)]),
    ('G','Driver cancels week',2,4,'regular',13,2,[('yelyn',1,True,True),('hannah',1,True,True),('emily',1,True,True)]),
    ('H','Round trip replacement',5,3,'round',8,2,[('yelyn',1,True,True),('hannah',1,True,True),('emily',1,True,True)]),
    ('I','Withdraw and rejoin',1,5,'one',16,1,[('yelyn',1,True,True),('emily',1,True,True),('hannah',1,True,True)]),
    ('J','Rider seeks driver',6,0,'one',15,2,[]),
]


def seed_scenarios(store,reset=False,only=None):
    with store.tx() as db:
        row=db.execute('SELECT value FROM app_settings WHERE key=?',(SCENARIO_KEY,)).fetchone()
        previous=json.loads(row['value']) if row else None
        if previous and not reset:return previous
        main=json.loads(db.execute('SELECT value FROM app_settings WHERE key=?',(KEY,)).fetchone()['value'])
        ids={name:main[name+'_id'] for name in ('kate','yelyn')}
        emails={name:main[name+'_email'] for name in ('kate','yelyn')}
        password=hash_password(os.getenv('DEMO_PASSWORD','heky-local-2026'))
        for name,vehicle in [('Hannah',''),('Emily',''),('Noah','Toyota Prius · Silver')]:
            key=name.lower()
            if previous:
                uid=previous['accounts'][key]['id']
                row=db.execute('SELECT email FROM users WHERE id=?',(uid,)).fetchone()
                ids[key]=uid;emails[key]=row['email'];continue
            candidate=key+'@usc.edu';number=1
            while db.execute('SELECT 1 FROM users WHERE email=?',(candidate,)).fetchone():
                candidate=key+'.demo'+(str(number) if number>1 else '')+'@usc.edu';number+=1
            ids[key]=db.execute('INSERT INTO users(name,email,password_hash,verified,vehicle) VALUES(?,?,?,1,?)',(name,candidate,password,vehicle)).lastrowid
            emails[key]=candidate
        users={key:dict(db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()) for key,uid in ids.items()}
        scenarios=list(previous['scenarios']) if previous else []
        if previous and reset:
            selected=[case for case in scenarios if not only or case['code']==only]
            for case in selected:
                for row in db.execute("SELECT id FROM occurrences WHERE trip_id=? AND status='active'",(case['trip_id'],)).fetchall():
                    occurrence=joined_occurrence(db,row['id'])
                    try:ensure_open(occurrence)
                    except Problem:continue
                    cancel_occurrence(db,users['yelyn' if case['code']=='J' else 'kate'],row['id'])
            scenarios=[case for case in scenarios if case not in selected]
        day=next_tuesday()
        for code,title,origin_index,dest_index,kind,hour,seats,members in SCENARIOS:
            if only and code!=only:continue
            origin={**{k:v for k,v in PLACES[origin_index].items() if k!='id'},'mode':'area','radius_miles':.5}
            dest={**{k:v for k,v in PLACES[dest_index].items() if k!='id'},'mode':'exact','radius_miles':0}
            start=day+dt.timedelta(days=7) if dt.datetime.combine(day,dt.time(hour),ZONE)<=now() else day
            owner=users['yelyn' if code=='J' else 'kate']
            data=dict(role='rider' if code=='J' else 'driver',kind=kind,origin=origin,destination=dest,
                      departure_hour=hour,arrive_by=hour+1,start_date=str(start),
                      end_date=str(start+dt.timedelta(days=21)),weekdays=[1],seats=seats,price_cents=400,
                      detour_minutes=10,return_hour=17,note='Walkthrough '+code+' · '+title+'. Manual gas contribution; each date is independent.',_price_meta={'mode':'manual'})
            tid=trip_create(db,owner,data)
            for occurrence in db.execute('SELECT id FROM occurrences WHERE trip_id=? ORDER BY trip_date',(tid,)).fetchall():
                for name,party,auto,approve in members:
                    aid=request_ride(db,users[name],occurrence['id'],dict(party_size=party,auto_confirm=auto,
                        meeting_origin={**origin,'mode':'exact','radius_miles':0},meeting_destination=dest))
                    if approve:decide(db,owner,aid,True)
            scenarios.append(dict(code=code,title=title,trip_id=tid,kind=kind,first_date=str(start),departure_hour=hour,
                                  origin=origin['label'],destination=dest['label'],seats=seats))
        result=dict(accounts={name:dict(id=uid,email=emails[name]) for name,uid in ids.items()},scenarios=sorted(scenarios,key=lambda c:c['code']))
        db.execute('INSERT OR REPLACE INTO app_settings(key,value) VALUES(?,?)',(SCENARIO_KEY,json.dumps(result)))
        return result


def walkthrough_config(db):
    row=db.execute('SELECT value FROM app_settings WHERE key=?',(KEY,)).fetchone()
    if not row:return None
    result=json.loads(row['value'])
    result.pop('kate_id',None);result.pop('yelyn_id',None)
    original_date=result['first_date']
    if result['first_date']<str(next_tuesday()):
        result['first_date']=str(next_tuesday());result['end_date']=str(next_tuesday()+dt.timedelta(days=21))
    result['scenarios']=[dict(code='A',title='Tuesday class · start here',trip_id=result['trip_id'],kind='regular',first_date=original_date,
                              departure_hour=13,origin=result['origin']['label'],destination=result['destination']['label'],seats=2)]
    row=db.execute('SELECT value FROM app_settings WHERE key=?',(SCENARIO_KEY,)).fetchone()
    if row:
        extra=json.loads(row['value'])
        result['accounts']={key:value['email'] for key,value in extra['accounts'].items()}
        for name in ('hannah','emily','noah'):result[name+'_email']=extra['accounts'][name]['email']
        result['scenarios']+=extra['scenarios']
    else:result['accounts']={'kate':result['kate_email'],'yelyn':result['yelyn_email']}
    return result


def main():
    parser=argparse.ArgumentParser(description='Legacy preset booking fixtures are no longer part of the app.')
    parser.add_argument('--reset',action='store_true')
    parser.add_argument('--scenario')
    parser.parse_args()
    parser.error('Preset booking resets are disabled. Use Post a ride, Requests and My rides to perform real actions. No files were changed.')


if __name__=='__main__':main()
