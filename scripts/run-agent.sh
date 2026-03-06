#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENTS_FILE="${ROOT_DIR}/.autoflow/agents.json"

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <agent-name> <prompt-file>" >&2
  exit 1
fi

if [[ ! -f "${AGENTS_FILE}" ]]; then
  echo "missing ${AGENTS_FILE}; copy config/agents.example.json first" >&2
  exit 1
fi

AGENT_NAME="$1"
PROMPT_FILE="$2"

python3 - "$AGENTS_FILE" "$AGENT_NAME" "$PROMPT_FILE" <<'PY'
import json
import os
import shlex
import sys
from pathlib import Path

agents_file = Path(sys.argv[1])
agent_name = sys.argv[2]
prompt_file = sys.argv[3]

data = json.loads(agents_file.read_text(encoding="utf-8"))
spec = data["agents"].get(agent_name)
if not spec:
    raise SystemExit(f"unknown agent: {agent_name}")

command = [spec["command"], *spec.get("args", []), prompt_file]
os.execvp(command[0], command)
PY
