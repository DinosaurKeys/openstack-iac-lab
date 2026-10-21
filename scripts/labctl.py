#!/usr/bin/env python3
"""Explicit entry points for the lab. No action implies running every stage."""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from configure import ROOT, validate

WORKLOADS = {'first': '01-first-workload', 'app': '02-application', 'monitor': '03-monitoring'}


def run(argv, **kwargs):
    print('+ ' + ' '.join(map(str, argv)), flush=True)
    return subprocess.run(list(map(str, argv)), check=True, cwd=ROOT, **kwargs)


def config(path, include_workloads=True):
    if not path.is_file():
        raise SystemExit('Copy config/lab.yml.example to private/lab.yml first.')
    cfg = yaml.safe_load(path.read_text())
    errors = validate(cfg, include_workloads=include_workloads)
    if errors:
        raise SystemExit('\n'.join(errors))
    return cfg


def inventory_args():
    return ['-i', ROOT / 'build/inventory.yml']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'private/lab.yml')
    parser.add_argument('--ask-become-pass', action='store_true')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ['doctor', 'discover', 'configure', 'preflight', 'base', 'netplan', 'init-config', 'storage', 'init-cloud']:
        entry = sub.add_parser(name)
        if name == 'discover':
            entry.add_argument('--ssh-user', required=True, help='Actual Ubuntu login account on the selected nodes')
            entry.add_argument('nodes', nargs='*', help='Optional lab node IPs; default is all three nodes')
        if name == 'configure':
            entry.add_argument('--hosts-only', action='store_true')
    kolla = sub.add_parser('kolla')
    kolla.add_argument('action', choices=['bootstrap-servers', 'prechecks', 'pull', 'deploy', 'post-deploy', 'check'])
    tf = sub.add_parser('terraform')
    tf.add_argument('workload', choices=list(WORKLOADS))
    tf.add_argument('action', choices=['init', 'validate', 'plan', 'apply', 'outputs'])
    sub.add_parser('application')
    sub.add_parser('monitoring')
    args = parser.parse_args()
    if args.command == 'doctor':
        missing = []
        for name in ['python3', 'ssh', 'git', 'ansible-playbook', 'ansible-inventory', 'kolla-ansible', 'openstack', 'terraform']:
            path = shutil.which(name)
            print(f'{name}: {path or "MISSING"}')
            if not path:
                missing.append(name)
        raise SystemExit(bool(missing))
    if args.command == 'discover':
        run(['bash', ROOT / 'scripts/discover.sh', args.ssh_user, *args.nodes])
        return
    require_workloads = args.command in ['terraform', 'application', 'monitoring'] or (args.command == 'configure' and not args.hosts_only)
    cfg = config(args.config, include_workloads=require_workloads)
    if args.command == 'configure':
        extra = ['--hosts-only'] if args.hosts_only else []
        run([sys.executable, ROOT / 'scripts/configure.py', '--config', args.config, *extra])
        return
    if not (ROOT / 'build/inventory.yml').exists():
        raise SystemExit('Run configure before this stage.')
    become = ['--ask-become-pass'] if args.ask_become_pass else []
    if args.command in ['preflight', 'base', 'netplan']:
        if args.command == 'base' and cfg.get('fresh_install_confirmed') is not True:
            raise SystemExit('Confirm the three fresh Ubuntu installs in private/lab.yml before base preparation.')
        playbook = {'preflight': 'preflight.yml', 'base': 'base.yml', 'netplan': 'render-netplan.yml'}[args.command]
        run(['ansible-playbook', *inventory_args(), ROOT / 'ansible/playbooks' / playbook, *become])
        return
    config_dir = Path.home() / '.config/kolla-iac-lab'
    if args.command == 'init-config':
        config_dir.mkdir(parents=True, exist_ok=True)
        config_dir.chmod(0o700)
        shutil.copy2(ROOT / 'build/globals.yml', config_dir / 'globals.yml')
        passwords = config_dir / 'passwords.yml'
        if not passwords.exists():
            sample = Path.home() / 'venvs/kolla-iac/share/kolla-ansible/etc_examples/kolla/passwords.yml'
            shutil.copy2(sample, passwords)
            passwords.chmod(0o600)
            run(['kolla-genpwd', '-p', passwords])
        print(f'Updated new-project globals; existing new-project passwords preserved: {config_dir}')
        return
    if args.command == 'storage':
        expected = cfg['storage']['host'] + ':' + cfg['storage']['expected_serial']
        print('This creates cinder-volumes on the selected blank data disk. It refuses mounted or already-owned disks.')
        if input(f'Type {expected} to approve this target: ') != expected:
            raise SystemExit('Storage action cancelled.')
        run(['ansible-playbook', *inventory_args(), ROOT / 'ansible/playbooks/storage.yml',
             '-e', 'storage_prepare_approved=true', *become])
        return
    if args.command == 'kolla':
        if cfg.get('fresh_install_confirmed') is not True:
            raise SystemExit('Confirm the fresh OS baseline before Kolla operations.')
        if not (config_dir / 'passwords.yml').is_file():
            raise SystemExit('Run init-config first.')
        env = os.environ.copy()
        if args.ask_become_pass:
            env['ANSIBLE_BECOME_ASK_PASS'] = 'True'
        run(['kolla-ansible', args.action, '-i', ROOT / 'build/kolla-inventory.yml', '--configdir', config_dir], env=env)
        return
    if args.command == 'init-cloud':
        run([sys.executable, ROOT / 'scripts/init-cloud.py', '--config', args.config])
        return
    if args.command == 'terraform':
        directory = ROOT / 'terraform' / WORKLOADS[args.workload]
        if args.workload == 'monitor' and args.action == 'plan':
            app = ROOT / 'terraform/02-application'
            ip = subprocess.check_output(['terraform', f'-chdir={app}', 'output', '-raw', 'app_private_ip'], text=True).strip()
            vars_path = directory / 'terraform.tfvars.json'
            values = json.loads(vars_path.read_text())
            values['app_private_ip'] = ip
            vars_path.write_text(json.dumps(values, indent=2) + '\n')
        base = ['terraform', f'-chdir={directory}']
        if args.action == 'init':
            run([*base, 'init', '-input=false'])
        elif args.action == 'validate':
            run([*base, 'validate'])
        elif args.action == 'plan':
            run([*base, 'plan', '-input=false', '-out=tfplan'])
            run([*base, 'show', 'tfplan'])
        elif args.action == 'apply':
            if not (directory / 'tfplan').is_file():
                raise SystemExit('Create and review the saved plan first.')
            if input(f'Type apply:{args.workload} to apply the reviewed saved plan: ') != 'apply:' + args.workload:
                raise SystemExit('Apply cancelled.')
            run([*base, 'apply', 'tfplan'])
            (directory / 'tfplan').unlink(missing_ok=True)
        else:
            run([*base, 'output'])
        if args.action in ['apply', 'outputs'] and args.workload in ['app', 'monitor']:
            content = subprocess.check_output([*base, 'output', '-json', 'ansible_inventory'], text=True)
            dest = ROOT / 'build' / ('application.inventory.json' if args.workload == 'app' else 'monitoring.inventory.json')
            dest.write_text(content)
            dest.chmod(0o600)
        return
    vault = ROOT / 'private' / (args.command + '.vault.yml')
    if not vault.is_file():
        raise SystemExit(f'Create the private vault file first: {vault}')
    if args.command == 'application':
        inventories = ['-i', ROOT / 'build/application.inventory.json']
    else:
        inventories = [*inventory_args(), '-i', ROOT / 'build/application.inventory.json', '-i', ROOT / 'build/monitoring.inventory.json']
    run(['ansible-playbook', *inventories, ROOT / 'ansible/playbooks' / (args.command + '.yml'),
         '-e', '@' + str(vault), '--ask-vault-pass', *become])


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode)
