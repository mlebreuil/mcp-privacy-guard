---

description: "Task list for 001-mcp-pseudonymization"
---

# Tasks: Pseudonymize MCP Data Sent to the Model

**Input**: Design documents from `/specs/001-mcp-pseudonymization/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Required. Constitution Principle VI (non-negotiable): write each test first and see
it fail before writing the code that makes it pass. Leak tests are the merge gate.

**Organization**: Tasks are grouped by user story so each story can be implemented and tested
on its own.

**Regenerated 2026-10-19** after constitution v2.0.0, session-only stand-ins (research R13,
R14), the warm-up gate (FR-034, R9) and the gate fixes R15 and R16. It also resolves the
`/speckit-analyze` findings D4 (verification tasks come before the code that relies on them),
H2 (the `prompt.submit` `.catch`) and H4 (`table` is built in Phase 2).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on unfinished tasks)
- **[Story]**: The user story the task belongs to (US1–US6)
- Paths are relative to the repository root. `<home>` is `$MCP_PRIVACY_GUARD_HOME`, default
  `~/.config/mcp-privacy-guard`. `<sid>` is a Claude Code session id.

## Path Conventions

- Engine: `engine/src/mcp_privacy_guard/`, tests in `engine/tests/`
- Plugin: `plugin/` (`plugin/hooks/register.ts`, tests `plugin/hooks/*.test.ts`)
- Dev-only test MCP server: `testservers/generic/`
- User documentation: `docs/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the repository layout and tooling.

- [x] T001 Create the directory layout from plan.md "Source Code": `engine/src/mcp_privacy_guard/{standins,classify,profiles,data}/`, `engine/tests/{unit,contract,leak,fixtures/panos-mcp,bench,tools}/`, `plugin/{.claude-plugin,hooks}/`, `testservers/generic/`, `docs/`, `scripts/`, each Python package with an empty `__init__.py`
- [x] T002 Create `engine/pyproject.toml`: project `mcp-privacy-guard` 0.1.0, `requires-python = ">=3.11"`, **no runtime dependencies**, hatchling build backend, console script `mcp-privacy-guard = "mcp_privacy_guard.cli:main"`, dev dependency group `pytest`, `hypothesis`, `ruff`, `mypy`, `mcp`; package data includes `profiles/*.toml`, `profiles/**/*.txt`, `data/*`
- [x] T003 [P] Configure ruff (line length 100, rules E,F,I,B,UP,S) and mypy (`strict = true`) in `engine/pyproject.toml`, and pytest (`testpaths = ["tests"]`, markers `leak`, `bench`)
- [x] T004 [P] Create `plugin/.claude-plugin/plugin.json` (`name` `mcp-privacy-guard`, `version` `0.1.0`, description, minimum Claude Code version (`2.1.303`, enforced by the T037 check since the manifest has no version field), user option `enginePath` string default `mcp-privacy-guard`, no option that disables anything) and `plugin/hooks/hooks.json` (`{ "modules": ["./register.ts"] }`) with an empty `register` export in `plugin/hooks/register.ts`. Also create `plugin/tsconfig.json` (`strict`, `noEmit`, extending the `tsconfig.json` and `claude-code.d.ts` that the `plugin-authoring` skill writes) and a dev dependency on `typescript`
- [x] T005 [P] Add `.gitignore` entries (`.venv/`, `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `dist/`, `*.sqlite`, `*.sqlite-wal`, `*.sqlite-shm`, `secret.key`) in `.gitignore`
- [x] T006 [P] Add `scripts/update-public-suffix.sh` that downloads `https://publicsuffix.org/list/public_suffix_list.dat` into `engine/src/mcp_privacy_guard/data/public_suffix_list.dat`, run it once, and add `NOTICE` at the repository root attributing the Public Suffix List (MPL-2.0)
- [x] T007 [P] Add `engine/src/mcp_privacy_guard/data/common_words.txt`: about 5,000 lower-case English words with no proper nouns, plus networking terms (`inside`, `outside`, `trust`, `untrust`, `dmz`, `web`, `test`, `prod`, `dev`, `lan`, `wan`, `mgmt`), one per line, sorted; record its source and licence in `NOTICE`
- [x] T008 Create CI workflow `.github/workflows/ci.yml`: job `engine` (uv sync, ruff, mypy, pytest on Python 3.11 and 3.14); job `plugin` running `claude plugin validate plugin`, `tsc -p plugin` and `claude plugin test plugin`; each prints `SKIPPED: claude CLI not available` (or, for `tsc`, `SKIPPED: claude-code.d.ts not available`, since only the host's skill writes that file) and exits 0 when its prerequisite is absent, so the skip shows in the log (constitution, Development Workflow)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Host facts verified, session store, stand-in generators, shape detection, profile
loader, CLI skeleton with `status`/`begin`/`end`/`table`, and the plugin's fail-closed core and
session lifecycle. Every user story depends on these.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Verify host facts first (constitution: "re-checked when the related task starts")

- [x] T009 Verify the **Verify at implementation** items of research R1 against the Claude Code types (load the `plugin-authoring` skill; it writes `claude-code.d.ts` and names its path): the shape of `result` for an MCP tool from core (expected `McpToolResult` with `content`, `isError`, `structuredContent`) and the shape a hook returns for `{ result }`; whether a hook can replace an errored MCP result with `{ result }` (fallback: `{ deny: <pseudonymized error text> }`); how `mcp__<server>__<tool>` maps to the alias when names contain `__` (expected: connected-tool listing `ContextMcpTool { name, server }`); the minimum host version to pin. Record the findings in `specs/001-mcp-pseudonymization/research.md` R1, and correct `contracts/claude-code-plugin.md` if a fact differs
- [x] T010 Verify research R11: the exact settings keys of Claude Code ≥ 2.1.303 for sandbox enablement, the filesystem read-deny list and the unsandboxed-command escape; whether managed (`policy`) settings can enforce them and pin the plugin enabled (`enabledPlugins`). Record the findings in research R11, and update precondition 3 in `contracts/claude-code-plugin.md` with the exact keys
- [ ] T011 Verify research R13 and R14: `session.end` fires for `prompt_input_exit`, `clear`, `resume`, `logout` and `other` with `e.sessionId` and `next.budget`; after `/clear` the session id changes and no `session.start` fires; `$.session.turns()` is above 0 at `session.start` of a resumed (`--resume`, `--continue`) session; whether `--resume` keeps the original session id; `session.start` fires again on a module reload. Declarations read 2026-10-20 on 2.1.303 (research R13/R14); the live-run facts remain. The minimum host version is pinned at 2.1.303 (owner decision 2026-10-20); lower it only after the facts are checked on an older build. Record the findings in research R13/R14, and adjust precondition 5 in `contracts/claude-code-plugin.md` if a fact differs

### Tests for the foundation (write first, see them fail)

- [x] T012 [P] Write `engine/tests/unit/test_store.py`: `begin(sid)` creates `<home>/store/sessions/<sid>/` with mode `0700`, `secret.key` of 32 bytes with mode `0600`, and `mapping.sqlite` with mode `0600`; `begin` on an existing folder raises `Refused("session-live")`; every other store operation on a missing folder raises `StoreUnavailable("session-missing")` and creates nothing; a `secret.key` with mode `0644` → `StoreUnavailable("too-permissive")`; an unreadable one → `StoreUnavailable("unreadable")`; `<home>/store` inside a git work tree that does not ignore it → `StoreUnavailable("in-git-tree")`; `<sid>` not matching `[A-Za-z0-9_-]{1,128}` → `BadInput`; `end(sid)` deletes the folder with `mapping.sqlite`, `-wal` and `-shm`, and succeeds when it is already gone; `sweep()` deletes other sessions' folders whose last change is over 24 hours old and never the caller's; `issue()` is idempotent for the same `(kind, real)`; `rev` starts at 1 per session and strictly increases; `table(since)` returns only newer rows; two sessions have different secrets and separate tables; an ephemeral in-memory store with a fixed test key works the same way
- [x] T013 [P] Write `engine/tests/unit/test_ip.py` with hypothesis: the keyed Crypto-PAn permutation is a bijection on random IPv4/IPv6; `invert(permute(x)) == x`; the shared prefix length of any two addresses is preserved; RFC 1918, CGNAT `100.64/10`, loopback, link-local, multicast, broadcast, documentation ranges, `fc00::/7` and `fe80::/10` keep their block; public IPv4 keeps its first octet and global IPv6 its first 16 bits; `0.0.0.0/0`, `255.255.255.0` and `any` are unchanged; prefixes and ranges map consistently (the stand-in of `10.1.2.15` lies inside the stand-in of `10.1.2.0/24`); two different keys give different permutations
- [x] T014 [P] Write `engine/tests/unit/test_names.py`: `n-` + 6 base32 lower-case characters (`[a-z2-7]`); deterministic for the same session secret; different for different secrets; same stand-in for the same real whatever kind is passed (FR-009); a forced collision within the session's mapping increments `attempt` and lengthens the token by 2 characters
- [x] T015 [P] Write `engine/tests/unit/test_domains.py`: FQDN labels below the public suffix replaced (`h-` + `t(6)` leftmost, `d-` + `t(6)` others), public suffix kept, two hosts under one parent share the parent stand-in; URL keeps scheme and port and replaces path, query and fragment with `/p-<t(6)>`; e-mail is `u-<t(6)>@<fqdn stand-in>`; `DOMAIN\user` → `dom-<t>\u-<t>` and groups → `dom-<t>\g-<t>`
- [x] T016 [P] Write `engine/tests/unit/test_misc_standins.py`: MAC → a keyed Feistel permutation of the 46 bits other than the two low bits of the first octet, which are fixed to `10` (locally administered, unicast; hypothesis: no two random MACs collide; a bijection, unlike a fixed `02:` prefix, which would collide MACs that differ only in the first octet); DIGITS keeps the length, digits only (a leading zero is allowed, so the map is a bijection), and is a keyed Feistel permutation (hypothesis: no two inputs of one length collide); TEXT → `text-` + 8 characters (`t(8)`), equal inputs give equal outputs
- [x] T017 [P] Write `engine/tests/unit/test_shapes.py`: whole-value detection of IPv4/IPv6 address, prefix, range and wildcard, URL, e-mail, MAC, `DOMAIN\user`, FQDN (only when it ends in a public suffix), digit runs of 7 or more (`DIGITS`); embedded detection returns spans in free text; timestamps (RFC 3339, ISO 8601), durations and up to 6-digit numeric strings are reported as safe forms
- [x] T018 [P] Write `engine/tests/unit/test_profile_loader.py`: the bundled `default.toml` loads; a profile with a vocabulary or enum value of identifying shape (IP, FQDN, e-mail, MAC, URL, `DOMAIN\user`, 7+ digits) is refused; kind names must match `[A-Z][A-Z0-9_]*` and must not redefine a core kind; `profile.id` must match `[a-z0-9-]+` and `profile.version` must be 1; each field rule has exactly one of `kind`/`enum`/`keys`, and `keys` is `keep` or `hide`; invalid path patterns are refused; path pattern matching of `name`, `*`, `[]` and `**` (zero or more steps) against sample JSON paths; tool-specific rules are tried before general ones; first match wins; a profile without `warmup` that applies to a server whose bundled profile has one is refused (`warmup-required`)
- [x] T019 [P] Write `engine/tests/contract/test_cli_envelope.py`: every subcommand reads at most one JSON object on stdin and writes one on stdout; on a non-zero exit stdout is `{"error": {"code", "message", "hint"}}` and contains no input value; exit codes `2` bad input (including a malformed `--session`), `3` store unavailable (including a missing session folder), `4` refused (including `begin` on a live session), `5` internal error; `status` exits `0`, creates nothing and never prints a store value, reports `store`, and with `--session` reports `session` (`live|none|unreadable|too-permissive`), `rev` and `swept`; `begin --session <sid> --servers a` prints `{"session": "live", "swept", "warmup"}`; `end --session <sid>` prints `{"deleted", "swept"}` and exits 0 whether or not the folder existed; `table --session <sid> --since 0` prints `{"table": {"rev", "entries"}}`
- [x] T020 [P] Write `plugin/hooks/preconditions.test.ts`: a session whose `$.session.surfaces()` lacks `terminal` sets the block reason "privacy guard: use Claude Code in a terminal"; settings without the sandbox enabled, without `<home>` in its filesystem read-deny list, or allowing unsandboxed commands set a block reason that names the settings to add; a host older than 2.1.303 sets a block reason; engine `status` failing (missing command, exit ≠ 0, timeout, invalid JSON) sets a block reason; `session: "none"` with `turns()` > 0, or a throwing `turns()`, sets "privacy guard: this conversation is from an ended session; start a new one (/clear)" and does not call `begin` (FR-033); `session: "none"` with `turns()` = 0 calls `begin --session <sid> --servers <connected aliases>`; `session: "live"` calls neither; all checks passing clears the block reason (the engine-exit-3 "session expired" case is tested in `mcp.test.ts`, T048, where a later engine call exists)
- [x] T021 [P] Write `plugin/hooks/guard.test.ts`: `Read` of `<home>/store/sessions/<sid>/mapping.sqlite` or `…/secret.key`, `Grep`/`Glob` under `<home>`, `Bash` running `mcp-privacy-guard table`, `mcp-privacy-guard reveal` or `python -m mcp_privacy_guard`, `Edit`/`Write` inside the plugin folder, `Edit` of `.claude/settings.json` or `.claude/settings.local.json`, `Write` to `~/.claude/settings.json`, `~/.claude.json` or under `~/.claude/plugins/`, `Bash` writing `~/.claude/settings.json`, and `Bash` with `dangerouslyDisableSandbox: true` are denied; an unrelated `Read` passes; a throw inside the guard hook still denies (`.catch`)
- [x] T022 [P] Write `plugin/hooks/session.test.ts`: `session.end` runs `end --session <e.sessionId>` with a timeout within `next.budget`, empties the reveal table and calls `next(e)`; a failing or hanging `end` does not delay `next(e)` past the budget; a changed `$.session.id()` seen at the start of any hook empties the reveal table, resets `rev` to 0 and re-runs the preconditions (so `begin` runs for the new id); `session.start` keeps the server map and the `recognise` regex from `status` and loads `table --session <sid> --since 0`; the status line is `privacy-guard: active · n protected · m exempt` or the block reason

### Implementation of the foundation

- [x] T023 Implement `engine/src/mcp_privacy_guard/config.py`: resolve `<home>` from `MCP_PRIVACY_GUARD_HOME` or `~/.config/mcp-privacy-guard`; load `<home>/config.toml` with `tomllib` into a typed object with exactly `keep.values`, `keep.files`, `hide.values`, `hide.files`, `servers.<alias>.profile`, `servers.<alias>.exempt` (unknown keys → error); **no key that disables pseudonymization** (FR-027)
- [x] T024 Implement `engine/src/mcp_privacy_guard/store.py` to pass T012: session folder `<home>/store/sessions/<sid>/` (`0700`), `<sid>` matching `[A-Za-z0-9_-]{1,128}`; `begin(sid)` creates `secret.key` (32 bytes from `secrets.token_bytes`, `0600`) and `mapping.sqlite` (`0600`, WAL, `busy_timeout` 5 s) and refuses an existing folder; every other operation raises `StoreUnavailable("session-missing")` on a missing folder and never creates a secret; table `standin(standin TEXT UNIQUE, token TEXT NULL, kind TEXT, real TEXT, rev INTEGER, first_seen TEXT, fixed BOOL DEFAULT 0)` with `UNIQUE(kind, real)`; table `names(real TEXT, kind TEXT, server TEXT, common_word BOOL, UNIQUE(real, kind))`; table `meta(key TEXT PRIMARY KEY, value TEXT)` with `schema_version`, `session_id`, `created_at` and per server `warmup_state`/`warmup_reason`; methods `issue(kind, real, standin, token=None, fixed=False)`, `lookup_standin(standin)`, `lookup_token(token)`, `table(since)`, `rev()`, `end(sid)` (delete folder incl. `-wal`/`-shm`, idempotent), `sweep(except_sid)` (delete folders untouched over 24 h), `ephemeral(key)` for tests; permission and git-tree checks; never logs values
- [x] T025 [P] Implement `engine/src/mcp_privacy_guard/standins/ip.py` to pass T013: Crypto-PAn with HMAC-SHA256 as the pseudo-random function, keyed by the session secret, special-block bit fixing, public first octet (v4) / first 16 bits (v6) kept, `permute()` and `invert()` for addresses, prefixes, ranges and wildcards, per-process cache keyed by secret
- [x] T026 [P] Implement `engine/src/mcp_privacy_guard/standins/names.py` to pass T014: `t(n)` = first `n` characters of lower-case unpadded base32 of HMAC-SHA256(session secret, domain ‖ 0x1f ‖ value ‖ 0x1f ‖ attempt); name stand-in `n-` + `t(6)` with domain `name` independent of kind; on collision (token already used by another real in the session's mapping) attempt+1 and grow the length by 2
- [x] T027 [P] Implement `engine/src/mcp_privacy_guard/standins/domains.py` to pass T015, using the bundled public suffix list parsed once per process
- [x] T028 [P] Implement `engine/src/mcp_privacy_guard/standins/misc.py` to pass T016 (keyed Feistel permutations for MAC (46 bits, first-octet low bits `10`) and DIGITS, `t(8)` for TEXT)
- [x] T029 Implement `engine/src/mcp_privacy_guard/standins/__init__.py` with `pseudonymize(kind, real, store, key) -> str`, which dispatches to the generators and records every issued stand-in (including IPs and label-level FQDN stand-ins) in the session's mapping (depends on T024–T028)
- [x] T030 [P] Implement `engine/src/mcp_privacy_guard/classify/shapes.py` to pass T017
- [x] T031 [P] Implement `engine/src/mcp_privacy_guard/classify/vocabulary.py`: the built-in safe vocabulary (`true`, `false`, `yes`, `no`, `none`, `null`, `allow`, `deny`, `drop`, `permit`, `block`, `enabled`, `disabled`, `up`, `down`, `active`, `inactive`, `tcp`, `udp`, `icmp`, `ipv4`, `ipv6`, `http`, `https`, `ssh`, `dns`, `ntp`, `info`, `informational`, `low`, `medium`, `high`, `critical`, `warning`, `error`, `debug`, HTTP methods, well-known service names), the common-word list loader, and `is_safe_word()`
- [x] T032 Implement `engine/src/mcp_privacy_guard/profiles/loader.py` to pass T018: TOML schema from contracts/profile-format.md (`profile.id` `[a-z0-9-]+`, `profile.version` = 1, `servers` globs, `kinds.<KIND>.cues`, `vocabulary.values`/`files`, `fields[]` with `path`, optional `tools`, exactly one of `kind`/`enum`/`keys`, `text.mode` `mixed`|`whole`, `warmup[]` with `tool`/`args`); path pattern compiler; profile states `valid`/`invalid` with reasons; selection order: `servers.<alias>.profile` in config, then the user profile in `<home>/profiles/` whose globs match, then the bundled profile whose globs match, then `default`
- [x] T033 [P] Write `engine/src/mcp_privacy_guard/profiles/default.toml`: `id = "default"`, `version = 1`, no field rules, no warm-up, `text.mode = "mixed"`
- [x] T034 Implement `engine/src/mcp_privacy_guard/cli.py` to pass the envelope part of T019: `argparse` subcommands `status`, `begin`, `end`, `table`, `result`, `args`, `prompt`, `learn`, `warmup`, `observe`, `reveal`, `check-profile` (those not built yet exit 5); `--session` validated against `[A-Za-z0-9_-]{1,128}`; JSON in and out; the error envelope; exception → exit code mapping (`BadInput` 2, `StoreUnavailable` 3, `Refused` 4, other 5); logging to stderr without values (checked by T107); a reply helper that adds `"table": {"rev", "entries"}` after `--since`
- [x] T035 Implement `status`, `begin`, `end` and `table` in `engine/src/mcp_privacy_guard/cli.py` per contracts/engine-cli.md to pass the rest of T019: `status [--servers a,b] [--session <sid>]` with `engine`, `home` (the resolved `<home>`; the plugin checks it against `sandbox.filesystem.denyRead`), `store`, `session`, `rev`, `swept`, `servers` (profile, profile_state, exempt, warmup, warmup_state, warmup_reason), `recognise` = `\b(n|text|h|d|u|g|dom|p)-[a-z2-7]{6,}\b`, `kinds`, `keep_entries`, `hide_entries`, creating nothing; `begin --session <sid> --servers a,b` (sweep, create the folder, record `warmup_state: not-started` for every listed protected, non-exempt server whose profile declares a warm-up; exit 4 on a live folder); `end --session <sid>` (no secret read, no profile load, so it finishes well inside 1.5 s); `table --session <sid> --since <rev>` (real values, meant only for the plugin)
- [x] T036 Implement the engine runner in `plugin/hooks/engine.ts`: `runEngine($, args, stdin, timeoutMs)` via `$.process.run([enginePath, ...args], { stdin: JSON.stringify(stdin), timeoutMs })`; returns parsed JSON or throws an `EngineError { exitCode, code }` on non-zero exit, timeout or invalid JSON; timeouts `prompt` 5 s, `args` 5 s, `result` 15 s, `begin` 5 s, `warmup` 5 s, `end` 1 s, others 30 s (add `begin` and `warmup` to the timeouts line of `contracts/claude-code-plugin.md`); merges any `table` field into the module-memory reveal table (`Map<standin, {real, kind}>` plus `rev`, tagged with the current session id), which is never written to `$.store`, `$.state` or disk
- [x] T037 Implement preconditions in `plugin/hooks/preconditions.ts` to pass T020: host version, `$.session.surfaces()` includes `terminal` (FR-031), `$.settings.read()` sandbox checks with the keys found in T010 (FR-026), engine `status --session <sid>`, precondition 5 (live → continue; none and `turns()` = 0 → `begin`; none and `turns()` > 0 or throwing → resumed block, FR-033); exposes `blockReason` (module memory), `recheck($)` called at `session.start` and at the start of every guard hook, and `onEngineExit3()` that sets "session expired"; sets the status line to the block reason when set
- [x] T038 Implement the built-in tool guard in `plugin/hooks/guard.ts` and register it in `plugin/hooks/register.ts` to pass T021: `tool.call` on `Bash`, `Read`, `Grep`, `Glob`, `Edit`, `Write`, `NotebookEdit`, `WebFetch` and any tool input with a path-like argument; deny when the input mentions `<home>` (expanded and `~` forms), the engine command or module (`mcp-privacy-guard`, `mcp_privacy_guard`), or the plugin folder; deny writes to `~/.claude/settings*.json`, `<project>/.claude/settings*.json`, `~/.claude/plugins/` and `~/.claude.json`; deny `Bash` with `dangerouslyDisableSandbox: true`; registration with `.catch(() => ({ deny: "privacy guard: refused" }))`
- [x] T039 Implement the session lifecycle in `plugin/hooks/session.ts` and register it in `plugin/hooks/register.ts` to pass T022: `session.start` runs preconditions, `status --servers <connected MCP server aliases> --session <sid>` (listed with `$.session.usage({ breakdown: 'summary' })`; `mcpTools[].serverName`), keeps the server map and the `recognise` regex in module memory, `table --session <sid> --since 0`, and sets the status line; `session.end` runs `end --session <e.sessionId>` bounded by `next.budget`, empties the reveal table, then `next(e)`; a `currentSession($)` helper used at the start of every hook detects a changed `$.session.id()` and resets the table and preconditions

**Checkpoint**: Foundation ready. A session gets its own secret and mapping, deleted at its end;
stand-ins can be generated; the CLI answers; the plugin fails closed, blocks resumed
conversations and protects the store and Claude Code's settings.

---

## Phase 3: User Story 1 - Use any MCP server without sending real data to the model (Priority: P1) 🎯 MVP

**Goal**: Every result of every protected MCP server reaches the model pseudonymized. Failures withhold.

**Independent Test**: With `panos-mcp` in offline demo mode and the generic test server, run every tool and check what the model receives: no real value, structure intact (spec Story 1; SC-001).

### Tests for User Story 1 (write first, see them fail)

- [x] T040 [P] [US1] Create the generic test MCP server `testservers/generic/server.py` (Python `mcp` SDK, stdio), with tools returning structured JSON, JSON in text blocks, plain-text log lines, an error result, an image block, a 3 MB result, and an object keyed by hostnames and IPs, all built from `testservers/generic/seed.json`. That file lists known "real" values of every FR-004 category (IPs, networks, FQDNs, URLs, device names, serials, users, groups, e-mails, MACs, object names, descriptions, log free text)
- [x] T041 [P] [US1] Record `panos-mcp` offline-demo results for every tool into `engine/tests/fixtures/panos-mcp/<tool>.json` (one MCP result per file) with `engine/tests/tools/record_panos_fixtures.py`, which runs `panos-mcp` with `PANOS_MCP_SAMPLES_SCENARIO` and **without runtime pseudonymization** (find and record in research R12 how `panos-mcp` turns it off, or which version no longer has it), writes `engine/tests/fixtures/panos-mcp/real_values.json` listing the identifying values found in the demo data and `tools.json` listing the server's tools, and fails if the fixtures lack any FR-004 shape (IP, FQDN, serial, user, name)
- [x] T042 [P] [US1] Write `engine/tests/unit/test_walker.py`: decision order hide list → keep list → profile field rule (kind or enum; a value outside the enum becomes `NAME`) → safe forms and vocabulary → whole-value shape → single token `NAME` → `MIXED`; JSON numbers, booleans and `null` unchanged; object keys kept only when at most 4 tokens after splitting on `_`, `-`, `.` and camelCase, no digits, and every token a common word or vocabulary word, otherwise pseudonymized; profile `keys = "hide"` hides every key; profile `keys = "keep"` keeps keys **except** keys of identifying shape (IP, FQDN, e-mail, MAC, URL, `DOMAIN\user`, 7+ digits) and hide-list keys, which are pseudonymized (FR-004 floor, analysis H3)
- [x] T043 [P] [US1] Write `engine/tests/unit/test_text.py`: MIXED replaces embedded shapes and dictionary names in place, keeps the unit when every remaining word is vocabulary or a common word, otherwise the whole unit becomes `text-…`; the unit is a JSON string or one line of plain text; `text.mode = "whole"` hides a whole block
- [x] T044 [P] [US1] Write `engine/tests/unit/test_results.py`: text blocks that parse as JSON are walked and re-serialised in the same compact or indented style; `structuredContent` is walked; non-text blocks are removed and replaced by one block `[privacy-guard: n non-text item(s) withheld]` with `withheld = n`; error results (`is_error`) are pseudonymized too; over 2 MB of text, or processing past 10 s → `Refused` (exit 4); without a live session → exit 3
- [x] T045 [P] [US1] Write the leak tests `engine/tests/leak/test_panos_leak.py` and `engine/tests/leak/test_generic_leak.py` (marker `leak`): in one session, for every fixture and seed result, run `result` with the `panos-mcp` profile and with the default profile, and assert that no value from `real_values.json` / `seed.json` appears anywhere in the output (case-insensitive substring), keys included; the same real value in two tools and in two servers gets the same stand-in; two different reals get different stand-ins; a `/24` and an address inside it keep containment (Story 1 scenarios 1–5)
- [x] T046 [P] [US1] Write `engine/tests/leak/test_panos_vocabulary.py`: `any`, `allow`, `application-default`, predefined applications and well-known ports in panos fixtures pass unchanged with the `panos-mcp` profile (Story 1 scenario 6)
- [x] T047 [P] [US1] Write `engine/tests/tools/scan_transcript.py`: reads a Claude Code transcript (JSONL) and a values file (`seed.json` or `real_values.json`), and reports every real value found in anything sent to the model (user messages, tool results, system sections), case-insensitive; exits 1 if any is found and prints only counts and line numbers, never the values. Used by quickstart §4 and T102
- [x] T048 [P] [US1] Write `plugin/hooks/mcp.test.ts` (result part): a protected `mcp__generic__list` call returns the engine's `result`; engine exit 3/4/5, timeout, invalid JSON, or a throw in the hook → `{ deny }` and the model reads that the result was withheld (Story 1 scenario 7); exit 3 also sets "session expired"; a block reason → `{ deny }` before the tool runs; `prompt.compose` adds a `session` section saying values are stand-ins

### Implementation for User Story 1

- [x] T049 [US1] Implement `engine/src/mcp_privacy_guard/classify/walker.py` to pass T042: walk JSON with the current path, apply the decision order, call `standins.pseudonymize`, handle keys with the `keys = "keep"` shape rule
- [x] T050 [US1] Implement `engine/src/mcp_privacy_guard/classify/text.py` to pass T043 (shared by results, prompts and errors)
- [x] T051 [US1] Implement `engine/src/mcp_privacy_guard/results.py` to pass T044: McpToolResult handling (`content`, `isError`, `structuredContent`, with the shape found in T009), JSON-in-text detection and re-serialisation, non-text withholding, 2 MB and 10 s limits
- [x] T052 [US1] Implement the `result --session <sid> --server <alias> --tool <name> [--since <rev>]` subcommand in `engine/src/mcp_privacy_guard/cli.py`: profile selection for the server, stdin `{"result", "is_error"}`, stdout `{"result", "withheld", "notices", "table"}`
- [x] T053 [P] [US1] Write `engine/src/mcp_privacy_guard/profiles/panos-mcp.toml` for raw `panos-mcp` output, with `servers = ["panos", "panos-*", "panos-mcp"]`, name kinds (`DEVICE_GROUP`, `TEMPLATE`, `TEMPLATE_STACK`, `DEVICE_NAME`, `RULE_NAME`, `ADDRESS`, `ADDRESS_GROUP`, `SERVICE`, `SERVICE_GROUP`, `APP_GROUP`, `TAG`, `ZONE`, `PROFILE_GROUP`, `VSYS`) with cue words, field rules for every `panos-mcp` result field (names → kinds, `action`/`log_type`/`severity` → enums, descriptions → `TEXT`, log free-text fields → `TEXT`, interface names such as `ethernet1/1` via vocabulary pattern list), and `warmup` entries only for read-only listing tools present in `engine/tests/fixtures/panos-mcp/tools.json` (a missing tool would block questions, FR-034); plus `engine/src/mcp_privacy_guard/profiles/panos-mcp/builtin.txt` and `applications.txt` (PAN-OS built-ins, predefined applications and services); passes T045 and T046
- [x] T054 [US1] Implement the MCP `tool.call` hook (result path) in `plugin/hooks/mcp.ts` and register it on `mcp__*` in `plugin/hooks/register.ts` to pass T048: `currentSession($)`, recheck preconditions; parse the server alias as found in T009; protected server → `await next(e)` → `result --session <sid>` → `{ result, context }` (context notes withheld items); any failure → `{ deny: "result withheld by privacy guard" }`, and exit 3 → `onEngineExit3()`; `.catch(() => ({ deny: "result withheld by privacy guard" }))`
- [x] T055 [US1] Implement the `prompt.compose` hook in `plugin/hooks/register.ts`: append a `session`-scope section saying that values from MCP tools and in user messages are pseudonymized stand-ins, that the model must not present them as real or guess the real values, and that it must use them as given in tool calls (FR-029)

**Checkpoint**: MVP. MCP results reach the model only as stand-ins, in a terminal session with the sandbox.

---

## Phase 4: User Story 2 - Follow-up tool calls using stand-ins (Priority: P1)

**Goal**: Stand-ins in the model's tool arguments reach MCP servers as real values.

**Independent Test**: Take a stand-in from one result, pass it to another tool on the same or another server, and check that the server received the real value and that the model received a pseudonymized result (spec Story 2; SC-003).

### Tests for User Story 2 (write first, see them fail)

- [x] T056 [P] [US2] Write `engine/tests/unit/test_arguments.py`: an issued `n-` stand-in → real value; an IP form (also inside a filter string or a range) → inverted with the session key, issued or not; FQDN, e-mail, user, URL and TEXT stand-ins → real through the session table; mixed strings translate each stand-in and keep the rest; an unknown `n-zzzzzz` stays as typed; argument keys never change; the reply reveals nothing about unknown stand-ins; a stand-in issued in another session is unknown here (Story 2 scenarios 1, 3, 4)
- [x] T057 [P] [US2] Write `engine/tests/leak/test_roundtrip.py`: in one session, for each panos fixture and the generic server, every name or IP stand-in in a result translated through `args` equals the original real value, across two server aliases (SC-003, Story 2 scenario 2)
- [x] T058 [P] [US2] Extend `plugin/hooks/mcp.test.ts`: arguments are rewritten with the engine's `args` before `next`; an `args` failure denies before the tool runs

### Implementation for User Story 2

- [x] T059 [US2] Implement `engine/src/mcp_privacy_guard/arguments.py` to pass T056 and T057
- [x] T060 [US2] Implement the `args --session <sid> --server <alias> --tool <name> [--since <rev>]` subcommand in `engine/src/mcp_privacy_guard/cli.py`: stdin `{"args"}`, stdout `{"args", "translated", "table"}` (`translated` counts values only)
- [x] T061 [US2] Extend `plugin/hooks/mcp.ts` to pass T058: call `args` and `next({ ...e, ...args })` for protected and exempt servers alike, keeping the reserved keys `tool` and `tool_use_id` untouched

**Checkpoint**: Multi-step investigations work on stand-ins.

---

## Phase 5: User Story 3 - Type real values in a question (Priority: P1)

**Goal**: Real values typed or pasted in a question reach the model as the same stand-ins the tool results use, and no question is sent before the session's name lists have loaded.

**Independent Test**: Submit questions containing known real values, capture what is sent, and check that it holds only stand-ins matching those in tool results; submit a question during warm-up and check it is held (spec Story 3; SC-007; FR-034).

### Tests for User Story 3 (write first, see them fail)

- [x] T062 [P] [US3] Write `engine/tests/unit/test_names_dictionary.py`: `result` records every value classified with a name kind, `USER` or `GROUP` in the session's `names(real, kind, server, common_word)` with `UNIQUE(real, kind)`; `common_word` is true when the value is in the common-word list; `learn --session <sid> --server --tool` records names and stand-ins and prints only `{"names": <count>}`; a new session starts with an empty dictionary
- [x] T063 [P] [US3] Write `engine/tests/unit/test_warmup_gate.py`: `begin --servers panos,generic` records `warmup_state: not-started` only for servers whose profile declares a warm-up and that are protected and not exempt; `warmup --state running|complete|failed [--reason]` updates the state, `failed` requires `--reason` in `timeout`, `tool-missing`, `tool-error`, `learn-failed`, and the reply is `{"pending": [...], "failed": [...]}`; `warmup --state running` for an unlisted server registers it; `prompt` (with and without `--command`) exits 4 with code `warmup-pending` and the pending servers while any state is `not-started` or `running`, and with code `warmup-failed`, the server and its reason once one has failed; nothing is replaced or recorded then; with every warm-up `complete`, `prompt` works (FR-034)
- [x] T064 [P] [US3] Write `engine/tests/unit/test_prompts.py`: shapes in questions are replaced with the same stand-ins as in results of the same session; dictionary names are matched whole-token and case-sensitive; a common-word name is replaced only when quoted, back-ticked, or preceded within three tokens by a cue word of its kind or `server`, `host`, `object`, `group`, `rule`; offsets refer to the text as typed; `reason` is `shape`, `name`, `name+cue` or `name+quote`; `--command` returns `{"identifying": true|false}` and replaces nothing; no live session → exit 3 (Story 3 scenarios 1–4)
- [x] T065 [P] [US3] Write `engine/tests/leak/test_prompt_leak.py`: a question test set containing known real values of every category from the panos fixtures and the generic seed, run after the fixtures went through `result` in the same session, yields zero real values in the output, and every stand-in equals the one in tool results (SC-007)
- [x] T066 [P] [US3] Write `plugin/hooks/prompt.test.ts`: a question with an IP is rewritten to the engine's text; engine exit ≠ 0, timeout or a throw before `next` → `{ drop }` with the reason; exit 4 `warmup-pending` → `{ drop: "privacy guard: loading names for <servers>, try again in a moment" }`; exit 4 `warmup-failed` → `{ drop }` with the reason and fix; the same for a slash command during warm-up; a block reason → `{ drop }`; `e.attachments` present → `{ drop: "…paste the text instead" }` without calling the engine (FR-032); a slash command with an identifying value in its arguments has them rewritten at `command.run` (T104), not dropped, and one without passes; a toast `n value(s) replaced` when n > 0; **a throw after `next` was called does not call `next` again and returns the earlier `next` result** (analysis H2)
- [x] T067 [P] [US3] Write `plugin/hooks/warmup.test.ts`: for each server that `begin` or `status` lists with `warmup_state` not `complete`, the plugin sends `warmup --state running`, calls each warm-up tool with `$.mcp.call` and pipes the result to `learn`, then sends `warmup --state complete`; nothing is added to the conversation; a call over 30 s or a server over 120 s → `warmup --state failed --reason timeout`; a missing tool → `tool-missing`; a tool error → `tool-error`; a `learn` failure → `learn-failed`; the status line shows `privacy-guard: loading names (k/n)` meanwhile; when `warmup` reports nothing pending, a toast "privacy guard: names loaded, questions accepted"; on failure, the status line and a toast give the reason and the fix (`/clear` to retry; fix the profile or exempt the server); a server that connects after `session.start` is found by the connected-server listing at the start of the next hook (including `prompt.submit`) and warmed up the same way, and questions wait for it; a configured server that has not connected is not seen (documented residual risk, R9)

### Implementation for User Story 3

- [x] T068 [US3] Extend `engine/src/mcp_privacy_guard/classify/walker.py` and `engine/src/mcp_privacy_guard/store.py` to record names in the session dictionary to pass T062, and implement the `learn --session <sid> --server <alias> --tool <name>` subcommand in `engine/src/mcp_privacy_guard/cli.py`
- [x] T069 [US3] Implement the warm-up gate to pass T063: `warmup --session <sid> --server <alias> --state running|complete|failed [--reason <code>]` in `engine/src/mcp_privacy_guard/cli.py` and the state checks in `engine/src/mcp_privacy_guard/store.py` (`begin` already records `not-started`, T035)
- [x] T070 [US3] Implement `engine/src/mcp_privacy_guard/prompts.py` to pass T064 and T065, refusing with `warmup-pending` / `warmup-failed` before any recognition
- [x] T071 [US3] Implement the `prompt --session <sid> [--since <rev>] [--command]` subcommand in `engine/src/mcp_privacy_guard/cli.py`: stdin `{"text"}`, stdout `{"text", "replacements", "warnings", "table"}` or `{"identifying"}`
- [x] T072 [US3] Implement the `prompt.submit` hook in `plugin/hooks/prompt.ts` and register it in `plugin/hooks/register.ts` to pass T066: the hook keeps the promise of its single `next({ ...e, text })` call in a variable; `.catch(($, e, next) => next.called ? <that promise> : { drop: "privacy guard: question not checked" })`, which never calls `next` again and never sends the raw `e`
- [x] T073 [US3] Implement the warm-up in `plugin/hooks/warmup.ts`, started in the background from `session.start` and for servers first seen mid-session, to pass T067

- [x] T103 [US3] Verify research R1 "Slash commands and skills" (items 1–4) against the Claude Code types and a live run; record the result in R1, and amend the design in spec Edge Cases, FR-034, `contracts/claude-code-plugin.md` and `docs/coverage.md` if a path cannot be covered. Before T104. (Numbered after T102 to keep existing IDs stable.)
- [x] T104 [P] [US3] Write `plugin/hooks/command.test.ts`: `command.run` with an identifying value in `args` → `next({ ...e, args })` with the engine's text; the same for a fork command; engine failure, timeout, throw, block reason or warm-up pending → the run is refused; `skill.prompt` text with an identifying value is rewritten the same way; a `.catch` refuses in both hooks
- [x] T105 [P] [US3] Extend `engine/tests/leak/test_prompt_leak.py` (T065) with slash-command lines and skill-expanded text containing known real values: zero leak
- [x] T106 [US3] Implement the `command.run` and `skill.prompt` hooks in `plugin/hooks/command.ts`, registered in `plugin/hooks/register.ts`, calling the engine's `prompt` (T071), to pass T104 and T105. The `/privacy-guard` command (T095) is excluded from masking

**Checkpoint**: Questions, results and follow-up calls are all pseudonymized consistently, and questions wait for the name lists. The compliance goal is met.

---

## Phase 6: User Story 4 - See the real values on screen (Priority: P2)

**Goal**: In the terminal, answers, questions and tool rows show real values, highlighted. Nothing goes back to the model.

**Independent Test**: In Claude Code in a terminal, ask a question whose answer has stand-ins and check that the screen shows real values while the transcript holds stand-ins (spec Story 4; SC-005).

### Tests for User Story 4 (write first, see them fail)

- [x] T074 [P] [US4] Write `engine/tests/unit/test_reveal.py`: `reveal --session <sid>` replaces only known stand-ins, leaves other text unchanged, and marks unknown name-shaped stand-ins with `⟨?⟩`; `--json` returns `{"text", "revealed", "unknown"}`; without `--session` it uses the only live session; with no live session, or several and no `--session`, it exits 3 (stand-ins of an ended session are never revealed); `observe --session <sid>` inverts IP forms in assistant text with the session key, records them, and returns new table entries; a stand-in from another session is unknown
- [x] T075 [P] [US4] Write `plugin/hooks/reveal.test.ts`: `AssistantMessage`, `ToolUse` and `ToolResult` on `terminal` show real values, highlighted, with other text unchanged; the same on `desktop`, `vscode` and `mobile` is unchanged; after `session.attach { surface: 'terminal' }` nothing is revealed and a toast says so; an unknown `n-zzzzzz` gets a dim `(?)`; `UserMessage` from the composer shows the question as typed with replaced values underlined; a throw in the render hook draws the engine's row (stand-ins); `turn.complete` calls `observe` and invalidates rows; after a session id change the old table no longer reveals anything
- [x] T076 [P] [US4] Write `plugin/hooks/reveal.bench.test.ts`: with a 100k-entry reveal table, revealing a 4 KB row takes at most 4 ms (median of 50 runs) (SC-005, research R10, constitution VI)

### Implementation for User Story 4

- [x] T077 [US4] Implement `engine/src/mcp_privacy_guard/reveal.py` and the `reveal [--session <sid>] [--json]` and `observe --session <sid> [--since <rev>]` subcommands in `engine/src/mcp_privacy_guard/cli.py` to pass T074
- [x] T078 [US4] Implement `plugin/hooks/reveal.ts` and register the `ui.render` hooks (`AssistantMessage`, `ToolUse`, `ToolResult`, `UserMessage`), `session.attach` (surface `terminal`) and `turn.complete` in `plugin/hooks/register.ts` to pass T075 and T076: longest-match substitution through one compiled alternation (or trie) rebuilt when the table changes, highlight, `(?)` marking with the `recognise` regex from `status`, only when `e.surface === 'terminal'` and reveal is allowed
- [x] T079 [US4] After `args`, `result` and `prompt` replies, call `$.ui.invalidate` for the rows drawn so new table entries show, in `plugin/hooks/mcp.ts` and `plugin/hooks/prompt.ts`

**Checkpoint**: Terminal users see real values. The model and the transcript still hold stand-ins only.

---

## Phase 7: User Story 5 - Add a new MCP server with precise handling (Priority: P2)

**Goal**: Operators add a profile for a server and get more readable results without weakening protection.

**Independent Test**: Run a tool of the test server with the default profile, add a profile, run it again: no real value in either run, fewer needless stand-ins in the second (spec Story 5; SC-008).

### Tests for User Story 5 (write first, see them fail)

- [x] T080 [P] [US5] Write `engine/tests/unit/test_profile_selection.py`: a user profile in `<home>/profiles/` beats a bundled profile with matching globs; `servers.<alias>.profile` in config beats both; an unreadable or invalid user profile → the default profile with `profile_state: "invalid"` and a reason in `status` (FR-015); `check-profile <file>` returns `{"valid": true}` or `{"valid": false, "errors": [{"path", "message"}]}` and exits 0 either way; a user profile without `warmup` for a server whose bundled profile has one → the bundled profile applies, `profile_state: "invalid"`, reason `warmup-required`
- [x] T081 [P] [US5] Write `engine/tests/leak/test_generic_profile.py`: with `testservers/generic/profile.example.toml`, zero seed values leak and fewer `n-` stand-ins appear than with the default profile; a profile that lists shape-identifying enum or vocabulary values is refused; a `keys = "keep"` rule on the hostname-keyed object still hides the identifying keys (FR-014, analysis H3)
- [x] T082 [P] [US5] Extend `plugin/hooks/preconditions.test.ts`: a server whose `profile_state` is `invalid` triggers a toast naming the server and the reason, and the server stays protected by the default profile

### Implementation for User Story 5

- [x] T083 [US5] Implement user profile discovery in `<home>/profiles/` and the selection order in `engine/src/mcp_privacy_guard/profiles/loader.py`, and the `check-profile <file>` subcommand in `engine/src/mcp_privacy_guard/cli.py`, to pass T080
- [x] T084 [P] [US5] Write `testservers/generic/profile.example.toml` covering the generic server's fields (names, enums, descriptions, keys) to pass T081
- [x] T085 [US5] Show the invalid-profile toast at `session.start` in `plugin/hooks/session.ts` to pass T082
- [x] T086 [P] [US5] Write `docs/profiles.md`: when a profile helps, the format (link to the contract), path patterns with examples, enum versus vocabulary, `keys` and its shape rule, warm-up (list only read-only tools that exist and answer quickly, because questions wait for them and a failure blocks questions, FR-034; you may change the warm-up tools but cannot remove them, so exempt the server instead), what a profile cannot do, `check-profile`, a worked example from the generic server, aimed at writing and applying a profile in under 30 minutes (SC-008)

**Checkpoint**: Any server is protected at once and can be made precise with a profile.

---

## Phase 8: User Story 6 - Operator control and transparency (Priority: P3)

**Goal**: Operators see that the guard is active, which servers it protects and with which profile, and can set keep and hide lists and exemptions. Nothing turns it off. Values that pass unchanged are never mistaken for stand-ins.

**Independent Test**: Start Claude Code with the guard and several servers, check the start toast and `/privacy-guard`, add a keep value and an exemption, and check their effect, including tool calls that reuse those values (spec Story 6; research R15, R16).

- [x] T087 [US6] Verify research R16 before T091: that `$.command.register` and `command.run` work as declared in the types, and whether the `{ text }` returned by `command.run` enters the conversation the model reads. Record the finding in research R16

### Tests for User Story 6 (write first, see them fail)

- [x] T088 [P] [US6] Write `engine/tests/unit/test_operator_lists.py`: values in `keep.values`/`keep.files` pass unchanged; values in `hide.values`/`hide.files` become `TEXT` even where a profile enum or vocabulary would keep them; `status` reports `keep_entries`, `hide_entries` and `exempt: true` for an exempted alias
- [x] T089 [P] [US6] Write `engine/tests/contract/test_no_off_switch.py`: `mcp-privacy-guard --help` and every subcommand's help list no `disable`, `off`, `passthrough` or `bypass` option; the config schema rejects any such key; no `MCP_PRIVACY_GUARD_*` environment variable other than `MCP_PRIVACY_GUARD_HOME` is read (FR-027)
- [x] T090 [P] [US6] Write `engine/tests/unit/test_fixed_entries.py` (research R15): `begin` records IP-shaped keep-list values as `fixed` entries (`standin = real`); `result --exempt` returns `{"fixed": n}`, does not echo the result, and records its IP forms as fixed; `args` passes a fixed IP unchanged; an IP that is both fixed and an issued stand-in → exit 4 `ambiguous-address` with no value in the error; a real IP whose stand-in would equal a fixed keep-list IP is pseudonymized as `TEXT`; `observe` does not invert fixed IPs; the `table` reveals a fixed IP as itself
- [x] T091 [P] [US6] Write `plugin/hooks/operator.test.ts`: an exempt server's result is returned unchanged, its arguments are still translated, and its result is passed to `result --exempt` (a failure there is ignored); `args` exit 4 `ambiguous-address` → `{ deny: "privacy guard: an address in this call is ambiguous; ask the user to state it" }` before the tool runs; session start shows a toast listing each server with its profile or `exempt`, flags invalid profiles, and cuts long lists with "… /privacy-guard for all"; `/privacy-guard` returns the guard state or block reason and, per server, profile, profile state, exemption and warm-up state, with no store value; the status line shows `active · n protected · m exempt`; no plugin option disables the guard

### Implementation for User Story 6

- [x] T092 [US6] Apply keep and hide lists in `engine/src/mcp_privacy_guard/classify/walker.py` and `engine/src/mcp_privacy_guard/classify/text.py`, and report them in `status`, to pass T088 and T089
- [x] T093 [US6] Implement fixed entries to pass T090: keep-list IPs in `begin` and the keep-list collision rule in `engine/src/mcp_privacy_guard/standins/__init__.py`; `result --exempt` in `engine/src/mcp_privacy_guard/results.py` and `cli.py`; the fixed check and `ambiguous-address` in `engine/src/mcp_privacy_guard/arguments.py`; the fixed check in `engine/src/mcp_privacy_guard/reveal.py` (`observe`)
- [x] T094 [US6] Implement exempt handling (`args` → `next` → `result --exempt`, failure ignored) and the `ambiguous-address` deny in `plugin/hooks/mcp.ts` to pass the exempt part of T091
- [x] T095 [US6] Implement the per-server start toast and the `/privacy-guard` command (`$.command.register` in `session.start`, answered by a `command.run` hook) in `plugin/hooks/status.ts`, registered in `plugin/hooks/register.ts`, to pass the status part of T091 (FR-029, research R16)

**Checkpoint**: All user stories work independently.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, performance gate, end-to-end validation.

- [x] T096 [P] Write `engine/tests/bench/test_latency.py` (marker `bench`): the plugin's MCP hook path (`args` → tool stub → `result`, two fresh engine processes) on 500 records of 1 KB takes under 1 s from the hook's start to its reply, the engine-only `args` + `result` part is asserted separately, and `prompt` on a 2,000-character question takes under 1 s (SC-006); fail the build otherwise and, if it fails, record the long-lived helper alternative in plan.md Complexity Tracking before adopting it
- [x] T097 [P] Write `engine/tests/unit/test_consistency.py` (SC-004): `result` on the same fixture in two separate processes of one session gives identical stand-ins; the same fixture in two sessions gives different stand-ins; after `end` the session folder, its secret and its mapping are gone, and a stand-in from it is neither revealed nor translated by a later session; a folder untouched for over 24 hours is swept by the next `begin`
- [x] T098 [P] Write `docs/coverage.md` for compliance reviewers: what leaves the machine and in what form (stand-in table); what is covered (MCP results, arguments, questions including pasted text); what is blocked (attachments, sessions outside a terminal, missing sandbox, resumed conversations, questions until warm-up completes, a failed warm-up); session-only stand-ins (per-session secret and mapping, deleted at session end, swept after 24 h if a session crashes; deletion is an unlink, not a secure wipe, so full-disk encryption is advised); the guard as the only pseudonymization layer (`panos-mcp` keeps it only for sample creation); what is not covered (built-in tool output, other clients, an uninstalled guard); residual risks (public IP /8, common-word object keys, names of servers without warm-up typed before they are returned, names of a server that connects after the question or never connects (R9), keep-list and exempt values reaching the model unchanged); readable in under 15 minutes (SC-009, FR-030)
- [x] T099 [P] Write `docs/install.md`: install the engine (`uv tool install mcp-privacy-guard` or `pipx`), install the plugin, the exact sandbox settings found in T010 (enabled, `<home>` in the read-deny list, unsandboxed commands not allowed) and permission `deny` rules for `Read`/`Grep`/`Glob` on `<home>`, managed (`policy`) settings that pin the plugin enabled and the sandbox on where available, terminal-only use, `/clear` instead of `--resume`, the `enginePath` option, `/privacy-guard`, troubleshooting for each block reason (no terminal, sandbox, engine unavailable, host too old, resumed conversation, session expired, warm-up failed)
- [x] T100 Update `README.md` with the status, a one-paragraph description, links to `docs/install.md`, `docs/coverage.md` and `docs/profiles.md`, and the terminal, sandbox and session-only requirements
- [x] T101 Run ruff, mypy, the full pytest suite (including `leak` and `bench`), `claude plugin validate plugin`, `tsc -p plugin` and `claude plugin test plugin`, and fix every failure
- [x] T102 Run every step of `specs/001-mcp-pseudonymization/quickstart.md` by hand and record the results (pass or fail per step) at the end of quickstart.md
- [x] T107 [P] Write `engine/tests/leak/test_no_value_in_output.py` (marker `leak`; constitution II): run every subcommand from a seeded session, on success and on each error path (exit 2, 3, 4, 5), with real values from `seed.json` in stdin, and assert that neither stdout (except where the contract returns values: `table`, `reveal`) nor stderr contains any seed value or any stand-in/real pair, in error envelopes and in debug output. Run it before T101

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on Setup and blocks every user story. T009–T011 come first: T009 before T051/T054, T010 before T037, T011 before T037/T039
- **US1 (Phase 3)**: depends on Foundational
- **US2 (Phase 4)**: depends on Foundational; extends `plugin/hooks/mcp.ts` from US1 (T054), so do it after US1
- **US3 (Phase 5)**: depends on Foundational and on the walker from US1 (T049) for name recording, and on the panos profile's warm-up list (T053). T103 comes before T104–T106, and T106 after T071
- **US4 (Phase 6)**: depends on Foundational; useful once US1 or US3 issues stand-ins
- **US5 (Phase 7)**: depends on Foundational and US1 (profile application in `result`)
- **US6 (Phase 8)**: depends on US1 (walker, MCP hook), US2 (argument translation, `arguments.py`) and US4 (`observe` in `reveal.py`, for the fixed check); T087 before T091
- **Polish (Phase 9)**: after the stories you intend to ship

### User Story Dependencies

```text
Setup → Foundational → US1 ─┬─▶ US2 ─┐
                            ├─▶ US3  ├─▶ US6
                            ├─▶ US4 ─┘
                            └─▶ US5
```

### Within Each User Story

- Verification tasks first, then tests, seen failing (constitution VI)
- Engine modules, then the CLI subcommand, then the plugin hook
- Story checkpoint before the next priority

### Parallel Opportunities

- Setup: T003–T007 in parallel after T001–T002
- Foundational: T009–T011 (verification) in parallel; tests T012–T022 all in parallel; generators T025–T028, T030, T031 and T033 in parallel
- After US1: US3, US4 and US5 can proceed in parallel (different files, except `register.ts` registrations, which are small and should be merged one at a time)
- Inside each story, all tasks marked [P] in the tests block run together

---

## Parallel Example: User Story 1

```bash
# Tests first, together:
Task: "T040 generic test MCP server in testservers/generic/server.py"
Task: "T041 record raw panos-mcp fixtures in engine/tests/fixtures/panos-mcp/"
Task: "T042 walker tests in engine/tests/unit/test_walker.py"
Task: "T043 MIXED text tests in engine/tests/unit/test_text.py"
Task: "T044 result handling tests in engine/tests/unit/test_results.py"
Task: "T045 leak tests in engine/tests/leak/"
Task: "T048 plugin MCP hook tests in plugin/hooks/mcp.test.ts"

# Then, in parallel where files differ:
Task: "T053 panos-mcp profile in engine/src/mcp_privacy_guard/profiles/panos-mcp.toml"
Task: "T049 walker in engine/src/mcp_privacy_guard/classify/walker.py"
```

## Parallel Example: User Story 3

```bash
Task: "T062 name dictionary tests in engine/tests/unit/test_names_dictionary.py"
Task: "T063 warm-up gate tests in engine/tests/unit/test_warmup_gate.py"
Task: "T064 prompt tests in engine/tests/unit/test_prompts.py"
Task: "T066 prompt hook tests in plugin/hooks/prompt.test.ts"
Task: "T067 warm-up hook tests in plugin/hooks/warmup.test.ts"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 Setup
2. Phase 2 Foundational (verification tasks T009–T011 first)
3. Phase 3 US1
4. **Stop and validate**: leak tests green, quickstart §3 step 2 and §4 step 1
5. The MVP alone already stops tool data from reaching the model. Questions are not yet
   pseudonymized, so do not use it on production data until US3 is done.

### Incremental Delivery

1. Setup + Foundational
2. US1 → validate (results protected)
3. US2 → validate (follow-up calls work)
4. US3 → validate (questions protected, held during warm-up): **first release usable on production data** (all P1 stories)
5. US4 → real values on screen
6. US5 → operator profiles
7. US6 → keep/hide lists, exemptions, per-server status
8. Polish → docs, benchmark, quickstart run

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps each task to its user story
- Verify each test fails before implementing
- Commit after each task or logical group
- Never weaken a leak or fail-closed test to make it pass (constitution, Development Workflow)
- Stand-ins are valid in one session only: tests that compare stand-ins must issue them in the
  same session (ephemeral store or one `begin`)
