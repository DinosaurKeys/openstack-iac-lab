#!/usr/bin/env bash
# Stage 1: install the existing Hermes-only toolchain, record versions and run doctor.
set -euo pipefail
if (( $# )); then
  printf 'Usage: bash scripts/prepare-hermes.sh\nRun from a terminal on Hermes.\n' >&2
  exit 2
fi
[[ -t 0 ]] || { printf 'Run directly in a Hermes terminal so sudo can ask for your password.\n' >&2; exit 2; }
[[ "$(hostname -s)" == hermes ]] || { printf 'STOP: run this on Hermes, not a cloud node.\n' >&2; exit 2; }
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_dir"
umask 077
mkdir -p build
report_dir=$(mktemp -d "$repo_dir/build/hermes-tools-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
report="$report_dir/report.txt"
printf 'Stage 1: Hermes tool preparation\nHost: %s\nUTC: %s\n' "$(hostname -s)" "$(date -u +%FT%TZ)" > "$report"
save_report() {
  install -m 0600 "$report" "$repo_dir/build/hermes-tools-report.txt"
  printf '\nCombined report: %s/build/hermes-tools-report.txt\nHistory: %s\n' "$repo_dir" "$report_dir"
}
printf 'On Hermes: install tools in ~/venvs/kolla-iac and this project\047s build/collections.\n'
printf 'This does not SSH to nodes, edit their networks, create storage, or deploy OpenStack.\n'
printf 'Hermes sudo may ask for your password. Package installation can take several minutes.\n'
if bash "$repo_dir/scripts/bootstrap-hermes.sh" 2>&1 | tee -a "$report"; then
  printf '\nINSTALL: COMPLETED\n' | tee -a "$report"
else
  code=$?
  printf '\nINSTALL: STOPPED; exit=%s. Read the first installation error before retrying.\n' "$code" | tee -a "$report"
  save_report
  exit "$code"
fi
venv_dir="$HOME/venvs/kolla-iac"
export PATH="$venv_dir/bin:$PATH"
export ANSIBLE_COLLECTIONS_PATH="$repo_dir/build/collections"
printf '\n--- Installed Python package versions ---\n' >> "$report"
if "$venv_dir/bin/python" -m pip freeze > "$report_dir/python-versions.txt"; then
  cat "$report_dir/python-versions.txt" >> "$report"
else
  printf 'STOP: could not record installed Python packages.\n' | tee -a "$report"
  save_report
  exit 1
fi
printf '\n--- Tool locations (doctor) ---\n' | tee -a "$report"
if "$venv_dir/bin/python" "$repo_dir/scripts/labctl.py" doctor 2>&1 | tee -a "$report"; then
  printf '\nRESULT: TOOLS_FOUND; no cloud deployment was attempted.\n' | tee -a "$report"
  save_report
else
  code=$?
  printf '\nRESULT: REVIEW; doctor exit=%s. Read each MISSING tool. Terraform is needed by Stage 3.\n' "$code" | tee -a "$report"
  save_report
  exit "$code"
fi
