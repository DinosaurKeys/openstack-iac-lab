import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from configure import validate

spec = importlib.util.spec_from_file_location('storage_target', ROOT / 'scripts/storage-target.py')
storage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(storage)
guest_spec = importlib.util.spec_from_file_location('guest_volume', ROOT / 'scripts/guest-volume.py')
guest = importlib.util.module_from_spec(guest_spec)
guest_spec.loader.exec_module(guest)


def valid_config():
    return {
        'schema_version': 1,
        'nodes': {f'node{i}': {'address': f'192.168.0.{199+i}', 'provider_mac': f'02:00:00:00:00:0{i}'} for i in range(1, 4)},
        'management': {'interface': 'enp0s31f6', 'cidr': '192.168.0.0/24', 'gateway': '192.168.0.1', 'vip': '192.168.0.100', 'dns_servers': ['192.0.2.53']},
        'provider': {'interface': 'ext0', 'physical_network': 'physnet1'},
        'floating_pool': {'start': '192.168.0.210', 'end': '192.168.0.220', 'router_dhcp_exclusions_verified': True},
        'storage': {'host': 'node3', 'disk_by_id': '/dev/disk/by-id/ata-TEST', 'expected_serial': 'TEST', 'ownership_and_health_verified': True},
        'workloads': {'admin_cidr': '192.168.0.0/24', 'first_cidr': '10.42.10.0/24', 'app_cidr': '10.42.20.0/24', 'cidr_nonoverlap_verified': True, 'image_name': 'test-image', 'flavor_name': 'test-flavor', 'key_pair': 'test-key', 'public_key_path': '~/.ssh/test.pub'},
        'hcp': {'organization': 'test-org', 'local_execution_verified': True},
    }


class InputTests(unittest.TestCase):
    def test_reviewed_fixture_passes(self):
        self.assertEqual(validate(valid_config()), [])

    def test_changed_node_ip_rejected(self):
        cfg = valid_config()
        cfg['nodes']['node1']['address'] = '192.168.0.210'
        self.assertTrue(any('preserve' in error for error in validate(cfg)))

    def test_reserved_floating_range_rejected(self):
        cfg = valid_config()
        cfg['floating_pool'].update(start='192.168.0.190', end='192.168.0.210')
        self.assertTrue(any('Floating-IP pool includes' in error for error in validate(cfg)))

    def test_overlapping_workloads_rejected(self):
        cfg = valid_config()
        cfg['workloads']['app_cidr'] = '10.42.10.128/25'
        self.assertTrue(any('overlaps' in error for error in validate(cfg)))

    def test_duplicate_nic_mac_rejected(self):
        cfg = valid_config()
        cfg['nodes']['node2']['provider_mac'] = cfg['nodes']['node1']['provider_mac']
        self.assertTrue(any('unique' in error for error in validate(cfg)))


class DiskGuardTests(unittest.TestCase):
    def setUp(self):
        self.disk = {'blockdevices': [{'name': '/dev/test', 'type': 'disk', 'serial': 'TEST', 'ro': False, 'fstype': None, 'mountpoints': [None]}]}

    def test_blank_expected_disk_accepted(self):
        self.assertEqual(storage.check_tree(self.disk, 'TEST')['name'], '/dev/test')

    def test_wrong_serial_rejected(self):
        with self.assertRaisesRegex(ValueError, 'serial'):
            storage.check_tree(self.disk, 'OTHER')

    def test_mounted_os_child_rejected_even_for_existing_cinder(self):
        self.disk['blockdevices'][0]['children'] = [{'type': 'lvm', 'mountpoints': ['/']}]
        with self.assertRaisesRegex(ValueError, 'mounted'):
            storage.check_tree(self.disk, 'TEST', allow_existing_cinder=True)

    def test_ceph_signature_requires_separate_review(self):
        self.disk['blockdevices'][0]['fstype'] = 'ceph_bluestore'
        with self.assertRaisesRegex(ValueError, 'cleanup'):
            storage.check_tree(self.disk, 'TEST')

    def test_unmounted_partition_is_still_not_blank(self):
        self.disk['blockdevices'][0]['children'] = [{'type': 'part', 'mountpoints': [None]}]
        with self.assertRaisesRegex(ValueError, 'children'):
            storage.check_tree(self.disk, 'TEST')

    def test_volume_serial_prefix_matches_only_the_expected_uuid(self):
        volume = '12345678-1234-1234-1234-123456789012'
        self.assertTrue(guest.serial_matches_volume('12345678-1234-1234-12', volume))
        self.assertFalse(guest.serial_matches_volume('87654321-1234-1234-12', volume))
        self.assertFalse(guest.serial_matches_volume('1234', volume))


if __name__ == '__main__':
    unittest.main()
