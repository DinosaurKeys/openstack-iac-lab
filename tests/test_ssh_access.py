"""Run the SSH setup wrapper with fake SSH/agent/Ansible commands only."""
import json
import os
import pty
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = r'''
import json, os, shlex, subprocess, sys
from pathlib import Path
name=Path(sys.argv[0]).name
args=sys.argv[1:]
with Path(os.environ['LAB_SSH_AUDIT']).open('a') as f: f.write(json.dumps([name,*args])+'\n')
failure=os.environ.get('LAB_SSH_FAILURE','')
if name=='hostname':
    print(os.environ.get('LAB_REMOTE_NODE',os.environ.get('LAB_CLIENT_HOST','hermes')))
elif name=='id': print('joe')
elif name=='ip':
    ip={'node1':'192.168.0.200','node2':'192.168.0.201','node3':'192.168.0.202'}[os.environ['LAB_REMOTE_NODE']]
    print('2: enp0s31f6 inet '+ip+'/24 brd 192.168.0.255 scope global enp0s31f6')
elif name=='ssh-add':
    if args[0]=='-l': sys.exit(2 if failure=='agent' else 1)
    if args[0]=='-t' and failure in ['unlock','unlock-agent']:
        if failure=='unlock-agent': print('Fixture: agent became unavailable during load',file=sys.stderr)
        sys.exit(2 if failure=='unlock-agent' else 1)
    if args[0]=='-T' and failure=='key': sys.exit(1)
elif name=='tee':
    data=sys.stdin.buffer.read()
    if failure=='log' and not data:
        print('Fixture: log sink failed',file=sys.stderr)
        sys.exit(9)
    sys.exit(subprocess.run(['/usr/bin/tee',*args],input=data).returncode)
elif name=='ssh-keygen':
    if '-f' in args and '-t' in args:
        key=Path(args[args.index('-f')+1])
        assert not key.exists() and not key.with_suffix('.pub').exists()
        key.write_text('FIXTURE_PRIVATE_DO_NOT_LOG')
        Path(str(key)+'.pub').write_text('ssh-ed25519 AAAATEST fixture\n')
    else: print('256 SHA256:fixture fixture (ED25519)')
elif name=='ssh-copy-id':
    assert args[args.index('-i')+1].endswith('.pub')
    assert 'StrictHostKeyChecking=yes' in args
    if failure=='copy' and args[-1]=='joe@192.168.0.201': sys.exit(1)
    print('Fixture public key installed')
elif name=='ssh':
    assert args[:2]==['-F','/dev/null']
    for option in ['BatchMode=yes','IdentitiesOnly=yes','StrictHostKeyChecking=yes',
                   'PasswordAuthentication=no','KbdInteractiveAuthentication=no','ControlPath=none','ForwardAgent=no']:
        assert option in args,option
    parts=shlex.split(args[-1])
    assert parts[:2]==['bash','-c']
    node=parts[4]
    assert args[-2]=='joe@'+{'node1':'192.168.0.200','node2':'192.168.0.201','node3':'192.168.0.202'}[node]
    env={**os.environ,'LAB_REMOTE_NODE':('wrong-node' if failure=='host' and node=='node1' else node)}
    sys.exit(subprocess.run(parts,env=env).returncode)
elif name=='ansible':
    data=json.loads(Path(args[args.index('-i')+1]).read_text())
    variables=data['all']['vars']
    assert variables['ansible_become'] is False
    assert variables['ansible_user']=='joe'
    assert variables['ansible_ssh_private_key_file']==os.environ['LAB_SSH_KEY']
    assert 'BatchMode=yes' in variables['ansible_ssh_common_args']
    assert args[-2:]==['-m','ansible.builtin.ping']
    if failure=='ansible': sys.exit(4)
    for node,values in data['all']['children']['lab_nodes']['hosts'].items():
        assert values['ansible_host']=={'node1':'192.168.0.200','node2':'192.168.0.201','node3':'192.168.0.202'}[node]
        print(node+' | SUCCESS => {"ping": "pong"}')
else: raise AssertionError('Unexpected tool: '+name)
'''


class SSHAccessTests(unittest.TestCase):
    def run_case(self, failure='', args=('joe','--node','all','--apply'), key_state='existing', host='hermes'):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory)
            (work/'scripts').mkdir()
            (work/'bin').mkdir()
            venv=work/'venv'
            (venv/'bin').mkdir(parents=True)
            keys=work/'ssh'
            keys.mkdir()
            old_key=keys/'openstack-iac-lab'
            old_public=keys/'openstack-iac-lab.pub'
            old_key.write_text('FIXTURE_OLD_PRIVATE_DO_NOT_LOG')
            old_public.write_text('ssh-ed25519 AAAAOLD retained\n')
            original_pair={p:p.read_bytes() for p in [old_key,old_public]}
            key=keys/'openstack-iac-lab-ansible'
            if key_state!='absent':
                key.write_text('FIXTURE_PRIVATE_DO_NOT_LOG')
                if key_state!='incomplete':
                    Path(str(key)+'.pub').write_text('ssh-ed25519 AAAATEST fixture\n'+('ssh-ed25519 SECOND extra\n' if key_state=='multiple' else ''))
            source=(ROOT/'scripts/prepare-ssh.sh').read_text()
            # Redirect fixture locations only; do not alter HOME.
            source=source.replace('venv_dir="$HOME/venvs/kolla-iac"','venv_dir="'+str(venv)+'"')
            source=source.replace('key="$HOME/.ssh/openstack-iac-lab-ansible"','key="'+str(key)+'"')
            source=source.replace('"$HOME/.ssh"','"'+str(keys)+'"')
            (work/'scripts/prepare-ssh.sh').write_text(source)
            commands=['hostname','id','ip','ssh','ssh-copy-id','ssh-add','ssh-keygen']
            if failure=='log': commands.append('tee')
            for name in commands:
                path=work/'bin'/name
                path.write_text(f'#!{sys.executable}\n'+TOOL)
                path.chmod(0o755)
            path=venv/'bin/ansible'
            path.write_text(f'#!{sys.executable}\n'+TOOL)
            path.chmod(0o755)
            (venv/'bin/python').symlink_to(sys.executable)
            audit=work/'audit.txt'
            env={**os.environ,'PATH':str(work/'bin')+':/usr/bin:/bin','LAB_SSH_AUDIT':str(audit),
                 'LAB_SSH_FAILURE':failure,'LAB_SSH_KEY':str(key),'LAB_CLIENT_HOST':host}
            master,slave=pty.openpty()
            try:
                result=subprocess.run(['bash',str(work/'scripts/prepare-ssh.sh'),*args],stdin=slave,
                                      capture_output=True,text=True,env=env,timeout=20)
            finally:
                os.close(master)
                os.close(slave)
            summary=work/'build/ssh-access-summary.txt'
            report=work/'build/ssh-access-report.txt'
            text=summary.read_text() if summary.exists() else ''
            if summary.exists():
                self.assertEqual(summary.stat().st_mode&0o777,0o600)
                self.assertEqual(report.stat().st_mode&0o777,0o600)
                self.assertNotIn('FIXTURE_PRIVATE_DO_NOT_LOG',report.read_text())
                self.assertNotIn('FIXTURE_OLD_PRIVATE_DO_NOT_LOG',report.read_text())
                history=[p for p in report.parent.glob('ssh-access-*') if p.is_dir()]
                self.assertEqual(history[0].stat().st_mode&0o777,0o700)
            calls=[json.loads(row) for row in audit.read_text().splitlines()] if audit.exists() else []
            for path,original in original_pair.items():
                self.assertEqual(path.read_bytes(),original,'The forgotten key pair must remain intact')
            self.assertFalse(any(str(old_key) in call or str(old_public) in call for call in calls))
            return result,text,calls

    def test_all_nodes_public_only_and_key_verification(self):
        result,summary,calls=self.run_case()
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('RESULT: SSH_READY for all',summary)
        self.assertEqual([c[-1] for c in calls if c[0]=='ssh-copy-id'],['joe@192.168.0.200','joe@192.168.0.201','joe@192.168.0.202'])
        self.assertEqual(len([c for c in calls if c[0]=='ansible']),1)

    def test_verify_mode_never_creates_or_copies_key(self):
        result,summary,calls=self.run_case(args=('joe','--node','node2'))
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertFalse(any(c[0]=='ssh-copy-id' or (c[0]=='ssh-keygen' and '-t' in c) for c in calls))
        self.assertIn('SSH_READY for node2',summary)

    def test_missing_key_created_only_in_apply(self):
        result,summary,calls=self.run_case(key_state='absent')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(len([c for c in calls if c[0]=='ssh-keygen' and '-t' in c]),1)
        generation=next(c for c in calls if c[0]=='ssh-keygen' and '-t' in c)
        self.assertTrue(generation[generation.index('-f')+1].endswith('/openstack-iac-lab-ansible'))

    def test_missing_key_in_verify_mode_stops(self):
        result,summary,calls=self.run_case(key_state='absent',args=('joe',))
        self.assertEqual(result.returncode,1)
        self.assertIn('No dedicated key exists',summary)
        self.assertFalse(any(c[0]=='ssh-copy-id' for c in calls))

    def test_incomplete_pair_is_not_overwritten(self):
        result,summary,calls=self.run_case(key_state='incomplete')
        self.assertEqual(result.returncode,1)
        self.assertIn('incomplete',summary)
        self.assertFalse(any(c[0] in ['ssh-copy-id','ssh-keygen'] for c in calls))

    def test_multiple_public_keys_are_rejected(self):
        result,summary,calls=self.run_case(key_state='multiple')
        self.assertEqual(result.returncode,1)
        self.assertIn('exactly one',summary)
        self.assertFalse(any(c[0]=='ssh-copy-id' for c in calls))

    def test_no_agent_stops_before_key_actions(self):
        result,summary,calls=self.run_case(failure='agent')
        self.assertEqual(result.returncode,1)
        self.assertIn('No reachable ssh-agent',summary)
        self.assertFalse(any(c[0] in ['ssh-copy-id','ssh-keygen'] for c in calls))

    def test_agent_key_mismatch_stops(self):
        result,summary,calls=self.run_case(failure='key')
        self.assertEqual(result.returncode,1)
        self.assertFalse(any(c[0]=='ssh-copy-id' for c in calls))

    def test_silent_unlock_failure_records_status_before_any_node_action(self):
        result,summary,calls=self.run_case(failure='unlock',key_state='absent')
        self.assertEqual(result.returncode,1)
        self.assertIn('Create dedicated key: COMPLETED',summary)
        self.assertIn('Unlock key for four hours: STOPPED; command_exit=1; log_exit=0',summary)
        self.assertIn('No public-key installation was attempted',summary)
        self.assertNotIn('additions remain',summary)
        self.assertNotIn('RESULT: SSH_READY',summary)
        self.assertFalse(any(c[0] in ['ssh-copy-id','ssh','ansible'] or (c[0]=='ssh-add' and c[1]=='-T') for c in calls))

    def test_unlock_agent_failure_preserves_stderr_and_exit_code(self):
        result,summary,calls=self.run_case(failure='unlock-agent')
        self.assertEqual(result.returncode,1)
        self.assertIn('command_exit=2; log_exit=0',summary)
        self.assertIn('Fixture: agent became unavailable during load',result.stdout)
        self.assertFalse(any(c[0] in ['ssh-copy-id','ssh','ansible'] for c in calls))

    def test_log_failure_is_distinguished_from_successful_unlock(self):
        result,summary,calls=self.run_case(failure='log')
        self.assertEqual(result.returncode,1)
        self.assertIn('command_exit=0; log_exit=9',summary)
        self.assertNotIn('RESULT: SSH_READY',summary)
        self.assertFalse(any(c[0] in ['ssh-copy-id','ssh','ansible'] for c in calls))

    def test_node2_copy_failure_stops_before_node3(self):
        result,summary,calls=self.run_case(failure='copy')
        self.assertEqual(result.returncode,1)
        self.assertIn('node2 public-key installation failed',summary)
        self.assertIn('Any public-key additions remain',summary)
        self.assertFalse(any(c[0]=='ssh-copy-id' and c[-1].endswith('.202') for c in calls))

    def test_wrong_remote_hostname_stops(self):
        result,summary,calls=self.run_case(failure='host')
        self.assertEqual(result.returncode,1)
        self.assertIn('node1 fresh key login failed',summary)
        self.assertFalse(any(c[0]=='ansible' for c in calls))

    def test_ansible_failure_does_not_claim_ready(self):
        result,summary,calls=self.run_case(failure='ansible')
        self.assertEqual(result.returncode,1)
        self.assertIn('Ansible SSH/Python ping failed',summary)
        self.assertNotIn('RESULT: SSH_READY',summary)

    def test_wrong_local_host_rejected(self):
        result,summary,calls=self.run_case(host='node1')
        self.assertEqual(result.returncode,2)
        self.assertEqual(summary,'')

    def test_invalid_node_rejected(self):
        result,summary,calls=self.run_case(args=('joe','--node','hermes'))
        self.assertEqual(result.returncode,2)
        self.assertEqual(summary,'')

    def test_tracked_and_kolla_inventories_select_dedicated_key(self):
        import importlib.util
        import yaml
        common=yaml.safe_load((ROOT/'ansible/inventory/group_vars/all.yml').read_text())
        spec=importlib.util.spec_from_file_location('ssh_kolla_inventory',ROOT/'scripts/render-kolla-inventory.py')
        renderer=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(renderer)
        sample='\n'.join('['+name+']' for name in ['control','network','compute','storage','monitoring','deployment','glance','cinder-volume','cinder-backup','cinder-volume-lvm','tgtd'])
        kolla=renderer.render(sample)['all']['vars']
        for variables in [common,kolla]:
            self.assertEqual(variables['ansible_user'],'joe')
            self.assertEqual(variables['ansible_ssh_private_key_file'],'~/.ssh/openstack-iac-lab-ansible')
            self.assertIn('StrictHostKeyChecking=yes',variables['ansible_ssh_common_args'])


if __name__=='__main__':
    unittest.main()
