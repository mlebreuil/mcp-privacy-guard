# Implementation Plan: Pseudonymize MCP Data Sent to the Model

**Branch**: `001-mcp-pseudonymization` | **Date**: 2026-10-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-mcp-pseudonymization/spec.md`

## Summary

A Claude Code plugin plus a local Python engine. They pseudonymize every MCP tool result and
every typed question before it reaches the model, translate stand-ins in tool arguments back
to real values, and reveal real values on the user's terminal. The plugin hooks
`tool.call`, `prompt.submit`, `prompt.compose` and `ui.render` (verified against Claude Code
2.1.301, [research R1](./research.md#r1-claude-code-plugin-api-the-main-risk)). It hands every
decision to the stdlib-only engine CLI, which holds the per-user secret, the mapping store,
the profiles and the stand-in generators (keyed Crypto-PAn for IPs, one `n-<token>` per real
name everywhere). Any MCP server is covered by the default profile, and `panos-mcp` gets a
bundled profile. No MCP server or MCP configuration changes. The guard runs only in Claude
Code in a terminal with the sandbox protecting its store. Anywhere else, it blocks questions
and withholds protected results (clarified 2026-10-18).

## Technical Context

**Language/Version**: Python ≥ 3.11 (engine; developed on 3.14). TypeScript for the Claude Code
plugin shim (the host's required language).

**Primary Dependencies**: engine runtime: standard library only. Dev: pytest, hypothesis,
ruff, mypy, `mcp` (test server only). Plugin: Claude Code plugin API 2.1.301, no npm
dependencies.

**Storage**: SQLite (stdlib `sqlite3`, WAL) and a 32-byte key file under
`~/.config/mcp-privacy-guard/store/`, owner-only.

**Testing**: pytest (+ hypothesis) for the engine. `claude plugin validate` / `claude plugin
test` for the plugin. A quickstart end to end with the `panos-mcp` offline demo and a generic
test MCP server.

**Target Platform**: macOS and Linux developer machines running Claude Code in a terminal,
with the sandbox enabled. The VS Code extension and the desktop app are refused (FR-031).

**Project Type**: CLI engine + host plugin (two components in one repository).

**Performance Goals**: under 1 s added per tool call with up to 500 records, and per question
(SC-006). Reveal adds no visible delay (in-memory table, SC-005).

**Constraints**: fail closed everywhere. No network listener. No runtime dependencies. No
global off-switch. Hook `.catch` handlers have 1 s and must not call the engine.

**Scale/Scope**: one user per store. Up to about 100k stand-ins per store. Any number of MCP
servers. Two bundled profiles.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Pre-research | Post-design |
|---|---|---|---|
| I. No real data reaches the model | Every result, error and question is pseudonymized; every failure blocks or withholds; host fail-open defaults overridden; FR-004 floor not reducible | ✅ planned | ✅ `.catch` refusals on every guard hook (plugin contract); profile cannot keep a field, only enum or vocabulary values (profile contract); oversize, timeout and non-text content withheld (R6) |
| II. Local only, self-protecting | Secret, mapping and revealed text stay local; no listener; reveal only on local surfaces; model's tools blocked from the store | ✅ planned | ✅ reveal only on `terminal`, disabled on a spoofed attach (R1); table in plugin memory only; sandbox with a read-deny on the store is required, and its absence blocks the guard; `dangerouslyDisableSandbox` denied (R11) |
| III. Server-agnostic | No server or config change; default protection; knowledge in profile data | ✅ | ✅ `mcp__*` matcher, default profile, profiles as TOML data, invalid profile → default |
| IV. Consistent keyed stand-ins | Deterministic, distinct, shape-preserving, keyed; unknown never guessed | ✅ | ✅ standin-formats contract; one `n-` stand-in per real name across kinds, fields and servers (R7) |
| V. One engine, thin shims | Logic in the Python engine; shim delegates; no disable mode | ⚠️ | ⚠️ the shim applies the engine's reveal table to rendered rows (string substitution) and runs profile-declared warm-up calls. Justified below |
| VI. Test-first, leak gate | Offline suite; leak, fail-closed, consistency, reveal and benchmark tests | ✅ | ✅ R12 and plugin contract tests; quickstart |
| VII. Transparent, no off-switch, simple | Status at start; model told; documentation of coverage; no disable; YAGNI | ✅ | ✅ status line, `prompt.compose` section, no daemon, no dependencies; docs listed in structure |

**Result**: pass, with justified Principle V deviations (Complexity Tracking).

## Project Structure

### Documentation (this feature)

```text
specs/001-mcp-pseudonymization/
├── plan.md              # This file
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   ├── engine-cli.md
│   ├── claude-code-plugin.md
│   ├── profile-format.md
│   └── standin-formats.md
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
engine/
├── pyproject.toml                  # console script: mcp-privacy-guard
├── src/mcp_privacy_guard/
│   ├── cli.py                      # subcommands, exit codes, JSON I/O
│   ├── config.py                   # <home>, operator config, keep/hide lists
│   ├── store.py                    # secret, SQLite mapping, permissions, rev/table
│   ├── standins/
│   │   ├── ip.py                   # keyed Crypto-PAn, special blocks, inversion
│   │   ├── names.py                # n- tokens, collisions
│   │   ├── domains.py              # FQDN, URL, e-mail, user/group, public suffix
│   │   └── misc.py                 # MAC, DIGITS, TEXT
│   ├── classify/
│   │   ├── shapes.py               # whole-value and embedded shape detection
│   │   ├── vocabulary.py           # built-in vocabulary, common words
│   │   ├── walker.py               # JSON walk, path matching, keys, decision order
│   │   └── text.py                 # MIXED rule, plain-text lines
│   ├── profiles/
│   │   ├── loader.py               # TOML schema, validation, selection
│   │   ├── default.toml
│   │   ├── panos-mcp.toml
│   │   └── panos-mcp/              # builtin.txt, applications.txt
│   ├── results.py                  # McpToolResult handling, limits, notices
│   ├── arguments.py                # stand-in → real translation
│   ├── prompts.py                  # question recognition, common-word rule
│   ├── reveal.py                   # manual reveal, observe
│   └── data/                       # public_suffix_list.dat, common_words.txt
└── tests/
    ├── unit/
    ├── contract/                   # CLI shapes, no-off-switch, profile refusals
    ├── leak/                       # panos-mcp fixtures + generic seed, both profiles
    ├── fixtures/panos-mcp/         # recorded offline-demo results per tool
    ├── bench/
    └── tools/scan_transcript.py

plugin/
├── .claude-plugin/plugin.json      # name, version, min host version, enginePath option
├── hooks/hooks.json
├── hooks/register.ts
└── hooks/*.test.ts

testservers/generic/                # dev-only MCP server (Python `mcp` SDK)
├── server.py, seed.json, profile.example.toml

docs/
├── coverage.md                     # what leaves the machine and in what form (SC-009)
├── install.md                      # engine + plugin, permission and sandbox deny rules
└── profiles.md                     # writing a profile in under 30 min (SC-008)

scripts/update-public-suffix.sh
NOTICE                              # Public Suffix List attribution (MPL-2.0)
```

**Structure Decision**: two components, `engine/` (all logic, Python package) and `plugin/`
(Claude Code shim), plus a dev-only test server and user documentation. The engine is
installed separately (`uv tool install`) and found through the plugin's `enginePath` option
(research R3).

## Spec Clarifications Applied (2026-10-18)

1. **Terminal only** (FR-021, FR-023, FR-031): reveal in the terminal. Sessions without a
   terminal surface (VS Code extension, desktop app, `-p`) block questions and withhold
   protected results. Plugin precondition 2.
2. **Pasted text covered** (FR-017): it is part of the question text. No design change.
3. **Attachments blocked** (FR-032): `prompt.submit` drops submissions with attachments.
4. **Sandbox required** (FR-026): plugin precondition 3 reads the settings. The built-in
   tool guard denies `dangerouslyDisableSandbox`.
5. **One stand-in per name** (FR-008, FR-009): every name is `n-<token>`. Profile kinds keep
   their role for question recognition only.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Principle V: the plugin applies the reveal table (longest-match string substitution and marking of unknown stand-ins) on rendered rows | `ui.render` runs on every draw, and a process per draw would break SC-005 | Calling the engine per render: about 100 ms per row, visible lag. The table and the recognition regex both come from the engine, so the shim decides nothing |
| Principle V: the plugin runs profile-declared warm-up tool calls with `$.mcp.call` | Only the host holds the MCP connections. The engine must not contact data sources (Principle II) | No warm-up: names typed before they are first returned would reach the model more often. The shim only forwards the results to `learn` |
| Principle V: the plugin checks host preconditions (terminal surface, sandbox settings, host version) and drops questions with attachments | Only the host knows its surfaces, settings and attachments. The engine never sees them | Passing host state to the engine for a decision: same checks, plus a process call, plus host data crossing for no gain |
| Two components, two languages | The host requires TypeScript for plugins | Classic Python shell hooks cannot rewrite the question or the display (R1) |
