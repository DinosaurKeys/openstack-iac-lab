#!/usr/bin/env bash
# Stage 0: one guarded temporary USB link test per selected node, from Hermes.
set -euo pipefail
usage() {
  printf 'Usage: bash scripts/test-provider-link.sh SSH_USERNAME [--node node1|node2|node3|all] [--apply]\n'
  printf 'Default: plan only, all nodes. --apply temporarily enables each unused USB NIC, then restores DOWN.\n'
}
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then usage; exit 0; fi
(( $# >= 1 )) || { usage >&2; exit 2; }
ssh_user=$1
shift
[[ "$ssh_user" =~ ^[a-z_][a-z0-9_-]*$ ]] || { usage >&2; exit 2; }
selected_node=all
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
[[ -t 0 ]] || { printf 'Run directly in a Hermes terminal so SSH/sudo can ask for passwords.\n' >&2; exit 2; }
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
body=$(cat "$repo_dir/scripts/test-provider-link.py")
quoted_body=${body//\'/\'\\\'\'}
umask 077
mkdir -p "$repo_dir/build"
report_dir=$(mktemp -d "$repo_dir/build/provider-link-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
report="$report_dir/report.txt"
printf 'Stage 0: temporary USB provider link test\nNodes: %s\nApply requested: %s\nUTC: %s\n' "$selected_node" "$apply" "$(date -u +%FT%TZ)" > "$report"
overall=0
number=0
for node in "${nodes[@]}"; do
  number=$((number + 1))
  case "$node" in node1) ip=192.168.0.200 ;; node2) ip=192.168.0.201 ;; node3) ip=192.168.0.202 ;; esac
  printf '\nNode %s/%s: %s (%s). SSH and sudo may each ask for this node\047s password.\n' "$number" "${#nodes[@]}" "$node" "$ip"
  remote_command="sudo -- python3 -u -c '$quoted_body' --node $node"
  if (( apply )); then remote_command+=' --apply'; fi
  node_report="$report_dir/$node.txt"
  if ssh -tt -o BatchMode=no -o ConnectTimeout=8 -l "$ssh_user" "$ip" "$remote_command" 2>&1 | tee "$node_report"; then
    status=COMPLETED
    code=0
  else
    code=$?
    status=STOPPED
    if (( code == 3 )); then status=REVIEW; fi
  fi
  printf '\n=== %s: %s ===\n' "$node" "$status" >> "$report"
  tr -d '\r' < "$node_report" >> "$report"
  install -m 0600 "$report" "$repo_dir/build/provider-link-report.txt"
  if (( code != 0 )); then overall=1; fi
  if [[ "$status" == STOPPED ]]; then
    printf '\nStopped at %s; later nodes were not attempted. Read the STOP reason.\n' "$node"
    break
  fi
done
printf '\nCombined report: %s/build/provider-link-report.txt\nHistory: %s\n' "$repo_dir" "$report_dir"
printf 'LINK_OK verifies physical negotiation only; VLAN, throughput and floating-IP reachability remain later checks.\n'
exit "$overall"
