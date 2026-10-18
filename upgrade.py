"""Update the Compose app actually serving a local port, preserving its project and DB."""
from __future__ import annotations
import argparse
import ast
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parent

class UpgradeError(RuntimeError):
    pass


def check(condition,message):
    if not condition:
        raise UpgradeError(message)


def docker(args,capture=True,port=None):
    try:
        environment=dict(os.environ)
        if port is not None:environment['HEKY_PORT']=str(port)
        result=subprocess.run(['docker',*args],check=True,text=True,capture_output=capture,env=environment)
    except FileNotFoundError as exc:
        raise UpgradeError('Docker is not available. Start Docker Desktop and open a new terminal. If using native Python, stop the old server and run the new release with the same DATABASE_PATH.') from exc
    except subprocess.CalledProcessError as exc:
        raise UpgradeError('Docker command failed: docker '+' '.join(args)+'. Check that Docker Desktop is running and inspect the terminal output.') from exc
    return result.stdout if capture else ''


def host_path(value,base=None):
    """Resolve accessible native paths, including Docker Desktop VM aliases."""
    path=Path(value)
    if not path.is_absolute():path=Path(base or Path.cwd())/path
    if path.exists():return path.resolve()
    raw=str(path)
    for prefix in ('/host_mnt','/run/desktop/mnt/host'):
        if raw.startswith(prefix+'/'):
            native=Path(raw[len(prefix):])
            if native.exists():return native.resolve()
    return path.resolve()


def knowledge_mount(container):
    mounts=[m for m in container.get('Mounts',[]) if m['Destination']=='/app/knowledge']
    check(len(mounts)<=1,'Multiple knowledge mounts are ambiguous. No files were changed.')
    check(not any(m['Destination'].startswith('/app/knowledge/') for m in container.get('Mounts',[])),
        'Individual knowledge-file mounts require a manual update. No files were changed.')
    if not mounts:return None
    mount=mounts[0]
    check(mount['Type']=='bind','The knowledge folder uses a named volume instead of an accessible host folder. Update that volume explicitly; no files were changed.')
    return host_path(mount['Source'])


def knowledge_plan(container,service_config,working):
    actual=knowledge_mount(container)
    configured=[m for m in service_config.get('volumes',[]) if isinstance(m,dict) and m.get('target')=='/app/knowledge']
    if actual is None:
        check(not configured,'The knowledge mount differs from the running container. No files were changed.')
        return None
    check(len(configured)==1 and configured[0].get('type')=='bind',
        'The configured knowledge mount differs from the running folder. No files were changed.')
    expected=host_path(configured[0].get('source',''),working)
    check(actual==expected,'The configured knowledge folder differs from the running folder. No files were changed.')
    check(actual.is_dir(),'The mounted knowledge folder is not accessible on this computer: '+str(actual)+'. No files were changed.')
    check(os.access(actual,os.W_OK),'The mounted knowledge folder is not writable on this computer: '+str(actual)+'. No files were changed.')
    return actual


def database_mount(container):
    env=dict(item.split('=',1) for item in container.get('Config',{}).get('Env',[]) if '=' in item)
    path=env.get('DATABASE_PATH','/app/data/heky.sqlite3')
    mounts=[m for m in container.get('Mounts',[]) if path==m['Destination'] or path.startswith(m['Destination'].rstrip('/')+'/')]
    check(mounts,'The running database has no persistent mount. Recreating this container could lose data, so the update stopped before changing anything.')
    mount=max(mounts,key=lambda m:len(m['Destination']))
    check(mount['Type'] in ('volume','bind'),'Unsupported database storage. No files were changed.')
    return dict(path=path,type=mount['Type'],target=mount['Destination'],source=mount.get('Name') if mount['Type']=='volume' else str(host_path(mount['Source'])))


def release_files(source):
    output=[]
    for name in ['app','static','knowledge','tests']:
        output.extend(p for p in (source/name).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc')
    for name in ['Dockerfile','requirements.txt','Makefile','README.md','LIVE_TESTING.md','run_flow.py','TEST_RESULTS.md','.dockerignore','.gitignore','.env.example','upgrade.py']:
        if (source/name).is_file():output.append(source/name)
    return sorted(output)


def release_version(source):
    tree=ast.parse((source/'app/__init__.py').read_text())
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in node.targets):return ast.literal_eval(node.value)
    raise UpgradeError('The new release has no version identifier.')


def inspect_running(port,compose_dir=None):
    ids=docker(['ps','-q','--filter',f'publish={port}']).split()
    check(ids,f'No running Docker container publishes port {port}. If using native Python, stop the old server in its terminal and run this release with the existing DATABASE_PATH. No files were changed.')
    containers=json.loads(docker(['inspect',*ids]))
    matches=[c for c in containers if any(str(p.get('HostPort'))==str(port) for values in c.get('NetworkSettings',{}).get('Ports',{}).values() for p in (values or []))]
    check(len(matches)==1,'The port does not identify exactly one container. No files were changed.')
    container=matches[0];labels=container['Config'].get('Labels') or {}
    service=labels.get('com.docker.compose.service')
    project=labels.get('com.docker.compose.project')
    working=labels.get('com.docker.compose.project.working_dir')
    config_paths=labels.get('com.docker.compose.project.config_files','').split(',')
    check(service=='app' and project and working and all(config_paths),'The container is not a recognized CampusLoop Compose app. No files were changed.')
    if compose_dir is not None:return relocated_plan(container,project,service,host_path(compose_dir),port)
    working=host_path(working)
    config_paths=[host_path(p,working) for p in config_paths]
    check(working.is_dir() and all(p.is_file() for p in config_paths),'The original Compose files are not accessible on this computer: '+str(working)+'. Run again with --compose-dir pointing to the new project folder to retain the running project and database. No files were changed.')
    prefix=['compose','--project-directory',str(working),'-p',project]
    for path in config_paths:prefix.extend(['-f',str(path)])
    config=json.loads(docker([*prefix,'config','--format','json'],port=port))
    service_config=config.get('services',{}).get(service,{})
    check(any(str(p.get('published'))==str(port) for p in service_config.get('ports',[]) if isinstance(p,dict)),'The Compose configuration would move the app to another port. Resolve that difference first; no files were changed.')
    build=service_config.get('build',{})
    context=build if isinstance(build,str) else build.get('context','')
    check(context and '://' not in context,'This app does not build from a local source folder. No files were changed.')
    target=host_path(context,working)
    server_file=target/'app/server.py'
    check(server_file.is_file() and (target/'app/domain.py').is_file() and (target/'static/app.js').is_file(),'The build folder is not the expected Python carpool project. No files were changed.')
    check('/api/rides/search' in server_file.read_text(),'The build folder does not contain the expected carpool API. No files were changed.')
    before=database_mount(container)
    environment=service_config.get('environment') or {}
    if isinstance(environment,list):environment=dict(s.split('=',1) for s in environment if '=' in s)
    check(environment.get('DATABASE_PATH','/app/data/heky.sqlite3')==before['path'],'The Compose database path differs from the running container. Resolve that difference first; no files were changed.')
    persistent=[]
    for mount in service_config.get('volumes',[]):
        if not isinstance(mount,dict) or mount.get('target')!=before['target']:continue
        source=mount.get('source','')
        if mount.get('type')=='volume':source=config.get('volumes',{}).get(source,{}).get('name',source)
        else:source=str(host_path(source,working))
        persistent.append(dict(path=before['path'],type=mount.get('type'),target=mount['target'],source=source))
    check(before in persistent,'The configured database mount differs from the running database. Resolve that difference first; no files were changed.')
    knowledge=knowledge_plan(container,service_config,working)
    return dict(container=container,project=project,service=service,working=working,target=target,prefix=prefix,database=before,knowledge=knowledge)


def configured_database(config,service,working):
    environment=service.get('environment') or {}
    records=[]
    for mount in service.get('volumes',[]):
        if not isinstance(mount,dict):continue
        path=environment.get('DATABASE_PATH','/app/data/heky.sqlite3')
        target=mount.get('target','')
        if path!=target and not path.startswith(target.rstrip('/')+'/'):continue
        source=mount.get('source','')
        if mount.get('type')=='volume':source=config.get('volumes',{}).get(source,{}).get('name',source)
        else:source=str(host_path(source,working))
        records.append(dict(path=path,type=mount.get('type'),target=target,source=source))
    return records


def relocated_plan(container,project,service,working,port):
    """Plan an explicit move to current source while retaining live storage/settings."""
    check(working.is_dir(),'The selected new Compose folder does not exist. No files were changed.')
    compose=next((working/n for n in ('compose.yaml','compose.yml','docker-compose.yaml','docker-compose.yml') if (working/n).is_file()),None)
    check(compose is not None,'No Compose file exists in the selected new folder. No files were changed.')
    config=json.loads(docker(['compose','--project-directory',str(working),'-p',project,'-f',str(compose),'config','--format','json'],port=port))
    selected=config.get('services',{}).get(service)
    check(isinstance(selected,dict),'The new Compose file has no app service. No files were changed.')
    build=selected.get('build',{})
    context=build if isinstance(build,str) else build.get('context','')
    check(context and '://' not in context,'The new app needs a local build folder. No files were changed.')
    target=host_path(context,working)
    check((target/'app/server.py').is_file() and (target/'app/domain.py').is_file() and (target/'static/app.js').is_file(),'The new build folder is not the CampusLoop Python app. No files were changed.')
    check('/api/rides/search' in (target/'app/server.py').read_text(),'The new folder is not the expected CampusLoop API. No files were changed.')
    before=database_mount(container)
    check(before['type']=='volume' or Path(before['source']).exists(),'The existing database bind folder is inaccessible. No files were changed.')
    check(len(configured_database(config,selected,working))<=1,'Multiple database mounts in the new configuration are ambiguous. No files were changed.')
    # Keep the actual app environment, including credentials, in a private stable file.
    inherited=dict(item.split('=',1) for item in container.get('Config',{}).get('Env',[]) if '=' in item)
    image_keys={'PATH','HOSTNAME','HOME','LANG','GPG_KEY','PYTHON_VERSION','PYTHON_SHA256','PYTHON_PIP_VERSION','PYTHON_SETUPTOOLS_VERSION','PYTHON_GET_PIP_URL','PYTHON_GET_PIP_SHA256'}
    env=selected.get('environment') or {}
    if isinstance(env,list):env=dict(x.split('=',1) for x in env if '=' in x)
    for key,value in inherited.items():
        if key not in image_keys:env[key]=value.replace('$','$$')
    env['DATABASE_PATH']=before['path'];selected['environment']=env
    # Use the exact old host ports and their bindings, never a new default port.
    ports=[]
    for internal,bindings in container.get('NetworkSettings',{}).get('Ports',{}).items():
        number,protocol=internal.split('/')
        for binding in bindings or []:
            ports.append(dict(target=int(number),published=str(binding['HostPort']),host_ip=binding.get('HostIp') or '127.0.0.1',protocol=protocol))
    check(any(p['published']==str(port) for p in ports),'The running app does not publish the selected port. No files were changed.')
    selected['ports']=ports
    mounts=list(container.get('Mounts',[]))
    check(not any(m['Destination'] in ('/app','/app/app','/app/static') or m['Destination'].startswith(('/app/app/','/app/static/')) for m in mounts),'A source-code bind mount would hide the new image. No files were changed.')
    knowledge=knowledge_mount(container)
    recovery=Path.home()/'.campusloop'/'recovery'/(project+'-'+dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    recover_knowledge=knowledge is not None and not knowledge.is_dir()
    if recover_knowledge:knowledge=recovery/'knowledge'
    # Preserve all live mounts, including a database with a nonstandard volume name.
    combined={v['target']:v for v in selected.get('volumes',[]) if isinstance(v,dict)}
    definitions=config.setdefault('volumes',{})
    for index,m in enumerate(mounts):
        dest=m['Destination'];kind=m['Type']
        if kind not in ('bind','volume'):continue
        if kind=='volume':
            check(bool(m.get('Name')),'The running named volume has no name. No files were changed.')
            alias='campusloop_retained_'+str(index)
            definitions[alias]={'name':m['Name'],'external':True}
            entry=dict(type='volume',source=alias,target=dest,read_only=not m.get('RW',True))
        else:
            source=knowledge if dest=='/app/knowledge' else host_path(m['Source'])
            check(dest=='/app/knowledge' or source.exists(),'A running bind mount is inaccessible: '+str(source)+'. No files were changed.')
            entry=dict(type='bind',source=str(source),target=dest,read_only=not m.get('RW',True))
        combined[dest]=entry
    selected['volumes']=list(combined.values())
    # Attach the app to its actual existing networks so local model aliases survive.
    networks=container.get('NetworkSettings',{}).get('Networks',{})
    if networks:
        selected['networks']={}
        for index,name in enumerate(networks):
            alias='campusloop_retained_network_'+str(index)
            config.setdefault('networks',{})[alias]={'name':name,'external':True}
            selected['networks'][alias]={}
    check(before in configured_database(config,selected,working),'The recovery configuration would change the database mount. No files were changed.')
    config['name']=project
    saved=recovery/'compose.json'
    prefix=['compose','--project-directory',str(working),'-p',project,'-f',str(saved)]
    return dict(container=container,project=project,service=service,working=working,target=target,prefix=prefix,database=before,knowledge=knowledge,recovery=recovery,recovery_config=config,recover_knowledge=recover_knowledge)


def prepare_relocation(plan,port):
    """Save stable private settings before any container is recreated."""
    folder=plan['recovery']
    folder.mkdir(parents=True,mode=0o700)
    if plan['recover_knowledge']:
        plan['knowledge'].mkdir(mode=0o700)
        docker(['cp',plan['container']['Id']+':/app/knowledge/.',str(plan['knowledge'])])
        check(any(plan['knowledge'].iterdir()),'Knowledge could not be recovered from the running container. The container and database were not changed.')
    path=folder/'compose.json'
    # The file may contain SMTP/API settings; keep it outside the code repository.
    with open(path,'x',opener=lambda name,flags:os.open(name,flags,0o600)) as output:
        json.dump(plan['recovery_config'],output,indent=2)
    rendered=json.loads(docker([*plan['prefix'],'config','--format','json'],port=port))
    check(plan['database'] in configured_database(rendered,rendered['services'][plan['service']],plan['working']),'The saved recovery configuration does not retain the database. The running container was not changed.')
    print('Retained Compose settings: '+str(path),flush=True)


def copy_release(source,target,knowledge_target=None):
    """Back up every replaced file before copying; never delete custom documents."""
    source,target=Path(source).resolve(),Path(target).resolve()
    operations={}
    for path in release_files(source):
        relative=path.relative_to(source)
        # A standalone repair script must install itself rather than copy an older updater.
        if relative==Path('upgrade.py'):path=Path(__file__).resolve()
        destination=target/relative
        if path.resolve()!=destination.resolve():operations[destination]=(path,str(relative),target)
        if relative.parts[0]=='knowledge' and knowledge_target is not None:
            destination=Path(knowledge_target)/Path(*relative.parts[1:])
            if path.resolve()!=destination.resolve():
                operations[destination]=(path,'mounted-knowledge/'+str(Path(*relative.parts[1:])),Path(knowledge_target))
    if not operations:return None
    # Validate all destinations before the first backup or copy operation.
    for destination,(path,entry,allowed_root) in operations.items():
        check(destination.parent.resolve().is_relative_to(allowed_root.resolve()),'A destination escapes its selected folder. No files were changed.')
        check(not destination.is_symlink() and not destination.is_dir(),'A release destination is a symlink or directory: '+str(destination)+'. No files were changed.')
        parent=destination.parent
        while not parent.exists():parent=parent.parent
        check(os.access(parent,os.W_OK),'An update folder is not writable: '+str(parent)+'. No files were changed.')
    stamp=dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup=target/f'campusloop-source-before-{stamp}.zip'
    manifest=[]
    with zipfile.ZipFile(backup,'w',zipfile.ZIP_DEFLATED) as archive:
        for destination,(path,entry,allowed_root) in operations.items():
            existed=destination.is_file()
            if existed:archive.write(destination,entry)
            manifest.append(dict(destination=str(destination),archive_entry=entry,existed=existed))
        archive.writestr('campusloop-backup.json',json.dumps(manifest,indent=2))
    for destination,(path,entry,allowed_root) in operations.items():
        destination.parent.mkdir(parents=True,exist_ok=True)
        temporary=destination.with_name(destination.name+'.campusloop-new')
        try:
            shutil.copyfile(path,temporary)
            os.replace(temporary,destination)
        finally:
            if temporary.exists():temporary.unlink()
    return backup


def verify_server(port,version,attempts=40,source=ROOT):
    base=f'http://127.0.0.1:{port}'
    deadline=time.monotonic()+30
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(base+'/health',timeout=2) as response:health=json.load(response)
            if health.get('app')=='CampusLoop' and health.get('version')==version:
                with urllib.request.urlopen(base,timeout=2) as response:html=response.read().decode()
                with urllib.request.urlopen(base+f'/static/app.js?v={version}',timeout=2) as response:script=response.read().decode()
                with urllib.request.urlopen(base+f'/static/style.css?v={version}',timeout=2) as response:style=response.read().decode()
                check(f'content="{version}"' in html and 'CampusLoop home' in html,'The backend was updated but the served HTML is from another release.')
                check("CLIENT_VERSION='"+version+"'" in script and 'Ask CampusLoop.' in script,'The backend was updated but the served JavaScript is from another release.')
                for value,path in [(html,Path(source)/'static/index.html'),(script,Path(source)/'static/app.js'),(style,Path(source)/'static/style.css')]:
                    check(hashlib.sha256(value.encode()).digest()==hashlib.sha256(path.read_bytes()).digest(),'The served frontend files do not match the new release. A version badge alone is not accepted as a successful update.')
                pending=set(re.findall(r'/static/([A-Za-z0-9_./-]+\.(?:js|css|jpeg|jpg|png|svg|webp))',html+'\n'+script+'\n'+style))
                seen={'app.js','style.css','index.html'}
                while pending:
                    relative=pending.pop()
                    if relative in seen:continue
                    seen.add(relative);asset=Path(source)/'static'/relative
                    check(asset.resolve().is_relative_to((Path(source)/'static').resolve()) and asset.is_file(),'A referenced frontend asset is missing from the release.')
                    with urllib.request.urlopen(base+'/static/'+relative+f'?v={version}',timeout=2) as response:served=response.read()
                    check(hashlib.sha256(served).digest()==hashlib.sha256(asset.read_bytes()).digest(),'The served landing assets do not match the new release. The update is not marked successful.')
                    if asset.suffix in {'.js','.css'}:pending.update(re.findall(r'/static/([A-Za-z0-9_./-]+\.(?:js|css|jpeg|jpg|png|svg|webp))',asset.read_text()))
                return health
        except OSError:
            pass
        if time.monotonic()>=deadline:break
        if attempt+1<attempts:time.sleep(.5)
    raise UpgradeError('The updated app did not return the expected CampusLoop health response. The update is not marked successful. Keep the database volume; inspect docker compose logs app.')


def google_key_from_env(path):
    if path is None:return None
    path=Path(path).expanduser().resolve()
    check(path.is_file(),'The selected Google environment file does not exist. No files were changed.')
    value=None
    for line in path.read_text().splitlines():
        line=line.strip()
        if line.startswith('export '):line=line[7:]
        if line.startswith('GOOGLE_MAPS_API_KEY='):
            value=line.split('=',1)[1].strip()
    if value and len(value)>1 and value[0]==value[-1] and value[0] in ('"',"'"):value=value[1:-1]
    check(bool(value),'The selected environment file has no nonempty GOOGLE_MAPS_API_KEY. No files were changed.')
    return value


def apply_google_key(plan,key,port):
    folder=Path.home()/'.campusloop'/'pricing'/(plan['project']+'-'+dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    folder.mkdir(parents=True,mode=0o700)
    path=folder/'compose-google.json'
    with open(path,'x',opener=lambda name,flags:os.open(name,flags,0o600)) as output:
        json.dump({'services':{plan['service']:{'environment':{'GOOGLE_MAPS_API_KEY':key.replace('$','$$')}}}},output)
    plan['prefix']=[*plan['prefix'],'-f',str(path)]
    config=json.loads(docker([*plan['prefix'],'config','--format','json'],port=port))
    service=config['services'][plan['service']]
    check(plan['database'] in configured_database(config,service,plan['working']),'The Google pricing override does not retain the database. The container was not changed.')
    check(service.get('environment',{}).get('GOOGLE_MAPS_API_KEY')==key,'The Google pricing override could not be verified. The container was not changed.')
    print('Google route pricing key will be applied through a private Compose override.',flush=True)


def upgrade(source=ROOT,port=8010,dry_run=False,compose_dir=None,google_env=None):
    key=google_key_from_env(google_env)
    source=Path(source).resolve();version=release_version(source);plan=inspect_running(port,compose_dir=compose_dir)
    print('Running container: '+plan['container']['Name'].lstrip('/'),flush=True)
    print('Existing Compose project: '+plan['project'],flush=True)
    print('Actual source folder: '+str(plan['target']),flush=True)
    print('Release to install: '+version,flush=True)
    if plan['knowledge']:print('Mounted knowledge folder: '+str(plan['knowledge'])+' (bundled documents updated; custom files retained)',flush=True)
    if dry_run:
        print('Dry run complete. No source files, containers, settings, or data were changed.');return
    if plan.get('recovery'):prepare_relocation(plan,port)
    if key is not None:apply_google_key(plan,key,port)
    backup=copy_release(source,plan['target'],plan['knowledge'])
    if backup:print('Previous source backup: '+str(backup),flush=True)
    print('Existing project, database, mounted data, and app settings are retained.',flush=True)
    docker([*plan['prefix'],'build','--no-cache',plan['service']],capture=False,port=port)
    docker([*plan['prefix'],'up','-d','--no-deps','--force-recreate',plan['service']],capture=False,port=port)
    ids=docker([*plan['prefix'],'ps','-q',plan['service']],port=port).split()
    check(len(ids)==1,'The updated service could not be identified. The database was not deleted; inspect the Compose logs.')
    updated=json.loads(docker(['inspect',ids[0]]))[0]
    check(database_mount(updated)==plan['database'],'The service is not using its previous database mount. Stop here and inspect the retained original volume; no volume has been removed.')
    check(knowledge_mount(updated)==plan['knowledge'],'The service is not using its previous knowledge folder. No original folder was removed; inspect the retained Compose settings.')
    if key is not None:
        current=dict(item.split('=',1) for item in updated.get('Config',{}).get('Env',[]) if '=' in item)
        check(current.get('GOOGLE_MAPS_API_KEY')==key,'The recreated app did not receive the Google key. The database was retained.')
    verify_server(port,version,source=source)
    print(f'Verified CampusLoop {version} backend and frontend at http://127.0.0.1:{port}',flush=True)
    print('Open that address and refresh the browser. No database volume was removed.',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT,help='Extracted release folder containing app, static and knowledge (default: this script folder)')
    parser.add_argument('--compose-dir',type=Path,help='Explicit new Compose folder when the old folder was moved or removed; retains the live database and settings')
    parser.add_argument('--port',type=int,default=8010,help='Port already used by the running app (default: 8010)')
    parser.add_argument('--google-env',type=Path,help='Apply only GOOGLE_MAPS_API_KEY from this local .env file, using a private override while retaining existing storage/settings')
    parser.add_argument('--dry-run',action='store_true',help='Identify the running project and validate storage without making changes')
    args=parser.parse_args()
    if not 1<=args.port<=65535:parser.error('Port must be between 1 and 65535.')
    try:upgrade(source=args.source,port=args.port,dry_run=args.dry_run,compose_dir=args.compose_dir,google_env=args.google_env)
    except (UpgradeError,OSError,ValueError,KeyError) as exc:
        print('Update stopped: '+str(exc),file=sys.stderr);return 1
    return 0

if __name__=='__main__':sys.exit(main())
