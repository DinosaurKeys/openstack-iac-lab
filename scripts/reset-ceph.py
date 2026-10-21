#!/usr/bin/env python3
"""Stage 0: plan or remove only the three recorded, unused Ceph SATA allocations."""
import argparse
import json
import os
import shlex
import shutil
import socket
import stat
import subprocess
import sys
from pathlib import Path

# SMART's full model and lsblk's Linux model are separate reported fields.
# Both come from Joe's 2026-10-21 reports; never infer a model by prefix.
TARGETS = {
    'node1': {
        'ip': '192.168.0.200', 'model': 'KINGSTON SUV400S37240G',
        'lsblk_model': 'KINGSTON SUV400S',
        'serial': '50026B7766070422',
        'by_id': '/dev/disk/by-id/ata-KINGSTON_SUV400S37240G_50026B7766070422',
        'pv_uuid': 'AQDsnI-3mcw-CC50-WzMu-7krG-nWn2-A7Cjku',
        'vg': 'ceph-23770818-11f1-4b5c-8cc9-b0a03885e5d5',
        'lv': 'osd-block-6f1c32a3-4810-4bf1-8573-56e47e77ad73',
    },
    'node2': {
        'ip': '192.168.0.201', 'model': 'ADATA SU630',
        'lsblk_model': 'ADATA SU630',
        'serial': '4P3521354988',
        'by_id': '/dev/disk/by-id/ata-ADATA_SU630_4P3521354988',
        'pv_uuid': 'RMp9V0-TZ3W-uSBZ-6mgL-5Biu-W8f2-552tfm',
        'vg': 'ceph-994cce48-85c4-4ac9-9ad7-25c7ffbf914e',
        'lv': 'osd-block-962ff7dc-0d1c-4a7b-a997-ec28e72890c5',
    },
    'node3': {
        'ip': '192.168.0.202', 'model': 'KINGSTON SA400S37240G',
        'lsblk_model': 'KINGSTON SA400S3',
        'serial': '50026B768317883A',
        'by_id': '/dev/disk/by-id/ata-KINGSTON_SA400S37240G_50026B768317883A',
        'pv_uuid': '0dfQpA-3dLn-qbHp-J4Gr-z225-mxP7-RKDvW4',
        'vg': 'ceph-f3254fb3-99c7-4032-a11f-4af12cf6ce54',
        'lv': 'osd-block-3de29db8-a302-4b43-aaa1-c7502051e1bf',
    },
}
DISK_BYTES = 240057409536  # Reported User Capacity on all three SATA SSDs.


def output(argv):
    return subprocess.check_output(argv, text=True, env={**os.environ, 'LC_ALL': 'C'})


def walk(device):
    yield device
    for child in device.get('children', []):
        yield from walk(child)


def lvm_rows(command, fields, section):
    argv = [command, '--reportformat', 'json', '-o', fields]
    if command == 'lvs':
        argv.append('--all')
    data = json.loads(output(argv))
    return [{key: str(value).strip() for key, value in row.items()}
            for report in data['report'] for row in report.get(section, [])]


def open_block_devices(devices):
    """Detect raw block-device FDs as well as mounted-filesystem/DM checks."""
    numbers = {os.stat(name).st_rdev: name for name in devices}
    found = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            for fd in (proc / 'fd').iterdir():
                try:
                    info = fd.stat()
                    if stat.S_ISBLK(info.st_mode) and info.st_rdev in numbers:
                        found.append(f'pid={proc.name} {numbers[info.st_rdev]}')
                except (FileNotFoundError, ProcessLookupError):
                    continue
        except (FileNotFoundError, ProcessLookupError):
            continue
    return found


def collect(node):
    target = TARGETS[node]
    by_id = Path(target['by_id'])
    if not by_id.is_symlink():
        raise ValueError(f'Missing stable disk symlink: {by_id}')
    real = str(by_id.resolve(strict=True))
    if not stat.S_ISBLK(os.stat(real).st_mode):
        raise ValueError('Target is not a block device')
    tree = json.loads(output([
        'lsblk', '--json', '--bytes', '--paths', '--output',
        'NAME,KNAME,TYPE,SIZE,RO,SERIAL,MODEL,FSTYPE,MOUNTPOINTS,MAJ:MIN', real,
    ]))['blockdevices']
    root_source = output(['findmnt', '--noheadings', '--output', 'SOURCE', '--target', '/']).strip()
    if not root_source.startswith('/dev/') or '[' in root_source:
        raise ValueError(f'Unsupported root-device layout: {root_source}')
    root_tree = json.loads(output([
        'lsblk', '--json', '--paths', '--inverse', '--output', 'NAME,TYPE', root_source,
    ]))['blockdevices']
    root_disks = sorted({item['name'] for root in root_tree for item in walk(root)
                         if item['type'] == 'disk'})
    devices = [item for root in tree for item in walk(root)]
    holders = {}
    for item in devices:
        directory = Path('/sys/class/block') / Path(item['kname']).name / 'holders'
        holders[item['name']] = [p.name for p in directory.iterdir()]
    dm_open = {}
    for line in output(['dmsetup', 'info', '--columns', '--noheadings', '--separator', ':',
                        '-o', 'major,minor,open']).splitlines():
        if not line.strip():
            continue
        major, minor, count = [part.strip() for part in line.split(':')]
        number = f'{int(major)}:{int(minor)}'
        if number in {item['maj:min'] for item in devices}:
            dm_open[number] = int(count)
    addresses = json.loads(output(['ip', '--json', 'address', 'show', 'dev', 'enp0s31f6']))
    return {
        'hostname': socket.gethostname().split('.')[0], 'real': real, 'tree': tree,
        'ips': [entry['local'] for interface in addresses for entry in interface['addr_info']],
        'root_source': root_source, 'root_disks': root_disks,
        'pvs': lvm_rows('pvs', 'pv_name,pv_uuid,vg_name', 'pv'),
        'lvs': lvm_rows('lvs', 'vg_name,lv_name,lv_path,lv_attr,segtype', 'lv'),
        'signatures': json.loads(output(['wipefs', '--json', '--output', 'TYPE,OFFSET', real]))['signatures'],
        'holders': holders, 'dm_open': dm_open,
        'open_devices': open_block_devices([item['name'] for item in devices]),
    }


def check(node, state):
    """Fail closed on any identity, topology, ownership, or current-use change."""
    target = TARGETS[node]
    if state['hostname'] != node or target['ip'] not in state['ips']:
        raise ValueError('Host name/management IP does not match the selected node')
    if len(state['tree']) != 1:
        raise ValueError('Expected exactly one whole disk')
    disk = state['tree'][0]
    if disk['type'] != 'disk' or disk['name'] != state['real'] or 'nvme' in state['real']:
        raise ValueError('Target must be the recorded whole SATA disk')
    if str(disk.get('serial', '')).strip() != target['serial']:
        raise ValueError('Disk serial changed')
    model = str(disk.get('model', '')).strip()
    if model != target['lsblk_model']:
        raise ValueError(f'Disk Linux model mismatch: expected={target["lsblk_model"]!r}, observed={model!r}')
    if int(disk['size']) != DISK_BYTES:
        raise ValueError(f'Disk capacity mismatch: expected={DISK_BYTES} bytes, observed={disk["size"]!r} bytes')
    if not state['root_disks'] or state['real'] in state['root_disks']:
        raise ValueError('Target backs Ubuntu, or Ubuntu ancestors could not be established')
    devices = list(walk(disk))
    for item in devices:
        if item.get('ro') not in (False, 0):
            raise ValueError('Read-only or unknown device state')
        if any(item.get('mountpoints') or []):
            raise ValueError('Mounted filesystem or active swap on target')
    if state['open_devices']:
        raise ValueError(f'Block device is open: {state["open_devices"]}')
    known_names = {Path(item['kname']).name for item in devices}
    for holders in state['holders'].values():
        if any(name not in known_names for name in holders):
            raise ValueError('Unexpected device-mapper/RAID holder')
    selected_pvs = [pv for pv in state['pvs'] if os.path.realpath(pv['pv_name']) == state['real']]
    if not selected_pvs:
        if len(devices) == 1 and not disk.get('fstype') and not state['signatures'] and not any(state['holders'].values()):
            return 'blank'
        raise ValueError('Unexpected or partially removed storage; review before resuming')
    if len(selected_pvs) != 1:
        raise ValueError('Ambiguous PV ownership')
    pv = selected_pvs[0]
    if pv['vg_name'] != target['vg'] or pv['pv_uuid'] != target['pv_uuid']:
        raise ValueError('PV UUID/VG ownership changed; only the recorded Ceph allocation is allowed')
    if len([pv for pv in state['pvs'] if pv['vg_name'] == target['vg']]) != 1:
        raise ValueError('Ceph VG spans additional physical volumes')
    volumes = [lv for lv in state['lvs'] if lv['vg_name'] == target['vg']]
    if len(volumes) != 1:
        raise ValueError('Expected exactly one recorded Ceph LV')
    lv = volumes[0]
    expected_path = f'/dev/{target["vg"]}/{target["lv"]}'
    if lv['lv_name'] != target['lv'] or lv['lv_path'] != expected_path or lv['segtype'] != 'linear':
        raise ValueError('Ceph LV name/path/layout changed')
    attr = lv['lv_attr']
    if len(attr) < 6 or attr[0] != '-' or attr[4] != 'a' or attr[5] != '-':
        raise ValueError('Ceph LV must be a normal active, unopened LV; no force activation/removal')
    if len(devices) != 2 or devices[1]['type'] != 'lvm' or os.path.realpath(expected_path) != os.path.realpath(devices[1]['name']):
        raise ValueError('Unexpected children/partitions under the Ceph disk')
    child = devices[1]
    if child.get('fstype') != 'ceph_bluestore' or disk.get('fstype') != 'LVM2_member':
        raise ValueError('Expected the recorded Ceph BlueStore/LVM signatures')
    if state['dm_open'].get(child['maj:min']) != 0:
        raise ValueError('Ceph LV is open, or its device-mapper open count is unknown')
    return 'ceph'


def commands(node):
    target = TARGETS[node]
    lv_path = f'/dev/{target["vg"]}/{target["lv"]}'
    return [
        ['wipefs', '--all', '--lock=yes', lv_path],
        ['lvremove', '--yes', f'{target["vg"]}/{target["lv"]}'],
        ['vgremove', '--yes', target['vg']],
        ['pvremove', '--yes', target['by_id']],
        ['wipefs', '--all', '--lock=yes', target['by_id']],
    ]


def reset(node, apply=False):
    state = collect(node)
    target = TARGETS[node]
    print(f'\nStage 0: {node} ({target["ip"]})', flush=True)
    print(f'Mode: {"APPLY REQUESTED; validation and confirmation required" if apply else "PLAN ONLY"}', flush=True)
    print('Identity observations before validation:', flush=True)
    print(f'  Recorded full model (SMART): {target["model"]!r}', flush=True)
    print(f'  Expected Linux model (lsblk): {target["lsblk_model"]!r}', flush=True)
    print(f'  Expected serial: {target["serial"]!r}; expected capacity: {DISK_BYTES} bytes', flush=True)
    for disk in state['tree']:
        print(f'  Observed Linux model: {disk.get("model")!r}', flush=True)
        print(f'  Observed serial: {disk.get("serial")!r}; observed capacity: {disk.get("size")!r} bytes', flush=True)
    print(f'Stable target: {target["by_id"]} -> {state["real"]}', flush=True)
    print(f'Ubuntu: {state["root_source"]}; parent disks={state["root_disks"]}', flush=True)
    for disk in state['tree']:
        for item in walk(disk):
            print(f'  {item["name"]}: type={item["type"]} filesystem={item.get("fstype")} mounts={item.get("mountpoints")}', flush=True)
    status = check(node, state)
    print('All target, ownership and current-use checks passed.', flush=True)
    if status == 'blank':
        print(f'RESULT {node}: ALREADY_BLANK; no change', flush=True)
        return
    print(f'Ownership: PV {target["pv_uuid"]} -> {target["vg"]} -> {target["lv"]}', flush=True)
    print('Exact removal commands:', flush=True)
    for command in commands(node):
        print('  ' + shlex.join(command), flush=True)
    if not apply:
        print(f'RESULT {node}: PLAN_ONLY; no change', flush=True)
        return
    token = f'ERASE {node} {target["serial"]}'
    if input(f'Type {token} to approve these commands on this target: ') != token:
        raise ValueError('Cancelled; target was not changed')
    # Check again after the user reads the plan. Do not act on a stale snapshot.
    latest = collect(node)
    if check(node, latest) != 'ceph' or latest != state:
        raise ValueError('Device state changed during confirmation; rerun and review')
    for command in commands(node):
        print('+ ' + shlex.join(command), flush=True)
        subprocess.run(command, check=True)
    subprocess.run(['udevadm', 'settle', '--timeout=10'], check=True)
    after = collect(node)
    if check(node, after) != 'blank' or after['root_disks'] != state['root_disks'] or after['root_source'] != state['root_source']:
        raise ValueError('Post-check did not establish blank SATA plus unchanged Ubuntu backing')
    print(f'RESULT {node}: CLEANED; SATA has no detected signatures/PV/children; Ubuntu backing unchanged', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node', required=True, choices=TARGETS)
    parser.add_argument('--apply', action='store_true', help='Print exact plan, then require this node/serial confirmation')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise ValueError('Run through reset-ceph.sh so sudo can inspect protected device state')
    for tool in ['lsblk', 'findmnt', 'pvs', 'lvs', 'wipefs', 'dmsetup', 'ip', 'lvremove', 'vgremove', 'pvremove', 'udevadm']:
        if not shutil.which(tool):
            raise ValueError(f'Missing required tool: {tool}; no cleanup attempted')
    reset(args.node, args.apply)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError, EOFError, KeyboardInterrupt) as exc:
        print(f'STOP: {exc}. Review the report before another run.', file=sys.stderr, flush=True)
        sys.exit(1)
