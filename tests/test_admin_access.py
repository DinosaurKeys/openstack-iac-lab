"""Exercise the admin-check wrapper with fixture Ansible commands, never sudo/SSH."""
import json
import os
import pty
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = r'''
import json,os,sys
from pathlib import Path
import yaml
from jinja2 import Environment,StrictUndefined
name=Path(sys.argv[0]).name
args=sys.argv[1:]
with Path(os.environ['LAB_ADMIN_AUDIT']).open('a') as f: f.write(json.dumps([name,*args])+'\n')
failure=os.environ.get('LAB_ADMIN_FAILURE','')
if name=='hostname': print(os.environ.get('LAB_ADMIN_CLIENT','hermes'))
elif name=='id': print('joe')
elif name=='ansible-inventory':
    source=yaml.safe_load(Path(args[args.index('-i')+1]).read_text())
    nodes=source['all']['children']['lab_nodes']['hosts']
    hosts={node:{'ansible_host':v['ansible_host'],'ansible_user':'joe',
                'ansible_ssh_private_key_file':os.environ['LAB_ADMIN_KEY']} for node,v in nodes.items()}
    if failure=='address': hosts['node3']['ansible_host']='192.168.0.99'
    if failure=='key': hosts['node1']['ansible_ssh_private_key_file']='/wrong/key'
    print(json.dumps({'lab_nodes':{'hosts':list(hosts)},'_meta':{'hostvars':hosts}}))
elif name=='ansible-playbook':
    node=args[args.index('--limit')+1]
    assert '--ask-become-pass' in args and '--become' in args
    assert args[args.index('--become-user')+1]=='root'
    extra=json.loads(args[args.index('-e')+1])
    assert extra['ansible_become'] is True and extra['ansible_become_user']=='root'
    assert extra['ansible_become_method']=='sudo'
    assert 'BatchMode=yes' in extra['ansible_ssh_common_args']
    assert 'PasswordAuthentication=no' in extra['ansible_ssh_common_args']
    assert 'StrictHostKeyChecking=yes' in extra['ansible_ssh_common_args']
    assert os.environ['ANSIBLE_ASK_PASS']=='False'
    play=yaml.safe_load(Path(args[2]).read_text())[0]
    assert play['hosts']=='lab_nodes' and play['become'] is True and play['become_user']=='root'
    assert play['become_method']=='sudo'
    assert play['gather_facts'] is False
    commands=[t for t in play['tasks'] if 'ansible.builtin.command' in t]
    assert [t['ansible.builtin.command'] for t in commands]==['id -u','hostname -s']
    assert all(t['changed_when'] is False for t in commands)
    if failure=='cancel' and node=='node1': sys.exit(99)
    if failure=='auth' and node=='node1': print('Fixture SSH unavailable'); sys.exit(4)
    values={'admin_uid':{'stdout':'1000' if failure=='uid' and node=='node2' else '0'},
            'admin_hostname':{'stdout':'wrong' if failure=='hostname' and node=='node1' else node},
            'inventory_hostname':node}
    checks=next(t['ansible.builtin.assert']['that'] for t in play['tasks'] if 'ansible.builtin.assert' in t)
    env=Environment(undefined=StrictUndefined)
    if not all(env.compile_expression(check)(**values) for check in checks):
        print('Fixture identity assertion failed'); sys.exit(2)
    print('ADMIN_OK: '+node+'; effective UID 0 (root)')
else: raise AssertionError(name)
'''


class AdminAccessTests(unittest.TestCase):
    def run_case(self, failure='', args=('joe','--node','all'), client='hermes'):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory)
            (work/'scripts').mkdir()
            (work/'bin').mkdir()
            (work/'ansible/inventory').mkdir(parents=True)
            (work/'ansible/playbooks').mkdir()
            for path in ['ansible.cfg','ansible/inventory/hosts.yml','ansible/playbooks/check-admin.yml']:
                (work/path).write_text((ROOT/path).read_text())
            venv=work/'venv'
            (venv/'bin').mkdir(parents=True)
            key=work/'fixture-private-key'
            key.write_text('FIXTURE_PRIVATE_NOT_FOR_REPORTS')
            source=(ROOT/'scripts/check-admin.sh').read_text()
            source=source.replace('venv_dir="$HOME/venvs/kolla-iac"','venv_dir="'+str(venv)+'"')
            source=source.replace('key="$HOME/.ssh/openstack-iac-lab-ansible"','key="'+str(key)+'"')
            script=work/'scripts/check-admin.sh'
            script.write_text(source)
            (venv/'bin/python').symlink_to(sys.executable)
            for name in ['hostname','id','ansible-inventory','ansible-playbook']:
                path=(work/'bin' if name in ['hostname','id'] else venv/'bin')/name
                path.write_text(f'#!{sys.executable}\n'+TOOL)
                path.chmod(0o755)
            audit=work/'audit.jsonl'
            env={**os.environ,'PATH':str(work/'bin')+':/usr/bin:/bin','LAB_ADMIN_AUDIT':str(audit),
                 'LAB_ADMIN_KEY':str(key),'LAB_ADMIN_CLIENT':client,'LAB_ADMIN_FAILURE':failure}
            master,slave=pty.openpty()
            try:
                result=subprocess.run(['bash',str(script),*args],stdin=slave,capture_output=True,
                                      text=True,env=env,timeout=20)
            finally:
                os.close(master)
                os.close(slave)
            summary=work/'build/admin-access-summary.txt'
            text=summary.read_text() if summary.exists() else ''
            if summary.exists():
                report=work/'build/admin-access-report.txt'
                self.assertEqual(summary.stat().st_mode&0o777,0o600)
                self.assertEqual(report.stat().st_mode&0o777,0o600)
                self.assertNotIn('FIXTURE_PRIVATE_NOT_FOR_REPORTS',report.read_text())
                history=next(p for p in report.parent.glob('admin-access-*') if p.is_dir())
                self.assertEqual(history.stat().st_mode&0o777,0o700)
            calls=[json.loads(line) for line in audit.read_text().splitlines()] if audit.exists() else []
            return result,text,[c for c in calls if c[0]=='ansible-playbook']

    def test_all_nodes_use_sudo_separately_and_pass(self):
        result,summary,calls=self.run_case()
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual([c[c.index('--limit')+1] for c in calls],['node1','node2','node3'])
        self.assertIn('RESULT: ADMIN_ACCESS_OK for all',summary)

    def test_single_node_selection(self):
        result,summary,calls=self.run_case(args=('joe','--node','node2'))
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][calls[0].index('--limit')+1],'node2')

    def test_non_root_result_fails_but_later_node_is_observed(self):
        result,summary,calls=self.run_case(failure='uid')
        self.assertEqual(result.returncode,1)
        self.assertIn('node2: FAILED',summary)
        self.assertIn('node3: PASSED',summary)
        self.assertNotIn('RESULT: ADMIN_ACCESS_OK',summary)

    def test_wrong_hostname_fails(self):
        result,summary,calls=self.run_case(failure='hostname')
        self.assertEqual(result.returncode,1)
        self.assertIn('node1: FAILED',summary)
        self.assertEqual(len(calls),3)

    def test_ssh_failure_is_not_admin_success(self):
        result,summary,calls=self.run_case(failure='auth')
        self.assertEqual(result.returncode,1)
        self.assertIn('node1: FAILED; ansible_exit=4',summary)
        self.assertIn('node3: PASSED',summary)

    def test_cancel_stops_later_nodes(self):
        result,summary,calls=self.run_case(failure='cancel')
        self.assertEqual(result.returncode,1)
        self.assertEqual(len(calls),1)
        self.assertIn('STOP: Cancelled',summary)

    def test_inventory_mismatch_prevents_node_commands(self):
        for failure in ['address','key']:
            with self.subTest(failure=failure):
                result,summary,calls=self.run_case(failure=failure)
                self.assertEqual(result.returncode,1)
                self.assertFalse(calls)
                self.assertIn('no node check was attempted',summary)

    def test_wrong_client_and_selector_are_rejected(self):
        for options in [{'client':'node1'},{'args':('joe','--node','hermes')}]:
            with self.subTest(options=options):
                result,summary,calls=self.run_case(**options)
                self.assertEqual(result.returncode,2)
                self.assertFalse(calls)
