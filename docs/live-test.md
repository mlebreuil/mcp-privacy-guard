# Running the live check (tasks T011 and T102)

The automated tests cannot cover what only a real Claude Code terminal shows: the status line,
toasts, the reveal on screen, `/privacy-guard`, `/clear` and `--resume`. This is the short
version of `specs/001-mcp-pseudonymization/quickstart.md` §3–§6. Allow about 45 minutes.

**Guided version**: `scripts/live-test.sh` walks through the table below from a second terminal,
helps with the shell side of each check (scan, reveal, profiles, aging a folder, config), and
writes the results as a markdown table. This document stays the reference.

## 1. Prepare

```sh
cd ~/github/mcp-privacy-guard
export MCP_PRIVACY_GUARD_HOME=$PWD/temp/guard     # throwaway store (git-ignored); use it in every terminal
mkdir -p -m 700 "$MCP_PRIVACY_GUARD_HOME"          # owner-only; see install.md for the required modes
uv tool install --editable ./engine                # puts mcp-privacy-guard on PATH
(cd engine && uv sync && uv run pytest -q)         # all green before you start
```

Add the sandbox settings to `~/.claude/settings.json` (or `.claude/settings.local.json` of a
scratch project), with the real value of `$MCP_PRIVACY_GUARD_HOME` in `denyRead`:

```json
{ "sandbox": { "enabled": true, "allowUnsandboxedCommands": false, "failIfUnavailable": true,
               "filesystem": { "denyRead": ["<value of MCP_PRIVACY_GUARD_HOME>"] } } }
```

The servers are registered by the `.mcp.json` at the repository root: `generic` (the test
server) and `panorama-demo` (`panos-mcp` replaying the `baseline` scenario). Both use paths
relative to the repository root, so `panos-mcp` must be cloned next to this repository
(`../panos-mcp`) and Claude Code started from the root. Approve the project servers when
Claude Code asks. If a server of the same name was added earlier with `claude mcp add`, remove
it (`claude mcp remove <name>`), or the two entries clash. To use another scenario, change
`PANOS_MCP_SAMPLES_SCENARIO` in `.mcp.json`; to change a server, edit the file and run `/mcp`
to reconnect.

Start Claude Code **in a terminal**, from the repository root:

```sh
claude --plugin-dir plugin
```

## 2. Checks (record pass or fail for each)

| # | Do | Expect |
|---|---|---|
| 1 | Start; type a question at once | status line `loading names (k/n)`; the question is dropped with "loading names for panorama-demo, try again in a moment"; then a toast, and `active · 1 protected` |
| 2 | `/privacy-guard` | the guard state, then each server with profile, profile state, protected/exempt, warm-up state; no real value |
| 3 | Ask "which rules allow traffic to the web servers?" | real names, highlighted, on screen; `/export` or the transcript file holds only stand-ins (`n-…`, `text-…`) |
| 4 | Ask a follow-up that needs a second tool call | the answer is right for the real data |
| 5 | Type a real IP and rule name from the demo data | toast "n value(s) replaced"; your row shows them underlined; the transcript holds stand-ins |
| 6 | In a second terminal with the same `MCP_PRIVACY_GUARD_HOME` exported, while the Claude Code session is still open: `/export`, copy one sentence with an `n-…` value, then `echo '<sentence>' \| mcp-privacy-guard reveal` (the text goes in on stdin, never as arguments) | real values come back; a stand-in from an ended session gets `⟨?⟩` |
| 7 | Ask the model to `cat` the store or run `mcp-privacy-guard table`; to edit `.claude/settings.json` | both denied |
| 8 | Run every generic tool, then `cd engine && uv run python -m tests.tools.scan_transcript <transcript> ../testservers/generic/seed.json` | 0 real values |
| 9 | Copy `testservers/generic/profile.example.toml` to `$MCP_PRIVACY_GUARD_HOME/profiles/`, restart, rerun | still 0 real values, fewer `n-…`; with broken TOML a toast says the profile is invalid |
| 10 | `/exit`; `ls $MCP_PRIVACY_GUARD_HOME/store/sessions/` | empty |
| 11 | New session, same question; `reveal` on an old stand-in | different stand-ins; old one not revealed |
| 12 | Ask, then `/clear` | old folder gone, new one exists, new stand-ins |
| 13 | `claude --plugin-dir plugin --resume` | questions blocked ("ended session; start a new one (/clear)"); `/clear` lifts it |
| 14 | `kill -9` a session, `touch -t` its folder to 25+ hours ago, start another | `status` reports `swept: 1` |
| 15 | `chmod 644` a `secret.key`; set `enginePath` to a missing command; remove the `denyRead` entry; VS Code extension; attach an image | each blocks with a message saying how to fix it |
| 16 | A profile with a non-existent warm-up tool | toast with `tool-missing`; questions stay blocked until fixed and `/clear` |
| 17 | `[servers.generic] exempt = true` in `config.toml`; restart; ask the model to pass one of its IPs to a tool | the server receives the same IP; status line shows it exempt |
| 18 | `keep.values = ["9.9.9.9"]`; ask about it | the model sees `9.9.9.9`; a tool call with it reaches the server unchanged |

## 3. T011: facts to note while you are there

- Does `--resume` keep the original session id? (check 13)
- After `/clear`, does the session id change, and does `session.start` fire again? (check 12)
- Does `$.session.turns()` report above 0 for a resumed session?
- Do slash commands that fork raise `command.run` to the plugin's hooks? (try one with an IP in its arguments; the IP must be replaced)

## 4. Record the results

1. Replace the "not run" rows in the *Results* section at the end of
   `specs/001-mcp-pseudonymization/quickstart.md` with pass or fail per check.
2. Write the T011 facts into `research.md` R13/R14, and adjust precondition 5 of
   `contracts/claude-code-plugin.md` if a fact differs.
3. Tick T011 and T102 in `specs/001-mcp-pseudonymization/tasks.md`.
4. Any failure: note the status line or transcript lines (stand-ins only, no real data) and fix
   it test first.
