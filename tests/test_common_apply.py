"""Exercise apply/verification failure boundaries with no real SSH, APT or services."""
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
from ansible.plugins.filter.core import FilterModule as CoreFilters
from ansible.plugins.filter.mathstuff import FilterModule as MathFilters
name=Path(sys.argv[0]).name
args=sys.argv[1:]
with Path(os.environ['LAB_APPLY_AUDIT']).open('a') as f: f.write(json.dumps([name,*args])+'\n')
failure=os.environ.get('LAB_APPLY_FAILURE','')
if name=='hostname': print(os.environ.get('LAB_APPLY_CLIENT','hermes'))
elif name=='id': print('joe')
elif name=='ansible-inventory':
    source=yaml.safe_load(Path(args[args.index('-i')+1]).read_text())
    nodes=source['all']['children']['lab_nodes']['hosts']
    hosts={n:{'ansible_host':v['ansible_host'],'ansible_user':'joe',
              'ansible_ssh_private_key_file':os.environ['LAB_APPLY_KEY']} for n,v in nodes.items()}
    if failure=='address': hosts['node2']['ansible_host']='192.168.0.99'
    if failure=='key': hosts['node1']['ansible_ssh_private_key_file']='/wrong/key'
    print(json.dumps({'lab_nodes':{'hosts':list(hosts)},'_meta':{'hostvars':hosts}}))
elif name=='ansible-playbook':
    node=args[args.index('--limit')+1]
    assert '--check' not in args and '--diff' in args
    assert '--ask-become-pass' in args and '--become' in args
    assert args[args.index('--become-user')+1]=='root'
    extra=json.loads(args[args.index('-e')+1])
    assert extra['ansible_become'] is True and extra['ansible_become_user']=='root'
    assert extra['ansible_become_method']=='sudo'
    for option in ['BatchMode=yes','StrictHostKeyChecking=yes','PasswordAuthentication=no','ForwardAgent=no']:
        assert option in extra['ansible_ssh_common_args']
    assert os.environ['ANSIBLE_ASK_PASS']=='False'
    path=Path(args[2])
    play=yaml.safe_load(path.read_text())[0]
    assert play['hosts']=='lab_nodes' and play['roles']==['common']
    include=next(t for t in play['post_tasks'] if 'ansible.builtin.include_tasks' in t)
    assert include['when']=='not ansible_check_mode'
    tasks=yaml.safe_load((path.parent/include['ansible.builtin.include_tasks']).read_text())
    assert 'COMMON_APPLIED_OK:' in tasks[-1]['ansible.builtin.debug']['msg']
    role=yaml.safe_load((path.parent.parent/'roles/common/tasks/main.yml').read_text())
    hosts_task=next(t for t in role if 'ansible.builtin.import_tasks' in t)
    hosts_tasks=yaml.safe_load((path.parent.parent/'roles/common/tasks'/hosts_task['ansible.builtin.import_tasks']).read_text())
    assert next(t['ansible.builtin.template']['backup'] for t in hosts_tasks if 'ansible.builtin.template' in t) is True
    if failure=='cancel' and node=='node1': sys.exit(99)
    if failure=='sudo' and node=='node2': print('Fixture: Incorrect sudo password'); sys.exit(2)
    if failure=='marker' and node=='node1': print('Fixture: no matching hosts'); sys.exit(0)
    settings=yaml.safe_load((path.parent.parent/'inventory/group_vars/all.yml').read_text())
    packages=settings['common_packages']
    address={'node1':'192.168.0.200','node2':'192.168.0.201','node3':'192.168.0.202'}[node]
    installed={p:[{'version':'fixture-1'}] for p in packages}
    service={'state':'running','status':'enabled'}
    if node=='node2' and failure=='package': installed.pop('chrony')
    if node=='node2' and failure=='service': service['state']='stopped'
    values={'common_packages':packages,'ansible_facts':{'packages':installed,'services':{'chrony.service':service}},
            'common_hostname':{'stdout':'wrong' if node=='node2' and failure=='hostname' else node},
            'inventory_hostname':node,'management_address':address+'/24',
            'common_addresses':{'stdout':json.dumps([{'addr_info':[{'local':'192.168.0.99' if node=='node2' and failure=='ip' else address,'prefixlen':24}]}])}}
    env=Environment(undefined=StrictUndefined)
    env.filters.update(CoreFilters().filters())
    env.filters.update(MathFilters().filters())
    assertions=[t['ansible.builtin.assert']['that'] for t in tasks if 'ansible.builtin.assert' in t]
    assert len(assertions)==3
    def require(checks,values):
        if not all(env.compile_expression(c)(**values) for c in checks):
            print('Fixture actual YAML verification rejected '+failure); sys.exit(2)
    require(assertions[0],values)
    hosts={'node1':{'ansible_host':'192.168.0.200'},'node2':{'ansible_host':'192.168.0.201'},'node3':{'ansible_host':'192.168.0.202'}}
    for target,host in hosts.items():
        records={host['ansible_host']:[]}
        if failure=='resolution' and node=='node2' and target=='node2': records['127.0.1.1']=[]
        require(assertions[1],{'item':{'item':target,'ansible_facts':{'getent_ahostsv4':records}},'hostvars':hosts})
    require(assertions[2],{'common_waitsync':{'rc':1 if failure=='sync' and node=='node2' else 0},
                           'common_tracking':{'rc':0},'common_sources':{'rc':0}})
    wait=next(t for t in tasks if t.get('register')=='common_waitsync')
    assert wait['ansible.builtin.command']['argv']==['chronyc','waitsync','12','0','0','2']
    assert wait['failed_when'] is False and wait['changed_when'] is False
    print('COMMON_APPLIED_OK: '+node+'; fixture verification only.')
else: raise AssertionError(name)
'''


class CommonApplyTests(unittest.TestCase):
    def run_case(self, failure='', args=('joe','--node','all','--apply'), client='hermes', terminal=True):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory)
            (work/'scripts').mkdir()
            (work/'bin').mkdir()
            for path in ['ansible.cfg','ansible/inventory/hosts.yml','ansible/inventory/group_vars/all.yml',
                         'ansible/playbooks/base.yml','ansible/tasks/verify-common.yml',
                         'ansible/roles/common/tasks/main.yml','ansible/roles/common/tasks/hosts.yml']:
                target=work/path
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_text((ROOT/path).read_text())
            venv=work/'venv'
            (venv/'bin').mkdir(parents=True)
            key=work/'fixture-private-key'
            key.write_text('FIXTURE_PRIVATE_NOT_FOR_REPORTS')
            source=(ROOT/'scripts/apply-common.sh').read_text()
            source=source.replace('venv_dir="$HOME/venvs/kolla-iac"','venv_dir="'+str(venv)+'"')
            source=source.replace('key="$HOME/.ssh/openstack-iac-lab-ansible"','key="'+str(key)+'"')
            script=work/'scripts/apply-common.sh'
            script.write_text(source)
            (venv/'bin/python').symlink_to(sys.executable)
            for name in ['hostname','id','ansible-inventory','ansible-playbook']:
                path=(work/'bin' if name in ['hostname','id'] else venv/'bin')/name
                path.write_text(f'#!{sys.executable}\n'+TOOL)
                path.chmod(0o755)
            audit=work/'audit.jsonl'
            env={**os.environ,'PATH':str(work/'bin')+':/usr/bin:/bin','LAB_APPLY_AUDIT':str(audit),
                 'LAB_APPLY_KEY':str(key),'LAB_APPLY_CLIENT':client,'LAB_APPLY_FAILURE':failure}
            master,slave=pty.openpty()
            try:
                result=subprocess.run(['bash',str(script),*args],stdin=slave if terminal else subprocess.DEVNULL,
                                      capture_output=True,text=True,env=env,timeout=20)
            finally:
                os.close(master)
                os.close(slave)
            summary=work/'build/common-apply-summary.txt'
            text=summary.read_text() if summary.exists() else ''
            if summary.exists():
                report=work/'build/common-apply-report.txt'
                self.assertEqual(summary.stat().st_mode&0o777,0o600)
                self.assertEqual(report.stat().st_mode&0o777,0o600)
                self.assertNotIn('FIXTURE_PRIVATE_NOT_FOR_REPORTS',report.read_text())
                history=next(p for p in report.parent.glob('common-apply-*') if p.is_dir())
                self.assertEqual(history.stat().st_mode&0o777,0o700)
                for log in history.glob('node*.txt'):
                    self.assertEqual(log.stat().st_mode&0o777,0o600)
            calls=[json.loads(l) for l in audit.read_text().splitlines()] if audit.exists() else []
            return result,text,[c for c in calls if c[0]=='ansible-playbook']

    def test_all_nodes_apply_and_require_actual_yaml_verification(self):
        result,summary,calls=self.run_case()
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual([c[c.index('--limit')+1] for c in calls],['node1','node2','node3'])
        self.assertIn('RESULT: COMMON_APPLIED_OK for all',summary)

    def test_single_node_selection(self):
        result,summary,calls=self.run_case(args=('joe','--node','node2','--apply'))
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual([c[c.index('--limit')+1] for c in calls],['node2'])

    def test_explicit_apply_flag_is_required(self):
        result,summary,calls=self.run_case(args=('joe','--node','all'))
        self.assertEqual(result.returncode,2)
        self.assertFalse(calls)

    def test_sudo_failure_stops_later_nodes_and_keeps_earlier_result(self):
        result,summary,calls=self.run_case(failure='sudo')
        self.assertEqual(result.returncode,1)
        self.assertIn('node1: APPLIED_AND_VERIFIED',summary)
        self.assertIn('node2: FAILED; ansible_exit=2; log_exit=0',summary)
        self.assertEqual(len(calls),2)
        self.assertNotIn('RESULT: COMMON_APPLIED_OK',summary)

    def test_zero_exit_without_completion_marker_cannot_claim_success(self):
        result,summary,calls=self.run_case(failure='marker')
        self.assertEqual(result.returncode,1)
        self.assertEqual(len(calls),1)
        self.assertIn('completion marker missing',summary)

    def test_cancel_stops_later_nodes(self):
        result,summary,calls=self.run_case(failure='cancel')
        self.assertEqual(result.returncode,1)
        self.assertEqual(len(calls),1)
        self.assertIn('completed changes remain',summary)

    def test_inventory_mismatch_prevents_node_applies(self):
        for failure in ['address','key']:
            with self.subTest(failure=failure):
                result,summary,calls=self.run_case(failure=failure)
                self.assertEqual(result.returncode,1)
                self.assertFalse(calls)
                self.assertIn('no node apply was attempted',summary)

    def test_bad_actual_state_or_unsynchronized_clock_stops_at_failed_node(self):
        for failure in ['package','hostname','ip','service','resolution','sync']:
            with self.subTest(failure=failure):
                result,summary,calls=self.run_case(failure=failure)
                self.assertEqual(result.returncode,1,result.stdout+result.stderr)
                self.assertEqual(len(calls),2)
                self.assertIn('node2: FAILED',summary)
                self.assertNotIn('RESULT: COMMON_APPLIED_OK',summary)

    def test_invalid_client_arguments_or_nonterminal_prevent_node_applies(self):
        for options in [{'client':'node1'},{'args':('joe','--node','hermes','--apply')},
                        {'args':('joe','--apply','--check')},{'terminal':False}]:
            with self.subTest(options=options):
                result,summary,calls=self.run_case(**options)
                self.assertEqual(result.returncode,2)
                self.assertFalse(calls)
