"""Exercise destructive-operation guards with fixtures; never inspect or write real disks."""
import copy
import importlib.util
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ceph_reset', ROOT / 'scripts/reset-ceph.py')
reset = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reset)


# Literal lsblk MODEL values in the user's discovery, separately from SMART.
OBSERVED_LSBLK_MODELS = {
    'node1': 'KINGSTON SUV400S',
    'node2': 'ADATA SU630',
    'node3': 'KINGSTON SA400S3',
}


def fixture(node='node3'):
    target = reset.TARGETS[node]
    return {
        'hostname': node, 'ips': [target['ip']], 'real': '/dev/test-sata',
        'root_source': '/dev/mapper/ubuntu--vg-ubuntu--lv', 'root_disks': ['/dev/test-nvme'],
        'tree': [{
            'name': '/dev/test-sata', 'kname': 'test-sata', 'type': 'disk',
            'serial': target['serial'], 'model': OBSERVED_LSBLK_MODELS[node], 'size': reset.DISK_BYTES,
            'ro': False, 'mountpoints': [None], 'fstype': 'LVM2_member',
            'children': [{
                'name': '/dev/dm-test', 'kname': 'dm-test', 'type': 'lvm',
                'ro': False, 'mountpoints': [None], 'fstype': 'ceph_bluestore', 'maj:min': '253:1',
            }],
        }],
        'pvs': [{'pv_name': '/dev/test-sata', 'pv_uuid': target['pv_uuid'], 'vg_name': target['vg']}],
        'lvs': [{'vg_name': target['vg'], 'lv_name': target['lv'],
                 'lv_path': f'/dev/{target["vg"]}/{target["lv"]}',
                 'lv_attr': '-wi-a-----', 'segtype': 'linear'}],
        'signatures': [{'type': 'LVM2_member', 'offset': '0x218'}],
        'holders': {'/dev/test-sata': ['dm-test'], '/dev/dm-test': []},
        'open_devices': [], 'dm_open': {'253:1': 0},
    }


def blank_fixture():
    state = fixture()
    state['tree'][0].pop('children')
    state['tree'][0]['fstype'] = None
    state.update(pvs=[], lvs=[], signatures=[], holders={'/dev/test-sata': []}, dm_open={})
    return state


class CephResetTests(unittest.TestCase):
    def setUp(self):
        lv_paths = {f'/dev/{target["vg"]}/{target["lv"]}' for target in reset.TARGETS.values()}
        self.resolve = patch.object(reset.os.path, 'realpath', side_effect=lambda name: '/dev/dm-test' if str(name) in lv_paths else str(name))
        self.resolve.start()
        self.addCleanup(self.resolve.stop)
        self.state = fixture()

    def rejected(self, message):
        with self.assertRaisesRegex(ValueError, message):
            reset.check('node3', self.state)

    def test_recorded_unused_ceph_accepted(self):
        self.assertEqual(reset.check('node3', self.state), 'ceph')

    def test_already_blank_noop(self):
        self.assertEqual(reset.check('node3', blank_fixture()), 'blank')

    def test_wrong_host(self):
        self.state['hostname'] = 'hermes'
        self.rejected('Host')

    def test_wrong_management_ip(self):
        self.state['ips'] = ['192.168.0.201']
        self.rejected('Host')

    def test_wrong_serial(self):
        self.state['tree'][0]['serial'] = 'OTHER'
        self.rejected('serial')

    def test_wrong_model_or_size(self):
        for field, value, reason in [('model', 'OTHER', 'Linux model mismatch'), ('size', 1000, 'capacity mismatch')]:
            with self.subTest(field=field):
                self.state = fixture()
                self.state['tree'][0][field] = value
                self.rejected(reason)

    def test_actual_linux_models_pass_for_all_three_nodes(self):
        for node in OBSERVED_LSBLK_MODELS:
            with self.subTest(node=node):
                self.assertEqual(reset.check(node, fixture(node)), 'ceph')

    def test_shorter_kingston_model_is_not_a_prefix_rule(self):
        self.state['tree'][0]['model'] = 'KINGSTON SA400'
        self.rejected('Linux model mismatch')

    def test_model_stop_prints_actual_values_before_validation_and_never_mutates(self):
        self.state['tree'][0]['model'] = 'UNEXPECTED MODEL'
        with patch.object(reset, 'collect', return_value=self.state), patch('builtins.input') as ask, patch.object(reset.subprocess, 'run') as run, redirect_stdout(io.StringIO()) as log:
            with self.assertRaisesRegex(ValueError, "expected='KINGSTON SA400S3', observed='UNEXPECTED MODEL'"):
                reset.reset('node3', apply=True)
        run.assert_not_called()
        ask.assert_not_called()
        self.assertIn("Observed Linux model: 'UNEXPECTED MODEL'", log.getvalue())
        self.assertIn(f'observed capacity: {reset.DISK_BYTES} bytes', log.getvalue())
        self.assertNotIn('checks passed', log.getvalue())

    def test_size_stop_reports_exact_expected_and_observed_bytes(self):
        self.state['tree'][0]['size'] = reset.DISK_BYTES - 512
        with patch.object(reset, 'collect', return_value=self.state), patch.object(reset.subprocess, 'run') as run, redirect_stdout(io.StringIO()) as log:
            with self.assertRaisesRegex(ValueError, f'expected={reset.DISK_BYTES} bytes, observed={reset.DISK_BYTES - 512} bytes'):
                reset.reset('node3', apply=True)
        run.assert_not_called()
        self.assertIn(f'observed capacity: {reset.DISK_BYTES - 512} bytes', log.getvalue())

    def test_os_backing_disk(self):
        self.state['root_disks'].append('/dev/test-sata')
        self.rejected('Ubuntu')

    def test_missing_os_ancestors(self):
        self.state['root_disks'] = []
        self.rejected('Ubuntu')

    def test_readonly(self):
        self.state['tree'][0]['ro'] = True
        self.rejected('Read-only')

    def test_mount_or_swap_on_descendant(self):
        for mount in ['/', '/data', '[SWAP]']:
            with self.subTest(mount=mount):
                self.state['tree'][0]['children'][0]['mountpoints'] = [mount]
                self.rejected('Mounted')

    def test_raw_device_open(self):
        self.state['open_devices'] = ['pid=123 /dev/test-sata']
        self.rejected('open')

    def test_unexpected_holder(self):
        self.state['holders']['/dev/test-sata'].append('md0')
        self.rejected('holder')

    def test_dm_open_or_unknown(self):
        for counts in [{'253:1': 1}, {}]:
            with self.subTest(counts=counts):
                self.state['dm_open'] = counts
                self.rejected('open count')

    def test_pv_uuid_changed(self):
        self.state['pvs'][0]['pv_uuid'] = 'OTHER'
        self.rejected('ownership changed')

    def test_cinder_never_removed(self):
        self.state['pvs'][0]['vg_name'] = 'cinder-volumes'
        self.rejected('ownership changed')

    def test_vg_spans_other_disk(self):
        extra = copy.deepcopy(self.state['pvs'][0])
        extra['pv_name'] = '/dev/another-disk'
        self.state['pvs'].append(extra)
        self.rejected('additional physical')

    def test_extra_lv(self):
        extra = copy.deepcopy(self.state['lvs'][0])
        extra['lv_name'] = 'keep-me'
        self.state['lvs'].append(extra)
        self.rejected('exactly one')

    def test_wrong_lv_or_layout(self):
        for field, value in [('lv_name', 'OTHER'), ('lv_path', '/dev/OTHER'), ('segtype', 'thin')]:
            with self.subTest(field=field):
                self.state = fixture()
                self.state['lvs'][0][field] = value
                self.rejected('layout changed')

    def test_inactive_or_open_lv(self):
        for attr in ['-wi-------', '-wi-ao----', 'Vwi-a-----']:
            with self.subTest(attr=attr):
                self.state['lvs'][0]['lv_attr'] = attr
                self.rejected('unopened LV')

    def test_partitioned_disk(self):
        self.state['tree'][0]['children'].append({'name': '/dev/test-sata1', 'kname': 'test-sata1', 'type': 'part', 'ro': False, 'mountpoints': [None]})
        self.rejected('Unexpected children')

    def test_mapper_alias_for_same_recorded_lv_is_accepted(self):
        alias = '/dev/mapper/test-ceph-block'
        self.state['tree'][0]['children'][0]['name'] = alias
        target = reset.TARGETS['node3']
        lv_path = f'/dev/{target["vg"]}/{target["lv"]}'
        with patch.object(reset.os.path, 'realpath', side_effect=lambda name: '/dev/dm-test' if name in {alias, lv_path} else name):
            self.assertEqual(reset.check('node3', self.state), 'ceph')

    def test_mapper_alias_for_different_lv_is_rejected(self):
        self.state['tree'][0]['children'][0]['name'] = '/dev/mapper/unrelated-volume'
        self.rejected('Unexpected children')

    def test_unknown_filesystem(self):
        self.state['tree'][0]['children'][0]['fstype'] = 'ext4'
        self.rejected('signatures')

    def test_partial_removal_requires_review(self):
        self.state['pvs'] = []
        self.rejected('partially removed')

    def test_blank_still_rejects_signature(self):
        self.state = blank_fixture()
        self.state['signatures'] = [{'type': 'ext4'}]
        self.rejected('partially removed')

    def test_plan_does_not_mutate(self):
        with patch.object(reset, 'collect', return_value=self.state), patch.object(reset.subprocess, 'run') as run, redirect_stdout(io.StringIO()) as log:
            reset.reset('node3')
        run.assert_not_called()
        self.assertIn('PLAN_ONLY', log.getvalue())

    def test_wrong_confirmation_does_not_mutate(self):
        with patch.object(reset, 'collect', return_value=self.state), patch('builtins.input', return_value='yes'), patch.object(reset.subprocess, 'run') as run, redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, 'Cancelled'):
                reset.reset('node3', apply=True)
        run.assert_not_called()

    def test_changed_state_after_confirmation_does_not_mutate(self):
        changed = copy.deepcopy(self.state)
        changed['tree'][0]['children'][0]['mountpoints'] = ['/new-mount']
        token = 'ERASE node3 ' + reset.TARGETS['node3']['serial']
        with patch.object(reset, 'collect', side_effect=[self.state, changed]), patch('builtins.input', return_value=token), patch.object(reset.subprocess, 'run') as run, redirect_stdout(io.StringIO()):
            with self.assertRaises(ValueError):
                reset.reset('node3', apply=True)
        run.assert_not_called()

    def test_apply_exact_commands_and_postcheck(self):
        token = 'ERASE node3 ' + reset.TARGETS['node3']['serial']
        with patch.object(reset, 'collect', side_effect=[self.state, copy.deepcopy(self.state), blank_fixture()]), patch('builtins.input', return_value=token), patch.object(reset.subprocess, 'run') as run, redirect_stdout(io.StringIO()) as log:
            reset.reset('node3', apply=True)
        self.assertEqual([call.args[0] for call in run.call_args_list], reset.commands('node3') + [['udevadm', 'settle', '--timeout=10']])
        self.assertTrue(all(call.kwargs.get('check') for call in run.call_args_list))
        self.assertIn('CLEANED', log.getvalue())

    def test_rerun_on_blank_does_not_mutate_or_ask(self):
        with patch.object(reset, 'collect', return_value=blank_fixture()), patch('builtins.input') as ask, patch.object(reset.subprocess, 'run') as run, redirect_stdout(io.StringIO()) as log:
            reset.reset('node3', apply=True)
        ask.assert_not_called()
        run.assert_not_called()
        self.assertIn('ALREADY_BLANK', log.getvalue())


if __name__ == '__main__':
    unittest.main()
