#!/usr/bin/env bash
# Stage 0: exact old-Ceph targets only. Default is a plan, never a wipe-all loop.
set -euo pipefail
usage() {
  printf 'Usage: bash scripts/reset-ceph.sh SSH_USERNAME --node node1|node2|node3|all [--apply]\n'
  printf 'Default: inspect and print the exact plan. --apply asks for each node/serial approval.\n'
}
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then usage; exit 0; fi
if (( $# < 1 )); then usage >&2; exit 2; fi
ssh_user=$1
shift
[[ "$ssh_user" =~ ^[a-z_][a-z0-9_-]*$ ]] || { usage >&2; exit 2; }
selected_node=
apply=0
while (( $# )); do
  case "$1" in
    --node) (( $# >= 2 )) || { usage >&2; exit 2; }; selected_node=$2; shift 2 ;;
    --apply) apply=1; shift ;;
    *) usage >&2; exit 2 ;;
  esac
done
case "$selected_node" in
  node1|node2|node3) nodes=("$selected_node") ;;
  all) nodes=(node1 node2 node3) ;;
  *) usage >&2; exit 2 ;;
esac
[[ -t 0 ]] || { printf 'Run directly in an interactive Hermes terminal for SSH, sudo and target confirmation.\n' >&2; exit 2; }
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
remote_body=$(cat "$repo_dir/scripts/reset-ceph.py")
quoted_body=${remote_body//\'/\'\\\'\'}
umask 077
mkdir -p "$repo_dir/build"
report_dir=$(mktemp -d "$repo_dir/build/ceph-reset-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
report="$report_dir/report.txt"
printf 'Stage 0: exact Ceph reset\nNodes: %s\nApply requested: %s\nUTC: %s\n' "$selected_node" "$apply" "$(date -u +%FT%TZ)" > "$report"
printf 'Run order: %s. One node at a time; a failed node stops the run.\n' "${nodes[*]}"
node_number=0
for node in "${nodes[@]}"; do
  node_number=$((node_number + 1))
  case "$node" in
    node1) ip=192.168.0.200 ;;
    node2) ip=192.168.0.201 ;;
    node3) ip=192.168.0.202 ;;
  esac
  remote_command="sudo -- python3 -u -c '$quoted_body' --node $node"
  if (( apply )); then remote_command+=" --apply"; fi
  printf '\nNode %s/%s: %s (%s). SSH and sudo may each ask for this node\047s password.\n' "$node_number" "${#nodes[@]}" "$node" "$ip"
  node_report="$report_dir/$node.txt"
  if ssh -t -o BatchMode=no -o ConnectTimeout=8 -l "$ssh_user" "$ip" "$remote_command" 2>&1 | tee "$node_report"; then
    status=COMPLETED
  else
    status=STOPPED
  fi
  printf '\n=== %s: %s ===\n' "$node" "$status" >> "$report"
  tr -d '\r' < "$node_report" >> "$report"
  install -m 0600 "$report" "$repo_dir/build/ceph-reset-report.txt"
  if [[ "$status" == STOPPED ]]; then
    printf '\nStopped at %s; later nodes were not attempted.\n' "$node"
    printf 'Report: %s/build/ceph-reset-report.txt\n' "$repo_dir"
    exit 1
  fi
done
printf '\nCombined report: %s/build/ceph-reset-report.txt\nHistory: %s\n' "$repo_dir" "$report_dir"
printf 'Read RESULT for each node: PLAN_ONLY, CLEANED or ALREADY_BLANK.\n'
