# CLAUDE.md

Guidance for agents working in this repository. The constitution
(`.specify/memory/constitution.md`) takes precedence over this file. If they ever disagree,
follow the constitution and fix this file.

## What this is

**mcp-privacy-guard** pseudonymizes every MCP tool result and every question before they
reach the model provider, translates stand-ins in tool arguments back to real values, and
reveals real values only on the user's own terminal. It is the only pseudonymization layer
for MCP data. MCP servers and the MCP configuration are not changed.

Two components:

- `engine/`: Python ≥ 3.11 package and CLI `mcp-privacy-guard`. **All** logic lives here:
  classification, stand-in generation, the session store, profiles, translation and reveal.
  Standard library only at runtime.
- `plugin/`: Claude Code plugin in TypeScript. A thin shim that hands every decision to the
  engine CLI (JSON over stdin/stdout). It holds no cryptography, classification or mapping
  logic.

Also: `testservers/generic/` (dev-only MCP server for tests), `docs/` (user documentation).

## Where things are

- Feature 001 design: `specs/001-mcp-pseudonymization/`. Read `spec.md` (requirements,
  clarifications), `plan.md`, `research.md` (decisions R1–R16), `data-model.md`,
  `contracts/` (engine CLI, plugin hooks, profile format, stand-in formats) and
  `quickstart.md` (end-to-end checks).
- Work plan: `specs/001-mcp-pseudonymization/tasks.md`. Tasks are test-first and ordered.
  Mark a task `[x]` when it is done.

## Workflow

- Spec Kit flow: specify → clarify → plan → tasks → implement (`/speckit-*` commands).
  `/speckit-analyze` checks consistency.
- A design decision must be carried through every artifact it touches (constitution if
  needed, spec, plan/research, contracts, data model, tasks), never left in one file.
- Items marked **Verify at implementation** in `research.md` are re-checked when the related
  task starts, and the result is recorded there. To read the Claude Code plugin API
  declarations, load the `plugin-authoring` skill. It writes `claude-code.d.ts` and names
  its path.

## Non-negotiable rules (from the constitution)

- **Fail closed.** If a result cannot be processed, it is withheld. If a question cannot be
  checked, it is not sent. Every guard hook carries a `.catch` that refuses.
- **No off-switch.** No setting, flag or environment variable disables pseudonymization. The
  only opt-out is an operator exemption of a server by name.
- **Session-only stand-ins.** Each session has its own secret and mapping, deleted when the
  session ends. Nothing that links stand-ins to real values persists. Only `begin` creates a
  secret.
- **Local only.** The secret, the mappings and revealed text never leave the machine, never
  appear in logs, errors or status output, and are never kept in host-synced storage. The
  engine opens no listener and contacts no data source.
- **Test first.** Write the test, see it fail, then write the code. Leak tests are the merge
  gate. Never weaken a leak or fail-closed test to make it pass.
- **No real data in the repository.** Fixtures and samples are synthetic or sanitized.
- **New runtime dependencies, long-lived helpers or more languages** need a justification in
  `plan.md` Complexity Tracking.

## Commands

```sh
cd engine && uv sync                      # install with dev dependencies
uv run pytest                             # all tests; -m leak / -m bench for the gates
                                          # CI skips bench (shared runners are too slow): run it locally
uv run ruff check . && uv run mypy src    # lint and type checks
claude plugin validate plugin             # plugin manifest and module
claude plugin test plugin                 # plugin tests (*.test.ts)
CLAUDE_CODE_DTS=<path> scripts/typecheck-plugin.sh   # tsc; prints SKIPPED without the d.ts
```

Use a throwaway home for manual runs: `export MCP_PRIVACY_GUARD_HOME=$(mktemp -d)/guard`.

## Working notes

- **Progress**: `grep -n "^- \[ \]" specs/001-mcp-pseudonymization/tasks.md` lists what is left.
  Phases 1–5 (US1–US3) are done and committed; Phases 6–9 (US4–US6 and polish) are done except T011 and T102, which need a live Claude Code session; not yet committed; the guard has not yet been run in a live Claude
  Code session (quickstart, T102).
- **Plugin type declarations**: `claude-code.d.ts` is written only by the `plugin-authoring`
  skill, into a per-process temp folder. Set `CLAUDE_CODE_DTS` to its path for `tsc`.
- **Plugin tests** use the `claude-code/testing` kit with the fake host in
  `plugin/hooks/test-support.ts`. Bottom hooks answer `$` calls with `{ value }` or `{ deny }`.
- **Fixtures**: `engine/tests/tools/record_panos_fixtures.py --panos ~/github/panos-mcp`
  re-records the `panos-mcp` fixtures (needs that repository and `uv`). The generic test server
  is `testservers/generic/` (seed values in `seed.json`).
- **Lint**: `ruff check --fix` can reorder `tests.*` and `mcp_privacy_guard` imports whenever a
  module is new; run it again once the module exists.
- **Residual risks to document** (`docs/coverage.md`, T098): names that are plain English words
  and unquoted in free text, names with spaces in questions, a server that connects after a
  question, a partial PAN-OS application list.

## Conventions

- Engine CLI exit codes: `0` ok, `2` bad input, `3` store unavailable, `4` refused, `5`
  internal error. Error replies are `{"error": {"code", "message", "hint"}}` with no input
  value (`contracts/engine-cli.md`).
- Changes to stand-in formats, the store schema, or engine exit codes and payloads are
  breaking. They need a migration note and a version bump.
- Commit only when asked. A commit message covers every change since the previous commit.
