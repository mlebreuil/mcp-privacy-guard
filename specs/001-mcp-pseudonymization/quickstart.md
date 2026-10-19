# Quickstart: Validate the Privacy Guard End to End

Checks that the feature works in a real Claude Code session. Contracts:
[engine CLI](./contracts/engine-cli.md), [plugin](./contracts/claude-code-plugin.md),
[profiles](./contracts/profile-format.md), [stand-in formats](./contracts/standin-formats.md).

## Prerequisites

- Python ≥ 3.11 and `uv`.
- Claude Code ≥ 2.1.301, **in a terminal**. The guard refuses the VS Code extension and the
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
mcp-privacy-guard status                           # store: "absent"
echo '{"text":"why is 10.1.2.15 blocked to fw-paris-01.corp.example.com?"}' \
  | mcp-privacy-guard prompt                       # IP and FQDN replaced; store now "ready"
mcp-privacy-guard check-profile src/mcp_privacy_guard/profiles/panos-mcp.toml   # valid
```

Expected: every test passes. `prompt` returns two replacements, and running it twice gives
the same stand-ins.

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

1. The status line shows `privacy-guard: active · 1 protected`, with profile `panos-mcp`.
2. Ask: "which rules allow traffic to the web servers?". On screen, rule and object names
   are real and highlighted. Run `/export` or read the transcript file: it holds only
   stand-ins (`n-…`, `text-…`, stand-in IPs). The same rule name has the same `n-…` in the
   configuration result and in log results.
3. Ask a follow-up the model must answer with a second tool call using a stand-in from the
   first answer (Story 2). The answer is correct for the real data.
4. Type a real IP and a real rule name from the demo data in a question (Story 3). The toast
   says how many values were replaced, and your row shows them underlined. The transcript
   holds stand-ins.
5. In a second terminal, run `mcp-privacy-guard reveal` and paste a transcript line: the real
   values come back.
6. Ask the model to `cat` the store or run `mcp-privacy-guard table`: the tool call is
   denied.

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

1. `chmod 644 $MCP_PRIVACY_GUARD_HOME/store/secret.key` and ask a question: it is blocked,
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

## 6. Exemption (Story 6)

Add `[servers.<alias>] exempt = true` to `$MCP_PRIVACY_GUARD_HOME/config.toml` for the generic
server and restart. The status line lists it as exempt, and its results reach the model
unchanged.
