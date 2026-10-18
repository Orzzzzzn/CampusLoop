"""Update the Compose app actually serving a local port, preserving its project and DB."""
from __future__ import annotations
import argparse
import ast
import datetime as dt
import hashlib
import json
import os
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


def database_mount(container):
    env=dict(item.split('=',1) for item in container.get('Config',{}).get('Env',[]) if '=' in item)
    path=env.get('DATABASE_PATH','/app/data/heky.sqlite3')
    mounts=[m for m in container.get('Mounts',[]) if path==m['Destination'] or path.startswith(m['Destination'].rstrip('/')+'/')]
    check(mounts,'The running database has no persistent mount. Recreating this container could lose data, so the update stopped before changing anything.')
    mount=max(mounts,key=lambda m:len(m['Destination']))
    check(mount['Type'] in ('volume','bind'),'Unsupported database storage. No files were changed.')
    return dict(path=path,type=mount['Type'],target=mount['Destination'],source=mount.get('Name') if mount['Type']=='volume' else str(Path(mount['Source']).resolve()))


def release_files(source):
    output=[]
    for name in ['app','static','knowledge','tests']:
        output.extend(p for p in (source/name).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc')
    for name in ['Dockerfile','requirements.txt','Makefile','README.md','TEST_RESULTS.md','.dockerignore','.gitignore','.env.example','upgrade.py']:
        if (source/name).is_file():output.append(source/name)
    return sorted(output)


def release_version(source):
    tree=ast.parse((source/'app/__init__.py').read_text())
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in node.targets):return ast.literal_eval(node.value)
    raise UpgradeError('The new release has no version identifier.')


def inspect_running(port):
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
    working=Path(working).resolve()
    check(working.is_dir() and all(Path(p).is_file() for p in config_paths),'The original Compose files are not accessible on this computer. No files were changed.')
    prefix=['compose','--project-directory',str(working),'-p',project]
    for path in config_paths:prefix.extend(['-f',path])
    config=json.loads(docker([*prefix,'config','--format','json'],port=port))
    service_config=config.get('services',{}).get(service,{})
    check(any(str(p.get('published'))==str(port) for p in service_config.get('ports',[]) if isinstance(p,dict)),'The Compose configuration would move the app to another port. Resolve that difference first; no files were changed.')
    build=service_config.get('build',{})
    context=build if isinstance(build,str) else build.get('context','')
    check(context and '://' not in context,'This app does not build from a local source folder. No files were changed.')
    target=(working/context).resolve()
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
        else:source=str((working/source).resolve())
        persistent.append(dict(path=before['path'],type=mount.get('type'),target=mount['target'],source=source))
    check(before in persistent,'The configured database mount differs from the running database. Resolve that difference first; no files were changed.')
    for mount in container.get('Mounts',[]):
        if mount['Destination']=='/app/knowledge' and mount['Type']=='bind':
            check(Path(mount['Source']).resolve()==(target/'knowledge').resolve(),'Knowledge is mounted from a separate folder. Update that folder explicitly; no files were changed.')
    return dict(container=container,project=project,service=service,working=working,target=target,prefix=prefix,database=before)


def copy_release(source,target):
    if source.resolve()==target.resolve():return None
    files=release_files(source)
    stamp=dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup=target/f'campusloop-source-before-{stamp}.zip'
    with zipfile.ZipFile(backup,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            destination=target/path.relative_to(source)
            if destination.is_file():archive.write(destination,str(path.relative_to(source)))
    for path in files:
        destination=target/path.relative_to(source)
        destination.parent.mkdir(parents=True,exist_ok=True)
        temporary=destination.with_name(destination.name+'.campusloop-new')
        shutil.copyfile(path,temporary)
        os.replace(temporary,destination)
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
                return health
        except OSError:
            pass
        if time.monotonic()>=deadline:break
        if attempt+1<attempts:time.sleep(.5)
    raise UpgradeError('The updated app did not return the expected CampusLoop health response. The update is not marked successful. Keep the database volume; inspect docker compose logs app.')


def upgrade(source=ROOT,port=8010,dry_run=False):
    source=Path(source).resolve();version=release_version(source);plan=inspect_running(port)
    print('Running container: '+plan['container']['Name'].lstrip('/'),flush=True)
    print('Existing Compose project: '+plan['project'],flush=True)
    print('Actual source folder: '+str(plan['target']),flush=True)
    print('Release to install: '+version,flush=True)
    if dry_run:
        print('Dry run complete. No source files, containers, settings, or data were changed.');return
    backup=copy_release(source,plan['target'])
    if backup:print('Previous source backup: '+str(backup),flush=True)
    print('Existing .env, Compose configuration, database, and volume are retained.',flush=True)
    docker([*plan['prefix'],'build','--no-cache',plan['service']],capture=False,port=port)
    docker([*plan['prefix'],'up','-d','--no-deps','--force-recreate',plan['service']],capture=False,port=port)
    ids=docker([*plan['prefix'],'ps','-q',plan['service']],port=port).split()
    check(len(ids)==1,'The updated service could not be identified. The database was not deleted; inspect the Compose logs.')
    updated=json.loads(docker(['inspect',ids[0]]))[0]
    check(database_mount(updated)==plan['database'],'The service is not using its previous database mount. Stop here and inspect the retained original volume; no volume has been removed.')
    verify_server(port,version,source=source)
    print(f'Verified CampusLoop {version} backend and frontend at http://127.0.0.1:{port}',flush=True)
    print('Open that address and refresh the browser. No database volume was removed.',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8010,help='Port already used by the running app (default: 8010)')
    parser.add_argument('--dry-run',action='store_true',help='Identify the running project and validate storage without making changes')
    args=parser.parse_args()
    if not 1<=args.port<=65535:parser.error('Port must be between 1 and 65535.')
    try:upgrade(port=args.port,dry_run=args.dry_run)
    except (UpgradeError,OSError,ValueError,KeyError) as exc:
        print('Update stopped: '+str(exc),file=sys.stderr);return 1
    return 0

if __name__=='__main__':sys.exit(main())
