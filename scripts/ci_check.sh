#!/usr/bin/env bash
set -euo pipefail

if ! python3 -c "import pytest, click, apscheduler" >/dev/null 2>&1; then
  if [[ "${CI:-}" == "true" ]]; then
    python3 -m pip install --upgrade pip
    python3 -m pip install -e ".[dev]"
  else
    echo "missing Python test dependencies. Create a virtualenv and run: pip install -e '.[dev]'" >&2
    exit 1
  fi
fi

python3 -m py_compile \
  scripts/agent_runner.py \
  scripts/autoflow.py \
  scripts/autonomy_orchestrator.py \
  scripts/cli_healthcheck.py \
  scripts/continuous_iteration.py \
  scripts/doctor.py \
  scripts/scheduler.py \
  scripts/validate_readme_flow.py \
  scripts/validate_scheduler_start.py \
  scripts/validate_recovery_loop.py \
  scripts/validate_runtime_loop.py \
  tests/autoflow_tests/test_scheduler.py \
  tests/test_agent_runner.py \
  tests/test_cli_spec.py \
  tests/test_continuous_iteration.py \
  tests/test_autonomy_orchestrator.py \
  tests/test_phase4d.py

python3 -m unittest tests/test_phase4d.py tests/test_agent_runner.py tests/test_autonomy_orchestrator.py
python3 -m pytest tests/test_cli_spec.py tests/test_continuous_iteration.py tests/autoflow_tests/test_scheduler.py -q

bash -n scripts/run-agent.sh
bash -n scripts/tmux-start.sh
bash -n scripts/workflow-dispatch.sh
bash -n scripts/git-auto-commit.sh
bash -n scripts/git-prepare-branch.sh
