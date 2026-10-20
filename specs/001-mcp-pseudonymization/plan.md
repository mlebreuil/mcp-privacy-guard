# Implementation Plan: Pseudonymize MCP Data Sent to the Model

**Branch**: `001-mcp-pseudonymization` | **Date**: 2026-10-18 (revised 2026-10-19) | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-mcp-pseudonymization/spec.md`

## Summary

A Claude Code plugin plus a local Python engine. They pseudonymize every MCP tool result and
every typed question before it reaches the model, translate stand-ins in tool arguments back
to real values, and reveal real values on the user's terminal. The plugin hooks
`tool.call`, `prompt.submit`, `prompt.compose` and `ui.render` (verified against Claude Code
2.1.301, [research R1](./research.md#r1-claude-code-plugin-api-the-main-risk)). It hands every
decision to the stdlib-only engine CLI, which holds the per-session secret and mapping,
the profiles and the stand-in generators (keyed Crypto-PAn for IPs, one `n-<token>` per real
name everywhere). Stand-ins are valid only within one session: each session gets its own
secret and mapping, created at session start and deleted at `session.end`, and a resumed
conversation is blocked (owner decision 2026-10-19, research R13–R14). Any MCP server is covered by the default profile, and `panos-mcp` gets a
bundled profile. No MCP server or MCP configuration changes. The guard runs only in Claude
Code in a terminal with the sandbox protecting its store. Anywhere else, it blocks questions
and withholds protected results (clarified 2026-10-18).

## Technical Context

**Language/Version**: Python ≥ 3.11 (engine; developed on 3.14). TypeScript for the Claude Code
plugin shim (chosen; the host accepts TypeScript or JavaScript, research R1).

**Primary Dependencies**: engine runtime: standard library only. Dev: pytest, hypothesis,
ruff, mypy, `mcp` (test server only). Plugin: Claude Code plugin API 2.1.301, no runtime npm
dependencies. Dev only: `typescript` for `tsc --noEmit`.

**Storage**: one owner-only folder per live session,
`~/.config/mcp-privacy-guard/store/sessions/<session-id>/`, holding a 32-byte `secret.key`
and `mapping.sqlite` (stdlib `sqlite3`, WAL). It is created at session start and deleted at
session end. Nothing persists between sessions.

**Testing**: pytest (+ hypothesis) for the engine. `claude plugin validate` / `claude plugin
test` for the plugin. A quickstart end to end with the `panos-mcp` offline demo and a generic
test MCP server.

**Target Platform**: macOS and Linux developer machines running Claude Code in a terminal,
with the sandbox enabled. The VS Code extension and the desktop app are refused (FR-031).

**Project Type**: CLI engine + host plugin (two components in one repository).

**Performance Goals**: under 1 s added per tool call with up to 500 records, and per question
(SC-006). Reveal at most 4 ms per rendered row of up to 4 KB with a 100k-entry table
(SC-005 made measurable, research R10), with a plugin benchmark.

**Constraints**: fail closed everywhere. No network listener. No runtime dependencies. No
global off-switch. Hook `.catch` handlers have 1 s and must not call the engine.

**Scale/Scope**: one user per store. Up to about 100k stand-ins per session. Any number of MCP
servers. Two bundled profiles.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Pre-research | Post-design |
|---|---|---|---|
| I. No real data reaches the model | Every result, error and question is pseudonymized; every failure blocks or withholds; host fail-open defaults overridden; FR-004 floor not reducible | ✅ planned | ✅ `.catch` refusals on every guard hook (plugin contract); profile cannot keep a field, only enum or vocabulary values, and `keys = "keep"` never keeps an identifying-shape key (profile contract); oversize, timeout and non-text content withheld (R6); questions held until warm-up completes (FR-034, R9) |
| II. Local only, self-protecting | Secret, mapping and revealed text stay local; no listener; reveal only on local surfaces; model's tools blocked from the store | ✅ planned | ✅ reveal only on `terminal`, disabled on a spoofed attach (R1); table in plugin memory only; sandbox with a read-deny on the store is required, and its absence blocks the guard; `dangerouslyDisableSandbox` denied (R11); secret, mapping and real values on disk only while their session lives; nothing persists (R13); writes to Claude Code settings and plugin state denied, so the model cannot disable the guard or the sandbox (R11) |
| III. Server-agnostic | No server or config change; default protection; knowledge in profile data | ✅ | ✅ `mcp__*` matcher, default profile, profiles as TOML data, invalid profile → default |
| IV. Consistent keyed stand-ins (v2.0.0) | Deterministic, distinct, shape-preserving, keyed; one type-independent name form; unknown never guessed | ✅ | ✅ standin-formats contract; one `n-` stand-in per real name across kinds, fields and servers (R7); per-session secret, stand-ins valid in one session only; only `begin` creates a secret, so it is never replaced mid-session (R13); resumed conversations blocked, so old stand-ins are never inverted with another secret (R14); keep-list and exempt-server IPs recorded as fixed, never inverted, and ambiguity refused (R15) |
| V. One engine, thin shims | Logic in the Python engine; shim delegates; no disable mode | ⚠️ | ⚠️ the shim applies the engine's reveal table to rendered rows (string substitution) and runs profile-declared warm-up calls. Justified below |
| VI. Test-first, leak gate | Offline suite; leak, fail-closed, consistency, reveal and benchmark tests | ✅ | ✅ R12 and plugin contract tests, including the session, resume, warm-up and ambiguity fail-closed paths; benchmarks for SC-006 (engine) and SC-005 (reveal, R10); leak fixtures checked for every FR-004 shape; quickstart |
| VII. Transparent, no off-switch, simple | Status at start; model told; documentation of coverage; no disable; YAGNI | ✅ | ✅ status line plus per-server toast and `/privacy-guard` (each server's profile or exemption, R16), `prompt.compose` section, no daemon, no dependencies; docs listed in structure |

**Result**: pass, with justified Principle V deviations (Complexity Tracking). Re-checked
2026-10-19 against constitution v2.0.0: the post-design column now covers analysis findings
D1, D2, D3, H1, H3, H5 and H6. D4, H2 and H4 are task-ordering issues for `/speckit-tasks`.

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
│   ├── store.py                    # session folder: begin/end/sweep, secret, mapping, names, permissions, rev/table
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
    └── tools/                      # scan_transcript.py, record_panos_fixtures.py

plugin/
├── .claude-plugin/plugin.json      # name, version, min host version, enginePath option
├── hooks/hooks.json
├── hooks/register.ts                # registrations only
├── hooks/engine.ts                  # engine runner, reveal table merge
├── hooks/preconditions.ts           # host, surface, sandbox, session checks; block reason
├── hooks/session.ts                 # session.start / session.end, session id tracking
├── hooks/guard.ts                   # built-in tool guard
├── hooks/mcp.ts                     # MCP tool.call: args, result, exempt
├── hooks/prompt.ts                  # prompt.submit
├── hooks/command.ts                 # command.run, skill.prompt (slash-command args, skill text)
├── hooks/warmup.ts                  # warm-up calls and progress
├── hooks/reveal.ts                  # ui.render, observe, attach
├── hooks/status.ts                  # per-server toast, /privacy-guard
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

## Owner Decision Applied (2026-10-19)

"Key rotation is not required during a session. Mappings are deleted at the end of the
session." Then: "All stand-ins should be only valid during one session. No persisted ones."
Constitution IV (v2.0.0), spec FR-008, FR-010, FR-025, FR-033 and SC-004 were updated to
match.

1. **Per-session secret and mapping** (research R13): `begin` creates
   `store/sessions/<id>/` with a new secret at session start, and `end` deletes it from a
   `session.end` hook. Folders of sessions that end without the hook are swept after
   24 hours untouched. The engine CLI takes `--session` on every session command, and the
   plugin follows `$.session.id()` across `/clear`.
2. **No re-keying**: only `begin` creates a secret. Every other command exits 3 when the
   folder is missing, so stand-ins already in a conversation are never read with another
   key.
3. **Resumed conversations blocked** (FR-033, research R14): no live folder and
   `$.session.turns()` > 0 → block until `/clear`. This replaces the earlier
   "secret older than conversation" check and resolves analysis finding D2.
4. **Consequences**: the same value gets different stand-ins in different sessions. The
   name dictionary and warm-up are per session, so names typed before the warm-up finishes
   would be missed in each session. Item 5 closes that gap for servers with a warm-up.
   Manual `reveal` works only while the session lives. Stand-in formats keep their original
   token lengths.
5. **Questions wait for the warm-up** (FR-034, research R9): `begin --servers` records the
   pending warm-ups. The plugin reports progress with a new `warmup` subcommand. `prompt`
   exits 4 (`warmup-pending` / `warmup-failed`) until every warm-up is complete. A failed
   warm-up keeps questions blocked until `/clear` or a profile fix.
6. **Only pseudonymization layer**: the guard replaces the pseudonymization inside MCP
   servers. The `panos-mcp` profile must handle its raw results, and the leak fixtures are
   raw tool output from the offline demo samples (pseudonymized only by `panos-mcp`'s sample
   creation). The recording script fails if any FR-004 shape is missing from them (research
   R12). Removing runtime pseudonymization from `panos-mcp` is tracked in that project.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Principle V: the plugin applies the reveal table (longest-match string substitution and marking of unknown stand-ins) on rendered rows | `ui.render` runs on every draw, and a process per draw would break SC-005 | Calling the engine per render: about 100 ms per row, visible lag. The table and the recognition regex both come from the engine, so the shim decides nothing |
| Principle V: the plugin runs profile-declared warm-up tool calls with `$.mcp.call` | Only the host holds the MCP connections. The engine must not contact data sources (Principle II) | No warm-up: names typed before they are first returned would reach the model more often. The shim only forwards the results to `learn` |
| Principle V: the plugin checks host preconditions (terminal surface, sandbox settings, host version) and drops questions with attachments | Only the host knows its surfaces, settings and attachments. The engine never sees them | Passing host state to the engine for a decision: same checks, plus a process call, plus host data crossing for no gain |
| Two components, two languages | The host requires a hooks module in TypeScript or JavaScript. We choose TypeScript to type the plugin against `claude-code.d.ts` (R1) | Classic shell hooks (Python) cannot rewrite the question (`UserPromptSubmit` only adds context or suppresses). They cannot translate tool arguments or gate the reveal on the surface, and they have no `.catch` refusal. `MessageDisplay` covers assistant text only (R1). A JavaScript module would avoid the type checks for no gain |
