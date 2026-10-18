from __future__ import annotations

from collections import defaultdict, deque
import datetime as dt
from email.message import EmailMessage
import hashlib
import hmac
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import mimetypes
import os
from pathlib import Path
import re
import secrets
import smtplib
import sqlite3
import threading
import time
from urllib.parse import parse_qs, urlsplit

from . import VERSION
from .demo import seed_walkthrough, seed_scenarios, walkthrough_config
from .domain import (ROOT, PLACES, Problem, Store, application_views, boolean, can_chat,
    cancel_application, cancel_occurrence, check_password, claim, decide, ensure_open, event,
    hash_password, joined_occurrence, list_notifications, list_trips, mark_notifications_read,
    now, occupied, promote, public_user, republish_canceled_request, request_ride, require,
    text, trip_create, identity_name, private_text, integer)
from .rag import RAG
from .places import Places
from .pricing import occurrence_pricing, require_price
from .routes import Routes
from .live import prepare, accounts_config, GooglePrices
from .recurring import enroll, series_info, approve, withdraw, prepare_upgrade, upgrade_existing
from .features import my_rides, edit_date, skip_week, rate_person, create_demo, demo_views, release_demo

LOG=logging.getLogger('campusloop')


class App:
    def __init__(self,store,rag=None,demo_mode=None,*,seed_data=True,routes=None):
        self.store=store
        self.legacy_fixtures=not seed_data
        self.demo_mode=(os.getenv('DEMO_MODE','1')=='1') if demo_mode is None else demo_mode
        if self.demo_mode and seed_data:prepare(store)
        self.rag=rag or RAG(store)
        self.places=Places(store)
        self.routes=routes or Routes(store)
        self.google_prices=GooglePrices(store,self.routes)
        if seed_data:
            self.google_prices.prepare()
            prepare_upgrade(store);upgrade_existing(store)
            self.google_prices.on_complete=lambda:upgrade_existing(store)
            self.google_prices.start()
        self.rates=defaultdict(deque)
        self.lock=threading.Lock()

    def rate(self,key,maximum=30,window=300):
        with self.lock:
            queue=self.rates[key]
            current=time.monotonic()
            while queue and queue[0]<current-window:
                queue.popleft()
            require(len(queue)<maximum,'Too many attempts. Please try again later.',429)
            queue.append(current)

    def session(self,headers,mutating=False):
        cookie=SimpleCookie()
        try:
            cookie.load(headers.get('Cookie',''))
            token=(cookie.get('campusloop_session') or cookie.get('heky_session')).value
        except (KeyError,AttributeError):
            raise Problem(401,'Sign in to continue.')
        with self.store.read() as db:
            row=db.execute('''SELECT u.*,s.csrf,s.expires FROM sessions s JOIN users u ON u.id=s.user_id
                WHERE s.token_hash=? AND s.expires>?''',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
        require(row is not None,'Your session expired. Please sign in again.',401)
        if mutating:
            require(hmac.compare_digest(row['csrf'],headers.get('X-CSRF-Token','')),'Missing or invalid request token. Refresh the page.',403)
        return dict(row)

    def new_session(self,user):
        token,csrf=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
        with self.store.tx() as db:
            db.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
            db.execute('INSERT INTO sessions(token_hash,user_id,csrf,expires) VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user['id'],csrf,time.time()+7*86400))
        cookie=f'campusloop_session={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=604800'
        if os.getenv('COOKIE_SECURE','0')=='1':
            cookie+='; Secure'
        return dict(user=public_user(user),csrf=csrf),{'Set-Cookie':cookie}

    def email_code(self,email,code):
        if self.demo_mode:
            return
        require(bool(os.getenv('SMTP_HOST')),'Student email delivery is not configured.',503)
        message=EmailMessage()
        message['Subject']='CampusLoop student email verification'
        message['From']=os.getenv('SMTP_FROM','campusloop@localhost')
        message['To']=email
        message.set_content(f'Your CampusLoop verification code is {code}. It expires in 15 minutes.')
        try:
            with smtplib.SMTP(os.getenv('SMTP_HOST'),int(os.getenv('SMTP_PORT','587')),timeout=10) as smtp:
                if os.getenv('SMTP_STARTTLS','1')=='1':
                    smtp.starttls()
                if os.getenv('SMTP_USER'):
                    smtp.login(os.environ['SMTP_USER'],os.environ['SMTP_PASSWORD'])
                smtp.send_message(message)
        except (OSError,smtplib.SMTPException) as exc:
            raise Problem(503,'Verification email could not be delivered. Check SMTP settings and request a new code.') from exc

    def dispatch(self,method,path,data,headers,ip='local'):
        if path=='/api/config' and method=='GET':
            with self.store.read() as db:
                row=db.execute('SELECT min(trip_date) FROM occurrences WHERE trip_date>=?',(str(now().date()),)).fetchone()
                walkthrough=walkthrough_config(db) if self.demo_mode and self.legacy_fixtures else None
                accounts=accounts_config(db) if self.demo_mode else {}
                start=db.execute("SELECT value FROM app_settings WHERE key='live-rides:v2'").fetchone()
                start_trip=json.loads(start[0])['routes'].get('class') if start and self.demo_mode else None
            return dict(app_name='CampusLoop',version=VERSION,api_version='2.2',demo_mode=self.demo_mode,walkthrough=walkthrough,accounts=accounts,demo_start_trip_id=start_trip,pricing=self.google_prices.status(),places=PLACES,time_zone='America/Los_Angeles',default_date=row[0] or str(now().date()),chat_model=self.rag.client.chat_model,embed_model=self.rag.client.embed_model),200,{}
        if path=='/health' and method=='GET':
            with self.store.read() as db:
                db.execute('SELECT 1')
            return {'status':'ok','database':'ok','app':'CampusLoop','version':VERSION,'api_version':'2.2','google_maps':'configured' if self.routes.google_key else 'missing_key'},200,{}
        if path.startswith('/api/auth/'):
            self.rate(('auth',ip))
        if path=='/api/auth/register' and method=='POST':
            self.rate(('register',ip),5,3600)
            name,email=text(data,'name',2,80),text(data,'email',5,200).lower()
            domains=[s.strip().lower() for s in os.getenv('STUDENT_DOMAINS','usc.edu').split(',') if s.strip()]
            require(bool(re.fullmatch(r'[^\s@]+@[^\s@]+',email)) and email.rsplit('@',1)[1] in domains,'Use a supported campus email: '+', '.join(domains))
            password=hash_password(data.get('password'))
            code=f'{secrets.randbelow(1000000):06}'
            if not self.demo_mode:
                require(bool(os.getenv('SMTP_HOST')),'Configure SMTP before enabling registration outside development mode.',503)
            with self.store.tx() as db:
                require(not db.execute('SELECT 1 FROM users WHERE email=?',(email,)).fetchone(),'That email already has an account.',409)
                db.execute('INSERT INTO users(name,email,password_hash,verification_hash,verification_expires) VALUES(?,?,?,?,?)',(name,email,password,hashlib.sha256(code.encode()).hexdigest(),time.time()+900))
            self.email_code(email,code)
            result={'verification_required':True,'email':email}
            if self.demo_mode:
                result.update(development_code=code,notice='Development verification code. No real email was sent.')
            return result,201,{}
        if path=='/api/auth/verify' and method=='POST':
            email,code=text(data,'email',5,200).lower(),text(data,'code',6,6)
            with self.store.tx() as db:
                user=db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
                require(user is not None and not user['verified'],'Verification request not found.',400)
                require((user['verification_expires'] or 0)>time.time() and user['verification_attempts']<5,'Verification code expired or attempt limit reached.',400)
                # Commit the failed-attempt count too; raising inside tx would roll it back.
                valid=hmac.compare_digest(user['verification_hash'] or '',hashlib.sha256(code.encode()).hexdigest())
                if valid:
                    db.execute('UPDATE users SET verified=1,verification_hash=NULL,verification_expires=NULL WHERE id=?',(user['id'],))
                else:
                    db.execute('UPDATE users SET verification_attempts=verification_attempts+1 WHERE id=?',(user['id'],))
            require(valid,'Incorrect verification code.',400)
            with self.store.read() as db:
                user=db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
            body,out=self.new_session(user)
            return body,200,out
        if path=='/api/auth/resend' and method=='POST':
            email=text(data,'email',5,200).lower()
            with self.store.read() as db:
                user=db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
            require(user is not None and check_password(data.get('password'),user['password_hash']),'Email or password is incorrect.',401)
            require(not user['verified'],'This email is already verified.',409)
            code=f'{secrets.randbelow(1000000):06}'
            self.email_code(email,code)
            with self.store.tx() as db:
                db.execute('UPDATE users SET verification_hash=?,verification_expires=?,verification_attempts=0 WHERE id=?',(hashlib.sha256(code.encode()).hexdigest(),time.time()+900,user['id']))
            return ({'sent':True,'development_code':code} if self.demo_mode else {'sent':True}),200,{}
        if path=='/api/auth/login' and method=='POST':
            email=text(data,'email',5,200).lower()
            with self.store.read() as db:
                user=db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
            require(user is not None and check_password(data.get('password'),user['password_hash']),'Email or password is incorrect.',401)
            body,out=self.new_session(user)
            return body,200,out
        user=self.session(headers,method not in ('GET','HEAD'))
        if path=='/api/auth/logout' and method=='POST':
            cookie=SimpleCookie();cookie.load(headers.get('Cookie',''))
            with self.store.tx() as db:
                db.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256((cookie.get('campusloop_session') or cookie.get('heky_session')).value.encode()).hexdigest(),))
            return {'ok':True},200,{'Set-Cookie':'campusloop_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0'}
        if path=='/api/places/search' and method=='POST':
            self.rate(('places',user['id']),30,300)
            return self.places.search(text(data,'query',2,180),data.get('bias')),200,{}
        if path=='/api/me' and method=='GET':
            return dict(user=public_user(user),csrf=user['csrf']),200,{}
        if path=='/api/me' and method=='PUT':
            name,vehicle=text(data,'name',2,80),text(data,'vehicle',0,120)
            with self.store.tx() as db:
                db.execute('UPDATE users SET name=?,vehicle=? WHERE id=?',(name,vehicle,user['id']))
            return {'ok':True},200,{}
        if path=='/api/rides/search' and method=='POST':
            with self.store.read() as db:
                rides=list_trips(db,user['id'],data)
            return {'rides':rides},200,{}
        if path=='/api/pricing/quote' and method=='POST':
            self.rate(('quote',user['id']),40,300)
            return self.routes.quote(data.get('origin'),data.get('destination'),data.get('kind','one'),
                **{k:data.get(k) for k in ('seats','start_date','departure_hour','return_hour','weekdays')}),200,{}
        if path=='/api/routes/preview' and method=='POST':
            self.rate(('routes',user['id']),120,300)
            with self.store.read() as db:
                o=joined_occurrence(db,integer(data,'occurrence_id',1,2**53))
                origin,destination=json.loads(o['origin']),json.loads(o['destination'])
            return self.routes.route(origin,destination),200,{}
        if path=='/api/pricing/status' and method=='GET':
            return self.google_prices.status(),200,{}
        if path=='/api/pricing/retry' and method=='POST':
            require(user['verified'],'Verify your student email before retrying route prices.',403)
            require(bool(self.routes.google_key),'Configure GOOGLE_MAPS_API_KEY on the server and restart the app.',503)
            self.rate(('route-prices',user['id']),2,300)
            self.google_prices.start()
            return self.google_prices.status(),202,{}
        if path=='/api/trips' and method=='POST':
            mode=data.get('price_mode','manual' if self.legacy_fixtures else 'automatic')
            require(mode in ('automatic','manual'),'Choose automatic or manual pricing.')
            require(self.legacy_fixtures or mode=='automatic','All new rides use Google Maps pricing. Manual prices are no longer available.')
            data=dict(data)
            if mode=='automatic':
                quote=self.routes.quote(data.get('origin'),data.get('destination'),data.get('kind'),
                    **{k:data.get(k) for k in ('seats','start_date','departure_hour','return_hour','weekdays')})
                data.update(price_cents=quote['price_cents'],_price_meta=quote)
            else:
                data['_price_meta']={'mode':'manual'}
            with self.store.tx() as db:
                tid=trip_create(db,user,data)
                first_date=db.execute('SELECT min(trip_date) FROM occurrences WHERE trip_id=?',(tid,)).fetchone()[0]
            if not self.legacy_fixtures:self.google_prices.start()
            return {'trip_id':tid,'first_date':first_date},201,{}
        if path=='/api/applications' and method=='GET':
            with self.store.read() as db:
                rows=application_views(db,user)
            return {'applications':rows},200,{}
        if path=='/api/notifications' and method=='GET':
            with self.store.read() as db:
                notes=list_notifications(db,user)
            unread=sum(1 for n in notes if not n['read'])
            return {'notifications':notes,'unread':unread},200,{}
        if path=='/api/notifications/read' and method=='POST':
            with self.store.tx() as db:
                mark_notifications_read(db,user,data.get('ids'))
            return {'ok':True},200,{}
        if (path=='/api/my-rides' and method=='GET') or (path=='/api/my-rides/search' and method=='POST'):
            with self.store.read() as db:
                rides=my_rides(db,user,data)
            return {'rides':rides},200,{}
        if path=='/api/demo/scenarios' and method in ('GET','POST'):
            require(self.demo_mode and self.legacy_fixtures,'Preset booking fixtures are disabled.',404)
            if method=='POST':
                self.rate(('demo',user['id']),4,300)
                with self.store.tx() as db:
                    scenarios=create_demo(db,user)
            else:
                with self.store.read() as db:
                    scenarios=demo_views(db,user)
            return {'scenarios':scenarios},201 if method=='POST' else 200,{}
        match=re.fullmatch(r'/api/demo/scenarios/(\d+)/release',path)
        if match and method=='POST':
            require(self.demo_mode and self.legacy_fixtures,'Preset booking fixtures are disabled.',404)
            with self.store.tx() as db:
                promoted=release_demo(db,user,int(match[1]),integer(data,'application_id',1,2**53))
            return {'promoted_application_ids':promoted},200,{}
        match=re.fullmatch(r'/api/occurrences/(\d+)/(edit-date|skip-week|rating)',path)
        if match and method=='POST':
            oid,action=int(match[1]),match[2]
            with self.store.tx() as db:
                if action=='edit-date': edit_date(db,user,oid,data);result={'ok':True}
                elif action=='skip-week': result={'skipped_occurrence_ids':skip_week(db,user,oid)}
                else: result={'rating':rate_person(db,user,oid,data)}
            if action=='edit-date' and not self.legacy_fixtures:self.google_prices.start()
            return result,200,{}
        match=re.fullmatch(r'/api/occurrences/(\d+)/(request|cancel|activity|messages)',path)
        if match:
            oid,action=int(match[1]),match[2]
            if action=='request' and method=='POST':
                with self.store.tx() as db:
                    prior=db.execute('SELECT status FROM applications WHERE occurrence_id=? AND requester_id=?',(oid,user['id'])).fetchone()
                    reused=bool(prior and prior['status'] in ('pending','waitlisted','confirmed'))
                    occurrence=joined_occurrence(db,oid)
                    scope=data.get('scope','date' if self.legacy_fixtures else 'series' if occurrence['kind']=='regular' else 'date')
                    require(scope in ('series','date'),'Invalid request scope.')
                    sid=None
                    if scope=='series':aid,sid,reused=enroll(db,user,oid,data)
                    else:aid=request_ride(db,user,oid,data)
                    status=db.execute('SELECT status FROM applications WHERE id=?',(aid,)).fetchone()[0]
                    trip_id=joined_occurrence(db,oid)['trip_id']
                return {'application_id':aid,'trip_id':trip_id,'status':status,'already_requested':reused,'recurring_id':sid},200 if reused else 201,{}
            if action=='cancel' and method=='POST':
                with self.store.tx() as db:
                    canceled=cancel_occurrence(db,user,oid)
                return {'ok':True,'canceled_application_ids':canceled},200,{}
            if action=='activity' and method=='GET':
                with self.store.read() as db:
                    can_chat(db,user,oid)
                    events=[{**dict(r),'message':private_text(db,r['message'],user['id'],oid)} for r in db.execute('SELECT message,created_at FROM events WHERE occurrence_id=? ORDER BY id',(oid,))]
                    members=[dict(r) for r in db.execute("SELECT u.id AS subject_id,u.name,a.status,a.party_size,a.auto_confirm FROM applications a JOIN users u ON u.id=a.requester_id WHERE occurrence_id=? AND status IN ('confirmed','waitlisted') ORDER BY a.created_at,a.id",(oid,))]
                    for member in members:
                        member['name'],member['identity_revealed']=identity_name(db,user['id'],member.pop('subject_id'),oid)
                return {'events':events,'members':members},200,{}
            if action=='messages' and method in ('GET','POST'):
                if method=='POST':
                    body=text(data,'body',1,1000)
                    with self.store.tx() as db:
                        o=can_chat(db,user,oid)
                        require(o['status']=='active','This ride date was canceled.',409)
                        db.execute('INSERT INTO messages(occurrence_id,user_id,body,created_at) VALUES(?,?,?,?)',(oid,user['id'],body,time.time()))
                with self.store.read() as db:
                    can_chat(db,user,oid)
                    messages=[dict(r) for r in db.execute('''SELECT m.id,m.user_id AS subject_id,m.body,m.created_at,u.name FROM messages m JOIN users u ON u.id=m.user_id WHERE occurrence_id=? ORDER BY m.id LIMIT 200''',(oid,))]
                    for message in messages:
                        message['name'],message['identity_revealed']=identity_name(db,user['id'],message.pop('subject_id'),oid)
                        message['body']=private_text(db,message['body'],user['id'],oid)
                return {'messages':messages},200,{}
        
        match=re.fullmatch(r'/api/recurring/(\d+)/withdraw',path)
        if match and method=='POST':
            with self.store.tx() as db:result=withdraw(db,user,int(match[1]))
            return result,200,{}
        match=re.fullmatch(r'/api/applications/(\d+)/(accept|decline|cancel|claim|price|republish)',path)
        if match and method=='POST':
            aid,action=int(match[1]),match[2]
            with self.store.tx() as db:
                application=db.execute('SELECT * FROM applications WHERE id=?',(aid,)).fetchone()
                require(application is not None,'Request not found.',404)
                occurrence=joined_occurrence(db,application['occurrence_id'])
                require(user['id'] in (application['requester_id'],occurrence['owner_id']),'This request belongs to another member.',403)
                projected=occurrence_pricing(db,occurrence,application['party_size'] if application['status'] in ('pending','waitlisted') else 0)
                if application['recurring_id'] and action in ('price','accept','decline'):
                    info=series_info(db,application['recurring_id'],review=action in ('price','accept'))
                    if action=='price':return dict(pricing=projected,series=info,price_cents=application['agreed_price_cents'],party_size=application['party_size']),200,{}
                    info=approve(db,user,application['recurring_id'],action=='accept',data.get('expected_series_token'))
                    state=db.execute('SELECT status FROM applications WHERE id=?',(aid,)).fetchone()[0]
                    return dict(status=state,series=info,pricing=occurrence_pricing(db,joined_occurrence(db,application['occurrence_id']))),200,{}
                if action in ('price','accept','claim'):require_price(occurrence)
                if action=='price':
                    return dict(pricing=projected,price_cents=application['agreed_price_cents'],party_size=application['party_size']),200,{}
                if action in ('accept','claim') and projected:
                    require(data.get('expected_rider_count')==projected['rider_count'],
                            'Rider count changed. Review the current price and confirm again.',409)
                if action in ('accept','decline'):
                    result={'status':decide(db,user,aid,action=='accept')}
                elif action=='cancel':
                    result={'canceled':True,'promoted_application_ids':cancel_application(db,user,aid)}
                elif action=='republish':
                    result=republish_canceled_request(db,user,aid,google_only=not self.legacy_fixtures)
                else:
                    claim(db,user,aid);result={'status':'confirmed'}
                result['pricing']=occurrence_pricing(db,joined_occurrence(db,application['occurrence_id']))
            if action=='republish' and not self.legacy_fixtures:self.google_prices.start()
            return result,200,{}
        if path=='/api/rag/ask' and method=='POST':
            self.rate(('rag',user['id']),12,300)
            question=text(data,'question',2,2000)
            criteria=data.get('filters',{})
            require(isinstance(criteria,dict),'RAG filters must be an object.')
            return self.rag.ask(user,question,criteria),200,{}
        raise Problem(404,'API endpoint not found.')


class Handler(BaseHTTPRequestHandler):
    server_version='CampusLoop'

    def log_message(self,fmt,*args):
        # Do not log request bodies, credentials, session values, or coordinates.
        LOG.info('%s %s %s',self.command,urlsplit(self.path).path,args[1] if len(args)>1 else '')

    def send(self,payload,status=200,extra=None,mime='application/json; charset=utf-8'):
        content=payload if isinstance(payload,bytes) else json.dumps(payload,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(content)))
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','strict-origin-when-cross-origin')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' https://unpkg.com; style-src 'self' 'unsafe-inline' https://unpkg.com; img-src 'self' data: https://tile.openstreetmap.org; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        for name,value in (extra or {}).items():
            self.send_header(name,value)
        self.end_headers()
        self.wfile.write(content)

    def run_request(self):
        try:
            path=urlsplit(self.path).path
            static={'/':'index.html','/static/app.js':'app.js','/static/style.css':'style.css','/static/landing.js':'landing.js','/static/landing.css':'landing.css',**{f'/static/landing-photo-{i}.jpeg':f'landing-photo-{i}.jpeg' for i in range(7)}}
            if self.command=='GET' and path in static:
                file=ROOT/'static'/static[path]
                require(file.is_file(),'Page not found.',404)
                mime=mimetypes.guess_type(file.name)[0] or 'application/octet-stream'
                self.send(file.read_bytes(),mime=mime+'; charset=utf-8');return
            data={}
            if self.command in ('POST','PUT','PATCH','DELETE'):
                require(self.headers.get('Transfer-Encoding') is None,'Chunked requests are not supported.',400)
                try:
                    length=int(self.headers.get('Content-Length','0'))
                except ValueError:
                    raise Problem(400,'Invalid Content-Length.')
                require(0<=length<=65536,'Request body is too large.',413)
                require(self.headers.get_content_type()=='application/json','Send application/json.',415)
                try:
                    data=json.loads(self.rfile.read(length) or b'{}')
                except (ValueError,UnicodeDecodeError):
                    raise Problem(400,'Invalid JSON.')
                require(isinstance(data,dict),'JSON body must be an object.')
            result,status,extra=self.server.app.dispatch(self.command,path,data,self.headers,self.client_address[0])
            self.send(result,status,extra)
        except Problem as exc:
            self.send({'error':exc.message},exc.status)
        except sqlite3.IntegrityError:
            self.send({'error':'That change conflicts with an existing record. Refresh and try again.'},409)
        except (BrokenPipeError,ConnectionResetError):
            pass
        except Exception:
            LOG.exception('Request failed')
            self.send({'error':'An internal error occurred. Check the server log.'},500)

    do_GET=run_request
    do_POST=run_request
    do_PUT=run_request
    do_DELETE=run_request


class Server(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=True
    def __init__(self,address,app):
        self.app=app
        super().__init__(address,Handler)
    def get_request(self):
        sock,address=super().get_request()
        sock.settimeout(180)
        return sock,address


def main():
    logging.basicConfig(level=os.getenv('LOG_LEVEL','INFO'))
    store=Store(os.getenv('DATABASE_PATH',str(ROOT/'data/heky.sqlite3')))
    app=App(store)
    server=Server((os.getenv('HOST','127.0.0.1'),int(os.getenv('PORT','8010'))),app)
    LOG.info('CampusLoop listening on %s:%s',*server.server_address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__=='__main__':
    main()
