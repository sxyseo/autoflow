#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "usage: $0 <spec-slug> <role> <agent> [task-id]" >&2
  exit 1
fi

SPEC_SLUG="$1"
ROLE="$2"
AGENT="$3"
TASK_ID="${4:-}"

CMD=(python3 scripts/autoflow.py new-run --spec "${SPEC_SLUG}" --role "${ROLE}" --agent "${AGENT}")
if [[ -n "${TASK_ID}" ]]; then
  CMD+=(--task "${TASK_ID}")
fi

RUN_DIR="$("${CMD[@]}")"
scripts/tmux-start.sh "${RUN_DIR}/run.sh"
