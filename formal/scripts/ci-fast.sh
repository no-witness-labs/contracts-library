#!/usr/bin/env bash
set -euo pipefail

if (( $# != 0 )); then
  printf 'Usage: bash formal/scripts/ci-fast.sh\n' >&2
  exit 2
fi

upv_root=$(dirname -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")")
cd -- "$upv_root"

mkdir -p -- output
upv_logs=$(mktemp -d "$upv_root/output/ci-fast.XXXXXXXX")
upv_summary="$upv_logs/summary.md"
upv_receipts="$upv_logs/summary.tsv"
printf '# Plutus UPV fast checks\n\n' > "$upv_summary"
printf 'Test assertions and process exits determine success; expected negative-control text is allowed.\n\n' >> "$upv_summary"
printf '| Step | Result | Command exit | Log exit | Elapsed (ms) |\n| --- | --- | --- | --- | --- |\n' >> "$upv_summary"
printf 'step\tresult\tcommand_exit\tlog_exit\telapsed_ms\n' > "$upv_receipts"
cp -- lean-toolchain lake-manifest.json "$upv_logs/"
printf 'Fast-check logs: %s\n' "$upv_logs"

finish() {
  local upv_exit=$?
  trap - EXIT
  local upv_result=FAIL
  if (( upv_exit == 0 )); then upv_result=PASS; fi
  if [[ -n ${GITHUB_STEP_SUMMARY:-} ]]; then
    if cat -- "$upv_summary" >> "$GITHUB_STEP_SUMMARY"; then
      printf '\nResult: **%s** (exit %s).\n' "$upv_result" "$upv_exit" >> "$GITHUB_STEP_SUMMARY" || upv_exit=1
    else
      upv_exit=1
    fi
  fi
  if (( upv_exit != 0 )); then upv_result=FAIL; fi
  printf '\nResult: **%s** (exit %s).\n' "$upv_result" "$upv_exit" >> "$upv_summary" || upv_exit=1
  if (( upv_exit != 0 )); then upv_result=FAIL; fi
  printf 'Fast checks: %s\nSummary: %s\n' "$upv_result" "$upv_summary"
  exit "$upv_exit"
}
trap finish EXIT

run_step() {
  local upv_name=$1 upv_limit=$2
  shift 2
  local upv_start upv_end upv_command_exit upv_log_exit upv_result
  local -a upv_status
  upv_start=$(date +%s%3N) || return 1
  printf '\nSTART %s\nCommand:' "$upv_name"
  printf ' %q' timeout --signal=TERM --kill-after=10s "$upv_limit" "$@"
  printf '\n'
  if timeout --signal=TERM --kill-after=10s "$upv_limit" "$@" 2>&1 | tee "$upv_logs/$upv_name.log"; then
    upv_status=("${PIPESTATUS[@]}")
  else
    upv_status=("${PIPESTATUS[@]}")
  fi
  upv_command_exit=${upv_status[0]}
  upv_log_exit=${upv_status[1]}
  upv_end=$(date +%s%3N) || return 1
  upv_result=PASS
  if (( upv_command_exit != 0 || upv_log_exit != 0 )); then upv_result=FAIL; fi
  printf '%s\t%s\t%s\t%s\t%s\n' "$upv_name" "$upv_result" "$upv_command_exit" "$upv_log_exit" "$((upv_end-upv_start))" >> "$upv_receipts" || return 1
  printf '| %s | %s | %s | %s | %s |\n' "$upv_name" "$upv_result" "$upv_command_exit" "$upv_log_exit" "$((upv_end-upv_start))" >> "$upv_summary" || return 1
  printf 'FINISH %s: %s (command %s, log %s, %s ms)\n' "$upv_name" "$upv_result" "$upv_command_exit" "$upv_log_exit" "$((upv_end-upv_start))"
  (( upv_command_exit == 0 && upv_log_exit == 0 ))
}

upv_suites=(
  workflow_input_tests
  workflow_generator_tests
  workflow_preparation_tests
  workflow_metadata_tests
  workflow_selection_tests
  workflow_property_discovery_tests
  workflow_runner_tests
  workflow_declarative_up001_tests
  workflow_declarative_tests
  workflow_declarative_up015_tests
)

if ! run_step build 20m lake build plutus-upv "${upv_suites[@]}"; then
  printf 'Build failed; test executables were not run.\n'
  exit 1
fi

upv_exit=0
for upv_suite in "${upv_suites[@]}"; do
  upv_args=()
  if [[ $upv_suite == workflow_declarative_up015_tests ]]; then upv_args=(--unit); fi
  if ! run_step "$upv_suite" 2m lake env ".lake/build/bin/$upv_suite" "${upv_args[@]}"; then
    upv_exit=1
  fi
done
exit "$upv_exit"

