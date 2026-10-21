#!/usr/bin/env bash
# Stage 1: prepare Hermes, or resume only collections after Python tools installed.
set -euo pipefail
usage() { printf 'Usage: bash scripts/prepare-hermes.sh [--resume-collections]\nRun on Hermes. Resume skips apt, venv creation and Python package installation.\n'; }
mode=full
case "${1:-}" in
  '') (( $# == 0 )) || { usage >&2; exit 2; } ;;
  --resume-collections) (( $# == 1 )) || { usage >&2; exit 2; }; mode=resume-collections ;;
  --help|-h) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac
[[ -t 0 ]] || { printf 'Run directly in a Hermes terminal so sudo can ask for your password.\n' >&2; exit 2; }
[[ "$(hostname -s)" == hermes ]] || { printf 'STOP: run this on Hermes, not a cloud node.\n' >&2; exit 2; }
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_dir"
umask 077
mkdir -p build
report_dir=$(mktemp -d "$repo_dir/build/hermes-tools-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
report="$report_dir/report.txt"
summary="$report_dir/summary.txt"
printf 'Stage 1: Hermes tool preparation\nHost: %s\nMode: %s\nUTC: %s\n' "$(hostname -s)" "$mode" "$(date -u +%FT%TZ)" > "$report"
cp "$report" "$summary"
save_report() {
  install -m 0600 "$report" "$repo_dir/build/hermes-tools-report.txt"
  install -m 0600 "$summary" "$repo_dir/build/hermes-tools-summary.txt"
  printf '\nShort summary: %s/build/hermes-tools-summary.txt\nFull log: %s/build/hermes-tools-report.txt\nHistory: %s\n' "$repo_dir" "$repo_dir" "$report_dir"
}
step() {
  local label=$1 code
  shift
  printf '\n--- %s ---\n' "$label" | tee -a "$report"
  if "$@" 2>&1 | tee -a "$report"; then
    printf '%s: COMPLETED\n' "$label" >> "$summary"
  else
    code=$?
    printf '%s: STOPPED; exit=%s. Read the first error in the full log.\n' "$label" "$code" | tee -a "$report" "$summary"
    save_report
    exit "$code"
  fi
}
venv_dir="$HOME/venvs/kolla-iac"
export PATH="$venv_dir/bin:$PATH"
export ANSIBLE_COLLECTIONS_PATH="$repo_dir/build/collections"
if [[ "$mode" == resume-collections ]]; then
  printf 'Resume on Hermes: use installed Python tools; install collections in build/collections.\n'
  printf 'No apt, pip install, sudo, node SSH or cloud deployment is invoked in resume mode.\n'
  for executable in python kolla-ansible ansible-galaxy; do
    if [[ ! -x "$venv_dir/bin/$executable" ]]; then
      printf 'STOP: expected executable missing: %s/bin/%s. No installation attempted.\n' "$venv_dir" "$executable" | tee -a "$report" "$summary"
      save_report
      exit 1
    fi
  done
  mkdir -p "$ANSIBLE_COLLECTIONS_PATH"
  step 'Kolla collections' "$venv_dir/bin/kolla-ansible" install-deps
  step 'Project collections' "$venv_dir/bin/ansible-galaxy" collection install -p "$ANSIBLE_COLLECTIONS_PATH" -r "$repo_dir/ansible/requirements.yml"
else
  printf 'Full setup on Hermes: Ubuntu prerequisites, isolated Python tools and Ansible collections.\n'
  printf 'Hermes sudo may ask for your password.\n'
  step 'Tool installation' bash "$repo_dir/scripts/bootstrap-hermes.sh"
fi
step 'Python dependency check' "$venv_dir/bin/python" -m pip check
if "$venv_dir/bin/python" -m pip freeze > "$report_dir/python-versions.txt"; then
  printf 'Python version manifest: python-versions.txt in the history directory\n' >> "$summary"
else
  printf 'STOP: could not record installed Python packages.\n' | tee -a "$report" "$summary"
  save_report
  exit 1
fi
step 'Installed collections' "$venv_dir/bin/ansible-galaxy" collection list -p "$ANSIBLE_COLLECTIONS_PATH"
printf '\n--- Tool locations (doctor) ---\n' | tee -a "$report"
if "$venv_dir/bin/python" "$repo_dir/scripts/labctl.py" doctor 2>&1 | tee -a "$report" "$summary"; then
  printf '\nRESULT: TOOLS_FOUND; no cloud deployment was attempted.\n' | tee -a "$report" "$summary"
  save_report
else
  code=$?
  printf '\nRESULT: REVIEW; doctor exit=%s. Read each MISSING tool. Terraform is needed by Stage 3.\n' "$code" | tee -a "$report" "$summary"
  save_report
  exit "$code"
fi
