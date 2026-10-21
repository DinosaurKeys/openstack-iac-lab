#!/usr/bin/env bash
# Run explicitly on Hermes; preserves ~/venvs/kolla and /etc/kolla.
set -euo pipefail
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
export ANSIBLE_COLLECTIONS_PATH="$repo_dir/build/collections"
mkdir -p "$ANSIBLE_COLLECTIONS_PATH"
sudo apt-get update
sudo apt-get install -y git curl ca-certificates python3-dev python3-venv libffi-dev gcc libssl-dev libdbus-glib-1-dev
venv_dir="$HOME/venvs/kolla-iac"
python3 -m venv "$venv_dir"
"$venv_dir/bin/python" -m pip install --upgrade pip
"$venv_dir/bin/python" -m pip install 'ansible-core>=2.19,<2.20.99' 'kolla-ansible @ git+https://opendev.org/openstack/kolla-ansible@15ce36696a21356eb59abb4473e210f13cf7c98c' python-openstackclient PyYAML
# Kolla invokes ansible-galaxy by name in a child process; an absolute Kolla path
# alone does not make the environment's other console commands discoverable.
export PATH="$venv_dir/bin:$PATH"
"$venv_dir/bin/kolla-ansible" install-deps
"$venv_dir/bin/ansible-galaxy" collection install -p "$ANSIBLE_COLLECTIONS_PATH" -r "$repo_dir/ansible/requirements.yml"
printf 'Activate with: source %s/bin/activate\n' "$venv_dir"
if ! command -v terraform >/dev/null; then
  printf 'Terraform is not installed. Install it using the official HashiCorp instructions before Stage 3.\n'
fi
