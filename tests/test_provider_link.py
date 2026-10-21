"""USB identity/ownership/restoration checks; no real NIC or SSH operation."""
import copy
import importlib.util
import os
import pty
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('provider_link', ROOT / 'scripts/test-provider-link.py')
link = importlib.util.module_from_spec(spec)
spec.loader.exec_module(link)


def fixture(node='node1'):
    ip, management_mac, provider_mac = link.TARGETS[node]
    return {
        'hostname': node,
        'management': {'name': link.MANAGEMENT, 'mac': management_mac, 'index': 2, 'up': True,
                       'addresses': [{'family': 'inet', 'local': ip, 'prefixlen': 24, 'scope': 'global'}]},
        'provider': {'name': 'enxtest', 'mac': provider_mac, 'index': 3, 'up': False, 'usb': True,
                     'addresses': [], 'master': False, 'uppers': []},
        'routes': {'-4': [{'dst': 'default', 'gateway': '192.168.0.1', 'dev': link.MANAGEMENT}], '-6': []},
        'setup': 'unmanaged', 'network_manager': 'inactive', 'ipv6_disabled': '0',
    }


class ProviderGuardTests(unittest.TestCase):
    def reject(self, section, key, value, message):
        state = fixture()
        if section:
            state[section][key] = value
        else:
            state[key] = value
        with self.assertRaisesRegex(ValueError, message):
            link.validate('node1', state)

    def test_all_recorded_nodes_pass(self):
        for node in link.TARGETS:
            link.validate(node, fixture(node))

    def test_wrong_host(self):
        self.reject(None, 'hostname', 'node3', 'Hostname')

    def test_wrong_management_mac(self):
        self.reject('management', 'mac', '00:00:00:00:00:00', 'Management')

    def test_wrong_management_address(self):
        self.reject('management', 'addresses', [], 'management address')

    def test_management_is_never_target(self):
        self.reject('provider', 'index', 2, 'management interface')

    def test_wrong_usb_mac(self):
        self.reject('provider', 'mac', '00:00:00:00:00:00', 'recorded USB')

    def test_non_usb(self):
        self.reject('provider', 'usb', False, 'recorded USB')

    def test_already_up(self):
        self.reject('provider', 'up', True, 'must be DOWN')

    def test_existing_addresses(self):
        self.reject('provider', 'addresses', [{'family': 'inet6', 'local': 'fe80::1'}], 'must be DOWN')

    def test_bridge_membership(self):
        self.reject('provider', 'master', True, 'master or upper')

    def test_upper_vlan(self):
        self.reject('provider', 'uppers', ['upper_vlan10'], 'master or upper')

    def test_route_using_usb(self):
        state = fixture()
        state['routes']['-4'][0]['dev'] = 'enxtest'
        with self.assertRaisesRegex(ValueError, 'route already uses'):
            link.validate('node1', state)

    def test_multipath_route_using_usb(self):
        state = fixture()
        state['routes']['-4'][0]['nexthops'] = [{'dev': 'enxtest'}]
        with self.assertRaisesRegex(ValueError, 'route already uses'):
            link.validate('node1', state)

    def test_networkd_managed(self):
        self.reject(None, 'setup', 'configured', 'ownership needs review')

    def test_network_manager_active(self):
        self.reject(None, 'network_manager', 'active', 'ownership needs review')

    def test_networkctl_list_parser(self):
        with patch.object(link, 'run', return_value='  3 enxtest ether off unmanaged'):
            self.assertEqual(link.network_setup('enxtest'), 'unmanaged')
        with patch.object(link, 'run', return_value='unexpected output'):
            with self.assertRaisesRegex(ValueError, 'Cannot read'):
                link.network_setup('enxtest')

    def test_identity_reuse_rejected_before_write(self):
        with patch.object(link, 'read', side_effect=['wrong-mac']), patch.object(link, 'run') as command:
            with self.assertRaisesRegex(ValueError, 'USB identity changed'):
                link.set_link(fixture()['provider'], 'up')
            command.assert_not_called()


class ProviderRestorationTests(unittest.TestCase):
    def exercise(self, apply=True, measured=None, failure=None, ipv6='0', final=None):
        before = fixture()
        before['ipv6_disabled'] = ipv6
        after = copy.deepcopy(before) if final is None else final
        self.actions = []
        readings = measured or {'carrier': '1', 'speed': '1000', 'duplex': 'full'}
        def write_ip(provider, value):
            self.actions.append(('ipv6', value))
        def write_link(provider, value):
            self.actions.append(('link', value))
        with patch.object(link, 'collect', side_effect=[before, copy.deepcopy(before), after]), \
             patch.object(link, 'set_link', side_effect=write_link), \
             patch.object(link, 'set_ipv6', side_effect=write_ip), \
             patch.object(link, 'wait_for_link', side_effect=failure, return_value=readings):
            return link.test_link('node1', apply)

    def test_plan_never_writes(self):
        self.assertEqual(self.exercise(apply=False), 0)
        self.assertEqual(self.actions, [])

    def test_success_restores_link_before_ipv6(self):
        self.assertEqual(self.exercise(), 0)
        self.assertEqual(self.actions, [('ipv6', '1'), ('link', 'up'), ('link', 'down'), ('ipv6', '0')])

    def test_disabled_ipv6_unchanged(self):
        self.assertEqual(self.exercise(ipv6='1'), 0)
        self.assertEqual(self.actions, [('link', 'up'), ('link', 'down')])

    def test_no_carrier_is_review_after_restore(self):
        self.assertEqual(self.exercise(measured={'carrier': '0', 'speed': '-1', 'duplex': 'unknown'}), 3)
        self.assertEqual(self.actions[-2:], [('link', 'down'), ('ipv6', '0')])

    def test_slow_link_is_review(self):
        self.assertEqual(self.exercise(measured={'carrier': '1', 'speed': '100', 'duplex': 'full'}), 3)

    def test_measurement_exception_restores(self):
        with self.assertRaisesRegex(ValueError, 'after restoration'):
            self.exercise(failure=RuntimeError('fixture read failure'))
        self.assertEqual(self.actions[-2:], [('link', 'down'), ('ipv6', '0')])

    def test_interrupt_restores(self):
        with self.assertRaisesRegex(ValueError, 'after restoration'):
            self.exercise(failure=KeyboardInterrupt('fixture signal'))
        self.assertEqual(self.actions[-2:], [('link', 'down'), ('ipv6', '0')])

    def test_changed_route_fails_postcheck(self):
        after = fixture()
        after['routes']['-4'][0]['gateway'] = '192.168.0.254'
        with self.assertRaisesRegex(ValueError, 'RESTORATION NOT VERIFIED.*routes differ'):
            self.exercise(final=after)

    def test_failed_down_is_not_reported_restored(self):
        before = fixture()
        def fail_down(provider, state):
            if state == 'down':
                raise ValueError('fixture down failure')
        with patch.object(link, 'collect', return_value=before), patch.object(link, 'set_ipv6'), \
             patch.object(link, 'set_link', side_effect=fail_down), \
             patch.object(link, 'wait_for_link', return_value={'carrier': '1', 'speed': '1000', 'duplex': 'full'}):
            with self.assertRaisesRegex(ValueError, 'RESTORATION NOT VERIFIED'):
                link.test_link('node1', True)


MOCK_SSH = r'''
import json, os, shlex, sys
from pathlib import Path
assert os.isatty(0)
args = shlex.split(sys.argv[-1])
assert args[:5] == ['sudo', '--', 'python3', '-u', '-c']
compile(args[5], '<quoted-helper>', 'exec')
node = args[args.index('--node') + 1]
assert sys.argv[-2] == {'node1':'192.168.0.200','node2':'192.168.0.201','node3':'192.168.0.202'}[node]
assert ('--apply' in args) == (os.environ['EXPECT_APPLY'] == '1')
code = int(os.environ.get('NODE1_CODE', '0')) if node == 'node1' else 0
print('RESULT ' + node + ': fixture outcome ' + str(code), flush=True)
sys.exit(code)
'''


class ProviderTransportTests(unittest.TestCase):
    def wrapper(self, extra=(), node1_code=0, apply=True):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / 'scripts').mkdir()
            for name in ['test-provider-link.sh', 'test-provider-link.py']:
                shutil.copy2(ROOT / 'scripts' / name, work / 'scripts' / name)
            (work / 'bin').mkdir()
            ssh = work / 'bin/ssh'
            ssh.write_text(f'#!{sys.executable}\n' + MOCK_SSH)
            ssh.chmod(0o755)
            env = {**os.environ, 'PATH': str(work / 'bin') + os.pathsep + os.environ['PATH'],
                   'EXPECT_APPLY': str(int(apply)), 'NODE1_CODE': str(node1_code)}
            argv = ['bash', str(work / 'scripts/test-provider-link.sh'), 'joe', *extra]
            if apply:
                argv.append('--apply')
            master, slave = pty.openpty()
            try:
                result = subprocess.run(argv, stdin=slave, capture_output=True, text=True, env=env, timeout=15)
            finally:
                os.close(master)
                os.close(slave)
            report = work / 'build/provider-link-report.txt'
            if report.exists():
                self.assertEqual(report.stat().st_mode & 0o777, 0o600)
                history = [p for p in report.parent.glob('provider-link-*') if p.is_dir()]
                self.assertEqual(len(history), 1)
                self.assertEqual(history[0].stat().st_mode & 0o777, 0o700)
                log = report.read_text()
            else:
                log = ''
            return result, log

    def test_all_nodes_and_remote_quoting(self):
        result, log = self.wrapper()
        self.assertEqual(result.returncode, 0, result.stderr)
        for node in link.TARGETS:
            self.assertIn(f'=== {node}: COMPLETED ===', log)

    def test_plan_and_single_node_selection(self):
        result, log = self.wrapper(extra=['--node', 'node2'], apply=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('=== node2: COMPLETED ===', log)
        self.assertNotIn('=== node1:', log)

    def test_review_continues_to_later_nodes(self):
        result, log = self.wrapper(node1_code=3)
        self.assertEqual(result.returncode, 1)
        self.assertIn('=== node1: REVIEW ===', log)
        self.assertIn('=== node3: COMPLETED ===', log)

    def test_hard_failure_stops(self):
        result, log = self.wrapper(node1_code=1)
        self.assertEqual(result.returncode, 1)
        self.assertIn('=== node1: STOPPED ===', log)
        self.assertNotIn('=== node2:', log)

    def test_invalid_node_rejected_before_ssh(self):
        result, log = self.wrapper(extra=['--node', 'hermes'])
        self.assertEqual(result.returncode, 2)
        self.assertEqual(log, '')


if __name__ == '__main__':
    unittest.main()
