#!/usr/bin/env bash
# Type-check the plugin against Claude Code's declarations. Only the host writes them
# (the plugin-authoring skill, or a session that loads the plugin), so without them the
# check is skipped visibly instead of silently.
set -euo pipefail
cd "$(dirname "$0")/../plugin"
types=.claude-plugin/types/claude-code/index.d.ts
if [ ! -f "$types" ] && [ -n "${CLAUDE_CODE_DTS:-}" ] && [ -f "$CLAUDE_CODE_DTS" ]; then
  mkdir -p "$(dirname "$types")"
  cp "$CLAUDE_CODE_DTS" "$types"
fi
if [ ! -f "$types" ]; then
  echo "SKIPPED: claude-code.d.ts not available (set CLAUDE_CODE_DTS or load the plugin in Claude Code)"
  exit 0
fi
npx --yes -p typescript@5 tsc -p .
