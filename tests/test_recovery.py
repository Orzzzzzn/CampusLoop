import contextlib,copy,io,json,unittest
from pathlib import Path
from unittest.mock import patch
import test_upgrade as base
import upgrade as repair
class RecoveryTests(base.UpgradeTests):
    def setUp(self):
        super().setUp()
        self.container['Config']['Env']+=['DEMO_MODE=0','SMTP_PASSWORD=a$b secret','PATH=/container/only']
        self.container['NetworkSettings']['Networks']={'existing_default':{'Aliases':['app']}}
        self.container['Mounts'][0]['Name']='nonstandard_existing_database'
        self.container['Mounts'][1]['RW']=False
        self.compose.unlink()
        (self.source/'compose.yaml').write_text('services: {}')
        self.newconfig=copy.deepcopy(self.config)
        self.newconfig['services']['app']['build']={'context':str(self.source)}
        self.newconfig['services']['app']['environment']['NEW_PRICING_FACTOR']='0.65'
        self.newconfig['services']['app']['volumes'][1]['source']=str(self.source/'knowledge')
        self.home=Path(self.temp.name)/'home'
        self.home.mkdir()
        self.home_patch=patch.object(repair.Path,'home',return_value=self.home);self.home_patch.start()
    def tearDown(self):
        self.home_patch.stop();super().tearDown()
    def docker(self,args,capture=True,port=None):
        self.calls.append(args)
        if args[0]=='ps':return 'old\n'
        if args[0]=='inspect':
            container=copy.deepcopy(self.container)
            if args[-1]=='new' and self.saved_path:
                config=json.loads(self.saved_path.read_text())
                knowledge=next(m for m in config['services']['app']['volumes'] if m['target']=='/app/knowledge')
                container['Mounts'][1]['Source']=knowledge['source']
            return json.dumps([container])
        if args[0]=='cp':
            folder=Path(args[-1]);(folder/'custom.md').write_text('Custom knowledge retained');(folder/'accounts.md').write_text('Old accounts guide')
            return ''
        if 'config' in args:
            file=Path(args[args.index('-f')+1])
            if file.name=='compose.json':self.saved_path=file;return file.read_text()
            return json.dumps(copy.deepcopy(self.newconfig))
        if 'ps' in args:return 'new\n'
        if 'build' in args or 'up' in args:return ''
        raise AssertionError(args)
    def plan(self):
        self.saved_path=None
        with patch.object(repair,'docker',side_effect=self.docker):return repair.inspect_running(8010,compose_dir=self.source)
    def test_missing_old_compose_uses_explicit_new_folder_and_exact_live_database(self):
        plan=self.plan()
        self.assertEqual(plan['project'],'existing');self.assertEqual(plan['target'],self.source)
        self.assertEqual(plan['database']['source'],'nonstandard_existing_database')
        self.assertEqual(plan['recovery_config']['services']['app']['environment']['DEMO_MODE'],'0')
        self.assertEqual(plan['recovery_config']['services']['app']['environment']['SMTP_PASSWORD'],'a$$b secret')
        self.assertEqual(plan['recovery_config']['services']['app']['environment']['NEW_PRICING_FACTOR'],'0.65')
        self.assertNotIn('PATH',plan['recovery_config']['services']['app']['environment'])
        self.assertFalse(plan['recovery'].exists())
        self.assertFalse(any('build' in c or 'up' in c for c in self.calls))
    def test_complete_relocation_retains_database_and_private_settings(self):
        self.saved_path=None
        with patch.object(repair,'docker',side_effect=self.docker),patch.object(repair,'verify_server'),contextlib.redirect_stdout(io.StringIO()):
            repair.upgrade(self.source,compose_dir=self.source)
        self.assertTrue(self.saved_path.is_file())
        self.assertEqual(self.saved_path.stat().st_mode&0o777,0o600)
        self.assertEqual(self.saved_path.parent.stat().st_mode&0o777,0o700)
        settings=json.loads(self.saved_path.read_text())
        self.assertTrue(any(v.get('name')=='nonstandard_existing_database' and v.get('external') for v in settings['volumes'].values()))
        self.assertTrue(any(v.get('name')=='existing_default' and v.get('external') for v in settings['networks'].values()))
        self.assertTrue(any('build' in c for c in self.calls));self.assertTrue(any('up' in c for c in self.calls))
        self.assertFalse(any('down' in c or 'rm' in c or 'prune' in c for c in self.calls))
        self.assertEqual((self.target/'data/heky.sqlite3').read_bytes(),b'original database bytes')
    def test_dry_run_creates_no_private_files_and_does_not_recreate(self):
        self.saved_path=None
        with patch.object(repair,'docker',side_effect=self.docker),contextlib.redirect_stdout(io.StringIO()):repair.upgrade(self.source,dry_run=True,compose_dir=self.source)
        self.assertEqual(list(self.home.iterdir()),[])
        self.assertFalse(any('build' in c or 'up' in c or c[0]=='cp' for c in self.calls))
    def test_missing_knowledge_is_recovered_before_recreation(self):
        self.saved_path=None;self.container['Mounts'][1]['Source']=str(Path(self.temp.name)/'missing knowledge')
        with patch.object(repair,'docker',side_effect=self.docker),patch.object(repair,'verify_server'),contextlib.redirect_stdout(io.StringIO()):repair.upgrade(self.source,compose_dir=self.source)
        config=json.loads(self.saved_path.read_text());folder=Path(next(m['source'] for m in config['services']['app']['volumes'] if m['target']=='/app/knowledge'))
        self.assertEqual((folder/'custom.md').read_text(),'Custom knowledge retained')
        self.assertEqual((folder/'accounts.md').read_text(),'English policy')
        self.assertLess(next(i for i,c in enumerate(self.calls) if c[0]=='cp'),next(i for i,c in enumerate(self.calls) if 'up' in c))
    def test_unpersisted_database_stops_before_recovery_files(self):
        self.container['Mounts']=[]
        with self.assertRaisesRegex(repair.UpgradeError,'no persistent mount'):self.plan()
        self.assertEqual(list(self.home.iterdir()),[])
    def test_code_bind_stops_before_recovery_files(self):
        self.container['Mounts'].append({'Type':'bind','Destination':'/app/static','Source':str(self.target/'static')})
        with self.assertRaisesRegex(repair.UpgradeError,'source-code bind'):self.plan()
        self.assertEqual(list(self.home.iterdir()),[])
    def test_saved_configuration_with_changed_database_stops_before_build(self):
        plan=self.plan()
        original=self.docker
        def changed(args,capture=True,port=None):
            value=original(args,capture,port)
            if 'config' in args and 'compose.json' in ' '.join(args):
                config=json.loads(value)
                for v in config['volumes'].values():
                    if v.get('external') and v.get('name')=='nonstandard_existing_database':v['name']='wrong_database'
                return json.dumps(config)
            return value
        with patch.object(repair,'docker',side_effect=changed),self.assertRaisesRegex(repair.UpgradeError,'does not retain the database'):
            repair.prepare_relocation(plan,8010)
        self.assertFalse(any('build' in c or 'up' in c for c in self.calls))


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(RecoveryTests(name) for name in vars(RecoveryTests) if name.startswith("test_"))
