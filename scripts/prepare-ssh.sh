#!/usr/bin/env bash
# Stage 1: dedicated Hermes key -> joe on selected nodes, then SSH/Python checks.
set -euo pipefail
usage() {
  printf 'Usage: bash scripts/prepare-ssh.sh joe [--node node1|node2|node3|all] [--apply]\n'
  printf 'Default: verify only. --apply creates/reuses the dedicated key and installs its public key.\n'
}
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then usage; exit 0; fi
[[ "${1:-}" == joe ]] || { usage >&2; exit 2; }
ssh_user=$1
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
case "$selection" in
  all) nodes=(node1 node2 node3) ;;
  node1|node2|node3) nodes=("$selection") ;;
  *) usage >&2; exit 2 ;;
esac
[[ -t 0 ]] || { printf 'Run in the Hermes terminal; key/password prompts need terminal input.\n' >&2; exit 2; }
[[ "$(hostname -s)" == hermes && "$(id -un)" == joe ]] || { printf 'STOP: run as joe on Hermes.\n' >&2; exit 2; }
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_dir"
venv_dir="$HOME/venvs/kolla-iac"
key="$HOME/.ssh/openstack-iac-lab-ansible"
export PATH="$venv_dir/bin:$PATH"
for tool in ssh ssh-copy-id ssh-keygen ssh-add; do
  command -v "$tool" >/dev/null || { printf 'STOP: required command missing: %s\n' "$tool" >&2; exit 1; }
done
for tool in python ansible; do
  [[ -x "$venv_dir/bin/$tool" ]] || { printf 'STOP: project tool missing: %s\n' "$tool" >&2; exit 1; }
done
umask 077
mkdir -p build
history=$(mktemp -d "$repo_dir/build/ssh-access-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
report="$history/report.txt"
summary="$history/summary.txt"
printf 'Stage 1: SSH-key access\nClient: joe@hermes\nNodes: %s\nApply: %s\nUTC: %s\n' "$selection" "$apply" "$(date -u +%FT%TZ)" > "$report"
cp "$report" "$summary"
printf 'Project key: %s\n' "$key" | tee -a "$report" "$summary"
save() {
  install -m 0600 "$report" "$repo_dir/build/ssh-access-report.txt"
  install -m 0600 "$summary" "$repo_dir/build/ssh-access-summary.txt"
  printf '\nSummary: %s/build/ssh-access-summary.txt\nFull log: %s/build/ssh-access-report.txt\n' "$repo_dir" "$repo_dir"
}
stop() { printf 'STOP: %s\n' "$*" | tee -a "$report" "$summary"; save; exit 1; }
copy_attempts=0
step() {
  local label=$1
  local -a phase_status
  shift
  printf '\n--- %s ---\n' "$label" | tee -a "$report"
  if "$@" 2>&1 | tee -a "$report"; then
    printf '%s: COMPLETED\n' "$label" >> "$summary"
  else
    phase_status=("${PIPESTATUS[@]}")
    printf '%s: STOPPED; command_exit=%s; log_exit=%s\n' "$label" "${phase_status[0]}" "${phase_status[1]}" | tee -a "$report" "$summary"
    if (( copy_attempts == 0 )); then
      stop "$label failed; later steps were not attempted. No public-key installation was attempted."
    else
      stop "$label failed; later steps were not attempted. Any public-key additions remain."
    fi
  fi
}
# Exit 1 means a reachable agent with no identities; exit 2 means no usable agent.
if ssh-add -l >/dev/null 2>&1; then agent_code=0; else agent_code=$?; fi
(( agent_code <= 1 )) || stop 'No reachable ssh-agent. Start it in this terminal as explained in the lesson.'
[[ ! -L "$key" && ! -L "$key.pub" ]] || stop 'Dedicated key files must not be symlinks.'
if [[ -e "$key" || -e "$key.pub" ]]; then
  [[ -f "$key" && -f "$key.pub" && -s "$key" && -s "$key.pub" ]] || stop 'Dedicated key pair is incomplete; no file was overwritten.'
elif (( apply )); then
  printf 'Creating a new project key at %s; other key files are retained.\n' "$key"
  printf 'Choose a NEW key passphrase and save it in your password manager.\n'
  printf 'ssh-keygen asks for it twice; ssh-add then asks for that SAME key passphrase.\n'
  install -d -m 0700 "$HOME/.ssh"
  step 'Create dedicated key' ssh-keygen -t ed25519 -a 64 -C 'openstack-iac-lab Ansible on Hermes' -f "$key"
else
  stop 'No dedicated key exists. Use the documented --apply setup step first.'
fi
awk 'NF {count++; if ($1 != "ssh-ed25519" || NF < 2) bad=1} END {exit (count != 1 || bad)}' "$key.pub" || stop 'Expected exactly one dedicated ED25519 public key.'
printf 'Key-loading prompt: enter the key passphrase chosen at creation. A blank response cancels this prompt.\n'
step 'Unlock key for four hours' ssh-add -t 4h "$key"
step 'Verify agent can use public key' ssh-add -T "$key.pub"
fingerprint=$(ssh-keygen -lf "$key.pub") || stop 'Cannot read public-key fingerprint.'
printf 'Project key fingerprint: %s\n' "$fingerprint" | tee -a "$report" "$summary"
remote_body=$(cat <<'REMOTE'
set -euo pipefail
node=$1
expected_ip=$2
expected_user=$3
[[ "$(hostname -s)" == "$node" ]] || { printf 'Unexpected hostname\n'; exit 1; }
[[ "$(id -un)" == "$expected_user" ]] || { printf 'Unexpected login account\n'; exit 1; }
ip -o -4 address show dev enp0s31f6 | awk -v wanted="$expected_ip/24" '$4 == wanted {found=1} END {exit !found}'
printf 'KEY_LOGIN_OK: %s as %s; management address matched\n' "$node" "$expected_user"
REMOTE
)
quoted_body=${remote_body//\'/\'\\\'\'}
verify_options=(-o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -o ForwardAgent=no -o ConnectTimeout=8
                -o BatchMode=yes -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no
                -o PreferredAuthentications=publickey -o ControlMaster=no -o ControlPath=none)
number=0
for node in "${nodes[@]}"; do
  number=$((number + 1))
  case "$node" in node1) ip=192.168.0.200 ;; node2) ip=192.168.0.201 ;; node3) ip=192.168.0.202 ;; esac
  printf '\nNode %s/%s: %s (%s)\n' "$number" "${#nodes[@]}" "$node" "$ip"
  if (( apply )); then
    printf 'Install only the dedicated PUBLIC key. SSH may ask for joe\047s password on this node.\n'
    copy_attempts=$((copy_attempts + 1))
    step "$node public-key installation" ssh-copy-id -i "$key.pub" -o StrictHostKeyChecking=yes \
      -o IdentitiesOnly=yes -o "IdentityFile=$key" -o ForwardAgent=no -o ConnectTimeout=8 "$ssh_user@$ip"
  fi
  remote_command="bash -c '$quoted_body' -- $node $ip $ssh_user"
  step "$node fresh key login" ssh -F /dev/null "${verify_options[@]}" -i "$key" "$ssh_user@$ip" "$remote_command"
done
inventory="$history/inventory.json"
if ! "$venv_dir/bin/python" -c '
import json,sys
key=sys.argv[1]
addresses={"node1":"192.168.0.200","node2":"192.168.0.201","node3":"192.168.0.202"}
vars={"ansible_user":"joe","ansible_become":False,"ansible_python_interpreter":"/usr/bin/python3",
      "ansible_ssh_private_key_file":key,
      "ansible_ssh_common_args":"-F /dev/null -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o ForwardAgent=no -o BatchMode=yes -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no -o ControlPath=none"}
print(json.dumps({"all":{"vars":vars,"children":{"lab_nodes":{"hosts":{name:{"ansible_host":addresses[name]} for name in sys.argv[2:]}}}}}))
' "$key" "${nodes[@]}" > "$inventory"; then stop 'Could not generate the SSH-only test inventory.'; fi
step 'Ansible SSH/Python ping' env ANSIBLE_BECOME_ASK_PASS=False ANSIBLE_ASK_PASS=False \
  "$venv_dir/bin/ansible" -i "$inventory" lab_nodes -m ansible.builtin.ping
printf 'RESULT: SSH_READY for %s; key login and Ansible ping passed. Sudo policy unchanged.\n' "$selection" | tee -a "$report" "$summary"
save
