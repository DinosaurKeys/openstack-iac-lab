#!/usr/bin/env bash
# Read-only remote discovery. Does not install, configure, stop or erase anything.
set -euo pipefail
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
report_dir="$repo_dir/build/discovery-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$report_dir"
chmod 700 "$report_dir"
for ip in 192.168.0.200 192.168.0.201 192.168.0.202; do
  ssh -o BatchMode=yes -o ConnectTimeout=8 "openstack@$ip" 'bash -s' > "$report_dir/$ip.txt" <<'REMOTE'
set -u
hostnamectl
ip -br address
ip -br link
ip route
resolvectl dns
lsblk -e7 -o NAME,PATH,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL,SERIAL
ls -l /dev/disk/by-id/
timedatectl status
free -h
test ! -e /dev/kvm || ls -l /dev/kvm
if sudo -n true 2>/dev/null; then
  sudo -n pvs -o pv_name,vg_name,pv_size
  sudo -n vgs
  if command -v smartctl >/dev/null; then sudo -n smartctl --scan; fi
else
  printf 'Privileged disk inspection skipped: passwordless sudo is unavailable.\n'
fi
REMOTE
  chmod 600 "$report_dir/$ip.txt"
done
printf 'Private read-only reports: %s\n' "$report_dir"
