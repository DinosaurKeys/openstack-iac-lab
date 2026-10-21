"""Drive real terminal input through the SSH wrapper; every disk action is mocked."""
import json
import os
import pty
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPT = 'Response (full line; Enter or cancel to stop): '
TOKENS = ['ERASE node1 50026B7766070422', 'ERASE node2 4P3521354988', 'ERASE node3 50026B768317883A']

# This replacement SSH executes the actual quoted helper with fixture collectors
# and a command recorder. No SSH connection, sudo, device read or wipe is possible.
MOCK_SSH = r'''
import copy, json, os, shlex, sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, os.environ['LAB_RESET_TESTS'])
from test_ceph_reset import fixture
assert os.isatty(0), 'SSH lost terminal input'
parts = shlex.split(sys.argv[-1])
assert parts[:5] == ['sudo', '--', 'python3', '-u', '-c']
node = parts[parts.index('--node') + 1]
expected_ip = {'node1': '192.168.0.200', 'node2': '192.168.0.201', 'node3': '192.168.0.202'}[node]
assert sys.argv[-2] == expected_ip
ns = {'__name__': 'fixture_remote'}
exec(compile(parts[5], '<remote-helper>', 'exec'), ns)
state = fixture(node)
target = ns['TARGETS'][node]
state['tree'][0]['children'][0]['name'] = '/dev/' + target['vg'] + '/' + target['lv']
reads = 0
def collect(selected):
    global reads
    assert selected == node
    reads += 1
    result = copy.deepcopy(state)
    if reads >= 3:
        result['tree'][0].pop('children')
        result['tree'][0]['fstype'] = None
        result.update(pvs=[], lvs=[], signatures=[], holders={'/dev/test-sata': []}, dm_open={})
    return result
def record(command, check):
    assert check is True
    assert command in ns['commands'](node) + [['udevadm', 'settle', '--timeout=10']]
    with Path(os.environ['LAB_RESET_AUDIT']).open('a') as audit:
        audit.write(json.dumps({'node': node, 'command': command}) + '\n')
    return SimpleNamespace(returncode=0)
ns['collect'] = collect
ns['subprocess'] = SimpleNamespace(run=record)
try:
    ns['reset'](node, '--apply' in parts)
except (ValueError, EOFError) as exc:
    print('STOP: ' + str(exc), flush=True)
    sys.exit(1)
'''


class ResetTerminalTests(unittest.TestCase):
    def run_case(self, responses, apply=True):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / 'scripts').mkdir()
            for name in ['reset-ceph.sh', 'reset-ceph.py']:
                shutil.copy2(ROOT / 'scripts' / name, work / 'scripts' / name)
            (work / 'bin').mkdir()
            ssh = work / 'bin/ssh'
            ssh.write_text(f'#!{sys.executable}\n' + MOCK_SSH)
            ssh.chmod(0o755)
            audit = work / 'commands.jsonl'
            env = {
                **os.environ, 'PATH': str(work / 'bin') + os.pathsep + os.environ['PATH'],
                'LAB_RESET_TESTS': str(ROOT / 'tests'), 'LAB_RESET_AUDIT': str(audit),
            }
            argv = ['bash', str(work / 'scripts/reset-ceph.sh'), 'joe', '--node', 'all']
            if apply:
                argv.append('--apply')
            master, slave = pty.openpty()
            proc = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave, env=env)
            os.close(slave)
            output = bytearray()
            sent = 0
            deadline = time.monotonic() + 20
            try:
                while True:
                    if time.monotonic() > deadline:
                        self.fail('Terminal test timed out: ' + output.decode(errors='replace'))
                    ready, _, _ = select.select([master], [], [], 0.05)
                    if ready:
                        try:
                            chunk = os.read(master, 65536)
                        except OSError as exc:
                            if exc.errno == 5:  # Linux PTY EIO after the last slave closes.
                                break
                            raise
                        if not chunk:
                            break
                        output.extend(chunk)
                    count = output.decode(errors='replace').count(PROMPT)
                    if count > sent:
                        self.assertEqual(count, sent + 1)
                        self.assertLess(sent, len(responses), 'Unexpected prompt: ' + output.decode(errors='replace'))
                        response = responses[sent]
                        os.write(master, b'\x04' if response is None else response.encode() + b'\n')
                        sent += 1
                    if proc.poll() is not None and not ready:
                        break
                rc = proc.wait(timeout=5)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=5)
                os.close(master)
            self.assertEqual(sent, len(responses))
            report = work / 'build/ceph-reset-report.txt'
            self.assertEqual(report.stat().st_mode & 0o777, 0o600)
            log = report.read_text()
            commands = [json.loads(line) for line in audit.read_text().splitlines()] if audit.exists() else []
            return rc, output.decode(errors='replace'), log, commands

    def assert_all_completed(self, result):
        rc, output, report, commands = result
        self.assertEqual(rc, 0, output)
        for index, node in enumerate(['node1', 'node2', 'node3'], 1):
            self.assertIn(f'Node {index}/3: {node}', output)
            self.assertIn(f'RESULT {node}: CLEANED', report)
        self.assertEqual([row['node'] for row in commands], ['node1'] * 6 + ['node2'] * 6 + ['node3'] * 6)

    def test_full_phrases_reach_all_three_nodes(self):
        self.assert_all_completed(self.run_case(TOKENS))

    def test_erase_alone_then_full_phrase_reaches_all_nodes(self):
        result = self.run_case(['ERASE', *TOKENS])
        self.assert_all_completed(result)
        self.assertIn('2 attempts remaining', result[1])
        self.assertIn('no changes made', result[1])

    def test_three_partial_responses_stop_without_any_disk_command(self):
        rc, output, report, commands = self.run_case(['ERASE'] * 3)
        self.assertEqual(rc, 1, output)
        self.assertIn('3 unmatched responses', report)
        self.assertNotIn('Node 2/3:', output)
        self.assertEqual(commands, [])

    def test_explicit_cancel_stops_without_any_disk_command(self):
        rc, output, report, commands = self.run_case(['cancel'])
        self.assertEqual(rc, 1, output)
        self.assertIn('Cancelled; target was not changed', report)
        self.assertNotIn('Node 2/3:', output)
        self.assertEqual(commands, [])

    def test_terminal_eof_stops_without_any_disk_command(self):
        rc, output, report, commands = self.run_case([None])
        self.assertEqual(rc, 1, output)
        self.assertIn('Confirmation input ended', report)
        self.assertNotIn('Node 2/3:', output)
        self.assertEqual(commands, [])

    def test_plan_all_never_asks_or_records_disk_commands(self):
        rc, output, report, commands = self.run_case([], apply=False)
        self.assertEqual(rc, 0, output)
        for node in ['node1', 'node2', 'node3']:
            self.assertIn(f'RESULT {node}: PLAN_ONLY', report)
        self.assertEqual(commands, [])


if __name__ == '__main__':
    unittest.main()
