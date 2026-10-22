#!/usr/bin/env python3
"""Preserve a pinned Kolla sample's group hierarchy and replace lab placement.

This only writes a candidate YAML inventory on the deployment machine.
It does not connect to nodes or run Ansible.
"""
import argparse
import re
import shlex
from pathlib import Path

import yaml


def render(text):
    groups = {}
    section = None
    kind = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        match = re.fullmatch(r'\[([^\]:]+)(?::(children|vars))?\]', line)
        if match:
            section, kind = match.group(1), match.group(2) or 'hosts'
            groups.setdefault(section, {}).setdefault(kind, {})
            continue
        if section is None:
            raise ValueError('Unexpected inventory content before first section')
        tokens = shlex.split(line, comments=True)
        if not tokens:
            continue
        if kind == 'vars':
            key, value = line.split('=', 1)
            groups[section][kind][key.strip()] = value.strip()
        elif kind == 'children':
            if len(tokens) != 1:
                raise ValueError('Unexpected child group expression')
            groups[section][kind][tokens[0]] = {}
        else:
            host = tokens[0]
            attrs = dict(token.split('=', 1) for token in tokens[1:])
            groups[section][kind][host] = attrs

    placements = {
        'control': ['node1', 'node2', 'node3'],
        'network': ['node1', 'node2', 'node3'],
        'compute': ['node2', 'node3'],
        'storage': ['node3'],
        'monitoring': [],
    }
    required = set(placements) | {'deployment', 'glance', 'cinder-volume',
                                  'cinder-backup', 'cinder-volume-lvm', 'tgtd'}
    missing = required - set(groups)
    if missing:
        raise ValueError(f'Incompatible Kolla inventory: missing {sorted(missing)}')
    for group, hosts in placements.items():
        groups[group] = {'hosts': {host: {} for host in hosts}}
    groups['deployment'] = {'hosts': {'localhost': {'ansible_connection': 'local'}}}
    groups['glance'] = {'hosts': {'node1': {}}}
    # API/scheduler stay on all controllers, but the LVM backend is a singleton.
    # Align the parent group with the actual backend placement for HA prechecks.
    groups['cinder-volume'] = {'children': {'storage': {}}}
    groups['cinder-backup'] = {'children': {'storage': {}}}
    node_hosts = {f'node{i}': {'ansible_host': f'192.168.0.{199+i}'}
                  for i in range(1, 4)}
    result = {'all': {'vars': {'ansible_user': 'joe',
                                'ansible_ssh_private_key_file': '~/.ssh/openstack-iac-lab-ansible',
                                'ansible_ssh_common_args': '-o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o ForwardAgent=no',
                                'ansible_become': True,
                                'ansible_python_interpreter': '/usr/bin/python3'},
                      'hosts': node_hosts, 'children': groups}}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sample', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = render(args.sample.read_text())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise SystemExit('Output exists; review it or choose a new filename.')
    args.output.write_text(yaml.safe_dump(result, sort_keys=False))
    print(f'Candidate written: {args.output}; review group membership before use.')


if __name__ == '__main__':
    main()
