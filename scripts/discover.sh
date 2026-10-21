#!/usr/bin/env bash
# Read-only remote discovery. Does not install, configure, stop or erase anything.
set -euo pipefail
usage() {
  printf 'Usage: bash scripts/discover.sh SSH_USERNAME [NODE_IP ...]\n'
  printf 'Example (node1 only): bash scripts/discover.sh joe 192.168.0.200\n'
  printf 'With no IP arguments, collect all three lab nodes. SSH passwords are allowed.\n'
}
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
  usage
  exit 0
fi
if (( $# == 0 )) || [[ -z "$1" ]]; then
  usage >&2
  exit 2
fi
ssh_user=$1
shift
nodes=("$@")
if (( ${#nodes[@]} == 0 )); then
  nodes=(192.168.0.200 192.168.0.201 192.168.0.202)
fi
for ip in "${nodes[@]}"; do
  case "$ip" in
    192.168.0.200|192.168.0.201|192.168.0.202) ;;
    *) printf 'Not a lab node IP: %s\n' "$ip" >&2; exit 2 ;;
  esac
done
umask 077
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$repo_dir/build"
report_dir=$(mktemp -d "$repo_dir/build/discovery-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
failed=0
for ip in "${nodes[@]}"; do
  printf 'Collecting %s@%s (SSH may ask for this account\047s password)...\n' "$ssh_user" "$ip"
  if ssh -o BatchMode=no -o ConnectTimeout=8 -l "$ssh_user" "$ip" 'bash -s' > "$report_dir/$ip.txt" <<'REMOTE'
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
  then
    printf 'Saved: %s/%s.txt\n' "$report_dir" "$ip"
  else
    printf 'Discovery failed for %s@%s; its report may be incomplete.\n' "$ssh_user" "$ip" >&2
    printf 'Check login first: ssh %s@%s\n' "$ssh_user" "$ip" >&2
    printf 'For a changed host key, verify its fingerprint at that node\047s console before replacing the saved entry.\n' >&2
    failed=1
  fi
done
printf 'Private read-only reports: %s\n' "$report_dir"
exit "$failed"
