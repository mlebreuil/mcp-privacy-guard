#!/usr/bin/env bash
# Guided walk through the live check (tasks T011 and T102), see docs/live-test.md.
#
# Run it in a SECOND terminal, next to the terminal where `claude --plugin-dir plugin` runs.
# It prints each check, helps with the shell side where it can, asks for pass/fail, and writes
# the results as a markdown table you can paste into quickstart.md.
#
#   scripts/live-test.sh [results-file]
#
# Use the same MCP_PRIVACY_GUARD_HOME in both terminals: export the line this script prints.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RESULTS="${1:-$ROOT/specs/001-mcp-pseudonymization/live-test-results.md}"
if [ -z "${MCP_PRIVACY_GUARD_HOME:-}" ]; then
  MCP_PRIVACY_GUARD_HOME="$(mktemp -d)/guard"
  FRESH_HOME=1
else
  FRESH_HOME=0
fi
export MCP_PRIVACY_GUARD_HOME
HOME_DIR="$MCP_PRIVACY_GUARD_HOME"
SESSIONS="$HOME_DIR/store/sessions"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
dim() { printf '\033[2m%s\033[0m\n' "$*"; }
ask() { local reply; read -r -p "$1" reply; printf '%s' "$reply"; }

PASS=0; FAIL=0; SKIP=0
ROWS=""

# -- helpers a check can offer ---------------------------------------------------------------

h_sessions() { ls -la "$SESSIONS" 2>&1; }

h_scan() {
  local path
  path="$(ask 'Path of the transcript file: ')"
  [ -f "$path" ] || { echo "no such file"; return; }
  (cd "$ROOT/engine" && uv run python -m tests.tools.scan_transcript "$path" ../testservers/generic/seed.json)
}

h_reveal() {
  echo "Paste a transcript line, then press Ctrl-D:"
  mcp-privacy-guard reveal
}

h_profile() {
  mkdir -p "$HOME_DIR/profiles"
  cp "$ROOT/testservers/generic/profile.example.toml" "$HOME_DIR/profiles/generic.toml"
  mcp-privacy-guard check-profile "$HOME_DIR/profiles/generic.toml"
  dim "Restart Claude Code now. To test the broken profile, run:  echo 'not toml [' > $HOME_DIR/profiles/generic.toml"
}

h_badwarmup() {
  mkdir -p "$HOME_DIR/profiles"
  sed 's/list_device_groups/no_such_tool/' \
    "$ROOT/engine/src/mcp_privacy_guard/profiles/panos-mcp.toml" > "$HOME_DIR/profiles/panos-bad.toml"
  mcp-privacy-guard check-profile "$HOME_DIR/profiles/panos-bad.toml"
  dim "Restart Claude Code. Afterwards remove it:  rm $HOME_DIR/profiles/panos-bad.toml"
}

h_chmod() {
  local f
  for f in "$SESSIONS"/*/secret.key; do
    [ -f "$f" ] && chmod 644 "$f" && echo "chmod 644 $f"
  done
  dim "Ask a question in Claude Code, then restore with:  chmod 600 $SESSIONS/*/secret.key"
}

h_age() {
  local folder old
  folder="$(ls -d "$SESSIONS"/*/ 2>/dev/null | head -1)"
  [ -n "$folder" ] || { echo "no session folder"; return; }
  old="$(date -v-25H +%Y%m%d%H%M 2>/dev/null || date -d '25 hours ago' +%Y%m%d%H%M)"
  touch -t "$old" "$folder" "$folder"*
  echo "aged: $folder"
  dim "Start another Claude Code session (or run: mcp-privacy-guard begin --session x), then check swept: 1."
}

h_exempt() {
  if [ -e "$HOME_DIR/config.toml" ]; then
    echo "$HOME_DIR/config.toml exists; add by hand:"
    printf '[servers.generic]\nexempt = true\n'
  else
    mkdir -p "$HOME_DIR"
    printf '[servers.generic]\nexempt = true\n' > "$HOME_DIR/config.toml"
    echo "wrote $HOME_DIR/config.toml"
  fi
  mcp-privacy-guard status --servers generic
}

h_keep() {
  if [ -e "$HOME_DIR/config.toml" ]; then
    echo "$HOME_DIR/config.toml exists; add by hand:"
    printf '[keep]\nvalues = ["9.9.9.9"]\n'
  else
    mkdir -p "$HOME_DIR"
    printf '[keep]\nvalues = ["9.9.9.9"]\n' > "$HOME_DIR/config.toml"
    echo "wrote $HOME_DIR/config.toml"
  fi
}

# -- one check -------------------------------------------------------------------------------

# check <number> <title> <do> <expect> [helper-function]
check() {
  local num="$1" title="$2" todo="$3" expect="$4" helper="${5:-}" answer note
  echo
  bold "Check $num: $title"
  echo "  Do:     $todo"
  echo "  Expect: $expect"
  while :; do
    if [ -n "$helper" ]; then
      answer="$(ask '  [p]ass  [f]ail  [s]kip  [h]elp with the shell side  [q]uit > ')"
    else
      answer="$(ask '  [p]ass  [f]ail  [s]kip  [q]uit > ')"
    fi
    case "$answer" in
      h|H) [ -n "$helper" ] && "$helper" ;;
      p|P) PASS=$((PASS + 1)); ROWS="$ROWS| $num | $title | pass |  |\n"; return ;;
      f|F) note="$(ask '  what happened (no real values)? ')"
           FAIL=$((FAIL + 1)); ROWS="$ROWS| $num | $title | **fail** | $note |\n"; return ;;
      s|S) note="$(ask '  why skipped? ')"
           SKIP=$((SKIP + 1)); ROWS="$ROWS| $num | $title | skipped | $note |\n"; return ;;
      q|Q) finish; exit 0 ;;
    esac
  done
}

finish() {
  {
    echo "# Live check results"
    echo
    echo "Run $(date '+%Y-%m-%d %H:%M'), Claude Code $(claude --version 2>/dev/null | head -1)."
    echo
    echo "| # | Check | Result | Note |"
    echo "|---|---|---|---|"
    printf '%b' "$ROWS"
    echo
    echo "## T011 facts"
    echo
    printf '%b' "${FACTS:-not recorded\n}"
  } > "$RESULTS"
  echo
  bold "pass $PASS, fail $FAIL, skipped $SKIP. Results written to $RESULTS"
  dim "Next: copy the table into quickstart.md (Results), the T011 facts into research.md R13/R14, tick T011/T102."
}

# -- preflight -------------------------------------------------------------------------------

bold "mcp-privacy-guard live check"
echo
echo "In the Claude Code terminal (and any other), first run:"
echo "  export MCP_PRIVACY_GUARD_HOME=$HOME_DIR"
[ "$FRESH_HOME" = 1 ] && dim "(a fresh throwaway home; export the same one before starting Claude Code)"
echo
for tool in claude uv mcp-privacy-guard python3; do
  if command -v "$tool" >/dev/null 2>&1; then echo "  ok       $tool"; else echo "  MISSING  $tool"; fi
done
command -v mcp-privacy-guard >/dev/null 2>&1 \
  || dim "  install the engine:  uv tool install --editable $ROOT/engine"

python3 - "$HOME_DIR" <<'PY'
import json, os, sys
home = sys.argv[1]
found = {}
for path in ("~/.claude/settings.json", ".claude/settings.json", ".claude/settings.local.json"):
    try:
        data = json.load(open(os.path.expanduser(path)))
    except (OSError, ValueError):
        continue
    sb = data.get("sandbox", {})
    found[path] = (sb.get("enabled"), sb.get("allowUnsandboxedCommands"),
                   any(home.startswith(os.path.expanduser(e)) for e in sb.get("filesystem", {}).get("denyRead", [])))
if not found:
    print("  no sandbox settings found: add them before check 1 (docs/install.md)")
for path, (enabled, unsandboxed, denied) in found.items():
    print(f"  {path}: sandbox.enabled={enabled} allowUnsandboxedCommands={unsandboxed} denyRead covers home={denied}")
PY
echo
if [ "$(ask 'Run the engine test suite first? [y/N] ')" = "y" ]; then
  (cd "$ROOT/engine" && uv run pytest -q) || { bold "tests fail: fix them first"; exit 1; }
fi
echo
dim "Servers (once): claude mcp add generic -- uv run --project $ROOT/engine python $ROOT/testservers/generic/server.py"
dim "                claude mcp add panos -e PANOS_MCP_SAMPLES_SCENARIO=<scenario> -- <panos-mcp command>"
dim "Start:         cd $ROOT && claude --plugin-dir plugin"
ask 'Press Enter when Claude Code is running with the plugin... ' >/dev/null

# -- the checks (same order as docs/live-test.md) --------------------------------------------

check 1 "start and early question" \
  "Start; type a question at once" \
  "status line 'loading names (k/n)'; the question is dropped with 'loading names for panos, try again in a moment'; then a toast and 'active · 1 protected'"
check 2 "/privacy-guard" \
  "Type /privacy-guard" \
  "guard state, then each server with profile, profile state, protected/exempt, warm-up state; no real value"
check 3 "reveal on screen, stand-ins in the transcript" \
  "Ask: which rules allow traffic to the web servers?" \
  "real names, highlighted, on screen; /export or the transcript file holds only stand-ins (n-…, text-…)"
check 4 "follow-up with a second tool call" \
  "Ask a follow-up that needs a stand-in from the first answer in a tool call" \
  "the answer is right for the real data"
check 5 "question with real values" \
  "Type a real IP and rule name from the demo data in a question" \
  "toast 'n value(s) replaced'; your row shows them underlined; the transcript holds stand-ins"
check 6 "manual reveal" \
  "In this terminal, reveal a pasted transcript line" \
  "real values come back (only while the session lives)" h_reveal
check 7 "self-protection" \
  "Ask the model to cat the store or run mcp-privacy-guard table, and to edit .claude/settings.json" \
  "both denied"
check 8 "generic server: nothing leaks" \
  "Run every generic tool, then scan the transcript" \
  "0 real values" h_scan
check 9 "profile example, then a broken profile" \
  "Install the example profile, restart, rerun; then break it and restart" \
  "0 real values and fewer n-… stand-ins; with broken TOML a toast says the profile is invalid" h_profile
check 10 "session ends" \
  "/exit in Claude Code, then list the sessions folder" \
  "empty" h_sessions
check 11 "new session, new stand-ins" \
  "Start again, ask the same question; reveal an old stand-in here" \
  "different stand-ins; the old one is not revealed" h_reveal
check 12 "/clear" \
  "Ask a question, then /clear, then ask again; list the sessions folder" \
  "old folder gone, new one exists, new stand-ins" h_sessions
check 13 "--resume" \
  "claude --plugin-dir plugin --resume" \
  "questions blocked ('ended session; start a new one (/clear)'); /clear lifts it"
check 14 "stale folder swept" \
  "kill -9 a session, age its folder, start another" \
  "status reports swept: 1" h_age
check 15 "failure paths" \
  "Break one at a time: chmod 644 a secret.key; enginePath to a missing command; remove the denyRead entry; open in the VS Code extension; attach an image" \
  "each blocks with a message saying how to fix it" h_chmod
check 16 "failed warm-up" \
  "Install a panos profile whose warm-up tool does not exist, restart" \
  "toast with tool-missing; questions stay blocked until fixed and /clear" h_badwarmup
check 17 "exempt server" \
  "Exempt generic in config.toml, restart, ask the model to pass one of its IPs to a tool" \
  "the server receives the same IP; the status line shows it exempt" h_exempt
check 18 "keep list" \
  "Add 9.9.9.9 to keep.values, restart, ask about it" \
  "the model sees 9.9.9.9; a tool call with it reaches the server unchanged" h_keep

# -- T011 ------------------------------------------------------------------------------------

echo
bold "T011 facts (answer from what you saw in checks 12 and 13)"
FACTS=""
for q in \
  "Does --resume keep the original session id?" \
  "After /clear does the session id change, and does session.start fire again?" \
  "Does session.turns() report above 0 for a resumed session?" \
  "Does a forking slash command raise command.run to the plugin (IP in its arguments replaced)?"; do
  a="$(ask "  $q > ")"
  FACTS="$FACTS- $q **$a**\n"
done

if [ "$(ask $'\nRemove the profiles and config.toml this script helped create? [y/N] ')" = "y" ]; then
  rm -f "$HOME_DIR/profiles/generic.toml" "$HOME_DIR/profiles/panos-bad.toml" "$HOME_DIR/config.toml"
fi
finish
