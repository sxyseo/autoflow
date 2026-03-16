#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <command-or-script> [session-name]" >&2
  exit 1
fi

TARGET="$1"
SESSION_NAME="${2:-autoflow-$(date +%s)}"

if [[ -f "${TARGET}" ]]; then
  tmux new-session -d -s "${SESSION_NAME}" "AUTOFLOW_TMUX_SESSION=${SESSION_NAME} bash ${TARGET}"
else
  tmux new-session -d -s "${SESSION_NAME}" "${TARGET}"
fi

echo "${SESSION_NAME}"
