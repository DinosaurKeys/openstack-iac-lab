#!/usr/bin/env bash
# Stage 1: verify Ansible + sudo on selected nodes; no host configuration.
set -euo pipefail
usage() { printf 'Usage: bash scripts/check-admin.sh joe [--node node1|node2|node3|all]\nRead identity through Ansible + sudo; ask separately for each selected node.\n'; }
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
[[ -f "$key" && -s "$key" && ! -L "$key" ]] || { printf 'STOP: selected private-key file is missing or unsuitable; review the SSH lesson.\n' >&2; exit 1; }
export PATH="$venv_dir/bin:$PATH" ANSIBLE_CONFIG="$repo_dir/ansible.cfg" ANSIBLE_NOCOLOR=1 ANSIBLE_FORCE_COLOR=0 ANSIBLE_ASK_PASS=False
umask 077
mkdir -p build
history=$(mktemp -d "$repo_dir/build/admin-access-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
report="$history/report.txt"
summary="$history/summary.txt"
printf 'Stage 1: Ansible administrator access\nClient: joe@hermes\nNodes: %s\nUTC: %s\n' "$selection" "$(date -u +%FT%TZ)" > "$report"
cp "$report" "$summary"
save() {
  install -m 0600 "$report" "$repo_dir/build/admin-access-report.txt"
  install -m 0600 "$summary" "$repo_dir/build/admin-access-summary.txt"
  printf '\n'
  cat "$summary"
  printf '\nFull log: %s/build/admin-access-report.txt\n' "$repo_dir"
}
stop() { printf 'STOP: %s\n' "$*" | tee -a "$report" "$summary"; save; exit 1; }
trap 'stop "Interrupted; later node checks were not attempted."' INT TERM
inventory="$repo_dir/ansible/inventory/hosts.yml"
if ! "$venv_dir/bin/ansible-inventory" -i "$inventory" --list > "$history/inventory.json" 2>> "$report"; then
  stop 'Could not resolve the preparation inventory; no node check was attempted.'
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
then stop 'Preparation inventory did not match the documented nodes/key; no node check was attempted.'; fi
extra='{"ansible_become":true,"ansible_become_user":"root","ansible_become_method":"sudo","ansible_ssh_common_args":"-F /dev/null -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -o ForwardAgent=no -o BatchMode=yes -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no -o ControlMaster=no -o ControlPath=none"}'
overall=0
for node in "${nodes[@]}"; do
  printf '\n%s: BECOME password means this node\047s joe sudo password.\n' "$node"
  printf '\n--- %s: Ansible + sudo identity check ---\n' "$node" >> "$report"
  if "$venv_dir/bin/ansible-playbook" -i "$inventory" "$repo_dir/ansible/playbooks/check-admin.yml" \
       --limit "$node" --become --become-user root --ask-become-pass -e "$extra" 2>&1 | tee -a "$report"; then
    printf '%s: PASSED; UID 0 and expected hostname verified\n' "$node" | tee -a "$report" "$summary"
  else
    status=("${PIPESTATUS[@]}")
    printf '%s: FAILED; ansible_exit=%s; log_exit=%s\n' "$node" "${status[0]}" "${status[1]}" | tee -a "$report" "$summary"
    case "${status[0]}" in 99|130|143) stop 'Cancelled; later node checks were not attempted.' ;; esac
    overall=1
  fi
done
if (( overall == 0 )); then
  printf 'RESULT: ADMIN_ACCESS_OK for %s; identity checks passed.\n' "$selection" | tee -a "$report" "$summary"
else
  printf 'RESULT: REVIEW; inspect failed node checks before host configuration.\n' | tee -a "$report" "$summary"
fi
save
exit "$overall"
