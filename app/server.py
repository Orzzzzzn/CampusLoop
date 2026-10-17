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

from .domain import (ROOT, DEFAULT_DATABASE_NAME, PLACES, Problem, Store, application_views,
    boolean, can_chat, cancel_application, check_password, claim, decide, ensure_open, event,
    hash_password, joined_occurrence, list_trips, now, occupied, promote, public_user,
    request_ride, require, seed, text, trip_create, identity_name, private_text)
from .rag import RAG
from .places import Places

LOG=logging.getLogger('campusloop')


class App:
    def __init__(self,store,rag=None,demo_mode=None):
        self.store=store
        self.demo_mode=(os.getenv('DEMO_MODE','1')=='1') if demo_mode is None else demo_mode
        if self.demo_mode:
            seed(store)
        self.rag=rag or RAG(store)
        self.places=Places(store)
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
            token=cookie['campusloop_session'].value
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
            return dict(app_name='CampusLoop',api_version='2.0',demo_mode=self.demo_mode,places=PLACES,time_zone='America/Los_Angeles',default_date=row[0] or str(now().date()),chat_model=self.rag.client.chat_model,embed_model=self.rag.client.embed_model),200,{}
        if path=='/health' and method=='GET':
            with self.store.read() as db:
                db.execute('SELECT 1')
            return {'status':'ok','database':'ok','app':'CampusLoop','api_version':'2.0'},200,{}
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
                db.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(cookie['campusloop_session'].value.encode()).hexdigest(),))
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
        if path=='/api/trips' and method=='POST':
            with self.store.tx() as db:
                tid=trip_create(db,user,data)
                first_date=db.execute('SELECT min(trip_date) FROM occurrences WHERE trip_id=?',(tid,)).fetchone()[0]
            return {'trip_id':tid,'first_date':first_date},201,{}
        if path=='/api/applications' and method=='GET':
            with self.store.read() as db:
                rows=application_views(db,user)
            return {'applications':rows},200,{}
        if path=='/api/my-rides' and method=='GET':
            with self.store.read() as db:
                dates=db.execute('''SELECT DISTINCT o.trip_date FROM occurrences o JOIN trips t ON t.id=o.trip_id
                    LEFT JOIN applications a ON a.occurrence_id=o.id AND a.requester_id=?
                    WHERE o.trip_date>=? AND (t.owner_id=? OR a.status='confirmed') ORDER BY o.trip_date LIMIT 120''',(user['id'],str(now().date()),user['id'])).fetchall()
                rides=[]
                for date in dates:
                    for r in list_trips(db,user['id'],{'date':date[0]}):
                        if r['is_owner'] or (r['application'] and r['application']['status']=='confirmed'):
                            r['my_role']=r['role'] if r['is_owner'] else ('rider' if r['role']=='driver' else 'driver')
                            rides.append(r)
            return {'rides':rides},200,{}
        match=re.fullmatch(r'/api/occurrences/(\d+)/(request|cancel|activity|messages)',path)
        if match:
            oid,action=int(match[1]),match[2]
            if action=='request' and method=='POST':
                with self.store.tx() as db:
                    aid=request_ride(db,user,oid,data)
                return {'application_id':aid},201,{}
            if action=='cancel' and method=='POST':
                with self.store.tx() as db:
                    o=joined_occurrence(db,oid)
                    require(o['owner_id']==user['id'],'Only the post owner can cancel the entire ride date.',403)
                    ensure_open(o)
                    db.execute("UPDATE occurrences SET status='canceled',driver_id=NULL WHERE id=?",(oid,))
                    db.execute("UPDATE applications SET status='canceled' WHERE occurrence_id=? AND status IN ('pending','confirmed','waitlisted')",(oid,))
                    event(db,oid,user['id'],'The owner canceled this ride date. No other dates were changed.')
                return {'ok':True},200,{}
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
        match=re.fullmatch(r'/api/applications/(\d+)/(accept|decline|cancel|claim)',path)
        if match and method=='POST':
            aid,action=int(match[1]),match[2]
            with self.store.tx() as db:
                if action in ('accept','decline'):
                    result={'status':decide(db,user,aid,action=='accept')}
                elif action=='cancel':
                    result={'canceled':True,'promoted_application_ids':cancel_application(db,user,aid)}
                else:
                    claim(db,user,aid);result={'status':'confirmed'}
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
        self.send_header('Cache-Control','no-store' if mime.startswith('application/json') else 'no-cache')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' https://unpkg.com; style-src 'self' 'unsafe-inline' https://unpkg.com; img-src 'self' data: https://tile.openstreetmap.org; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        for name,value in (extra or {}).items():
            self.send_header(name,value)
        self.end_headers()
        self.wfile.write(content)

    def run_request(self):
        try:
            path=urlsplit(self.path).path
            static={'/':'index.html','/static/app.js':'app.js','/static/style.css':'style.css'}
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
    store=Store(os.getenv('DATABASE_PATH',str(ROOT/'data'/DEFAULT_DATABASE_NAME)))
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
