#!/usr/bin/env python3
"""Offline checks for source syntax, relative document links, and fixed addresses."""
import ast
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def main():
    counts = {'yaml': 0, 'json': 0, 'python': 0, 'markdown': 0}
    for path in ROOT.rglob('*'):
        if not path.is_file() or any(part in {'build', 'private', '.git', '.terraform', '__pycache__'} for part in path.parts):
            continue
        if path.suffix in {'.yml', '.yaml'} or path.name.endswith(('.yml.example', '.yaml.example')):
            yaml.safe_load(path.read_text())
            counts['yaml'] += 1
        elif path.suffix == '.json':
            json.loads(path.read_text())
            counts['json'] += 1
        elif path.suffix == '.py':
            ast.parse(path.read_text(), filename=str(path))
            counts['python'] += 1
        elif path.suffix == '.md':
            text = path.read_text()
            if text.count('```') % 2:
                raise ValueError(f'Unbalanced Markdown fences: {path}')
            for link in re.findall(r'\]\(([^)]+)\)', text):
                if '://' not in link and not link.startswith('#'):
                    target = (path.parent / link.split('#')[0]).resolve()
                    if not target.exists():
                        raise ValueError(f'Broken relative link: {path}: {link}')
            counts['markdown'] += 1
    inventory = yaml.safe_load((ROOT / 'ansible/inventory/hosts.yml').read_text())
    nodes = inventory['all']['children']['lab_nodes']['hosts']
    expected = {'node1': '192.168.0.200', 'node2': '192.168.0.201', 'node3': '192.168.0.202'}
    if {key: value['ansible_host'] for key, value in nodes.items()} != expected:
        raise ValueError('Fixed node IPs were changed')
    dashboards = ROOT / 'ansible/roles/monitoring/files'
    if len(list(dashboards.glob('*.json'))) != 3:
        raise ValueError('Expected exactly three dashboards')
    alerts = yaml.safe_load((dashboards / 'alerts.yml').read_text())
    if sum(len(group['rules']) for group in alerts['groups']) != 2:
        raise ValueError('Expected exactly two alert rules')
    print(json.dumps(counts, sort_keys=True))


if __name__ == '__main__':
    main()
