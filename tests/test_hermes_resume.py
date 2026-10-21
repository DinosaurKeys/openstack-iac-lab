"""Exercise resume control flow with fixture commands; no installer or SSH runs."""
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
FIXTURE_TOOL = r'''
import json, os, shutil, subprocess, sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
with Path(os.environ['LAB_HERMES_AUDIT']).open('a') as audit:
    audit.write(json.dumps([name, *args]) + '\n')
failure = os.environ.get('LAB_HERMES_FAIL', '')
if name == 'kolla-ansible':
    if failure == 'kolla': sys.exit(7)
    assert shutil.which('ansible-galaxy') == str(Path(sys.argv[0]).with_name('ansible-galaxy'))
    subprocess.run(['ansible-galaxy', 'fixture-kolla-deps'], check=True)
elif name == 'ansible-galaxy':
    if failure == 'project' and args[:2] == ['collection', 'install']: sys.exit(8)
    print('Fixture Ansible collections')
elif name == 'python':
    if args[:3] == ['-m', 'pip', 'check']:
        if failure == 'pip-check': sys.exit(9)
        print('No broken requirements found (fixture).')
    elif args[:3] == ['-m', 'pip', 'freeze']:
        print('fixture-package==1.0')
    else:
        assert args[-1] == 'doctor'
        print('terraform: ' + ('MISSING' if failure == 'doctor' else '/fixture/terraform'))
        sys.exit(1 if failure == 'doctor' else 0)
else:
    raise AssertionError('Unexpected fixture tool')
'''


class HermesResumeTests(unittest.TestCase):
    def run_case(self, failure='', args=('--resume-collections',), host='hermes', missing=None):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / 'scripts').mkdir()
            (work / 'ansible').mkdir()
            (work / 'ansible/requirements.yml').write_text('collections: []\n')
            shutil.copy2(ROOT / 'scripts/labctl.py', work / 'scripts/labctl.py')
            venv = work / 'fixture-venv'
            (venv / 'bin').mkdir(parents=True)
            # Fixture only: redirect the venv location without altering HOME.
            script = (ROOT / 'scripts/prepare-hermes.sh').read_text().replace(
                'venv_dir="$HOME/venvs/kolla-iac"', 'venv_dir="' + str(venv) + '"')
            (work / 'scripts/prepare-hermes.sh').write_text(script)
            bootstrap = work / 'scripts/bootstrap-hermes.sh'
            bootstrap.write_text('#!/usr/bin/env bash\nprintf "BOOTSTRAP\\n" >> "$LAB_HERMES_AUDIT"\n')
            for name in ['python', 'kolla-ansible', 'ansible-galaxy']:
                if name != missing:
                    target = venv / 'bin' / name
                    target.write_text(f'#!{sys.executable}\n' + FIXTURE_TOOL)
                    target.chmod(0o755)
            (work / 'bin').mkdir()
            hostname = work / 'bin/hostname'
            hostname.write_text('#!/usr/bin/env bash\nprintf "' + host + '\\n"\n')
            hostname.chmod(0o755)
            audit = work / 'audit.txt'
            env = {**os.environ, 'PATH': str(work / 'bin') + ':/usr/bin:/bin',
                   'LAB_HERMES_AUDIT': str(audit), 'LAB_HERMES_FAIL': failure}
            master, slave = pty.openpty()
            try:
                result = subprocess.run(['bash', str(work / 'scripts/prepare-hermes.sh'), *args],
                                        stdin=slave, capture_output=True, text=True, env=env, timeout=15)
            finally:
                os.close(master)
                os.close(slave)
            report = work / 'build/hermes-tools-report.txt'
            summary = work / 'build/hermes-tools-summary.txt'
            log = report.read_text() if report.exists() else ''
            short = summary.read_text() if summary.exists() else ''
            if report.exists():
                self.assertEqual(report.stat().st_mode & 0o777, 0o600)
                self.assertEqual(summary.stat().st_mode & 0o777, 0o600)
                histories = [p for p in report.parent.glob('hermes-tools-*') if p.is_dir()]
                self.assertEqual(len(histories), 1)
                self.assertEqual(histories[0].stat().st_mode & 0o777, 0o700)
            calls = audit.read_text().splitlines() if audit.exists() else []
            return result, log, short, calls

    def test_resume_uses_existing_tools_and_child_path(self):
        result, log, summary, calls = self.run_case()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('RESULT: TOOLS_FOUND', summary)
        self.assertIn('Kolla collections: COMPLETED', summary)
        self.assertNotIn('BOOTSTRAP', calls)
        commands = [json.loads(line) for line in calls]
        self.assertTrue(any(row[0] == 'ansible-galaxy' and row[1] == 'fixture-kolla-deps' for row in commands))
        self.assertFalse(any(row[1:4] == ['-m', 'pip', 'install'] for row in commands))

    def test_kolla_failure_stops_before_project_and_doctor(self):
        result, log, summary, calls = self.run_case(failure='kolla')
        self.assertEqual(result.returncode, 7)
        self.assertIn('Kolla collections: STOPPED', summary)
        self.assertEqual(len(calls), 1)

    def test_project_failure_stops_before_checks(self):
        result, log, summary, calls = self.run_case(failure='project')
        self.assertEqual(result.returncode, 8)
        self.assertIn('Project collections: STOPPED', summary)
        self.assertFalse(any(json.loads(row)[0] == 'python' for row in calls))

    def test_dependency_failure_stops_before_doctor(self):
        result, log, summary, calls = self.run_case(failure='pip-check')
        self.assertEqual(result.returncode, 9)
        self.assertIn('Python dependency check: STOPPED', summary)
        self.assertNotIn('Tool locations', log)

    def test_missing_terraform_remains_a_review(self):
        result, log, summary, calls = self.run_case(failure='doctor')
        self.assertEqual(result.returncode, 1)
        self.assertIn('terraform: MISSING', summary)
        self.assertIn('RESULT: REVIEW', summary)
        self.assertIn('Project collections: COMPLETED', summary)

    def test_missing_existing_executable_stops_without_install(self):
        result, log, summary, calls = self.run_case(missing='ansible-galaxy')
        self.assertEqual(result.returncode, 1)
        self.assertIn('expected executable missing', summary)
        self.assertEqual(calls, [])

    def test_wrong_host_rejected(self):
        result, log, summary, calls = self.run_case(host='node1')
        self.assertEqual(result.returncode, 2)
        self.assertEqual((log, summary, calls), ('', '', []))

    def test_invalid_mode_rejected(self):
        result, log, summary, calls = self.run_case(args=('--unknown',))
        self.assertEqual(result.returncode, 2)
        self.assertEqual((log, summary, calls), ('', '', []))

    def test_full_mode_retains_bootstrap(self):
        result, log, summary, calls = self.run_case(args=())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls[0], 'BOOTSTRAP')
        self.assertIn('Tool installation: COMPLETED', summary)


if __name__ == '__main__':
    unittest.main()
