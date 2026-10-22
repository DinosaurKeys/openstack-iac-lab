#!/usr/bin/env bash
# Stage 1: preview the common role; this wrapper always uses --check --diff.
set -euo pipefail
usage() { printf 'Usage: bash scripts/preview-common.sh joe [--node node1|node2|node3|all]\nPreview packages, names and time settings; no apply mode.\n'; }
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then usage; exit 0; fi
[[ "${1:-}" == joe ]] || { usage >&2; exit 2; }
shift
selection=all
while (( $# )); do
  case "$1" in
    --node) (( $# >= 2 )) || { usage >&2; exit 2; }; selection=$2; shift 2 ;;
    *) usage >&2; exit 2 ;;
  esac
done
case "$selection" in all) nodes=(node1 node2 node3) ;; node1|node2|node3) nodes=("$selection") ;; *) usage >&2; exit 2 ;; esac
[[ -t 0 ]] || { printf 'Run directly in the Hermes terminal so sudo can ask for a password.\n' >&2; exit 2; }
[[ "$(hostname -s)" == hermes && "$(id -un)" == joe ]] || { printf 'STOP: run as joe on Hermes.\n' >&2; exit 2; }
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_dir"
venv_dir="$HOME/venvs/kolla-iac"
key="$HOME/.ssh/openstack-iac-lab-ansible"
for tool in python ansible-inventory ansible-playbook; do
  [[ -x "$venv_dir/bin/$tool" ]] || { printf 'STOP: project executable missing: %s\n' "$tool" >&2; exit 1; }
done
[[ -f "$key" && -s "$key" && ! -L "$key" ]] || { printf 'STOP: selected private-key file is missing or unsuitable; review SSH access.\n' >&2; exit 1; }
export PATH="$venv_dir/bin:$PATH" ANSIBLE_CONFIG="$repo_dir/ansible.cfg" ANSIBLE_NOCOLOR=1 ANSIBLE_FORCE_COLOR=0 ANSIBLE_ASK_PASS=False
umask 077
mkdir -p build
history=$(mktemp -d "$repo_dir/build/common-preview-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
report="$history/report.txt"
summary="$history/summary.txt"
printf 'Stage 1: common role preview\nClient: joe@hermes\nNodes: %s\nMode: CHECK + DIFF; configuration is not applied\nUTC: %s\n' "$selection" "$(date -u +%FT%TZ)" > "$report"
cp "$report" "$summary"
save() {
  install -m 0600 "$report" "$repo_dir/build/common-preview-report.txt"
  install -m 0600 "$summary" "$repo_dir/build/common-preview-summary.txt"
  printf '\n'
  cat "$summary"
  printf '\nProposed changes: %s/build/common-preview-report.txt\n' "$repo_dir"
}
stop() { printf 'STOP: %s\n' "$*" | tee -a "$report" "$summary"; save; exit 1; }
trap 'stop "Interrupted; later node previews were not attempted."' INT TERM
inventory="$repo_dir/ansible/inventory/hosts.yml"
if ! "$venv_dir/bin/ansible-inventory" -i "$inventory" --list > "$history/inventory.json" 2>> "$report"; then
  stop 'Could not resolve the preparation inventory; no node preview was attempted.'
fi
if ! "$venv_dir/bin/python" - "$history/inventory.json" "$key" >> "$report" 2>&1 <<'PY'
import json,sys
from pathlib import Path
data=json.loads(Path(sys.argv[1]).read_text())
expected={'node1':'192.168.0.200','node2':'192.168.0.201','node3':'192.168.0.202'}
group=data.get('lab_nodes',{})
if group.get('children') or set(group.get('hosts',[])) != set(expected):
    raise SystemExit('Expected exactly node1, node2 and node3 in lab_nodes.')
for node,address in expected.items():
    host=data.get('_meta',{}).get('hostvars',{}).get(node,{})
    if host.get('ansible_host') != address or host.get('ansible_user') != 'joe':
        raise SystemExit('Preparation inventory address/account mismatch for '+node)
    if Path(host.get('ansible_ssh_private_key_file','')).expanduser() != Path(sys.argv[2]):
        raise SystemExit('Preparation inventory key mismatch for '+node)
print('Preparation inventory: fixed node addresses, joe account and selected key verified.')
PY
then stop 'Preparation inventory did not match the documented nodes/key; no node preview was attempted.'; fi
extra='{"ansible_become":true,"ansible_become_user":"root","ansible_become_method":"sudo","ansible_ssh_common_args":"-F /dev/null -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -o ForwardAgent=no -o BatchMode=yes -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no -o ControlMaster=no -o ControlPath=none"}'
overall=0
for node in "${nodes[@]}"; do
  printf '\n%s: PREVIEW ONLY. BECOME password means this node\047s joe sudo password.\n' "$node"
  printf '\n--- %s: common role CHECK + DIFF ---\n' "$node" >> "$report"
  node_log="$history/$node.txt"
  if "$venv_dir/bin/ansible-playbook" -i "$inventory" "$repo_dir/ansible/playbooks/base.yml" \
       --limit "$node" --check --diff --become --become-user root --ask-become-pass -e "$extra" 2>&1 | tee -a "$report" "$node_log"; then
    if [[ $(< "$node_log") == *"COMMON_PREVIEW_OK: $node;"* ]]; then
      printf '%s: PREVIEWED; review proposed changes in the full report\n' "$node" | tee -a "$report" "$summary"
    else
      printf '%s: REVIEW; playbook completion marker missing\n' "$node" | tee -a "$report" "$summary"
      overall=1
    fi
  else
    status=("${PIPESTATUS[@]}")
    printf '%s: FAILED; ansible_exit=%s; log_exit=%s\n' "$node" "${status[0]}" "${status[1]}" | tee -a "$report" "$summary"
    case "${status[0]}" in 99|130|143) stop 'Cancelled; later node previews were not attempted.' ;; esac
    overall=1
  fi
done
if (( overall == 0 )); then
  printf 'RESULT: COMMON_PREVIEW_OK for %s; review predictions before applying.\n' "$selection" | tee -a "$report" "$summary"
else
  printf 'RESULT: REVIEW; inspect failed or incomplete previews before applying.\n' | tee -a "$report" "$summary"
fi
save
exit "$overall"
