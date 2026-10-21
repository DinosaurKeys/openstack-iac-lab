#!/usr/bin/env bash
# Stage 0: observe current NICs/routes/name resolution. No node configuration changes.
set -euo pipefail
usage() {
  printf 'Usage: bash scripts/check-network.sh SSH_USERNAME [--node node1|node2|node3|all]\n'
  printf 'Default: all three nodes. Read-only; no sudo or package installation.\n'
}
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then usage; exit 0; fi
(( $# >= 1 )) || { usage >&2; exit 2; }
ssh_user=$1
shift
[[ "$ssh_user" =~ ^[a-z_][a-z0-9_-]*$ ]] || { usage >&2; exit 2; }
selected_node=all
while (( $# )); do
  case "$1" in
    --node) (( $# >= 2 )) || { usage >&2; exit 2; }; selected_node=$2; shift 2 ;;
    *) usage >&2; exit 2 ;;
  esac
done
case "$selected_node" in
  node1|node2|node3) nodes=("$selected_node") ;;
  all) nodes=(node1 node2 node3) ;;
  *) usage >&2; exit 2 ;;
esac
[[ -t 0 ]] || { printf 'Run directly in a Hermes terminal so SSH can ask for a password.\n' >&2; exit 2; }
remote_body=$(cat <<'REMOTE'
set -uo pipefail
export LC_ALL=C
node=$1
case "$node" in
  node1) expected_ip=192.168.0.200; management_mac=00:23:24:eb:e0:0b; provider_mac=00:e0:4c:55:7e:58 ;;
  node2) expected_ip=192.168.0.201; management_mac=00:23:24:eb:f5:01; provider_mac=00:e0:4c:2c:16:78 ;;
  node3) expected_ip=192.168.0.202; management_mac=00:23:24:eb:df:ea; provider_mac=00:e0:4c:30:46:88 ;;
  *) exit 2 ;;
esac
review=0
read_sys() {
  local value
  if value=$(cat "$1" 2>/dev/null); then printf '%s' "$value"; else printf 'unavailable'; fi
}
check() {
  local label=$1
  shift
  printf '\n--- %s ---\n' "$label"
  if ! "$@"; then printf 'REVIEW: this observation failed.\n'; review=1; fi
}
inspect_nic() {
  local role=$1 iface=$2 expected_mac=$3 path flags admin carrier speed duplex driver actual_mac
  path="/sys/class/net/$iface"
  printf '\n--- %s NIC: %s ---\n' "$role" "$iface"
  if [[ ! -d "$path" ]]; then printf 'REVIEW: interface missing.\n'; review=1; return; fi
  actual_mac=$(read_sys "$path/address")
  printf 'MAC: %s; recorded MAC: %s\n' "$actual_mac" "$expected_mac"
  if [[ "$actual_mac" != "$expected_mac" ]]; then printf 'REVIEW: MAC differs from discovery.\n'; review=1; fi
  flags=$(read_sys "$path/flags")
  admin=UNKNOWN
  if [[ "$flags" =~ ^0x[0-9a-fA-F]+$ ]]; then
    if (( flags & 1 )); then admin=UP; else admin=DOWN; fi
  fi
  carrier=$(read_sys "$path/carrier")
  speed=$(read_sys "$path/speed")
  duplex=$(read_sys "$path/duplex")
  driver=unavailable
  if [[ -L "$path/device/driver" ]]; then driver=$(basename "$(readlink -f "$path/device/driver")"); fi
  printf 'Admin: %s; operstate: %s; carrier: %s; speed_Mbps: %s; duplex: %s; driver: %s\n' "$admin" "$(read_sys "$path/operstate")" "$carrier" "$speed" "$duplex" "$driver"
  if [[ -L "$path/master" ]]; then printf 'Master: %s\n' "$(basename "$(readlink -f "$path/master")")"; fi
  check "$iface addresses" ip -br address show dev "$iface"
  check "$iface link details" ip -details link show dev "$iface"
  if [[ "$admin" != UP ]]; then
    printf 'REVIEW: interface is not administratively UP; cable/link speed is not established by this inspection.\n'
    review=1
  elif [[ "$carrier" != 1 ]]; then
    printf 'REVIEW: carrier is not confirmed. Check cable, adapter and switch port.\n'
    review=1
  fi
  if command -v ethtool >/dev/null; then check "$iface Ethernet link readings" ethtool "$iface"; fi
}
printf 'Stage 0 network observation: %s; expected %s at %s\n' "$(hostname -s)" "$node" "$expected_ip"
if [[ "$(hostname -s)" != "$node" ]]; then printf 'REVIEW: hostname differs from the selected node.\n'; review=1; fi
inspect_nic management enp0s31f6 "$management_mac"
if addresses=$(ip -o -4 address show dev enp0s31f6); then
  if [[ "$addresses" != *" inet $expected_ip/24 "* ]]; then printf 'REVIEW: expected management address %s/24 was not found.\n' "$expected_ip"; review=1; fi
else review=1; fi
matches=()
for path in /sys/class/net/*; do
  if [[ -r "$path/address" ]] && [[ "$(read_sys "$path/address")" == "$provider_mac" ]]; then matches+=("$(basename "$path")"); fi
done
if (( ${#matches[@]} == 1 )); then
  inspect_nic provider "${matches[0]}" "$provider_mac"
  if provider_addresses=$(ip -o address show dev "${matches[0]}"); then
    if [[ -n "$provider_addresses" ]]; then printf 'REVIEW: provider has host addresses; review them before the planned ext0 configuration.\n%s\n' "$provider_addresses"; review=1; fi
  else review=1; fi
else
  printf 'REVIEW: expected one provider NIC with MAC %s; found %s.\n' "$provider_mac" "${#matches[@]}"
  review=1
fi
check 'All interface addresses' ip -br address
check 'IPv4 routes' ip -4 route show
check 'Configured DNS servers' resolvectl dns
check 'Name-resolution test for Ubuntu packages' timeout 12 resolvectl query archive.ubuntu.com
printf '\nRESULT %s: OBSERVED; review=%s. Review flags are not a diagnosis of hardware failure.\n' "$node" "$review"
printf 'No interfaces were enabled/renamed, and no addresses, routes or Netplan files were changed.\n'
exit "$review"
REMOTE
)
quoted_body=${remote_body//\'/\'\\\'\'}
umask 077
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$repo_dir/build"
report_dir=$(mktemp -d "$repo_dir/build/network-check-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
report="$report_dir/report.txt"
printf 'Stage 0: network observation\nSelection: %s\nUTC: %s\n' "$selected_node" "$(date -u +%FT%TZ)" > "$report"
printf '\n--- Hermes/client IPv4 route to each selected node ---\n' >> "$report"
client_review=0
for node in "${nodes[@]}"; do
  case "$node" in node1) ip=192.168.0.200 ;; node2) ip=192.168.0.201 ;; node3) ip=192.168.0.202 ;; esac
  if ! ip -4 route get "$ip" >> "$report" 2>&1; then printf 'REVIEW: client route lookup failed for %s.\n' "$node" >> "$report"; client_review=1; fi
done
printf 'Inspecting in order: %s. Observation continues to later nodes after a review flag.\n' "${nodes[*]}"
overall=$client_review
number=0
for node in "${nodes[@]}"; do
  number=$((number + 1))
  case "$node" in node1) ip=192.168.0.200 ;; node2) ip=192.168.0.201 ;; node3) ip=192.168.0.202 ;; esac
  printf '\nNode %s/%s: %s (%s). SSH may ask for this node\047s password.\n' "$number" "${#nodes[@]}" "$node" "$ip"
  remote_command="bash -c '$quoted_body' -- $node"
  node_report="$report_dir/$node.txt"
  if ssh -o BatchMode=no -o ConnectTimeout=8 -l "$ssh_user" "$ip" "$remote_command" 2>&1 | tee "$node_report"; then
    status=COLLECTED
  else status=REVIEW; overall=1; fi
  printf '\n=== %s: %s ===\n' "$node" "$status" >> "$report"
  tr -d '\r' < "$node_report" >> "$report"
  install -m 0600 "$report" "$repo_dir/build/network-check-report.txt"
done
printf '\nCombined report: %s/build/network-check-report.txt\nHistory: %s\n' "$repo_dir" "$report_dir"
printf 'Read the actual states and reasons; collection alone does not establish provider-network readiness.\n'
exit "$overall"
