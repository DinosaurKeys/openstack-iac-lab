#!/usr/bin/env python3
"""Inspect a stable data-disk target; --apply only provisions a verified blank disk.

It refuses existing Ceph/filesystem ownership instead of choosing a wipe target.
"""
import argparse
import json
import os
import subprocess
from pathlib import Path


def walk(node):
    yield node
    for child in node.get('children', []):
        yield from walk(child)


def check_tree(tree, serial, allow_existing_cinder=False):
    devices = tree.get('blockdevices', [])
    if len(devices) != 1 or devices[0].get('type') != 'disk':
        raise ValueError('Target must resolve to one whole physical disk, not a partition or mapper device')
    disk = devices[0]
    if str(disk.get('serial') or '').strip() != serial.strip():
        raise ValueError('Actual disk serial differs from the approved expected serial')
    if disk.get('ro') in [True, 1, '1']:
        raise ValueError('Target disk is read-only')
    for node in walk(disk):
        if any(x for x in (node.get('mountpoints') or [])) or node.get('mountpoint'):
            raise ValueError('Target or one of its descendants is mounted/in use, including possible OS storage')
        if not allow_existing_cinder:
            if node.get('fstype'):
                raise ValueError('Existing filesystem/Ceph/LVM signature: exact cleanup must be reviewed separately')
            if node is not disk:
                raise ValueError('Target has partitions or mapped children; it is not an unowned blank disk')
    return disk


def output(argv):
    return subprocess.check_output(argv, text=True)


def provision(target, serial, apply=False):
    if not target.startswith('/dev/disk/by-id/'):
        raise ValueError('Use a stable /dev/disk/by-id whole-disk path')
    path = Path(target)
    if not path.is_symlink():
        raise ValueError('Stable disk path is missing or is not a by-id symlink')
    real = str(path.resolve(strict=True))
    tree = json.loads(output(['lsblk', '--json', '--paths', '--output',
                              'NAME,TYPE,FSTYPE,MOUNTPOINTS,SERIAL,RO', real]))
    pvs = json.loads(output(['pvs', '--reportformat', 'json', '-o', 'pv_name,vg_name']))
    rows = pvs['report'][0].get('pv', [])
    selected = [row for row in rows if os.path.realpath(row['pv_name'].strip()) == real]
    owned = bool(selected and selected[0]['vg_name'].strip() == 'cinder-volumes')
    if owned:
        all_cinder = [row for row in rows if row['vg_name'].strip() == 'cinder-volumes']
        if len(all_cinder) != 1:
            raise ValueError('Existing cinder-volumes spans unexpected PVs; inspect manually')
    elif selected:
        raise ValueError('Disk already belongs to LVM; exact removal of old ownership is not automatic')
    check_tree(tree, serial, allow_existing_cinder=owned)
    if owned:
        return {'changed': False, 'device': real, 'serial': serial, 'status': 'existing expected Cinder VG'}
    if not apply:
        return {'changed': False, 'device': real, 'serial': serial, 'status': 'blank candidate; no changes made'}
    subprocess.run(['pvcreate', '--yes', real], check=True, stdout=subprocess.PIPE, text=True)
    subprocess.run(['vgcreate', 'cinder-volumes', real], check=True, stdout=subprocess.PIPE, text=True)
    return {'changed': True, 'device': real, 'serial': serial, 'status': 'created cinder-volumes'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(provision(args.target, args.serial, args.apply)))
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc))


if __name__ == '__main__':
    main()
