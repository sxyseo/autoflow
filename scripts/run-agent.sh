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
  exec python3 "${ROOT_DIR}/scripts/agent_runner.py" "${AGENTS_FILE}" "${AGENT_NAME}" "${PROMPT_FILE}" "${RUN_JSON}"
fi

exec python3 "${ROOT_DIR}/scripts/agent_runner.py" "${AGENTS_FILE}" "${AGENT_NAME}" "${PROMPT_FILE}"
