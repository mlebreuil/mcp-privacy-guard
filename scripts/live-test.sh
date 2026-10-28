#!/usr/bin/env bash
# Guided walk through the live check (tasks T011 and T102), see docs/live-test.md.
#
# Run it in a SECOND terminal, next to the terminal where `claude --plugin-dir plugin` runs.
# It prints each check, helps with the shell side where it can, asks for pass/fail, and writes
# the results as a markdown table you can paste into quickstart.md.
#
#   scripts/live-test.sh [results-file]
#   FROM=10 scripts/live-test.sh      # start at check 10 (earlier checks are skipped silently;
#                                     # results go to live-test-results-from-10.md, so the
#                                     # default results file is not overwritten)
#
# Use the same MCP_PRIVACY_GUARD_HOME in both terminals: export the line this script prints.
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FROM="${FROM:-1}"
if [ "$FROM" -gt 1 ] 2>/dev/null; then
  RESULTS="${1:-$ROOT/specs/001-mcp-pseudonymization/live-test-results-from-$FROM.md}"
else
  RESULTS="${1:-$ROOT/specs/001-mcp-pseudonymization/live-test-results.md}"
fi
if [ -z "${MCP_PRIVACY_GUARD_HOME:-}" ]; then
  MCP_PRIVACY_GUARD_HOME="$ROOT/temp/guard"   # repo-local, git-ignored
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
  local path dir newest live id
  dir="$HOME/.claude/projects/$(printf '%s' "$ROOT" | tr / -)"
  echo "Transcripts of this project are in $dir (one <session-id>.jsonl per session)."
  echo "This folder also holds the transcripts of other sessions (for example the one you develop in), so the newest file may be the wrong one."
  newest=""
  live="$(ls "$SESSIONS" 2>/dev/null)"
  if [ -n "$live" ] && [ "$(printf '%s\n' "$live" | wc -l | tr -d ' ')" = 1 ] && [ -f "$dir/$live.jsonl" ]; then
    newest="$dir/$live.jsonl"
    echo "The one live guard session is $live; its transcript is:"
    echo "  $newest"
  else
    echo "No single live guard session found (sessions folder: ${live:-empty}). Newest transcripts:"
    ls -lt "$dir"/*.jsonl 2>/dev/null | head -5 | awk '{print "  " $6, $7, $8, $9}'
    echo "In Claude Code, /status shows the session id; the file is <session-id>.jsonl."
  fi
  path="$(ask 'Transcript path (Enter for the one above): ')"
  [ -n "$path" ] || path="$newest"
  [ -f "$path" ] || { echo "no such file"; return; }
  (cd "$ROOT/engine" && uv run python -m tests.tools.scan_transcript "$path" ../testservers/generic/seed.json)
}

h_reveal() {
  local line
  echo "Needs MCP_PRIVACY_GUARD_HOME=$HOME_DIR exported in this terminal, and Claude Code still open."
  echo "In Claude Code run /export, then copy ONE sentence that contains an n-… value."
  line="$(ask 'Paste that sentence here, then Enter: ')"
  printf '%s\n' "$line" | mcp-privacy-guard reveal
  echo
  dim "Real values = revealed. A trailing ⟨?⟩ after a stand-in = unknown to the live session."
}

h_profile() {
  mkdir -p "$HOME_DIR/profiles"
  cp "$ROOT/testservers/generic/profile.example.toml" "$HOME_DIR/profiles/generic.toml"
  mcp-privacy-guard check-profile "$HOME_DIR/profiles/generic.toml"
  dim "Profile installed: $HOME_DIR/profiles/generic.toml (the line above should say it is valid)."
  dim "Next: /exit Claude Code, start it again (cd $ROOT && claude --plugin-dir plugin), run /privacy-guard (generic must say 'profile generic-example', not 'default'),"
  dim "then repeat the check 8 prompt, and press h in check 8 again on the NEW transcript: still 0 real values."
  dim "Fewer stand-ins: count distinct stand-ins in each transcript with"
  dim "  grep -o 'n-[a-z2-7]\\{6,\\}' <transcript> | sort -u | wc -l"
  dim "The count of the new transcript must be lower than the one of check 8."
  dim "Broken profile: run  echo 'not toml [' > $HOME_DIR/profiles/generic.toml , /exit, restart Claude Code: a toast says the profile is invalid."
  dim "Restore afterwards: rm $HOME_DIR/profiles/generic.toml"
}

h_badwarmup() {
  mkdir -p "$HOME_DIR/profiles"
  # self-contained: a copy of the bundled profile would lose its vocabulary files and be rejected
  cat > "$HOME_DIR/profiles/panos-bad.toml" <<'EOF'
[profile]
id = "panos-bad-warmup"
version = 1
description = "Live check 16: a warm-up tool that does not exist"
servers = ["panorama-demo"]

[[warmup]]
tool = "no_such_tool"
args = {}
EOF
  mcp-privacy-guard check-profile "$HOME_DIR/profiles/panos-bad.toml"
  dim "That line must say valid. Now /exit, restart Claude Code: a toast says loading names failed (tool-missing)."
  dim "/privacy-guard must show panorama-demo with profile panos-bad-warmup and warm-up failed."
  dim "Ask a question: it must be dropped, and /clear alone must not lift it."
  dim "Then remove the profile:  rm $HOME_DIR/profiles/panos-bad.toml   and run /clear: questions work again."
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
  [ "$num" -lt "$FROM" ] && return
  echo
  bold "Check $num: $title"
  echo "  Do:     $todo"
  echo "  Expect: $expect"
  [ -n "$helper" ] && echo "  Press h to run the shell step of this check here (see 'Do')."
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
if [ "$FRESH_HOME" = 1 ]; then
  dim "(the repo-local throwaway home <repo>/temp/guard; export the same one before starting Claude Code)"
else
  dim "(taken from MCP_PRIVACY_GUARD_HOME already set in this shell; 'unset MCP_PRIVACY_GUARD_HOME' to use <repo>/temp/guard)"
fi
mkdir -p -m 700 "$HOME_DIR"
if [ -n "$(find "$HOME_DIR" -maxdepth 0 -perm -077 2>/dev/null)" ]; then
  echo "  WARNING  $HOME_DIR is accessible to others; run: chmod 700 \"$HOME_DIR\""
fi
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
dim "Servers:       generic and panorama-demo (baseline) come from $ROOT/.mcp.json; approve them when asked"
dim "                (panos-mcp must be cloned at $(dirname "$ROOT")/panos-mcp)"
dim "Start:         cd $ROOT && claude --plugin-dir plugin"
ask 'Press Enter when Claude Code is running with the plugin... ' >/dev/null

# -- the checks (same order as docs/live-test.md) --------------------------------------------

check 1 "start and early question" \
  "Start; type a question at once" \
  "status line 'loading names (k/n)'; the question is dropped with 'loading names for panorama-demo, try again in a moment'; then a toast and 'active · 1 protected'"
check 2 "/privacy-guard" \
  "Type /privacy-guard" \
  "guard state, then each server with profile, profile state, protected/exempt, warm-up state; no real value"
check 3 "reveal on screen, stand-ins in the transcript" \
  "1) In Claude Code ask: which rules allow traffic to the web servers?  2) Look at the answer on screen.  3) Run /export (choose a file or the clipboard) and read it" \
  "screen: real names (not n-…); /export: only stand-ins (n-…, text-…), no real name"
check 4 "follow-up with a second tool call" \
  "After check 3, ask a follow-up that needs a second tool call, for example: show the details of the first rule in your answer (or: which firewalls are in that device group?)" \
  "the answer names real values and matches the demo data; no error or 'withheld' message"
check 5 "question with real values" \
  "Type a question containing a real IP and a real rule name from the demo data, for example: what is rule Allow-Web-In and which rules use 10.10.0.11?  Then /export" \
  "a toast 'n value(s) replaced' appears; your own row shows the values underlined; /export holds stand-ins in place of them"
check 6 "manual reveal" \
  "Using the Claude Code session that is still open (not a finished one): /export, copy one sentence with an n-… value, paste it when asked" \
  "real values come back (only while the session lives)" h_reveal
check 7 "self-protection" \
  "Ask the model to cat the store or run mcp-privacy-guard table, and to edit .claude/settings.json" \
  "both denied"
check 8 "generic server: nothing leaks" \
  "1) In Claude Code send: Call each of these tools of the generic server once, with no arguments, and tell me in one line what each returned: big, failing, get_config, get_logs, image, keyed, list_devices  (failing returns a tool error on purpose).  2) Press h here: Enter takes the most recent transcript and the scan runs" \
  "the scan prints 0 real values" h_scan
check 9 "profile example, then a broken profile" \
  "Press h to install the example profile. Then: /exit, restart Claude Code, check /privacy-guard shows the new profile for generic, send the check 8 prompt again, scan the NEW transcript (0 real values) and compare the number of distinct n-… stand-ins with check 8. Then break the profile (h prints the command), restart, and read the toast" \
  "0 real values and fewer n-… stand-ins; with broken TOML a toast says the profile is invalid" h_profile
check 10 "session ends" \
  "/exit in Claude Code, then list the sessions folder" \
  "empty" h_sessions
check 11 "new session, new stand-ins" \
  "1) Before check 10's /exit you needed an /export of the old session with an n-… sentence: have one ready (a sentence from an earlier export is fine, e.g. from check 3).  2) Start Claude Code again, ask the check 3 question: which rules allow traffic to the web servers?  3) /export: the n-… names differ from the old ones.  4) Press h, paste the OLD sentence" \
  "the new answer uses different stand-ins than the old export; the old sentence comes back with ⟨?⟩ after its stand-ins (not revealed)" h_reveal
check 12 "/clear" \
  "1) Ask: which rules allow traffic to the web servers?  2) Press h: note the session folder name  3) /clear  4) Ask the same question again  5) Press h again: the old folder is gone, a new one exists  6) /export: new stand-ins" \
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
  "Press h to install a profile for panorama-demo whose warm-up tool does not exist. Then /exit, restart Claude Code, ask any question, then remove the profile (h prints the command) and /clear" \
  "toast 'loading names for panorama-demo failed (tool-missing)'; every question is dropped with that message, also after /clear while the profile is there; after removing it and /clear, questions work" h_badwarmup
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
