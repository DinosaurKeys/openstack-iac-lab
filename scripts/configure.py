#!/usr/bin/env python3
"""Validate explicit lab inputs and generate local configuration, never deploy."""
import argparse
import importlib.util
import ipaddress
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_NODES = {'node1': '192.168.0.200', 'node2': '192.168.0.201',
                  'node3': '192.168.0.202'}
MAC = re.compile(r'^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$')


def validate(cfg, include_workloads=True):
    errors = []
    if not isinstance(cfg, dict):
        return ['Configuration must be a YAML mapping']
    if cfg.get('schema_version') != 1:
        errors.append('schema_version must be 1')
    nodes = cfg.get('nodes', {})
    if set(nodes) != set(EXPECTED_NODES):
        errors.append('nodes must contain exactly node1, node2, node3')
    macs = []
    for host, address in EXPECTED_NODES.items():
        node = nodes.get(host, {}) or {}
        if node.get('address') != address:
            errors.append(f'{host}.address must preserve {address}')
        mac = node.get('provider_mac')
        if not isinstance(mac, str) or not MAC.fullmatch(mac):
            errors.append(f'{host}.provider_mac needs its actual NIC MAC')
        else:
            macs.append(mac.lower())
    if len(macs) != len(set(macs)):
        errors.append('Provider MAC addresses must be unique')
    mgmt = cfg.get('management', {}) or {}
    if mgmt.get('cidr') != '192.168.0.0/24':
        errors.append('management.cidr must preserve 192.168.0.0/24')
    if mgmt.get('vip') != '192.168.0.100':
        errors.append('management.vip must preserve 192.168.0.100')
    for key in ['gateway', 'vip']:
        try:
            address = ipaddress.IPv4Address(mgmt.get(key))
            if address not in ipaddress.IPv4Network('192.168.0.0/24'):
                raise ValueError()
        except (ValueError, TypeError, ipaddress.AddressValueError):
            errors.append(f'management.{key} needs a usable management IPv4 address')
    dns = mgmt.get('dns_servers', [])
    if not isinstance(dns, list) or not dns:
        errors.append('management.dns_servers needs verified DNS IPs')
    else:
        for value in dns:
            try:
                ipaddress.IPv4Address(value)
            except (ValueError, TypeError):
                errors.append(f'Invalid DNS IP: {value!r}')
    provider = cfg.get('provider', {}) or {}
    for label, value in [('management.interface', mgmt.get('interface')),
                         ('provider.interface', provider.get('interface'))]:
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,15}', value):
            errors.append(f'{label} needs the verified interface name')
    if mgmt.get('interface') == provider.get('interface'):
        errors.append('Management and provider interfaces must differ')
    if provider.get('physical_network') != 'physnet1':
        errors.append('This starter maps exactly one provider network: physnet1')
    pool = cfg.get('floating_pool', {}) or {}
    try:
        first = ipaddress.IPv4Address(pool.get('start'))
        last = ipaddress.IPv4Address(pool.get('end'))
        network = ipaddress.IPv4Network('192.168.0.0/24')
        if not (first in network and last in network and first <= last):
            raise ValueError()
        reserved = [network.network_address, network.broadcast_address,
                    ipaddress.IPv4Address(mgmt.get('gateway')),
                    ipaddress.IPv4Address('192.168.0.100')]
        reserved += [ipaddress.IPv4Address(x) for x in EXPECTED_NODES.values()]
        if any(first <= x <= last for x in reserved):
            errors.append('Floating-IP pool includes a gateway, VIP, node, or network/broadcast address')
    except (ValueError, TypeError):
        errors.append('floating_pool.start/end need a valid reviewed range on 192.168.0.0/24')
    if pool.get('router_dhcp_exclusions_verified') is not True:
        errors.append('Verify the pool excludes router DHCP, Hermes, and other LAN devices')
    storage = cfg.get('storage', {}) or {}
    if storage.get('host') != 'node3':
        errors.append('This initial layout assigns the single storage backend to node3; review placement before changing it')
    disk = storage.get('disk_by_id')
    if not isinstance(disk, str) or not re.fullmatch(r'/dev/disk/by-id/[A-Za-z0-9_.:+-]+', disk):
        errors.append('storage.disk_by_id needs the actual stable whole-disk path')
    if not isinstance(storage.get('expected_serial'), str) or not storage['expected_serial'].strip():
        errors.append('storage.expected_serial needs the actual serial')
    if storage.get('ownership_and_health_verified') is not True:
        errors.append('Review storage ownership and health before marking it verified')
    work = cfg.get('workloads', {}) or {}
    if include_workloads:
        networks = [ipaddress.IPv4Network('192.168.0.0/24')]
        for key in ['first_cidr', 'app_cidr']:
            try:
                value = ipaddress.IPv4Network(work.get(key))
                if any(value.overlaps(other) for other in networks):
                    errors.append(f'workloads.{key} overlaps another lab network')
                networks.append(value)
            except (ValueError, TypeError):
                errors.append(f'workloads.{key} needs a valid non-overlapping IPv4 CIDR')
        try:
            admin = ipaddress.IPv4Network(work.get('admin_cidr'))
            if admin.prefixlen == 0:
                errors.append('admin_cidr must restrict access; 0.0.0.0/0 is not an admin network')
        except (ValueError, TypeError):
            errors.append('workloads.admin_cidr needs a valid IPv4 CIDR')
        if work.get('cidr_nonoverlap_verified') is not True:
            errors.append('Verify workload CIDRs against actual LAN/VPN/cloud routes')
        for key in ['image_name', 'flavor_name', 'key_pair', 'public_key_path']:
            if not isinstance(work.get(key), str) or not work[key].strip():
                errors.append(f'workloads.{key} is required')
        hcp = cfg.get('hcp', {}) or {}
        if not isinstance(hcp.get('organization'), str) or not re.fullmatch(r'[A-Za-z0-9_-]+', hcp['organization']):
            errors.append('hcp.organization is required for remote state')
        if hcp.get('local_execution_verified') is not True:
            errors.append('Confirm HCP workspaces use Local execution')
    return errors


def write_yaml(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(obj, sort_keys=False))
    path.chmod(0o600)


def generate(cfg, sample, include_workloads=True):
    spec = importlib.util.spec_from_file_location('kolla_inventory', ROOT / 'scripts/render-kolla-inventory.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    kolla = module.render(sample.read_text())
    inventory = yaml.safe_load((ROOT / 'ansible/inventory/hosts.yml').read_text())
    common = yaml.safe_load((ROOT / 'ansible/inventory/group_vars/all.yml').read_text())
    common.update(management_interface=cfg['management']['interface'],
                  provider_interface=cfg['provider']['interface'],
                  management_gateway=cfg['management']['gateway'],
                  management_dns=cfg['management']['dns_servers'],
                  storage_disk_by_id=cfg['storage']['disk_by_id'],
                  storage_expected_serial=cfg['storage']['expected_serial'])
    inventory['all']['vars'] = common
    for name, values in cfg['nodes'].items():
        inventory['all']['children']['lab_nodes']['hosts'][name]['provider_mac'] = values['provider_mac']
    write_yaml(ROOT / 'build/inventory.yml', inventory)
    kolla['all']['children']['lab_nodes'] = {'hosts': {name: {} for name in EXPECTED_NODES}}
    write_yaml(ROOT / 'build/kolla-inventory.yml', kolla)
    globals_cfg = yaml.safe_load((ROOT / 'kolla/globals.yml.example').read_text())
    globals_cfg.update(network_interface=cfg['management']['interface'],
                       neutron_external_interface=cfg['provider']['interface'])
    write_yaml(ROOT / 'build/globals.yml', globals_cfg)
    if not include_workloads:
        print('Generated host and Kolla candidates only. No infrastructure changed.')
        return
    work = cfg['workloads']
    for folder, workspace, cidr in [('01-first-workload', 'first', 'first_cidr'),
                                    ('02-application', 'app', 'app_cidr'),
                                    ('03-monitoring', 'monitor', None)]:
        path = ROOT / 'terraform' / folder
        variables = {key: work[key] for key in ['admin_cidr', 'image_name', 'flavor_name', 'key_pair']}
        if cidr:
            variables.update(workload_cidr=work[cidr], dns_servers=cfg['management']['dns_servers'])
        else:
            existing = path / 'terraform.tfvars.json'
            if existing.exists():
                prior = json.loads(existing.read_text())
                if prior.get('app_private_ip'):
                    variables['app_private_ip'] = prior['app_private_ip']
        (path / 'terraform.tfvars.json').write_text(json.dumps(variables, indent=2) + '\n')
        (path / 'terraform.tfvars.json').chmod(0o600)
        backend = {'terraform': {'cloud': {'organization': cfg['hcp']['organization'],
                    'workspaces': {'name': 'openstack-iac-' + workspace}}}}
        (path / 'backend.tf.json').write_text(json.dumps(backend, indent=2) + '\n')
    print('Generated local inventories, Kolla globals, and Terraform settings. No infrastructure changed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'private/lab.yml')
    parser.add_argument('--sample', type=Path,
                        default=Path.home() / 'venvs/kolla-iac/share/kolla-ansible/ansible/inventory/multinode')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--hosts-only', action='store_true', help='Do not require HCP/workload inputs or generate Terraform settings yet')
    args = parser.parse_args()
    if not args.config.is_file():
        parser.error('Copy config/lab.yml.example to private/lab.yml and fill verified values first.')
    cfg = yaml.safe_load(args.config.read_text())
    errors = validate(cfg, include_workloads=not args.hosts_only)
    if errors:
        for error in errors:
            print('- ' + error, file=sys.stderr)
        raise SystemExit(2)
    if args.check:
        print('Explicit configuration inputs passed local consistency checks.')
        return
    if not args.sample.is_file():
        parser.error('Install the pinned Kolla toolchain first; sample inventory is missing.')
    generate(cfg, args.sample, include_workloads=not args.hosts_only)


if __name__ == '__main__':
    main()
