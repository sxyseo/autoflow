#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <spec-slug> <task-id> [--create]" >&2
  exit 1
fi

SPEC_SLUG="$1"
TASK_ID="$2"
MODE="${3:-}"
BRANCH_NAME="codex/${SPEC_SLUG}-${TASK_ID,,}"

if [[ "${MODE}" == "--create" ]]; then
  git checkout -b "${BRANCH_NAME}"
fi

echo "${BRANCH_NAME}"
