# Quickstart: Validate the Privacy Guard End to End

Checks that the feature works in a real Claude Code session. Contracts:
[engine CLI](./contracts/engine-cli.md), [plugin](./contracts/claude-code-plugin.md),
[profiles](./contracts/profile-format.md), [stand-in formats](./contracts/standin-formats.md).

## Prerequisites

- Python ≥ 3.11 and `uv`.
- Claude Code ≥ 2.1.303, **in a terminal**. The guard refuses the VS Code extension and the
  desktop app (FR-031).
- Claude Code's sandbox enabled, with `$MCP_PRIVACY_GUARD_HOME` in its read-deny list and
  unsandboxed commands not allowed (FR-026; exact settings in `docs/install.md`).
- `panos-mcp` installed, with its offline demo mode (`PANOS_MCP_SAMPLES_SCENARIO`).
- A throwaway home, so the real store is not touched:
  `export MCP_PRIVACY_GUARD_HOME=$(mktemp -d)/guard`.

## 1. Engine checks (no Claude Code)

```sh
cd engine && uv sync && uv run pytest              # unit, contract, leak tests, benchmark
uv tool install --editable .                       # puts mcp-privacy-guard on PATH
mcp-privacy-guard status --session qs1            # session: "none"
mcp-privacy-guard begin --session qs1             # session: "live"
echo '{"text":"why is 10.1.2.15 blocked to fw-paris-01.corp.example.com?"}' \
  | mcp-privacy-guard prompt --session qs1         # IP and FQDN replaced
mcp-privacy-guard end --session qs1                # {"deleted": true, ...}
mcp-privacy-guard check-profile src/mcp_privacy_guard/profiles/panos-mcp.toml   # valid
```

Expected: every test passes. `prompt` returns two replacements, and the same stand-ins
when run twice in `qs1`. After `end`, `$MCP_PRIVACY_GUARD_HOME/store/sessions/` is empty and
`prompt --session qs1` exits 3. After `begin --session qs2`, the same question gives
different stand-ins.

## 2. Plugin checks

```sh
claude plugin validate plugin
claude plugin test plugin
```

Expected: every test in the plugin contract passes.

## 3. Session with `panos-mcp` (Stories 1–4)

Register `panos-mcp` in Claude Code as usual, with `PANOS_MCP_SAMPLES_SCENARIO=<scenario>`
in its environment. Do not change anything else. Then:

```sh
claude --plugin-dir plugin
```

1. Right at start, the status line shows `privacy-guard: loading names (k/n)`. A question
   typed now is dropped with "loading names for panos, try again in a moment" (FR-034).
   Then a toast says names are loaded, and the status line shows
   `privacy-guard: active · 1 protected`. The start toast and `/privacy-guard` list `panos`
   with profile `panos-mcp` (FR-029).
2. Ask: "which rules allow traffic to the web servers?". On screen, rule and object names
   are real and highlighted. Run `/export` or read the transcript file: it holds only
   stand-ins (`n-…`, `text-…`, stand-in IPs). The same rule name has the same `n-…` in the
   configuration result and in log results.
3. Ask a follow-up the model must answer with a second tool call using a stand-in from the
   first answer (Story 2). The answer is correct for the real data.
4. Type a real IP and a real rule name from the demo data in a question (Story 3). The toast
   says how many values were replaced, and your row shows them underlined. The transcript
   holds stand-ins.
5. In a second terminal, while the session is still open, run `mcp-privacy-guard reveal`
   and paste a transcript line: the real values come back (only while the session lives).
6. Ask the model to `cat` the store or run `mcp-privacy-guard table`: the tool call is
   denied. Ask it to disable the plugin or the sandbox in `.claude/settings.json`: the edit
   is denied.

## 3b. Session-only stand-ins (research R13, R14)

1. During the session from §3, `ls $MCP_PRIVACY_GUARD_HOME/store/sessions/` shows one folder.
   Note a stand-in from the transcript. Exit with `/exit`: `sessions/` is empty.
2. Start a new session and ask the same question: the same real values now have different
   stand-ins. Run `mcp-privacy-guard reveal` on the stand-in noted in step 1: it is not
   revealed.
3. Ask one question, then run `/clear`: the earlier session's folder is gone, a new one
   exists, and the next answer uses new stand-ins.
4. Resume the conversation from step 1 (`claude --plugin-dir plugin --resume`): questions are
   blocked with "this conversation is from an ended session; start a new one (/clear)", and
   MCP results are withheld. `/clear` lifts the block.
5. Kill a session with `kill -9`. Its folder stays. Set its modification time to more than
   24 h ago (`touch -t`), then start a new session: `status` reports `swept: 1` and the
   folder is gone.

## 4. Generic server with the default profile (Story 5, SC-001, SC-008)

Register the test server `testservers/generic/server.py` (seeded with known values listed
in `testservers/generic/seed.json`) under any alias. Restart the session.

1. Run each of its tools. Then run
   `uv run python -m tests.tools.scan_transcript <transcript> testservers/generic/seed.json`.
   It reports 0 real values.
2. Copy `testservers/generic/profile.example.toml` to `$MCP_PRIVACY_GUARD_HOME/profiles/`,
   restart, and run the tools again. Still 0 real values, and fewer `n-…` stand-ins.
3. Break the profile (invalid TOML) and restart. A toast says the profile is invalid, and
   results still contain only stand-ins.

## 5. Failure paths (FR-007, FR-019, FR-025)

1. `chmod 644 $MCP_PRIVACY_GUARD_HOME/store/sessions/*/secret.key` and ask a question: it is blocked,
   with a message saying how to fix it. Run a tool: the model reads that the result was
   withheld.
2. Set the plugin option `enginePath` to a missing command and restart: the status line
   reports the guard unavailable, and questions are blocked.
3. Remove `$MCP_PRIVACY_GUARD_HOME` from the sandbox read-deny list and restart: questions are
   blocked with the settings to add. Restore it.
4. Open the same project in the VS Code extension: questions are blocked with "use Claude
   Code in a terminal".
5. Attach an image to a question in the terminal: it is blocked with "paste the text
   instead".
6. Copy the `panos-mcp` profile to `$MCP_PRIVACY_GUARD_HOME/profiles/`, rename one `warmup`
   tool to a tool that does not exist, and start a session: a toast reports the warm-up
   failure (`tool-missing`) with the fix, and questions stay blocked. Remove the copy and run
   `/clear`: the warm-up runs again and questions are accepted.

## 6. Exemption (Story 6)

Add `[servers.<alias>] exempt = true` to `$MCP_PRIVACY_GUARD_HOME/config.toml` for the generic
server and restart. The status line lists it as exempt, and its results reach the model
unchanged. Ask the model to pass one of its IPs to one of its tools: the server receives
that same IP, not an inverted one (research R15).

Add a public IP to `keep.values` (for example `9.9.9.9`) and ask about it: the model sees
`9.9.9.9`, and a tool call with it reaches the server unchanged.

## Results

Run 2026-10-20 (engine at the Phase 9 state, Claude Code declarations 2.1.304).

| Step | Result |
|---|---|
| §1 `uv sync && uv run pytest` | pass: 495 tests, `-m leak` 200, `-m bench` 3 |
| §1 `status`, `begin`, `prompt` ×2, `end`, `prompt` after `end`, `begin qs2`, `check-profile` | pass: `session: none` then `live`; 2 replacements; same text twice in `qs1`; `sessions/` empty after `end`; `prompt --session qs1` exits 3; `qs2` gives other stand-ins; `panos-mcp` profile valid. Run with `uv run` instead of `uv tool install --editable .` |
| §2 `claude plugin validate plugin` / `claude plugin test plugin` | pass (one warning: no `author` in the manifest) / 127 pass, 0 fail |
| §3, §3b (session with `panos-mcp`, reveal, `/clear`, `--resume`, `kill -9`) | **not run**: needs a live Claude Code terminal session |
| §4 (generic server, profile example, broken profile) | **not run** live; the same checks run in `engine/tests/leak/test_generic_leak.py` and `test_generic_profile.py` (pass) |
| §5 (failure paths) | **not run** live; covered by the plugin tests (`preconditions`, `prompt`, `mcp`, `warmup`) |
| §6 (exemption, keep list) | **not run** live; covered by `operator.test.ts`, `test_operator_lists.py`, `test_fixed_entries.py` (pass) |

## Live run, 2026-10-28 (Claude Code 2.1.310, terminal, `scripts/live-test.sh`)

All 18 guided checks pass (table in `live-test-results.md`). Found and fixed on the way: results
sent to the engine as a non-object (check 3/8), a host that refuses an object result (check 1),
a warm-up that never left `not-started` (check 2/4), HA states shown as stand-ins, the
`/clear` block "ended session" because `turns()` is not 0 after `/clear` (check 12), and a loose
store reported as "session expired" instead of "store unusable" (check 15a).

Not run live: check 15d (VS Code extension; covered by the unit test for the terminal surface),
whether `--resume` keeps the original session id, and the forking slash command (`command.run`).
Reasons recorded in `live-test-results.md` (T011 facts).
