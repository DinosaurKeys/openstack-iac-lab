"""Check preview-only execution and role conditions without contacting lab nodes."""
import json
import os
import pty
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml
from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
TOOL = r'''
import json,os,sys
from pathlib import Path
import yaml
name=Path(sys.argv[0]).name
args=sys.argv[1:]
with Path(os.environ['LAB_PREVIEW_AUDIT']).open('a') as f: f.write(json.dumps([name,*args])+'\n')
failure=os.environ.get('LAB_PREVIEW_FAILURE','')
if name=='hostname': print(os.environ.get('LAB_PREVIEW_CLIENT','hermes'))
elif name=='id': print('joe')
elif name=='ansible-inventory':
    source=yaml.safe_load(Path(args[args.index('-i')+1]).read_text())
    nodes=source['all']['children']['lab_nodes']['hosts']
    hosts={node:{'ansible_host':v['ansible_host'],'ansible_user':'joe',
                'ansible_ssh_private_key_file':os.environ['LAB_PREVIEW_KEY']} for node,v in nodes.items()}
    if failure=='address': hosts['node2']['ansible_host']='192.168.0.99'
    if failure=='key': hosts['node1']['ansible_ssh_private_key_file']='/wrong/key'
    print(json.dumps({'lab_nodes':{'hosts':list(hosts)},'_meta':{'hostvars':hosts}}))
elif name=='ansible-playbook':
    node=args[args.index('--limit')+1]
    assert '--check' in args and '--diff' in args
    assert '--ask-become-pass' in args and '--become' in args
    assert args[args.index('--become-user')+1]=='root'
    extra=json.loads(args[args.index('-e')+1])
    assert extra['ansible_become'] is True and extra['ansible_become_user']=='root'
    assert extra['ansible_become_method']=='sudo'
    for option in ['BatchMode=yes','StrictHostKeyChecking=yes','PasswordAuthentication=no','ForwardAgent=no']:
        assert option in extra['ansible_ssh_common_args']
    assert os.environ['ANSIBLE_ASK_PASS']=='False'
    play=yaml.safe_load(Path(args[2]).read_text())[0]
    assert play['hosts']=='lab_nodes' and play['roles']==['common']
    marker=next(t for t in play['post_tasks'] if 'ansible.builtin.debug' in t)
    assert marker['when']=='ansible_check_mode'
    assert 'COMMON_PREVIEW_OK:' in marker['ansible.builtin.debug']['msg']
    if failure=='cancel' and node=='node1': sys.exit(99)
    if failure=='sudo' and node=='node2': print('Fixture: Incorrect sudo password'); sys.exit(2)
    if failure=='marker' and node=='node2': print('Fixture: no matching hosts'); sys.exit(0)
    print('Fixture proposed changes: '+node)
    print('COMMON_PREVIEW_OK: '+node+'; predictions only; service startup still requires a real run.')
else: raise AssertionError(name)
'''


class CommonPreviewTests(unittest.TestCase):
    def run_case(self, failure='', args=('joe', '--node', 'all'), client='hermes', terminal=True):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work/'scripts').mkdir()
            (work/'bin').mkdir()
            for path in ['ansible.cfg', 'ansible/inventory/hosts.yml', 'ansible/playbooks/base.yml']:
                target = work/path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text((ROOT/path).read_text())
            venv = work/'venv'
            (venv/'bin').mkdir(parents=True)
            key = work/'fixture-private-key'
            key.write_text('FIXTURE_PRIVATE_NOT_FOR_REPORTS')
            source = (ROOT/'scripts/preview-common.sh').read_text()
            source = source.replace('venv_dir="$HOME/venvs/kolla-iac"', 'venv_dir="'+str(venv)+'"')
            source = source.replace('key="$HOME/.ssh/openstack-iac-lab-ansible"', 'key="'+str(key)+'"')
            script = work/'scripts/preview-common.sh'
            script.write_text(source)
            (venv/'bin/python').symlink_to(sys.executable)
            for name in ['hostname', 'id', 'ansible-inventory', 'ansible-playbook']:
                path = (work/'bin' if name in ['hostname', 'id'] else venv/'bin')/name
                path.write_text(f'#!{sys.executable}\n'+TOOL)
                path.chmod(0o755)
            audit = work/'audit.jsonl'
            env = {**os.environ, 'PATH':str(work/'bin')+':/usr/bin:/bin', 'LAB_PREVIEW_AUDIT':str(audit),
                   'LAB_PREVIEW_KEY':str(key), 'LAB_PREVIEW_CLIENT':client, 'LAB_PREVIEW_FAILURE':failure}
            master, slave = pty.openpty()
            try:
                result = subprocess.run(['bash', str(script), *args],
                                        stdin=slave if terminal else subprocess.DEVNULL,
                                        capture_output=True, text=True, env=env, timeout=20)
            finally:
                os.close(master)
                os.close(slave)
            summary = work/'build/common-preview-summary.txt'
            text = summary.read_text() if summary.exists() else ''
            if summary.exists():
                report = work/'build/common-preview-report.txt'
                self.assertEqual(summary.stat().st_mode & 0o777, 0o600)
                self.assertEqual(report.stat().st_mode & 0o777, 0o600)
                self.assertNotIn('FIXTURE_PRIVATE_NOT_FOR_REPORTS', report.read_text())
                history = next(p for p in report.parent.glob('common-preview-*') if p.is_dir())
                self.assertEqual(history.stat().st_mode & 0o777, 0o700)
                for node_log in history.glob('node*.txt'):
                    self.assertEqual(node_log.stat().st_mode & 0o777, 0o600)
            calls = [json.loads(line) for line in audit.read_text().splitlines()] if audit.exists() else []
            return result, text, [c for c in calls if c[0]=='ansible-playbook']

    def test_all_nodes_are_previewed_separately_with_check_and_diff(self):
        result, summary, calls = self.run_case()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertEqual([c[c.index('--limit')+1] for c in calls], ['node1', 'node2', 'node3'])
        self.assertIn('RESULT: COMMON_PREVIEW_OK for all', summary)

    def test_single_node_selection(self):
        result, summary, calls = self.run_case(args=('joe', '--node', 'node3'))
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertEqual([c[c.index('--limit')+1] for c in calls], ['node3'])
        self.assertIn('COMMON_PREVIEW_OK for node3', summary)

    def test_sudo_failure_records_review_and_continues_read_only_checks(self):
        result, summary, calls = self.run_case(failure='sudo')
        self.assertEqual(result.returncode, 1)
        self.assertIn('node2: FAILED; ansible_exit=2; log_exit=0', summary)
        self.assertIn('node3: PREVIEWED', summary)
        self.assertNotIn('RESULT: COMMON_PREVIEW_OK', summary)

    def test_cancellation_stops_later_nodes(self):
        result, summary, calls = self.run_case(failure='cancel')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(calls), 1)
        self.assertIn('STOP: Cancelled', summary)

    def test_zero_exit_without_role_completion_is_not_success(self):
        result, summary, calls = self.run_case(failure='marker')
        self.assertEqual(result.returncode, 1)
        self.assertIn('node2: REVIEW; playbook completion marker missing', summary)
        self.assertIn('node3: PREVIEWED', summary)

    def test_inventory_mismatch_prevents_node_previews(self):
        for failure in ['address', 'key']:
            with self.subTest(failure=failure):
                result, summary, calls = self.run_case(failure=failure)
                self.assertEqual(result.returncode, 1)
                self.assertFalse(calls)
                self.assertIn('no node preview was attempted', summary)

    def test_wrong_client_arguments_and_nonterminal_are_rejected(self):
        for options in [{'client':'node1'}, {'args':('joe', '--node', 'hermes')},
                        {'args':('joe', '--apply')}, {'terminal':False}]:
            with self.subTest(options=options):
                result, summary, calls = self.run_case(**options)
                self.assertEqual(result.returncode, 2)
                self.assertFalse(calls)

    def test_role_defers_only_the_missing_service_during_preview(self):
        tasks = yaml.safe_load((ROOT/'ansible/roles/common/tasks/main.yml').read_text())
        service = next(t for t in tasks if 'ansible.builtin.service' in t)
        deferred = next(t for t in tasks if 'ansible.builtin.debug' in t)
        env = Environment(undefined=StrictUndefined)
        for check_mode, services, should_check in [
            (True, {}, False),
            (True, {'chrony.service':{'status':'not-found'}}, False),
            (True, {'chrony.service':{'status':'disabled'}}, True),
            (True, {'chrony.service':{'status':'enabled'}}, True),
            (False, {}, True),
        ]:
            with self.subTest(check_mode=check_mode, services=services):
                values={'ansible_check_mode':check_mode, 'ansible_facts':{'services':services}}
                self.assertEqual(bool(env.compile_expression(service['when'])(**values)), should_check)
                self.assertEqual(bool(env.compile_expression(deferred['when'])(**values)),
                                 check_mode and not should_check)

    def test_role_cannot_override_check_mode_or_silently_install_apt_bindings(self):
        tasks = yaml.safe_load((ROOT/'ansible/roles/common/tasks/main.yml').read_text())
        apt = next(t['ansible.builtin.apt'] for t in tasks if 'ansible.builtin.apt' in t)
        self.assertIs(apt['auto_install_module_deps'], False)
        self.assertEqual(apt['state'], 'present')
        self.assertTrue(all('check_mode' not in t for t in tasks))
        self.assertTrue(all('ansible.builtin.command' not in t and 'ansible.builtin.shell' not in t for t in tasks))
        service = next(t['ansible.builtin.service'] for t in tasks if 'ansible.builtin.service' in t)
        self.assertEqual(service, {'name':'chrony', 'enabled':True, 'state':'started'})
