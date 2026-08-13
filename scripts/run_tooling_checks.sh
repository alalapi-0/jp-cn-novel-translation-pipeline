#!/usr/bin/env sh
# Run only live-tree-safe, targeted control-plane checks.
# The full agent gate, mutating probe sync, inventory generation, baseline
# creation, and rebaseline are intentionally excluded.
set -u
cd "$(dirname "$0")/.." || exit 2

REPO_ROOT=$(pwd -P) || exit 2
WORKSPACE_ROOT="$REPO_ROOT/workspace"
BASELINE_MANIFEST="$REPO_ROOT/.agent_runtime/inspection_reports/workspace_file_baseline.json"

PYTHON="${PYTHON:-python3}"
if [ -x .venv/bin/python ]; then
  PYTHON=".venv/bin/python"
fi
PYTEST="${PYTEST:-pytest}"
if [ -x .venv/bin/pytest ]; then
  PYTEST=".venv/bin/pytest"
fi
export PYTHONDONTWRITEBYTECODE=1

path_exists() {
  [ -e "$1" ] || [ -L "$1" ]
}

verify_workspace() {
  "$PYTHON" scripts/workspace_file_baseline.py verify --json
}

verify_empty_checkout() {
  ! path_exists "$WORKSPACE_ROOT" && ! path_exists "$BASELINE_MANIFEST"
}

verify_tracked_workspace_skeleton() {
  path_exists "$WORKSPACE_ROOT" || return 1
  path_exists "$BASELINE_MANIFEST" && return 1

  git_root=$(GIT_OPTIONAL_LOCKS=0 git rev-parse --show-toplevel 2>/dev/null) || return 1
  [ "$git_root" = "$REPO_ROOT" ] || return 1

  tracked_workspace=$(GIT_OPTIONAL_LOCKS=0 git ls-files -- workspace/ 2>/dev/null) || return 1
  [ -n "$tracked_workspace" ] || return 1

  workspace_status=$(GIT_OPTIONAL_LOCKS=0 git status --porcelain=v1 \
    --untracked-files=all --ignored=matching -- workspace/ 2>/dev/null) || return 1
  [ -z "$workspace_status" ]
}

classify_workspace_state() {
  workspace_present=false
  baseline_present=false
  path_exists "$WORKSPACE_ROOT" && workspace_present=true
  path_exists "$BASELINE_MANIFEST" && baseline_present=true

  if [ "$workspace_present" = true ] && [ "$baseline_present" = true ]; then
    printf '%s\n' populated
    return 0
  fi
  if [ "$workspace_present" = false ] && [ "$baseline_present" = false ]; then
    printf '%s\n' empty
    return 0
  fi
  if [ "$workspace_present" = true ] && [ "$baseline_present" = false ]; then
    verify_tracked_workspace_skeleton || return 1
    printf '%s\n' skeleton
    return 0
  fi
  return 1
}

run_targeted_checks() {
  "$PYTHON" scripts/validate_agent_report.py || return $?
  "$PYTHON" scripts/check_prompts_refs.py || return $?
  "$PYTEST" -p no:cacheprovider \
    tests/test_workspace_file_baseline.py \
    tests/test_local_only_git_policy.py \
    tests/test_git_safe_cohort_finalizer.py \
    tests/test_validate_agent_report.py \
    tests/test_write_agent_report.py \
    tests/test_tool_probe.py \
    -q
}

verify_exit_state() {
  case "$initial_state" in
    populated)
      verify_workspace
      ;;
    empty)
      verify_empty_checkout || return 2
      ;;
    skeleton)
      verify_tracked_workspace_skeleton || return 2
      ;;
    *)
      return 2
      ;;
  esac
}

finalize() {
  original_status=$?
  trap - 0 2 15
  post_status=0
  verify_exit_state || post_status=$?
  if [ "$post_status" -ne 0 ]; then
    printf '%s\n' "check:tooling: workspace state changed during targeted checks" >&2
    exit "$post_status"
  fi
  exit "$original_status"
}

initial_state=$(classify_workspace_state) || {
  printf '%s\n' "check:tooling: incomplete or dirty workspace baseline state" >&2
  exit 2
}

case "$initial_state" in
  populated)
    verify_workspace || exit $?
    ;;
  empty)
    verify_empty_checkout || exit 2
    ;;
  skeleton)
    verify_tracked_workspace_skeleton || exit 2
    ;;
  *)
    exit 2
    ;;
esac

# Arm the exit check only after the initial state has been accepted. POSIX
# signal traps convert catchable INT/TERM into an exit so trap 0 can verify the
# workspace state. SIGKILL cannot be handled by any process.
trap 'finalize' 0
trap 'exit 130' 2
trap 'exit 143' 15

checks_status=0
run_targeted_checks || checks_status=$?
exit "$checks_status"
