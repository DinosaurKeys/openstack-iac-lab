"""Check hosts normalization and the real Ansible tasks against temporary files only."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT/'ansible/roles/common'
SPEC = importlib.util.spec_from_file_location('lab_hosts_fixture', ROLE/'filter_plugins/lab_hosts.py')
HOSTS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HOSTS)
render = HOSTS.lab_hosts_render
BLOCK = '\n'.join([HOSTS.BEGIN, '192.168.0.200 node1', '192.168.0.201 node2',
                   '192.168.0.202 node3', HOSTS.END])+'\n'


class CommonHostsTests(unittest.TestCase):
    def test_reported_duplicate_is_repaired_without_a_second_managed_block(self):
        original='127.0.0.1 localhost\n127.0.1.1 node1\n::1 localhost ip6-localhost\n'+BLOCK
        result=render(original, 'node1')
        self.assertNotIn('127.0.1.1 node1', result)
        self.assertIn('127.0.0.1 localhost\n', result)
        self.assertIn('::1 localhost ip6-localhost\n', result)
        self.assertEqual(result.count(HOSTS.BEGIN), 1)
        self.assertIn(BLOCK, result)
        self.assertEqual(render(result, 'node1'), result)

    def test_each_selected_node_retires_only_its_own_loopback_alias(self):
        for node in HOSTS.LAB_HOSTS:
            with self.subTest(node=node):
                original='127.0.1.1 node1 node2 node3\n'
                result=render(original, node)
                aliases=result.splitlines()[0].split()[1:]
                self.assertEqual(aliases, [n for n in HOSTS.LAB_HOSTS if n!=node])
                self.assertIn(BLOCK, result)

    def test_extra_aliases_fqdn_and_comment_survive(self):
        original='127.0.1.1  node1 node1.lab helper # keep this comment\n'
        result=render(original, 'node1')
        self.assertIn('127.0.1.1\tnode1.lab helper # keep this comment\n', result)
        self.assertEqual(render(result, 'node1'), result)

    def test_repeated_and_case_variant_aliases_are_removed(self):
        result=render('127.0.1.1 NODE1 node1 node10\n127.0.1.1 node1 # explanation\n', 'node1')
        self.assertIn('127.0.1.1\tnode10\n', result)
        self.assertIn('# explanation\n', result)
        self.assertEqual(render(result, 'node1'), result)

    def test_unrelated_records_and_literal_template_text_are_preserved(self):
        untouched='# {{ this_is_a_literal_comment }}\n127.0.0.1 localhost node1\n::1 localhost\n10.0.0.9 backup node1.lab\n'
        result=render(untouched, 'node1')
        self.assertTrue(result.startswith(untouched))
        self.assertEqual(render(result, 'node1'), result)

    def test_existing_owned_block_is_updated_in_place(self):
        original='# before\n'+HOSTS.BEGIN+'\n192.168.0.99 node1\n'+HOSTS.END+'\n# after\n'
        result=render(original, 'node1')
        self.assertEqual(result, '# before\n'+BLOCK+'# after\n')

    def test_missing_final_newline_and_crlf_are_repeatable(self):
        for original in ['127.0.0.1 localhost', '127.0.0.1 localhost\r\n127.0.1.1 node1\r\n']:
            with self.subTest(original=original):
                result=render(original, 'node1')
                self.assertEqual(render(result, 'node1'), result)
                self.assertEqual(result.count(HOSTS.BEGIN), 1)

    def test_ambiguous_markers_and_unknown_hostnames_are_rejected(self):
        for content in [HOSTS.BEGIN+'\n', HOSTS.END+'\n', BLOCK+BLOCK,
                        HOSTS.END+'\n'+HOSTS.BEGIN+'\n']:
            with self.subTest(content=content):
                with self.assertRaises(ValueError): render(content, 'node1')
        with self.assertRaises(ValueError): render('127.0.1.1 hermes\n', 'hermes')

    def test_native_ansible_preview_apply_backup_permissions_and_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            work=Path(directory)
            role=work/'roles/common'
            for folder in ['tasks', 'templates', 'filter_plugins']:
                (role/folder).mkdir(parents=True)
            hosts=work/'fixture-hosts'
            original='# {{ keep_literal }}\n127.0.0.1 localhost\n127.0.1.1 node1\n::1 localhost ip6-localhost\n'+BLOCK
            hosts.write_text(original)
            hosts.chmod(0o640)
            tasks=(ROLE/'tasks/hosts.yml').read_text().replace('/etc/hosts', str(hosts))
            self.assertNotIn('/etc/hosts', tasks)
            (role/'tasks/hosts.yml').write_text(tasks)
            shutil.copyfile(ROLE/'templates/hosts.j2', role/'templates/hosts.j2')
            shutil.copyfile(ROLE/'filter_plugins/lab_hosts.py', role/'filter_plugins/lab_hosts.py')
            inventory=work/'inventory.yml'
            inventory.write_text(yaml.safe_dump({'all':{'hosts':{'node1':{
                'ansible_connection':'local','ansible_become':False,
                'ansible_python_interpreter':sys.executable}}}}))
            play=work/'play.yml'
            play.write_text(yaml.safe_dump([{'name':'Hosts fixture; temporary file only','hosts':'node1',
                'gather_facts':False,'become':False,'tasks':[
                    {'ansible.builtin.include_role':{'name':str(role),'tasks_from':'hosts'}},
                    {'ansible.builtin.debug':{'var':'common_hosts_update'}}]}],sort_keys=False))
            env={**os.environ,'ANSIBLE_NOCOLOR':'1','ANSIBLE_FORCE_COLOR':'0'}
            def run(check=False):
                args=[sys.executable,'-c','from ansible.cli.playbook import main; main()',
                      '-i',str(inventory),str(play),'-e','{"ansible_become":false}']
                if check: args+=['--check','--diff']
                result=subprocess.run(args,capture_output=True,text=True,env=env,timeout=30)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                return result.stdout
            preview=run(check=True)
            self.assertEqual(hosts.read_text(),original)
            self.assertEqual(hosts.stat().st_mode & 0o777,0o640)
            self.assertIn('changed=1',preview)
            self.assertFalse(list(work.glob('fixture-hosts.*~')))
            applied=run()
            expected=render(original,'node1')
            self.assertEqual(hosts.read_text(),expected)
            self.assertEqual(hosts.stat().st_mode & 0o777,0o640)
            backups=list(work.glob('fixture-hosts.*~'))
            self.assertEqual(len(backups),1,applied)
            self.assertEqual(backups[0].read_text(),original)
            repeated=run()
            self.assertIn('changed=0',repeated)
            self.assertEqual(hosts.read_text(),expected)
            self.assertEqual(list(work.glob('fixture-hosts.*~')),backups)
