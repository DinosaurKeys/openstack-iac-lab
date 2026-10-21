#!/usr/bin/env python3
"""Run inside the DB VM to inspect/format its explicitly identified Cinder disk.

Requires a by-id path, its observed serial, and the Terraform volume UUID.
Default is inspection only. No device name is inferred.
"""
import argparse
import importlib.util
import json
import re
import subprocess
import uuid
from pathlib import Path


def serial_matches_volume(serial, volume_id):
    expected = uuid.UUID(volume_id).hex
    actual = serial.replace('-', '').lower()
    return bool(re.fullmatch(r'[0-9a-f]{16,32}', actual) and expected.startswith(actual))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--volume-id', required=True)
    parser.add_argument('--format', action='store_true')
    args = parser.parse_args()
    if not serial_matches_volume(args.serial, args.volume_id):
        raise SystemExit('Observed serial does not match the supplied Cinder UUID prefix. Stop and review the actual attachment.')
    path = Path(args.target)
    if not str(path).startswith('/dev/disk/by-id/') or not path.is_symlink():
        raise SystemExit('Supply the existing stable by-id path, not a guessed /dev/vdb.')
    real = str(path.resolve(strict=True))
    tree = json.loads(subprocess.check_output(['lsblk', '--json', '--paths', '-o', 'NAME,TYPE,FSTYPE,MOUNTPOINTS,SERIAL,RO', real], text=True))
    spec = importlib.util.spec_from_file_location('storage_guard', Path(__file__).with_name('storage-target.py'))
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    fstype = tree['blockdevices'][0].get('fstype')
    guard.check_tree(tree, args.serial, allow_existing_cinder=(fstype == 'ext4'))
    if fstype == 'ext4':
        print('Existing ext4 filesystem retained; no formatting performed.')
    elif args.format:
        if input(f'Type format:{args.serial} to format this verified blank Cinder disk: ') != 'format:' + args.serial:
            raise SystemExit('Formatting cancelled.')
        subprocess.run(['mkfs.ext4', '-q', real], check=True)
    else:
        print(json.dumps({'device': real, 'serial': args.serial, 'volume_id': args.volume_id,
                          'status': 'verified blank candidate; inspection only'}))
        return
    print(subprocess.check_output(['blkid', '-s', 'UUID', '-o', 'value', real], text=True).strip())


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc))
