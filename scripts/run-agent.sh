#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENTS_FILE="${ROOT_DIR}/.autoflow/agents.json"

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "usage: $0 <agent-name> <prompt-file> [run-json]" >&2
  exit 1
fi

if [[ ! -f "${AGENTS_FILE}" ]]; then
  echo "missing ${AGENTS_FILE}; copy config/agents.example.json first" >&2
  exit 1
fi

AGENT_NAME="$1"
PROMPT_FILE="$2"
RUN_JSON="${3:-}"

if [[ -n "${RUN_JSON}" ]]; then
  # Verify run.sh integrity if run.json is provided
  RUN_DIR="$(dirname "${RUN_JSON}")"
  RUN_SCRIPT="${RUN_DIR}/run.sh"

  if [[ -f "${RUN_SCRIPT}" && -f "${RUN_JSON}" ]]; then
    # Compute actual hash of run.sh
    ACTUAL_HASH="$(sha256sum "${RUN_SCRIPT}" | cut -d' ' -f1)"

    # Extract expected hash from run.json
    EXPECTED_HASH="$(python3 -c "import json; print(json.load(open('${RUN_JSON}')).get('integrity', {}).get('run.sh', ''))")"

    # Verify integrity
    if [[ -n "${EXPECTED_HASH}" && "${ACTUAL_HASH}" != "${EXPECTED_HASH}" ]]; then
      echo "integrity check failed for ${RUN_SCRIPT}: file may have been tampered with" >&2
      exit 1
    fi
  fi

  exec python3 "${ROOT_DIR}/scripts/agent_runner.py" "${AGENTS_FILE}" "${AGENT_NAME}" "${PROMPT_FILE}" "${RUN_JSON}"
fi

exec python3 "${ROOT_DIR}/scripts/agent_runner.py" "${AGENTS_FILE}" "${AGENT_NAME}" "${PROMPT_FILE}"
