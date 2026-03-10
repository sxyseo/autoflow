#!/usr/bin/env bash
set -euo pipefail

python3 -m py_compile \
  scripts/agent_runner.py \
  scripts/autoflow.py \
  scripts/autonomy_orchestrator.py \
  scripts/cli_healthcheck.py \
  scripts/continuous_iteration.py \
  scripts/validate_readme_flow.py \
  tests/test_agent_runner.py \
  tests/test_autonomy_orchestrator.py \
  tests/test_phase4d.py

ruff check scripts/ tests/

black --check scripts/ tests/

python3 -m mypy scripts/ tests/

# Run bandit but don't fail on findings (report only)
bandit -c pyproject.toml -r scripts/ tests/ || true

python3 -m unittest tests/test_phase4d.py tests/test_agent_runner.py tests/test_autonomy_orchestrator.py

bash -n scripts/run-agent.sh
bash -n scripts/tmux-start.sh
bash -n scripts/workflow-dispatch.sh
bash -n scripts/git-auto-commit.sh
bash -n scripts/git-prepare-branch.sh
