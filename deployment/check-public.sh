#!/usr/bin/env bash
# Refuse to publish private strings (host paths, hostnames, ...) listed in the gitignored
# .private-patterns file at the repo root. Fixed strings, case-insensitive, one per line.
#
#   check-public.sh            check staged + tracked files and untracked files git would add
#   check-public.sh --history  also scan every commit in git history
#
# Install as a pre-commit hook:  ln -sf ../../deployment/check-public.sh .git/hooks/pre-commit
set -euo pipefail

ROOT=$(git rev-parse --show-toplevel)
PATTERNS="$ROOT/.private-patterns"

if [[ ! -f "$PATTERNS" ]]; then
  echo "check-public: no .private-patterns file; nothing to check." >&2
  exit 0
fi

pats=$(mktemp)
trap 'rm -f "$pats"' EXIT
grep -vE '^[[:space:]]*(#|$)' "$PATTERNS" > "$pats" || true
[[ -s "$pats" ]] || exit 0

fail=0
cd "$ROOT"

# Index (what the next commit will contain).
if git grep --cached -n -I -i -F -f "$pats" -- . ':!.private-patterns'; then
  fail=1
fi

# Untracked files that are not ignored (would be picked up by `git add -A`).
mapfile -t untracked < <(git ls-files --others --exclude-standard)
if ((${#untracked[@]})); then
  if grep -n -I -i -F -f "$pats" -- "${untracked[@]}" 2>/dev/null; then
    fail=1
  fi
fi

if [[ "${1:-}" == "--history" ]] && git rev-parse --verify -q HEAD >/dev/null; then
  if git log -p --all --no-color | grep -n -i -F -f "$pats"; then
    echo "check-public: private strings found in git HISTORY (rewrite before pushing)." >&2
    fail=1
  fi
fi

if ((fail)); then
  echo "check-public: private strings found (patterns from .private-patterns). Not publishing." >&2
  exit 1
fi
echo "check-public: OK"
