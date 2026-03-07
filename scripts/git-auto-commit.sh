#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <commit-message> [--push]" >&2
  exit 1
fi

MESSAGE="$1"
MODE="${2:-}"

if [[ -z "$(git status --porcelain)" ]]; then
  echo "clean"
  exit 0
fi

git add -A
git commit -m "${MESSAGE}"

if [[ "${MODE}" == "--push" ]]; then
  BRANCH="$(git branch --show-current)"
  git push origin "${BRANCH}"
fi

echo "committed"
