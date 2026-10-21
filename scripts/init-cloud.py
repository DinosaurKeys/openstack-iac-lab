#!/usr/bin/env python3
"""Seed an explicitly configured fresh cloud using the operator's OpenStack CLI login.

Creates shared provider networking, a checksum-verified Ubuntu image, one flavor,
and a public SSH key. No password or application credential is generated here.
"""
import argparse
import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path

import yaml

from configure import ROOT, validate


def cli(*args):
    return json.loads(subprocess.check_output(['openstack', *args, '-f', 'json'], text=True))


def find(kind, name):
    rows = cli(kind, 'list')
    matches = [row for row in rows if row.get('Name', row.get('name')) == name]
    if len(matches) > 1:
        raise ValueError(f'Ambiguous {kind} name {name!r}; inspect IDs before continuing')
    return cli(kind, 'show', name) if matches else None


def check_subnet(subnet, cfg):
    if subnet.get('cidr') != cfg['management']['cidr'] or subnet.get('gateway_ip') != cfg['management']['gateway']:
        raise ValueError('Existing public-subnet CIDR/gateway differs from the reviewed configuration')
    pools = subnet.get('allocation_pools')
    if not isinstance(pools, list) or len(pools) != 1:
        raise ValueError('Inspect existing public-subnet allocation pools manually before reuse')
    if pools[0].get('start') != cfg['floating_pool']['start'] or pools[0].get('end') != cfg['floating_pool']['end']:
        raise ValueError('Existing floating allocation pool differs from the reviewed range')


def download_image():
    directory = ROOT / 'build/images'
    directory.mkdir(parents=True, exist_ok=True)
    name = 'noble-server-cloudimg-amd64.img'
    base = 'https://cloud-images.ubuntu.com/noble/current/'
    with urllib.request.urlopen(base + 'SHA256SUMS', timeout=60) as response:
        sums = response.read().decode()
    expected = None
    for line in sums.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip('*') == name:
            expected = parts[0]
    if not expected:
        raise ValueError('Official SHA256SUMS did not identify the requested image')
    destination = directory / name
    if not destination.exists():
        urllib.request.urlretrieve(base + name, destination)
    digest = hashlib.sha256()
    with destination.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise ValueError('Image checksum mismatch. Move aside the cached image and investigate before retrying.')
    (directory / 'verified-image.json').write_text(json.dumps({'url': base + name, 'sha256': expected}, indent=2) + '\n')
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'private/lab.yml')
    args = parser.parse_args()
    cfg = yaml.safe_load(args.config.read_text())
    errors = validate(cfg, include_workloads=False)
    if errors:
        raise SystemExit('\n'.join(errors))
    if cfg.get('fresh_install_confirmed') is not True:
        raise SystemExit('This seeding command is for the confirmed fresh lab.')
    work = cfg['workloads']
    key = Path(work['public_key_path']).expanduser()
    if not key.is_file() or not key.read_text().startswith(('ssh-ed25519 ', 'ssh-rsa ', 'ecdsa-sha2-')):
        raise SystemExit('Supply the intended SSH public key file; never pass a private key.')
    print('Using the current OpenStack CLI credentials to seed the fresh lab. Confirm the project/cloud before running.')
    network = find('network', 'public')
    if network is None:
        network = cli('network', 'create', '--external', '--share', '--provider-network-type', 'flat',
                      '--provider-physical-network', 'physnet1', 'public')
    if network.get('provider:network_type') != 'flat' or network.get('provider:physical_network') != 'physnet1':
        raise ValueError('Existing public network is not the expected flat physnet1 provider network')
    if str(network.get('router:external')).lower() != 'true' or str(network.get('shared')).lower() != 'true':
        raise ValueError('The expected provider network must be external and shared')
    subnet = find('subnet', 'public-subnet')
    if subnet is None:
        pool = cfg['floating_pool']
        subnet = cli('subnet', 'create', '--network', network['id'], '--subnet-range', cfg['management']['cidr'],
                     '--allocation-pool', f'start={pool["start"]},end={pool["end"]}',
                     '--gateway', cfg['management']['gateway'], '--no-dhcp',
                     '--dns-nameserver', cfg['management']['dns_servers'][0], 'public-subnet')
    check_subnet(subnet, cfg)
    if subnet.get('network_id') != network['id']:
        raise ValueError('public-subnet belongs to another network')
    flavor = find('flavor', work['flavor_name'])
    if flavor is None:
        flavor = cli('flavor', 'create', '--ram', '2048', '--vcpus', '2', '--disk', '15', work['flavor_name'])
    if any(int(flavor[key]) != value for key, value in [('ram', 2048), ('vcpus', 2), ('disk', 15)]):
        raise ValueError('Existing flavor differs from the documented size')
    image = find('image', work['image_name'])
    if image is None:
        path = download_image()
        image = cli('image', 'create', '--file', str(path), '--disk-format', 'qcow2',
                    '--container-format', 'bare', '--public', work['image_name'])
    if image.get('status', '').lower() != 'active':
        raise ValueError('Image is not ACTIVE; inspect upload/status before proceeding')
    keypair = find('keypair', work['key_pair'])
    if keypair is None:
        cli('keypair', 'create', '--public-key', str(key), work['key_pair'])
    else:
        actual = keypair.get('public_key', '').strip().split()
        intended = key.read_text().strip().split()
        if actual[:2] != intended[:2]:
            raise ValueError('Existing SSH key pair has different public-key material')
    print('Seed resources exist. Create/use the separate project-scoped IaC identity before Terraform workloads.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, subprocess.CalledProcessError, OSError) as exc:
        raise SystemExit(str(exc))
