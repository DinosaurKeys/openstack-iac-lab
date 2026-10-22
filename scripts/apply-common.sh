#!/usr/bin/env bash
# Stage 1: apply the reviewed common role, verify it, stop on the first failure.
set -euo pipefail
usage() { printf 'Usage: bash scripts/apply-common.sh joe --node node1|node2|node3|all --apply\nInstall missing common packages and configure names/time; real node changes.\n'; }
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then usage; exit 0; fi
[[ "${1:-}" == joe ]] || { usage >&2; exit 2; }
shift
selection=all
apply=0
while (( $# )); do
  case "$1" in
    --node) (( $# >= 2 )) || { usage >&2; exit 2; }; selection=$2; shift 2 ;;
    --apply) apply=1; shift ;;
    *) usage >&2; exit 2 ;;
  esac
done
(( apply == 1 )) || { usage >&2; exit 2; }
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
history=$(mktemp -d "$repo_dir/build/common-apply-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
report="$history/report.txt"
summary="$history/summary.txt"
printf 'Stage 1: common role application\nClient: joe@hermes\nNodes: %s\nMode: APPLY + VERIFY; real package/name/time changes\nUTC: %s\n' "$selection" "$(date -u +%FT%TZ)" > "$report"
cp "$report" "$summary"
save() {
  install -m 0600 "$report" "$repo_dir/build/common-apply-report.txt"
  install -m 0600 "$summary" "$repo_dir/build/common-apply-summary.txt"
  printf '\n'
  cat "$summary"
  printf '\nFull log: %s/build/common-apply-report.txt\n' "$repo_dir"
}
stop() { printf 'STOP: %s\n' "$*" | tee -a "$report" "$summary"; save; exit 1; }
trap 'stop "Interrupted; changes already completed remain. Later nodes were not attempted."' INT TERM
inventory="$repo_dir/ansible/inventory/hosts.yml"
if ! "$venv_dir/bin/ansible-inventory" -i "$inventory" --list > "$history/inventory.json" 2>> "$report"; then
  stop 'Could not resolve the preparation inventory; no node apply was attempted.'
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
then stop 'Preparation inventory did not match the documented nodes/key; no node apply was attempted.'; fi
extra='{"ansible_become":true,"ansible_become_user":"root","ansible_become_method":"sudo","ansible_ssh_common_args":"-F /dev/null -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -o ForwardAgent=no -o BatchMode=yes -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no -o ControlMaster=no -o ControlPath=none"}'
for node in "${nodes[@]}"; do
  printf '\n%s: APPLY + VERIFY. BECOME password means this node\047s joe sudo password.\n' "$node"
  printf '\n--- %s: common role APPLY + VERIFY ---\n' "$node" >> "$report"
  node_log="$history/$node.txt"
  if "$venv_dir/bin/ansible-playbook" -i "$inventory" "$repo_dir/ansible/playbooks/base.yml" \
       --limit "$node" --diff --become --become-user root --ask-become-pass -e "$extra" 2>&1 | tee -a "$report" "$node_log"; then
    if [[ $(< "$node_log") == *"COMMON_APPLIED_OK: $node;"* ]]; then
      printf '%s: APPLIED_AND_VERIFIED\n' "$node" | tee -a "$report" "$summary"
    else
      stop "$node completion marker missing; changes may remain. Later nodes were not attempted."
    fi
  else
    status=("${PIPESTATUS[@]}")
    printf '%s: FAILED; ansible_exit=%s; log_exit=%s\n' "$node" "${status[0]}" "${status[1]}" | tee -a "$report" "$summary"
    stop "$node apply or verification failed; completed changes remain. Later nodes were not attempted."
  fi
done
printf 'RESULT: COMMON_APPLIED_OK for %s; installed baseline and time synchronization verified.\n' "$selection" | tee -a "$report" "$summary"
save
