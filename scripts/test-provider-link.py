#!/usr/bin/env python3
"""Stage 0: measure one recorded, unused USB NIC and restore its DOWN state."""
import argparse
import json
import os
import signal
import socket
import subprocess
import time
from pathlib import Path

TARGETS = {
    'node1': ('192.168.0.200', '00:23:24:eb:e0:0b', '00:e0:4c:55:7e:58'),
    'node2': ('192.168.0.201', '00:23:24:eb:f5:01', '00:e0:4c:2c:16:78'),
    'node3': ('192.168.0.202', '00:23:24:eb:df:ea', '00:e0:4c:30:46:88'),
}
MANAGEMENT = 'enp0s31f6'


def run(argv, allowed=(0,)):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=15, check=False)
    if result.returncode not in allowed:
        raise ValueError(f'{argv[0]} failed ({result.returncode}): {result.stderr.strip()}')
    return result.stdout.strip()


def read(path):
    return Path(path).read_text().strip()


def nic_state(iface):
    path = Path('/sys/class/net') / iface
    return {
        'name': iface, 'mac': read(path / 'address'), 'index': int(read(path / 'ifindex')),
        'up': bool(int(read(path / 'flags'), 16) & 1),
        'usb': (path / 'device/subsystem').resolve().name == 'usb',
        'uppers': [p.name for p in path.glob('upper_*')],
        'master': (path / 'master').exists(),
        'addresses': json.loads(run(['ip', '-j', 'address', 'show', 'dev', iface]))[0]['addr_info'],
    }


def network_setup(iface):
    output = run(['networkctl', '--no-pager', '--no-legend', '--full', 'list', iface])
    rows = []
    for line in output.splitlines():
        fields = line.replace('●', '').split()
        if len(fields) == 5 and fields[0].isdigit() and fields[1] == iface:
            rows.append(fields[-1])
    if len(rows) != 1:
        raise ValueError('Cannot read the USB networkctl setup state: ' + output)
    return rows[0]


def collect(node):
    matches = [p.name for p in Path('/sys/class/net').iterdir() if read(p / 'address') == TARGETS[node][2]]
    if len(matches) != 1:
        raise ValueError(f'Expected exactly one USB MAC {TARGETS[node][2]}; found {len(matches)}')
    provider = nic_state(matches[0])
    ipv6_path = Path('/proc/sys/net/ipv6/conf') / provider['name'] / 'disable_ipv6'
    return {
        'hostname': socket.gethostname().split('.')[0],
        'management': nic_state(MANAGEMENT), 'provider': provider,
        'routes': {family: json.loads(run(['ip', '-j', family, 'route', 'show', 'table', 'all']))
                   for family in ['-4', '-6']},
        'setup': network_setup(provider['name']),
        'network_manager': run(['systemctl', 'is-active', 'NetworkManager.service'], allowed=(0, 3, 4)),
        'ipv6_disabled': read(ipv6_path) if ipv6_path.exists() else None,
    }


def route_uses(route, iface):
    return route.get('dev') == iface or any(route_uses(hop, iface) for hop in route.get('nexthops', []))


def validate(node, state):
    expected_ip, management_mac, provider_mac = TARGETS[node]
    management, provider = state['management'], state['provider']
    if state['hostname'] != node:
        raise ValueError('Hostname differs from the selected node')
    if management['name'] != MANAGEMENT or management['mac'] != management_mac or not management['up']:
        raise ValueError('Management NIC identity/state differs from discovery')
    if not any(a['family'] == 'inet' and a['local'] == expected_ip and a['prefixlen'] == 24
               for a in management['addresses']):
        raise ValueError('Preserved management address was not found')
    if provider['name'] == MANAGEMENT or provider['index'] == management['index']:
        raise ValueError('Provider target is the management interface')
    if provider['mac'] != provider_mac or not provider['usb']:
        raise ValueError('Provider identity is not the recorded USB adapter')
    if provider['up'] or provider['addresses'] or provider['master'] or provider['uppers']:
        raise ValueError('USB must be DOWN, without addresses, master or upper interfaces')
    if any(route_uses(r, provider['name']) for routes in state['routes'].values() for r in routes):
        raise ValueError('A route already uses the USB interface')
    if state['setup'] != 'unmanaged' or state['network_manager'] not in {'inactive', 'unknown'}:
        raise ValueError('USB network ownership needs review: networkctl=' + state['setup']
                         + '; NetworkManager=' + state['network_manager'])
    if state['ipv6_disabled'] not in {'0', '1', None}:
        raise ValueError('Unexpected USB IPv6 setting')


def stable_snapshot(state):
    # Ignore countdowns/caches, while comparing address identity and every route's other fields.
    addresses = [{k: a.get(k) for k in ['family', 'local', 'prefixlen', 'scope', 'peer']}
                 for a in state['management']['addresses']]
    def stable(value):
        if isinstance(value, dict):
            return {k: stable(v) for k, v in value.items() if k not in {'expires', 'cache'}}
        if isinstance(value, list):
            return [stable(v) for v in value]
        return value
    return (sorted(json.dumps(a, sort_keys=True) for a in addresses),
            {family: sorted(json.dumps(stable(r), sort_keys=True) for r in routes)
             for family, routes in state['routes'].items()})


def assert_identity(provider):
    path = Path('/sys/class/net') / provider['name']
    if read(path / 'address') != provider['mac'] or int(read(path / 'ifindex')) != provider['index']:
        raise ValueError('USB identity changed; refusing a write to a different device')


def set_ipv6(provider, value):
    assert_identity(provider)
    path = Path('/proc/sys/net/ipv6/conf') / provider['name'] / 'disable_ipv6'
    print(f"+ USB-only disable_ipv6={value}", flush=True)
    path.write_text(value + '\n')


def set_link(provider, state):
    assert_identity(provider)
    argv = ['ip', 'link', 'set', 'dev', provider['name'], state]
    print('+ ' + ' '.join(argv), flush=True)
    run(argv)


def measurement(provider):
    path = Path('/sys/class/net') / provider['name']
    values = {}
    for field in ['carrier', 'speed', 'duplex']:
        try:
            values[field] = read(path / field)
        except OSError:
            values[field] = 'unavailable'
    return values


def wait_for_link(provider):
    # Allow up to 12 seconds for USB negotiation. No IP traffic is generated.
    deadline = time.monotonic() + 12
    values = measurement(provider)
    while time.monotonic() < deadline:
        if values['carrier'] == '1' and values['speed'].isdigit() and values['duplex'] in {'full', 'half'}:
            return values
        time.sleep(0.5)
        values = measurement(provider)
    return values


def verify_restored(node, before, after):
    validate(node, after)
    if after['provider']['name'] != before['provider']['name'] or after['provider']['index'] != before['provider']['index']:
        raise ValueError('Provider interface identity changed during the test')
    if after['ipv6_disabled'] != before['ipv6_disabled']:
        raise ValueError('USB IPv6 setting was not restored')
    if stable_snapshot(after) != stable_snapshot(before):
        raise ValueError('Management addresses or routes differ after the test; review the report')


def test_link(node, apply=False):
    before = collect(node)
    validate(node, before)
    provider = before['provider']
    print(f"Stage 0 USB link test: {node} ({TARGETS[node][0]})", flush=True)
    print(f"Target: {provider['name']}; MAC {provider['mac']}; networkctl {before['setup']}", flush=True)
    print('Plan: temporarily UP, read carrier/speed/duplex, restore DOWN and USB IPv6 setting.', flush=True)
    print('No rename, DHCP request, static IP, Netplan edit or disk action is issued.', flush=True)
    if not apply:
        print(f'RESULT {node}: PLAN_ONLY; no writes performed', flush=True)
        return 0
    # Recheck ownership and identity immediately before the first write.
    current = collect(node)
    validate(node, current)
    if current != before:
        # Lifetimes may count down; compare only values relevant to writes and routing.
        if (current['provider'] != before['provider'] or current['ipv6_disabled'] != before['ipv6_disabled']
                or stable_snapshot(current) != stable_snapshot(before)):
            raise ValueError('Network state changed before activation; rerun after review')
    failure = None
    values = None
    try:
        if before['ipv6_disabled'] == '0':
            set_ipv6(provider, '1')
        set_link(provider, 'up')
        values = wait_for_link(provider)
        print('Measured: carrier={carrier}; speed_Mbps={speed}; duplex={duplex}'.format(**values), flush=True)
    except (Exception, KeyboardInterrupt) as exc:
        failure = exc
    finally:
        # A second handled interruption must not abort restoration half way through.
        previous = {s: signal.signal(s, signal.SIG_IGN) for s in [signal.SIGHUP, signal.SIGTERM, signal.SIGINT]}
        try:
            set_link(provider, 'down')
            if before['ipv6_disabled'] == '0':
                set_ipv6(provider, '0')
            verify_restored(node, before, collect(node))
            print('RESTORED: USB DOWN; IPv6 setting restored; management addresses/routes unchanged.', flush=True)
        except Exception as exc:
            raise ValueError('RESTORATION NOT VERIFIED: ' + str(exc)) from exc
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
    if failure is not None:
        raise ValueError('Test interrupted/failed after restoration: ' + str(failure)) from failure
    if values == {'carrier': '1', 'speed': '1000', 'duplex': 'full'}:
        print(f'RESULT {node}: LINK_OK; 1000 Mb/s full duplex; restored DOWN', flush=True)
        return 0
    print(f'RESULT {node}: REVIEW; inspect the measured link; restored DOWN', flush=True)
    return 3


def interrupted(signum, frame):
    raise KeyboardInterrupt(f'signal {signum}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node', choices=TARGETS, required=True)
    parser.add_argument('--apply', action='store_true', help='Permit the temporary USB-only link test')
    args = parser.parse_args()
    os.environ.update(LC_ALL='C', SYSTEMD_COLORS='0', SYSTEMD_PAGER='cat')
    if os.geteuid() != 0:
        parser.error('Run through test-provider-link.sh; protected observations require sudo')
    for sig in [signal.SIGHUP, signal.SIGTERM, signal.SIGINT]:
        signal.signal(sig, interrupted)
    try:
        return test_link(args.node, args.apply)
    except (Exception, KeyboardInterrupt) as exc:
        print('STOP: ' + str(exc), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
