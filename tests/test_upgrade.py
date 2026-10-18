"""Upgrade planning/copying tests with a Docker CLI fixture, not a Docker daemon."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import upgrade

class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name)
        self.source=root/'new download';self.target=root/'existing source';self.working=root/'compose project'
        for path in [self.source,self.target]:
            (path/'app').mkdir(parents=True);(path/'static').mkdir();(path/'knowledge').mkdir()
            (path/'app/server.py').write_text("# /api/rides/search\n")
            (path/'app/domain.py').write_text('# domain\n')
            (path/'static/app.js').write_text('old source' if path==self.target else 'new source')
            (path/'app/__init__.py').write_text("VERSION='2.2.0'\n")
            (path/'knowledge/accounts.md').write_text('English policy')
        self.working.mkdir();self.compose=self.working/'compose.yaml';self.compose.write_text('original compose')
        (self.target/'.env').write_text('KEEP=original')
        (self.target/'data').mkdir();(self.target/'data/heky.sqlite3').write_bytes(b'original database bytes')
        (self.source/'.env').write_text('DO_NOT_COPY=1')
        self.container={'Id':'old','Name':'/existing-app-1','Config':{'Labels':{'com.docker.compose.service':'app','com.docker.compose.project':'existing','com.docker.compose.project.working_dir':str(self.working),'com.docker.compose.project.config_files':str(self.compose)},'Env':['DATABASE_PATH=/app/data/heky.sqlite3']},'NetworkSettings':{'Ports':{'8000/tcp':[{'HostPort':'8010'}]}},'Mounts':[{'Type':'volume','Destination':'/app/data','Name':'existing_heky_data'},{'Type':'bind','Destination':'/app/knowledge','Source':str(self.target/'knowledge')}]}
        self.config={'services':{'app':{'build':{'context':str(self.target)},'environment':{'DATABASE_PATH':'/app/data/heky.sqlite3'},'ports':[{'target':8000,'published':'8010'}],'volumes':[{'type':'volume','source':'heky_data','target':'/app/data'}]}},'volumes':{'heky_data':{'name':'existing_heky_data'}}}
        self.config['services']['app']['volumes'].append({'type':'bind','source':str(self.target/'knowledge'),'target':'/app/knowledge','read_only':True})
        self.calls=[]
    def tearDown(self):self.temp.cleanup()
    def fake_docker(self,args,capture=True,port=None):
        self.calls.append(args)
        if args[:1]==['ps']:return 'old\n'
        if args[:1]==['inspect']:return json.dumps([copy.deepcopy(self.container)])
        if 'config' in args:return json.dumps(self.config)
        if 'ps' in args:return 'new\n'
        if 'build' in args or 'up' in args:return ''
        raise AssertionError(args)
    def test_google_env_file_is_explicit_and_never_copies_other_settings(self):
        path=Path(self.temp.name)/'local.env';path.write_text('KEEP=secret\nGOOGLE_MAPS_API_KEY="local-google-key"\n')
        self.assertEqual(upgrade.google_key_from_env(path),'local-google-key')
        path.write_text('GOOGLE_MAPS_API_KEY=\n')
        with self.assertRaises(upgrade.UpgradeError):upgrade.google_key_from_env(path)
        self.assertIsNone(upgrade.google_key_from_env(None))

    def test_google_key_override_is_private_preserves_database_and_escapes_dollars(self):
        with patch.object(upgrade,'docker',side_effect=self.fake_docker):plan=upgrade.inspect_running(8010)
        key='local$google-key';home=Path(self.temp.name)/'home';home.mkdir()
        def render(args,capture=True,port=None):
            config=copy.deepcopy(self.config);config['services']['app']['environment']['GOOGLE_MAPS_API_KEY']=key
            return json.dumps(config)
        log=io.StringIO()
        with patch.object(upgrade.Path,'home',return_value=home),patch.object(upgrade,'docker',side_effect=render),contextlib.redirect_stdout(log):upgrade.apply_google_key(plan,key,8010)
        saved=Path(plan['prefix'][-1]);self.assertEqual(saved.stat().st_mode&0o777,0o600);self.assertEqual(saved.parent.stat().st_mode&0o777,0o700)
        self.assertEqual(json.loads(saved.read_text())['services']['app']['environment']['GOOGLE_MAPS_API_KEY'],'local$$google-key')
        self.assertNotIn(key,log.getvalue());self.assertEqual((self.target/'.env').read_text(),'KEEP=original')

    def test_full_update_explicit_google_env_reaches_container_and_dry_run_does_not_write(self):
        home=Path(self.temp.name)/'private-home';home.mkdir();envfile=Path(self.temp.name)/'key.env';key='local-only-google-key'
        envfile.write_text('GOOGLE_MAPS_API_KEY='+key+'\n');recreated=False
        def fake(args,capture=True,port=None):
            nonlocal recreated
            if 'up' in args:recreated=True
            if args[0]=='inspect':
                container=copy.deepcopy(self.container)
                if recreated:container['Config']['Env'].append('GOOGLE_MAPS_API_KEY='+key)
                return json.dumps([container])
            if 'config' in args and any('compose-google.json' in s for s in args):
                config=copy.deepcopy(self.config);config['services']['app']['environment']['GOOGLE_MAPS_API_KEY']=key;return json.dumps(config)
            return self.fake_docker(args,capture,port)
        output=io.StringIO()
        with patch.object(upgrade.Path,'home',return_value=home),patch.object(upgrade,'docker',side_effect=fake),patch.object(upgrade,'verify_server'),contextlib.redirect_stdout(output):
            upgrade.upgrade(self.source,dry_run=True,google_env=envfile)
            self.assertEqual(list(home.iterdir()),[])
            upgrade.upgrade(self.source,google_env=envfile)
        self.assertNotIn(key,output.getvalue());self.assertTrue(recreated)
        self.assertEqual((self.target/'data/heky.sqlite3').read_bytes(),b'original database bytes')

    def test_update_uses_running_project_and_context_and_keeps_env_and_database(self):
        with patch.object(upgrade,'docker',side_effect=self.fake_docker),patch.object(upgrade,'verify_server',return_value={'app':'CampusLoop','version':'2.2.0'}) as verify,contextlib.redirect_stdout(io.StringIO()):
            upgrade.upgrade(self.source)
        self.assertEqual((self.target/'static/app.js').read_text(),'new source')
        self.assertEqual((self.target/'.env').read_text(),'KEEP=original')
        self.assertEqual((self.target/'data/heky.sqlite3').read_bytes(),b'original database bytes')
        self.assertEqual(self.compose.read_text(),'original compose')
        backup=next(self.target.glob('campusloop-source-before-*.zip'))
        with zipfile.ZipFile(backup) as z:
            self.assertEqual(z.read('static/app.js'),b'old source');self.assertNotIn('.env',z.namelist());self.assertNotIn('data/heky.sqlite3',z.namelist())
        build=next(call for call in self.calls if 'build' in call)
        self.assertIn('--no-cache',build);self.assertEqual(build[build.index('-p')+1],'existing');self.assertEqual(build[build.index('-f')+1],str(self.compose))
        self.assertFalse(any('down' in call for call in self.calls));verify.assert_called_once_with(8010,'2.2.0',source=self.source.resolve())
    def test_dry_run_does_not_copy_or_rebuild(self):
        with patch.object(upgrade,'docker',side_effect=self.fake_docker),contextlib.redirect_stdout(io.StringIO()):upgrade.upgrade(self.source,dry_run=True)
        self.assertEqual((self.target/'static/app.js').read_text(),'old source');self.assertFalse(list(self.target.glob('*.zip')))
        self.assertFalse(any('build' in call or 'up' in call for call in self.calls))
    def test_changed_database_mount_stops_before_copy(self):
        self.config['volumes']['heky_data']['name']='different_empty_volume'
        with patch.object(upgrade,'docker',side_effect=self.fake_docker),self.assertRaisesRegex(upgrade.UpgradeError,'database mount differs'):
            upgrade.upgrade(self.source)
        self.assertEqual((self.target/'static/app.js').read_text(),'old source')
    def test_unpersisted_database_stops_before_copy(self):
        self.container['Mounts']=[]
        with patch.object(upgrade,'docker',side_effect=self.fake_docker),self.assertRaisesRegex(upgrade.UpgradeError,'no persistent mount'):
            upgrade.upgrade(self.source)
        self.assertFalse(list(self.target.glob('*.zip')))
    def test_ambiguous_port_stops_before_copy(self):
        def fake(args,capture=True,port=None):
            if args[0]=='inspect':return json.dumps([self.container,self.container])
            return self.fake_docker(args,capture,port)
        with patch.object(upgrade,'docker',side_effect=fake),self.assertRaisesRegex(upgrade.UpgradeError,'exactly one container'):
            upgrade.upgrade(self.source)
    def test_old_health_response_is_never_reported_as_success(self):
        @contextlib.contextmanager
        def old_response(*args,**kwargs):yield io.BytesIO(b'{"status":"ok","database":"ok"}')
        with patch.object(upgrade.urllib.request,'urlopen',side_effect=old_response),self.assertRaisesRegex(upgrade.UpgradeError,'not marked successful'):
            upgrade.verify_server(8010,'2.2.0',attempts=1)

    def test_current_port_overrides_stale_environment_without_rewriting_it(self):
        with patch.dict(upgrade.os.environ,{'HEKY_PORT':'8000'}),patch.object(upgrade.subprocess,'run') as process:
            process.return_value.stdout='ok'
            upgrade.docker(['compose','config','--format','json'],port=8010)
            self.assertEqual(process.call_args.kwargs['env']['HEKY_PORT'],'8010')
            self.assertEqual(upgrade.os.environ['HEKY_PORT'],'8000')

    def test_a_new_version_badge_with_old_frontend_bytes_is_rejected(self):
        @contextlib.contextmanager
        def stale_assets(url,**kwargs):
            if url.endswith('/health'):body=b'{"app":"CampusLoop","version":"2.2.0"}'
            elif '/static/app.js' in url:body=b"const CLIENT_VERSION='2.2.0'; /* Ask CampusLoop. */"
            else:body=b'<meta content="2.2.0"><button aria-label="CampusLoop home">CampusLoop</button>'
            yield io.BytesIO(body)
        with patch.object(upgrade.urllib.request,'urlopen',side_effect=stale_assets),self.assertRaisesRegex(upgrade.UpgradeError,'do not match'):
            upgrade.verify_server(8010,'2.2.0',attempts=1)

    def test_matching_script_with_stale_css_is_rejected(self):
        version=upgrade.release_version(upgrade.ROOT)
        @contextlib.contextmanager
        def stale_style(url,**kwargs):
            if url.endswith('/health'):body=json.dumps({'app':'CampusLoop','version':version}).encode()
            elif '/static/style.css' in url:body=b'/* outdated stylesheet */'
            elif '/static/app.js' in url:body=(upgrade.ROOT/'static/app.js').read_bytes()
            else:body=(upgrade.ROOT/'static/index.html').read_bytes()
            yield io.BytesIO(body)
        with patch.object(upgrade.urllib.request,'urlopen',side_effect=stale_style),self.assertRaisesRegex(upgrade.UpgradeError,'do not match'):
            upgrade.verify_server(8010,version,attempts=1)

    def external_knowledge(self):
        folder=Path(self.temp.name)/'separate knowledge'
        folder.mkdir()
        (folder/'accounts.md').write_text('Previous guide')
        (folder/'my-campus-guide.md').write_text('Keep my custom guide')
        self.container['Mounts'][1]['Source']=str(folder)
        self.config['services']['app']['volumes'][1]['source']=str(folder)
        (self.source/'knowledge/accounts.md').write_text('Updated guide')
        return folder

    def test_separate_knowledge_is_updated_backed_up_and_custom_documents_retained(self):
        folder=self.external_knowledge()
        with patch.object(upgrade,'docker',side_effect=self.fake_docker),patch.object(upgrade,'verify_server'),contextlib.redirect_stdout(io.StringIO()):
            upgrade.upgrade(self.source)
        self.assertEqual((folder/'accounts.md').read_text(),'Updated guide')
        self.assertEqual((folder/'my-campus-guide.md').read_text(),'Keep my custom guide')
        self.assertEqual((self.target/'data/heky.sqlite3').read_bytes(),b'original database bytes')
        with zipfile.ZipFile(next(self.target.glob('campusloop-source-before-*.zip'))) as z:
            self.assertEqual(z.read('mounted-knowledge/accounts.md'),b'Previous guide')

    def test_separate_knowledge_drift_stops_before_copy(self):
        self.external_knowledge()
        self.config['services']['app']['volumes'][1]['source']=str(self.target/'knowledge')
        with patch.object(upgrade,'docker',side_effect=self.fake_docker),self.assertRaisesRegex(upgrade.UpgradeError,'knowledge folder differs'):
            upgrade.upgrade(self.source)
        self.assertEqual((self.target/'static/app.js').read_text(),'old source')
        self.assertFalse(list(self.target.glob('*.zip')))

    def test_same_release_folder_updates_external_documents(self):
        folder=self.external_knowledge()
        (self.target/'knowledge/accounts.md').write_text('Latest local guide')
        with patch.object(upgrade,'docker',side_effect=self.fake_docker),patch.object(upgrade,'verify_server'),contextlib.redirect_stdout(io.StringIO()):
            upgrade.upgrade(self.target)
        self.assertEqual((folder/'accounts.md').read_text(),'Latest local guide')

    def test_docker_desktop_host_alias_preserves_native_knowledge_folder(self):
        self.container['Mounts'][1]['Source']='/host_mnt'+str(self.target/'knowledge')
        with patch.object(upgrade,'docker',side_effect=self.fake_docker):plan=upgrade.inspect_running(8010)
        self.assertEqual(plan['knowledge'],self.target/'knowledge')

    def test_current_main_files_with_stale_landing_asset_are_rejected(self):
        version=upgrade.release_version(upgrade.ROOT)
        @contextlib.contextmanager
        def response(url,**kwargs):
            if url.endswith('/health'):body=json.dumps({'app':'CampusLoop','version':version}).encode()
            elif '/static/landing' in url:body=b'outdated landing asset'
            elif '/static/app.js' in url:body=(upgrade.ROOT/'static/app.js').read_bytes()
            elif '/static/style.css' in url:body=(upgrade.ROOT/'static/style.css').read_bytes()
            else:body=(upgrade.ROOT/'static/index.html').read_bytes()
            yield io.BytesIO(body)
        with patch.object(upgrade.urllib.request,'urlopen',side_effect=response),self.assertRaisesRegex(upgrade.UpgradeError,'landing assets do not match'):
            upgrade.verify_server(8010,version,attempts=1)

if __name__=='__main__':unittest.main()
