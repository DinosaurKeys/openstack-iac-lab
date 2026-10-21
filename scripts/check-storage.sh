#!/usr/bin/env bash
# Stage 0: one storage inspection for all three nodes, driven from Hermes.
# Disk commands inspect only. --install-tools permits missing diagnostic packages.
set -euo pipefail

usage() {
  printf 'Usage: bash scripts/check-storage.sh SSH_USERNAME [--install-tools]\n'
  printf 'Example: bash scripts/check-storage.sh joe --install-tools\n'
  printf 'Checks node1/node2/node3 and saves one private report on Hermes.\n'
  printf 'Without --install-tools, missing tools are reported but not installed.\n'
}
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
  usage
  exit 0
fi
if (( $# < 1 || $# > 2 )) || [[ -z "$1" ]]; then
  usage >&2
  exit 2
fi
ssh_user=$1
install_tools=0
if (( $# == 2 )); then
  if [[ "$2" != --install-tools ]]; then
    usage >&2
    exit 2
  fi
  install_tools=1
fi
if [[ ! -t 0 ]]; then
  printf 'Run this script directly in an interactive Hermes terminal; SSH/sudo may need passwords.\n' >&2
  exit 2
fi

# Send code as the SSH command, leaving terminal input available for sudo.
# Feeding a script through an SSH heredoc would compete with password input.
remote_body=$(cat <<'REMOTE'
set -uo pipefail
export LC_ALL=C
install_tools=$1
review=0
check() {
  local label=$1 rc=0
  shift
  printf '\n--- %s ---\n' "$label"
  "$@" || rc=$?
  if (( rc != 0 )); then
    printf 'REVIEW: command exit=%s; inspect the output above.\n' "$rc"
    review=1
  fi
  return "$rc"
}
printf 'Stage 0 storage inspection: %s\n' "$(hostname)"
printf 'UTC: %s\n' "$(date -u +%FT%TZ)"
if (( install_tools == 1 )); then
  packages=()
  command -v smartctl >/dev/null || packages+=(smartmontools)
  if ! command -v pvs >/dev/null || ! command -v vgs >/dev/null || ! command -v lvs >/dev/null; then
    packages+=(lvm2)
  fi
  if (( ${#packages[@]} )); then
    if check 'Refresh package index' apt-get update; then
      check 'Install missing diagnostic packages' apt-get -o Dpkg::Use-Pty=0 install -y --no-install-recommends "${packages[@]}"
    fi
  else
    printf 'Diagnostic tools already installed; no package operation needed.\n'
  fi
fi

check 'Disk tree: identity, filesystems and mountpoints' lsblk -e7 -o NAME,PATH,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL,SERIAL
check 'Mounted filesystems' findmnt -rn -o TARGET,SOURCE,FSTYPE
check 'Active swap' swapon --show
check 'Stable disk IDs' ls -l /dev/disk/by-id/
check 'Physical volumes: which disk belongs to which volume group' pvs -o pv_name,pv_uuid,vg_name,pv_size,pv_free
check 'Volume groups: allocated and free capacity' vgs -o vg_name,vg_size,vg_free,pv_count,lv_count
check 'Logical volumes: backing devices and activation state' lvs -a -o lv_path,vg_name,lv_attr,devices

# Enumerate actual whole disks. No guessed /dev/sda target and no changes to disks.
if disk_list=$(lsblk --nodeps --noheadings --paths --exclude 7 --output NAME,TYPE); then
  disk_count=0
  while read -r disk kind; do
    [[ "$kind" == disk ]] || continue
    disk_count=$((disk_count + 1))
    check "Existing signatures on $disk (inspection only)" wipefs --no-act "$disk"
    check "SMART attributes and existing logs for $disk" smartctl -a "$disk"
  done <<< "$disk_list"
  if (( disk_count == 0 )); then
    printf 'REVIEW: no physical disks were enumerated.\n'
    review=1
  fi
else
  printf 'REVIEW: whole-disk enumeration failed.\n'
  review=1
fi
printf '\nINSPECTION_END: %s review=%s\n' "$(hostname)" "$review"
printf 'Review the full evidence; this script does not certify health or approve disk reuse.\n'
exit "$review"
REMOTE
)
# POSIX single-quote escaping works regardless of the account's login shell.
quoted_body=${remote_body//\'/\'\\\'\'}
remote_command="sudo -- bash -c '$quoted_body' -- $install_tools"

umask 077
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$repo_dir/build"
report_dir=$(mktemp -d "$repo_dir/build/storage-health-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
report="$report_dir/report.txt"
printf 'Stage 0: three-node storage inspection\nUTC: %s\nInstall missing tools: %s\n' "$(date -u +%FT%TZ)" "$install_tools" > "$report"
overall=0
for ip in 192.168.0.200 192.168.0.201 192.168.0.202; do
  printf '\nCollecting %s@%s. SSH and sudo may each ask for this node\047s password.\n' "$ssh_user" "$ip"
  node_report="$report_dir/$ip.txt"
  if ssh -t -o BatchMode=no -o ConnectTimeout=8 -l "$ssh_user" "$ip" "$remote_command" 2>&1 | tee "$node_report"; then
    status=COLLECTED
  else
    status=REVIEW
    overall=1
  fi
  printf '\n=== %s: %s ===\n' "$ip" "$status" >> "$report"
  tr -d '\r' < "$node_report" >> "$report"
  printf '\n%s: %s.\n' "$ip" "$status"
done
install -m 0600 "$report" "$repo_dir/build/storage-health-report.txt"
printf '\nOne combined report: %s/build/storage-health-report.txt\n' "$repo_dir"
printf 'Historical run: %s\n' "$report_dir"
printf 'REVIEW means a command or connection returned nonzero; read its output, including SMART flags.\n'
exit "$overall"
