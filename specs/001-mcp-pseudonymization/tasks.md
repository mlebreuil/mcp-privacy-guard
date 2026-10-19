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

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on unfinished tasks)
- **[Story]**: The user story the task belongs to (US1–US6)
- Paths are relative to the repository root. `<home>` is `$MCP_PRIVACY_GUARD_HOME`, default
  `~/.config/mcp-privacy-guard`

## Path Conventions

- Engine: `engine/src/mcp_privacy_guard/`, tests in `engine/tests/`
- Plugin: `plugin/` (`plugin/hooks/register.ts`, tests `plugin/hooks/*.test.ts`)
- Dev-only test MCP server: `testservers/generic/`
- User documentation: `docs/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the repository layout and tooling.

- [ ] T001 Create the directory layout from plan.md "Source Code": `engine/src/mcp_privacy_guard/{standins,classify,profiles,data}/`, `engine/tests/{unit,contract,leak,fixtures/panos-mcp,bench,tools}/`, `plugin/{.claude-plugin,hooks}/`, `testservers/generic/`, `docs/`, `scripts/`, each Python package with an empty `__init__.py`
- [ ] T002 Create `engine/pyproject.toml`: project `mcp-privacy-guard` 0.1.0, `requires-python = ">=3.11"`, **no runtime dependencies**, hatchling build backend, console script `mcp-privacy-guard = "mcp_privacy_guard.cli:main"`, dev dependency group `pytest`, `hypothesis`, `ruff`, `mypy`, `mcp`; package data includes `profiles/*.toml`, `profiles/**/*.txt`, `data/*`
- [ ] T003 [P] Configure ruff (line length 100, rules E,F,I,B,UP,S) and mypy (`strict = true`) in `engine/pyproject.toml`, and pytest (`testpaths = ["tests"]`, markers `leak`, `bench`)
- [ ] T004 [P] Create `plugin/.claude-plugin/plugin.json` (`name` `mcp-privacy-guard`, `version` `0.1.0`, description, minimum Claude Code version `2.1.301`, user option `enginePath` string default `mcp-privacy-guard`) and `plugin/hooks/hooks.json` (`{ "modules": ["./register.ts"] }`) with an empty `register` export in `plugin/hooks/register.ts`
- [ ] T005 [P] Add `.gitignore` entries (`.venv/`, `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `dist/`, `*.sqlite`, `secret.key`) in `.gitignore`
- [ ] T006 [P] Add `scripts/update-public-suffix.sh` that downloads `https://publicsuffix.org/list/public_suffix_list.dat` into `engine/src/mcp_privacy_guard/data/public_suffix_list.dat`, run it once, and add `NOTICE` at the repository root attributing the Public Suffix List (MPL-2.0)
- [ ] T007 [P] Add `engine/src/mcp_privacy_guard/data/common_words.txt`: about 5,000 lower-case English words with no proper nouns, plus networking terms (`inside`, `outside`, `trust`, `untrust`, `dmz`, `web`, `test`, `prod`, `dev`, `lan`, `wan`, `mgmt`), one per line, sorted; record its source and licence in `NOTICE`
- [ ] T008 Create CI workflow `.github/workflows/ci.yml`: job `engine` (uv sync, ruff, mypy, pytest on Python 3.11 and 3.14); job `plugin` running `claude plugin validate plugin` and `claude plugin test plugin`, which prints `SKIPPED: claude CLI not available` and exits 0 when `claude` is absent, so the skip shows in the log (constitution, Development Workflow)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Store, stand-in generators, shape detection, profile loader, CLI skeleton, and the
plugin's fail-closed core. Every user story depends on these.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Tests for the foundation (write first, see them fail)

- [ ] T009 [P] Write `engine/tests/unit/test_store.py`: secret created on first use as 32 bytes with file mode `0600` in a `0700` directory; `status` does not create it; a secret with mode `0644` → `StoreUnavailable("too-permissive")`; an unreadable secret → `StoreUnavailable("unreadable")`; a store inside a git work tree that does not ignore it → `StoreUnavailable("in-git-tree")`; `issue()` is idempotent for the same `(kind, real)`; `rev` strictly increases; `table(since)` returns only newer rows; an ephemeral in-memory store with a fixed test key works the same way
- [ ] T010 [P] Write `engine/tests/unit/test_ip.py` with hypothesis: the keyed Crypto-PAn permutation is a bijection on random IPv4/IPv6; `invert(permute(x)) == x`; the shared prefix length of any two addresses is preserved; RFC 1918, CGNAT `100.64/10`, loopback, link-local, multicast, broadcast, documentation ranges, `fc00::/7` and `fe80::/10` keep their block; public IPv4 keeps its first octet and global IPv6 its first 16 bits; `0.0.0.0/0`, `255.255.255.0` and `any` are unchanged; prefixes and ranges map consistently (the stand-in of `10.1.2.15` lies inside the stand-in of `10.1.2.0/24`)
- [ ] T011 [P] Write `engine/tests/unit/test_names.py`: `n-` + 6 base32 lower-case characters; deterministic for the same secret; different for different secrets; same stand-in for the same real whatever kind is passed (FR-009); a forced collision lengthens the token by 2 characters
- [ ] T012 [P] Write `engine/tests/unit/test_domains.py`: FQDN labels below the public suffix replaced (`h-` leftmost, `d-` others), public suffix kept, two hosts under one parent share the parent stand-in; URL keeps scheme and port and replaces path, query and fragment with `/p-<token>`; e-mail is `u-<token>@<fqdn stand-in>`; `DOMAIN\user` → `dom-<t>\u-<t>` and groups → `dom-<t>\g-<t>`
- [ ] T013 [P] Write `engine/tests/unit/test_misc_standins.py`: MAC → `02:` plus keyed bytes; DIGITS keeps the length, digits only, first digit non-zero; TEXT → `text-` + 8 characters, equal inputs give equal outputs
- [ ] T014 [P] Write `engine/tests/unit/test_shapes.py`: whole-value detection of IPv4/IPv6 address, prefix, range and wildcard, URL, e-mail, MAC, `DOMAIN\user`, FQDN (only when it ends in a public suffix), digit runs of 7 or more (`DIGITS`); embedded detection returns spans in free text; timestamps (RFC 3339, ISO 8601), durations and up to 6-digit numeric strings are reported as safe forms
- [ ] T015 [P] Write `engine/tests/unit/test_profile_loader.py`: the bundled `default.toml` loads; a profile with a vocabulary or enum value of identifying shape (IP, FQDN, e-mail, MAC, URL, `DOMAIN\user`, 7+ digits) is refused; kind names must match `[A-Z][A-Z0-9_]*` and must not redefine a core kind; invalid path patterns are refused; path pattern matching of `name`, `*`, `[]` and `**` (zero or more steps) against sample JSON paths; tool-specific rules are tried before general ones; first match wins
- [ ] T016 [P] Write `engine/tests/contract/test_cli_envelope.py`: every subcommand reads one JSON object on stdin and writes one on stdout; on a non-zero exit stdout is `{"error": {"code", "message", "hint"}}` and contains no input value; exit codes `2` bad input, `3` store unavailable, `4` refused, `5` internal error; `status` exits `0` and never prints a store value
- [ ] T017 [P] Write `plugin/hooks/preconditions.test.ts`: a session whose `$.session.surfaces()` lacks `terminal` sets the block reason "use Claude Code in a terminal"; settings without the sandbox enabled, without `<home>` in its filesystem read-deny list, or allowing unsandboxed commands set a block reason that names the settings to add; a host older than 2.1.301 sets a block reason; engine `status` failing (missing command, exit ≠ 0, timeout, invalid JSON) sets a block reason; all checks passing clears it
- [ ] T018 [P] Write `plugin/hooks/guard.test.ts`: `Read` of `<home>/store/mapping.sqlite`, `Grep`/`Glob` under `<home>`, `Bash` running `mcp-privacy-guard table`, `Edit`/`Write` inside the plugin folder, and `Bash` with `dangerouslyDisableSandbox: true` are denied; an unrelated `Read` passes; a throw inside the guard hook still denies (`.catch`)

### Implementation of the foundation

- [ ] T019 Implement `engine/src/mcp_privacy_guard/config.py`: resolve `<home>` from `MCP_PRIVACY_GUARD_HOME` or `~/.config/mcp-privacy-guard`; load `<home>/config.toml` with `tomllib` into a typed object with exactly `keep.values`, `keep.files`, `hide.values`, `hide.files`, `servers.<alias>.profile`, `servers.<alias>.exempt` (unknown keys → error); **no key that disables pseudonymization** (FR-027)
- [ ] T020 Implement `engine/src/mcp_privacy_guard/store.py` to pass T009: secret at `<home>/store/secret.key` (32 bytes from `secrets.token_bytes`, mode `0600`, directory `0700`), states `absent`/`ready`/`unreadable`/`too-permissive`/`in-git-tree`; SQLite `<home>/store/mapping.sqlite` (mode `0600`, WAL, `busy_timeout` 5 s) with table `standin(standin TEXT UNIQUE, token TEXT NULL, kind TEXT, real TEXT, rev INTEGER, first_seen TEXT)` and `UNIQUE(kind, real)`, table `names(real TEXT, kind TEXT, server TEXT, common_word BOOL, UNIQUE(real, kind))`, table `meta(key TEXT PRIMARY KEY, value TEXT)` with `schema_version`; methods `issue(kind, real, standin, token=None)`, `lookup_standin(standin)`, `lookup_token(token)`, `table(since)`, `rev()`, `ephemeral(key)` for tests; never logs values
- [ ] T021 [P] Implement `engine/src/mcp_privacy_guard/standins/ip.py` to pass T010: Crypto-PAn with HMAC-SHA256 as the pseudo-random function, special-block bit fixing, public first octet (v4) / first 16 bits (v6) kept, `permute()` and `invert()` for addresses, prefixes, ranges and wildcards, per-process cache
- [ ] T022 [P] Implement `engine/src/mcp_privacy_guard/standins/names.py` to pass T011: `t(n)` = first `n` characters of lower-case unpadded base32 of HMAC-SHA256(secret, domain ‖ 0x1f ‖ value ‖ 0x1f ‖ attempt); name stand-in `n-` + `t(6)` with domain `name` independent of kind; on collision (token already used by another real in the store) attempt+1 and grow the length by 2
- [ ] T023 [P] Implement `engine/src/mcp_privacy_guard/standins/domains.py` to pass T012, using the bundled public suffix list parsed once per process
- [ ] T024 [P] Implement `engine/src/mcp_privacy_guard/standins/misc.py` to pass T013
- [ ] T025 Implement `engine/src/mcp_privacy_guard/standins/__init__.py` with `pseudonymize(kind, real, store, key) -> str`, which dispatches to the generators and records every issued stand-in (including IPs and label-level FQDN stand-ins) in the store (depends on T020–T024)
- [ ] T026 [P] Implement `engine/src/mcp_privacy_guard/classify/shapes.py` to pass T014
- [ ] T027 [P] Implement `engine/src/mcp_privacy_guard/classify/vocabulary.py`: the built-in safe vocabulary (`true`, `false`, `yes`, `no`, `none`, `null`, `allow`, `deny`, `drop`, `permit`, `block`, `enabled`, `disabled`, `up`, `down`, `active`, `inactive`, `tcp`, `udp`, `icmp`, `ipv4`, `ipv6`, `http`, `https`, `ssh`, `dns`, `ntp`, `info`, `informational`, `low`, `medium`, `high`, `critical`, `warning`, `error`, `debug`, HTTP methods, well-known service names), the common-word list loader, and `is_safe_word()`
- [ ] T028 Implement `engine/src/mcp_privacy_guard/profiles/loader.py` to pass T015: TOML schema from contracts/profile-format.md (`profile.id` `[a-z0-9-]+`, `profile.version` = 1, `servers` globs, `kinds.<KIND>.cues`, `vocabulary.values`/`files`, `fields[]` with `path`, optional `tools`, exactly one of `kind`/`enum`/`keys`, `text.mode` `mixed`|`whole`, `warmup[]` with `tool`/`args`); path pattern compiler; profile states `valid`/`invalid` with reasons; selection order: `servers.<alias>.profile` in config, then the user profile in `<home>/profiles/` whose globs match, then the bundled profile whose globs match, then `default`
- [ ] T029 [P] Write `engine/src/mcp_privacy_guard/profiles/default.toml`: `id = "default"`, no field rules, `text.mode = "mixed"`
- [ ] T030 Implement `engine/src/mcp_privacy_guard/cli.py` to pass T016: `argparse` subcommands `status`, `result`, `args`, `prompt`, `learn`, `observe`, `table`, `reveal`, `check-profile` (unimplemented ones exit 5 for now); JSON in and out; the error envelope; exception → exit code mapping; logging to stderr without values; a reply helper that adds `"table": {"rev", "entries"}` after `--since`
- [ ] T031 Implement `status` in `engine/src/mcp_privacy_guard/cli.py` per contracts/engine-cli.md: `engine`, `store`, `rev`, `servers` (with `--servers a,b`: profile, profile_state, exempt, warmup, warmup_state), `recognise` = `\b(n|text|h|d|u|g|dom|p)-[a-z2-7]{6,}\b`, `kinds`, `keep_entries`, `hide_entries`; creates nothing
- [ ] T032 Implement the engine runner in `plugin/hooks/engine.ts`: `runEngine($, args, stdin, timeoutMs)` via `$.process.run([enginePath, ...args], { stdin: JSON.stringify(stdin), timeoutMs })`; returns parsed JSON or throws on non-zero exit, timeout or invalid JSON; timeouts `prompt` 5 s, `args` 5 s, `result` 15 s, others 30 s; merges any `table` field into the module-memory reveal table (`Map<standin, {real, kind}>` plus `rev`), which is never written to `$.store`, `$.state` or disk
- [ ] T033 Implement preconditions in `plugin/hooks/preconditions.ts` to pass T017: host version, `$.session.surfaces()` includes `terminal` (FR-031), `$.settings.read()` sandbox checks (FR-026), engine `status`; exposes `blockReason` (module memory) and `recheck($)`, called at `session.start` and at the start of every guard hook; sets the status line to the block reason when set
- [ ] T034 Implement the built-in tool guard in `plugin/hooks/guard.ts` and register it in `plugin/hooks/register.ts` to pass T018: `tool.call` on `Bash`, `Read`, `Grep`, `Glob`, `Edit`, `Write`, `NotebookEdit`, `WebFetch` and any tool input with a path-like argument; deny when the input mentions `<home>` (expanded and `~` forms), the engine command, or the plugin folder, or when `Bash` has `dangerouslyDisableSandbox: true`; registration with `.catch(() => ({ deny: "privacy guard: refused" }))`
- [ ] T035 Implement `session.start` in `plugin/hooks/register.ts`: run preconditions, `status --servers <connected MCP server aliases>`, keep the server map and the `recognise` regex in module memory, `table --since 0`, and set the status line `privacy-guard: active · n protected · m exempt` or the block reason

**Checkpoint**: Foundation ready. Stand-ins can be generated and stored, the CLI answers, and the plugin fails closed and protects the store.

---

## Phase 3: User Story 1 - Use any MCP server without sending real data to the model (Priority: P1) 🎯 MVP

**Goal**: Every result of every protected MCP server reaches the model pseudonymized. Failures withhold.

**Independent Test**: With `panos-mcp` in offline demo mode and the generic test server, run every tool and check what the model receives: no real value, structure intact (spec Story 1; SC-001).

### Tests for User Story 1 (write first, see them fail)

- [ ] T036 [P] [US1] Create the generic test MCP server `testservers/generic/server.py` (Python `mcp` SDK, stdio), with tools returning structured JSON, JSON in text blocks, plain-text log lines, an error result, an image block and a 3 MB result, all built from `testservers/generic/seed.json`. That file lists known "real" values of every FR-004 category (IPs, networks, FQDNs, URLs, device names, serials, users, groups, e-mails, MACs, object names, descriptions, log free text)
- [ ] T037 [P] [US1] Record `panos-mcp` offline-demo results for every tool into `engine/tests/fixtures/panos-mcp/<tool>.json` (one MCP result per file) with a script `engine/tests/tools/record_panos_fixtures.py` that runs `panos-mcp` with `PANOS_MCP_SAMPLES_SCENARIO`, plus `engine/tests/fixtures/panos-mcp/real_values.json` listing the identifying values found in the demo data
- [ ] T038 [P] [US1] Write `engine/tests/unit/test_walker.py`: decision order hide list → keep list → profile field rule (kind or enum; a value outside the enum becomes `NAME`) → safe forms and vocabulary → whole-value shape → single token `NAME` → `MIXED`; JSON numbers, booleans and `null` unchanged; object keys kept only when at most 4 tokens after splitting on `_`, `-`, `.` and camelCase, no digits, and every token a common word or vocabulary word, otherwise pseudonymized; profile `keys = "keep"|"hide"` overrides
- [ ] T039 [P] [US1] Write `engine/tests/unit/test_text.py`: MIXED replaces embedded shapes and dictionary names in place, keeps the unit when every remaining word is vocabulary or a common word, otherwise the whole unit becomes `text-…`; the unit is a JSON string or one line of plain text; `text.mode = "whole"` hides a whole block
- [ ] T040 [P] [US1] Write `engine/tests/unit/test_results.py`: text blocks that parse as JSON are walked and re-serialised in the same compact or indented style; `structuredContent` is walked; non-text blocks are removed and replaced by one block `[privacy-guard: n non-text item(s) withheld]` with `withheld = n`; error results (`is_error`) are pseudonymized too; over 2 MB of text, or processing past 10 s → `Refused` (exit 4)
- [ ] T041 [P] [US1] Write the leak tests `engine/tests/leak/test_panos_leak.py` and `engine/tests/leak/test_generic_leak.py` (marker `leak`): for every fixture and seed result, run `result` with the `panos-mcp` profile and with the default profile, and assert that no value from `real_values.json` / `seed.json` appears anywhere in the output (case-insensitive substring); the same real value in two tools and in two servers gets the same stand-in; two different reals get different stand-ins; a `/24` and an address inside it keep containment (Story 1 scenarios 1–5)
- [ ] T042 [P] [US1] Write `engine/tests/leak/test_panos_vocabulary.py`: `any`, `allow`, `application-default`, predefined applications and well-known ports in panos fixtures pass unchanged with the `panos-mcp` profile (Story 1 scenario 6)
- [ ] T043 [P] [US1] Write `plugin/hooks/mcp.test.ts` (result part): a protected `mcp__generic__list` call returns the engine's `result`; engine exit 3/4/5, timeout, invalid JSON, or a throw in the hook → `{ deny }` and the model reads that the result was withheld (Story 1 scenario 7); a block reason → `{ deny }` before the tool runs; `prompt.compose` adds a `session` section saying values are stand-ins

### Implementation for User Story 1

- [ ] T044 [US1] Implement `engine/src/mcp_privacy_guard/classify/walker.py` to pass T038: walk JSON with the current path, apply the decision order, call `standins.pseudonymize`, handle keys
- [ ] T045 [US1] Implement `engine/src/mcp_privacy_guard/classify/text.py` to pass T039 (shared by results, prompts and errors)
- [ ] T046 [US1] Implement `engine/src/mcp_privacy_guard/results.py` to pass T040: McpToolResult handling (`content`, `isError`, `structuredContent`), JSON-in-text detection and re-serialisation, non-text withholding, 2 MB and 10 s limits
- [ ] T047 [US1] Implement the `result --server --tool --since` subcommand in `engine/src/mcp_privacy_guard/cli.py`: profile selection for the server, stdin `{"result", "is_error"}`, stdout `{"result", "withheld", "notices", "table"}`
- [ ] T048 [P] [US1] Write `engine/src/mcp_privacy_guard/profiles/panos-mcp.toml` with `servers = ["panos", "panos-*", "panos-mcp"]`, name kinds (`DEVICE_GROUP`, `TEMPLATE`, `TEMPLATE_STACK`, `DEVICE_NAME`, `RULE_NAME`, `ADDRESS`, `ADDRESS_GROUP`, `SERVICE`, `SERVICE_GROUP`, `APP_GROUP`, `TAG`, `ZONE`, `PROFILE_GROUP`, `VSYS`) with cue words, field rules for every `panos-mcp` result field (names → kinds, `action`/`log_type`/`severity` → enums, descriptions → `TEXT`, log free-text fields → `TEXT`, interface names such as `ethernet1/1` via vocabulary pattern list), and `warmup` entries for the read-only listing tools; plus `engine/src/mcp_privacy_guard/profiles/panos-mcp/builtin.txt` and `applications.txt` (PAN-OS built-ins, predefined applications and services); passes T041 and T042
- [ ] T049 [US1] Implement the MCP `tool.call` hook (result path) in `plugin/hooks/mcp.ts` and register it on `mcp__*` in `plugin/hooks/register.ts` to pass T043: recheck preconditions; parse the server alias from the connected-tool listing; protected server → `await next(e)` → `result` → `{ result, context }` (context notes withheld items); any failure → `{ deny: "result withheld by privacy guard" }`; `.catch(() => ({ deny: "result withheld by privacy guard" }))`
- [ ] T050 [US1] Implement the `prompt.compose` hook in `plugin/hooks/register.ts`: append a `session`-scope section saying that values from MCP tools and in user messages are pseudonymized stand-ins, that the model must not present them as real or guess the real values, and that it must use them as given in tool calls (FR-029)
- [ ] T051 [US1] Verify the **Verify at implementation** items of research R1 for result handling (shape of `result` for MCP tools from core, replacing an errored result with `{ result }` or falling back to `{ deny: <pseudonymized error text> }`, mapping `mcp__<server>__<tool>` to the alias) and record the findings in `specs/001-mcp-pseudonymization/research.md` R1

**Checkpoint**: MVP. MCP results reach the model only as stand-ins, in a terminal session with the sandbox.

---

## Phase 4: User Story 2 - Follow-up tool calls using stand-ins (Priority: P1)

**Goal**: Stand-ins in the model's tool arguments reach MCP servers as real values.

**Independent Test**: Take a stand-in from one result, pass it to another tool on the same or another server, and check that the server received the real value and that the model received a pseudonymized result (spec Story 2; SC-003).

### Tests for User Story 2 (write first, see them fail)

- [ ] T052 [P] [US2] Write `engine/tests/unit/test_arguments.py`: an issued `n-` stand-in → real value; an IP form (also inside a filter string or a range) → inverted with the key, issued or not; FQDN, e-mail, user, URL and TEXT stand-ins → real through the table; mixed strings translate each stand-in and keep the rest; an unknown `n-zzzzzz` stays as typed; argument keys never change; the reply reveals nothing about unknown stand-ins (Story 2 scenarios 1, 3, 4)
- [ ] T053 [P] [US2] Write `engine/tests/leak/test_roundtrip.py`: for each panos fixture and the generic server, every name or IP stand-in in a result translated through `args` equals the original real value, across two server aliases (SC-003, Story 2 scenario 2)
- [ ] T054 [P] [US2] Extend `plugin/hooks/mcp.test.ts`: arguments are rewritten with the engine's `args` before `next`; an `args` failure denies before the tool runs

### Implementation for User Story 2

- [ ] T055 [US2] Implement `engine/src/mcp_privacy_guard/arguments.py` to pass T052 and T053
- [ ] T056 [US2] Implement the `args --server --tool --since` subcommand in `engine/src/mcp_privacy_guard/cli.py`: stdin `{"args"}`, stdout `{"args", "translated", "table"}`
- [ ] T057 [US2] Extend `plugin/hooks/mcp.ts` to pass T054: call `args` and `next({ ...e, ...args })` for protected and exempt servers alike, keeping the reserved keys `tool` and `tool_use_id` untouched

**Checkpoint**: Multi-step investigations work on stand-ins.

---

## Phase 5: User Story 3 - Type real values in a question (Priority: P1)

**Goal**: Real values typed or pasted in a question reach the model as the same stand-ins the tool results use.

**Independent Test**: Submit questions containing known real values, capture what is sent, and check that it holds only stand-ins matching those in tool results (spec Story 3; SC-007).

### Tests for User Story 3 (write first, see them fail)

- [ ] T058 [P] [US3] Write `engine/tests/unit/test_names_dictionary.py`: `result` records every value classified with a name kind, `USER` or `GROUP` in `names(real, kind, server, common_word)` with `UNIQUE(real, kind)`; `common_word` is true when the value is in the common-word list; `learn` records names and prints only `{"names": <count>}`
- [ ] T059 [P] [US3] Write `engine/tests/unit/test_prompts.py`: shapes in questions are replaced with the same stand-ins as in results; dictionary names are matched whole-token and case-sensitive; a common-word name is replaced only when quoted, back-ticked, or preceded within three tokens by a cue word of its kind or `server`, `host`, `object`, `group`, `rule`; offsets refer to the text as typed; `reason` is `shape`, `name`, `name+cue` or `name+quote`; with a server's warm-up not `complete` the reply warns `name list loading for <alias>`; `--command` returns `{"identifying": true|false}` and replaces nothing; store unavailable → exit 3 (Story 3 scenarios 1–4)
- [ ] T060 [P] [US3] Write `engine/tests/leak/test_prompt_leak.py`: a question test set containing known real values of every category from the panos fixtures and the generic seed yields zero real values in the output, and every stand-in equals the one in tool results (SC-007)
- [ ] T061 [P] [US3] Write `plugin/hooks/prompt.test.ts`: a question with an IP is rewritten to the engine's text; engine exit ≠ 0, timeout or a throw → `{ drop }` with the reason; a block reason → `{ drop }`; `e.attachments` present → `{ drop: "…paste the text instead" }` without calling the engine (FR-032); a slash command with an identifying value → dropped, without one → passes; a toast `n value(s) replaced` when n > 0
- [ ] T062 [P] [US3] Write `plugin/hooks/warmup.test.ts`: at `session.start`, for each server whose `warmup` is not `complete`, each warm-up tool is called with `$.mcp.call` and its result piped to `learn`; nothing is added to the conversation; a warm-up failure only sets the status line

### Implementation for User Story 3

- [ ] T063 [US3] Extend `engine/src/mcp_privacy_guard/classify/walker.py` and `engine/src/mcp_privacy_guard/store.py` to record names to pass T058, and implement the `learn --server --tool` subcommand in `engine/src/mcp_privacy_guard/cli.py`, which also sets `meta` `warmup_state` (`not-started` → `running` → `complete` or `failed`) per server
- [ ] T064 [US3] Implement `engine/src/mcp_privacy_guard/prompts.py` to pass T059 and T060
- [ ] T065 [US3] Implement the `prompt [--since] [--command]` subcommand in `engine/src/mcp_privacy_guard/cli.py`: stdin `{"text"}`, stdout `{"text", "replacements", "warnings", "table"}` or `{"identifying"}`
- [ ] T066 [US3] Implement the `prompt.submit` hook in `plugin/hooks/prompt.ts` and register it in `plugin/hooks/register.ts` to pass T061, with `.catch(($, e, next) => next.called ? next(e) : { drop: "privacy guard: question not checked" })`
- [ ] T067 [US3] Implement the warm-up in `plugin/hooks/warmup.ts`, started in the background from `session.start`, to pass T062; show `name list loading` in the status line until every warm-up is complete

**Checkpoint**: Questions, results and follow-up calls are all pseudonymized consistently. The compliance goal is met.

---

## Phase 6: User Story 4 - See the real values on screen (Priority: P2)

**Goal**: In the terminal, answers, questions and tool rows show real values, highlighted. Nothing goes back to the model.

**Independent Test**: In Claude Code in a terminal, ask a question whose answer has stand-ins and check that the screen shows real values while the transcript holds stand-ins (spec Story 4; SC-005).

### Tests for User Story 4 (write first, see them fail)

- [ ] T068 [P] [US4] Write `engine/tests/unit/test_reveal.py`: `reveal` replaces only known stand-ins, leaves other text unchanged, and marks unknown name-shaped stand-ins with `⟨?⟩`; `--json` returns `{"text", "revealed", "unknown"}`; `observe` inverts IP forms in assistant text with the key, records them, and returns new table entries; a stand-in from another secret is reported as unknown
- [ ] T069 [P] [US4] Write `plugin/hooks/reveal.test.ts`: `AssistantMessage`, `ToolUse` and `ToolResult` on `terminal` show real values, highlighted, with other text unchanged; the same on `desktop`, `vscode` and `mobile` is unchanged; after `session.attach { surface: 'terminal' }` nothing is revealed and a toast says so; an unknown `n-zzzz9q` gets a dim `(?)`; `UserMessage` from the composer shows the question as typed with replaced values underlined; a throw in the render hook draws the engine's row (stand-ins); `turn.complete` calls `observe` and invalidates rows

### Implementation for User Story 4

- [ ] T070 [US4] Implement `engine/src/mcp_privacy_guard/reveal.py` and the `reveal [--json]`, `observe --since` and `table --since` subcommands in `engine/src/mcp_privacy_guard/cli.py` to pass T068
- [ ] T071 [US4] Implement `plugin/hooks/reveal.ts` and register the `ui.render` hooks (`AssistantMessage`, `ToolUse`, `ToolResult`, `UserMessage`), `session.attach` (surface `terminal`) and `turn.complete` in `plugin/hooks/register.ts` to pass T069: longest-match substitution from the module-memory reveal table, highlight, `(?)` marking with the `recognise` regex from `status`, only when `e.surface === 'terminal'` and reveal is allowed
- [ ] T072 [US4] After `args`, `result` and `prompt` replies, call `$.ui.invalidate` for the rows drawn so new table entries show, in `plugin/hooks/mcp.ts` and `plugin/hooks/prompt.ts`

**Checkpoint**: Terminal users see real values. The model and the transcript still hold stand-ins only.

---

## Phase 7: User Story 5 - Add a new MCP server with precise handling (Priority: P2)

**Goal**: Operators add a profile for a server and get more readable results without weakening protection.

**Independent Test**: Run a tool of the test server with the default profile, add a profile, run it again: no real value in either run, fewer needless stand-ins in the second (spec Story 5; SC-008).

### Tests for User Story 5 (write first, see them fail)

- [ ] T073 [P] [US5] Write `engine/tests/unit/test_profile_selection.py`: a user profile in `<home>/profiles/` beats a bundled profile with matching globs; `servers.<alias>.profile` in config beats both; an unreadable or invalid user profile → the default profile with `profile_state: "invalid"` and a reason in `status` (FR-015); `check-profile` returns `{"valid": true}` or `{"valid": false, "errors": [{"path", "message"}]}` and exits 0 either way
- [ ] T074 [P] [US5] Write `engine/tests/leak/test_generic_profile.py`: with `testservers/generic/profile.example.toml`, zero seed values leak and fewer `n-` stand-ins appear than with the default profile; a profile that tries to keep a FR-004 field (an enum listing a real name is allowed, but shape-identifying enum or vocabulary values are refused) cannot make a seed value of identifying shape leak (FR-014)
- [ ] T075 [P] [US5] Extend `plugin/hooks/preconditions.test.ts`: a server whose `profile_state` is `invalid` triggers a toast naming the server and the reason, and the server stays protected by the default profile

### Implementation for User Story 5

- [ ] T076 [US5] Implement user profile discovery in `<home>/profiles/` and the selection order in `engine/src/mcp_privacy_guard/profiles/loader.py`, and the `check-profile <file>` subcommand in `engine/src/mcp_privacy_guard/cli.py`, to pass T073
- [ ] T077 [P] [US5] Write `testservers/generic/profile.example.toml` covering the generic server's fields (names, enums, descriptions, keys) to pass T074
- [ ] T078 [US5] Show the invalid-profile toast at `session.start` in `plugin/hooks/register.ts` to pass T075
- [ ] T079 [P] [US5] Write `docs/profiles.md`: when a profile helps, the format (link to the contract), path patterns with examples, enum versus vocabulary, what a profile cannot do, `check-profile`, a worked example from the generic server, aimed at writing and applying a profile in under 30 minutes (SC-008)

**Checkpoint**: Any server is protected at once and can be made precise with a profile.

---

## Phase 8: User Story 6 - Operator control and transparency (Priority: P3)

**Goal**: Operators see that the guard is active, which servers it protects and how, and can set keep and hide lists and exemptions. Nothing turns it off.

**Independent Test**: Start Claude Code with the guard and several servers, check the status line, add a keep value and an exemption, and check their effect (spec Story 6).

### Tests for User Story 6 (write first, see them fail)

- [ ] T080 [P] [US6] Write `engine/tests/unit/test_operator_lists.py`: values in `keep.values`/`keep.files` pass unchanged; values in `hide.values`/`hide.files` become `TEXT` even where a profile enum or vocabulary would keep them; `status` reports `keep_entries`, `hide_entries` and `exempt: true` for an exempted alias
- [ ] T081 [P] [US6] Write `engine/tests/contract/test_no_off_switch.py`: `mcp-privacy-guard --help` and every subcommand's help list no `disable`, `off`, `passthrough` or `bypass` option; the config schema rejects any such key; no `MCP_PRIVACY_GUARD_*` environment variable other than `MCP_PRIVACY_GUARD_HOME` is read (FR-027)
- [ ] T082 [P] [US6] Write `plugin/hooks/operator.test.ts`: an exempt server's result is returned unchanged while its arguments are still translated; the status line shows `active · n protected · m exempt`; no plugin option disables the guard

### Implementation for User Story 6

- [ ] T083 [US6] Apply keep and hide lists in `engine/src/mcp_privacy_guard/classify/walker.py` and `engine/src/mcp_privacy_guard/classify/text.py`, and report them in `status`, to pass T080 and T081
- [ ] T084 [US6] Implement exempt handling and the status line in `plugin/hooks/mcp.ts` and `plugin/hooks/register.ts` to pass T082

**Checkpoint**: All user stories work independently.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, performance gate, end-to-end validation.

- [ ] T085 [P] Write `engine/tests/bench/test_latency.py` (marker `bench`): a fresh process running `args` then `result` on a 500-record result takes under 1 s in total, and `prompt` on a 2,000-character question under 1 s (SC-006); fail the build otherwise and, if it fails, record the long-lived helper alternative in plan.md Complexity Tracking before adopting it
- [ ] T086 [P] Write `engine/tests/unit/test_consistency.py`: run `result` on the same fixture in two separate processes over one store, and after deleting and reopening the store connection, and assert identical stand-ins (SC-004)
- [ ] T087 [P] Write `docs/coverage.md` for compliance reviewers: what leaves the machine and in what form (stand-in table), what is covered (MCP results, arguments, questions including pasted text), what is blocked (attachments, sessions outside a terminal, missing sandbox), what is not covered (built-in tool output, other clients, an uninstalled guard), residual risks (public IP /8, common-word object keys, names typed before they are learned), readable in under 15 minutes (SC-009, FR-030)
- [ ] T088 [P] Write `docs/install.md`: install the engine (`uv tool install mcp-privacy-guard` or `pipx`), install the plugin, the exact sandbox settings (enabled, `<home>` in the read-deny list, unsandboxed commands not allowed) and permission `deny` rules for `Read`/`Grep`/`Glob` on `<home>`, terminal-only use, the `enginePath` option, troubleshooting for each block reason
- [ ] T089 Verify the sandbox settings keys of Claude Code 2.1.301 (enablement, filesystem read-deny, unsandboxed-command escape) and whether managed `policy` settings can enforce them; update `plugin/hooks/preconditions.ts`, `docs/install.md` and research.md R11 with the findings
- [ ] T090 Update `README.md` with the status, a one-paragraph description, links to `docs/install.md`, `docs/coverage.md` and `docs/profiles.md`, and the terminal and sandbox requirements
- [ ] T091 Run ruff, mypy, the full pytest suite (including `leak` and `bench`), `claude plugin validate plugin` and `claude plugin test plugin`, and fix every failure
- [ ] T092 Run every step of `specs/001-mcp-pseudonymization/quickstart.md` by hand and record the results (pass or fail per step) at the end of quickstart.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on Setup and blocks every user story
- **US1 (Phase 3)**: depends on Foundational
- **US2 (Phase 4)**: depends on Foundational; extends `plugin/hooks/mcp.ts` from US1 (T049), so do it after US1
- **US3 (Phase 5)**: depends on Foundational and on the walker from US1 (T044) for name recording
- **US4 (Phase 6)**: depends on Foundational; it is useful once US1 or US3 issues stand-ins
- **US5 (Phase 7)**: depends on Foundational and US1 (profile application in `result`)
- **US6 (Phase 8)**: depends on US1 (walker, MCP hook) and US2 (argument translation for exempt servers)
- **Polish (Phase 9)**: after the stories you intend to ship

### User Story Dependencies

```text
Setup → Foundational → US1 ─┬─▶ US2 ─▶ US6
                            ├─▶ US3
                            ├─▶ US4
                            └─▶ US5
```

### Within Each User Story

- Tests first, and seen failing (constitution VI)
- Engine modules, then the CLI subcommand, then the plugin hook
- Story checkpoint before the next priority

### Parallel Opportunities

- Setup: T003–T007 in parallel after T001–T002
- Foundational tests T009–T018 all in parallel; generators T021–T024, T026, T027 and T029 in parallel
- After US1: US3, US4 and US5 can proceed in parallel (different files, except `register.ts` registrations, which are small and should be merged one at a time)
- Inside each story, all tasks marked [P] in the tests block run together

---

## Parallel Example: User Story 1

```bash
# Tests first, together:
Task: "T036 generic test MCP server in testservers/generic/server.py"
Task: "T037 record panos-mcp fixtures in engine/tests/fixtures/panos-mcp/"
Task: "T038 walker tests in engine/tests/unit/test_walker.py"
Task: "T039 MIXED text tests in engine/tests/unit/test_text.py"
Task: "T040 result handling tests in engine/tests/unit/test_results.py"
Task: "T041 leak tests in engine/tests/leak/"
Task: "T043 plugin MCP hook tests in plugin/hooks/mcp.test.ts"

# Then, in parallel where files differ:
Task: "T048 panos-mcp profile in engine/src/mcp_privacy_guard/profiles/panos-mcp.toml"
Task: "T044 walker in engine/src/mcp_privacy_guard/classify/walker.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 Setup
2. Phase 2 Foundational
3. Phase 3 US1
4. **Stop and validate**: leak tests green, quickstart §3 steps 1–2 and §4 step 1
5. The MVP alone already stops tool data from reaching the model. Questions are not yet
   pseudonymized, so do not use it on production data until US3 is done.

### Incremental Delivery

1. Setup + Foundational
2. US1 → validate (results protected)
3. US2 → validate (follow-up calls work)
4. US3 → validate (questions protected): **first release usable on production data** (all P1 stories)
5. US4 → real values on screen
6. US5 → operator profiles
7. US6 → keep/hide lists and exemptions
8. Polish → docs, benchmark, quickstart run

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps each task to its user story
- Verify each test fails before implementing
- Commit after each task or logical group
- Never weaken a leak or fail-closed test to make it pass (constitution, Development Workflow)
