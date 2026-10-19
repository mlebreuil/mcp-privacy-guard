# Research: Pseudonymize MCP Data Sent to the Model

**Feature**: `001-mcp-pseudonymization` | **Date**: 2026-10-18 | **Plan**: [plan.md](./plan.md)

This replaces the research carried over from the panos-mcp draft. The guard is now generic: it
sits in Claude Code, not inside any MCP server. Items marked **Verify at implementation** are
facts about third-party software that may change. Re-check them when the related task starts
and record the result here.

---

## R1. Claude Code plugin API (the main risk)

Source: the API declarations shipped with Claude Code 2.1.301 (`claude-code.d.ts`, read on
2026-10-18).

| Need | API | Finding |
|---|---|---|
| Rewrite MCP results | `on('tool.call', { tool }, hook)` | `await next(e)` runs the tool and resolves to `{ ref, result, text }`, or `{ …, isError: true }`. Returning `{ result }` hands the model the hook's result instead: core validates it against the tool's output schema and records it as the tool's result. Returning `{ deny }` after the tool ran withholds the result, and the model reads "`<tool>` ran, and a plugin withheld its result: `<text>`". The optional `context: string[]` is read by the model and never shown to the user. |
| Translate arguments | same hook | `next({ ...e, ...args })` runs the tool with rewritten arguments. MCP tool input is `{ tool: 'mcp__<server>__<tool>', tool_use_id, ...args }`. `tool` and `tool_use_id` are reserved. |
| Subagents | same hook | `tool.call` fires for subagent calls too (`agentId` set), so they are covered. |
| Rewrite questions | `on('prompt.submit', hook)` | `next({ ...e, text })` rewrites what reaches the model, and the user's row follows. `{ drop: reason }` stops it. `e.text` holds pastes already expanded, so **text pastes in the question are covered** (attachments are not). When `e.command` is set (slash command), a rewrite of `text` is not applied. |
| Tell the model about stand-ins | `on('prompt.compose', hook)` | A section appended with `scope: 'session'` goes into the system prompt (FR-029). |
| Reveal on screen | `on('ui.render', { component }, hook)` for `AssistantMessage`, `UserMessage`, `ToolUse`, `ToolResult` | A rewrite changes the drawing only; the stored message and what the model reads stay the same. |
| Run the engine | `$.process.run(argv, { stdin, timeoutMs })` | Runs a local command by argv without a shell. Timeout 30 s by default. **Time spent waiting does not count against the hook budget.** |
| Learn names in advance | `$.mcp.call(server, tool, args)` | A plugin can call a connected server's tool with the engine's own connection. The result goes to the plugin, not to the model. |
| Notices | `$.ui.toast`, `$.ui.status` | Short user-visible notices. |

**Fail-open defaults** (all confirmed):

- A hook that throws, returns a wrong shape or runs past its budget (10 s of its own time) is
  skipped. The tool runs and its result reaches the model, or the prompt goes through.
- **Decision**: every guard registration carries a `.catch` that refuses in its place:
  `tool.call` → `{ deny }` whether or not `next` was called; `prompt.submit` →
  `{ drop }` when `next` was not called. The `.catch` has a 1 s grace and must not call the
  engine. A contract test covers each case.

**Surfaces and reveal** (finding that changes Story 4):

- `e.surface` is `terminal`, `desktop`, `vscode` or `mobile`. The declarations state that the
  desktop, VS Code and mobile tables are *remote* surfaces: the engine sends the tree to a
  client over its control protocol.
- **Claude Code for VS Code attaches no surface yet: no `ui.render` names `vscode` today.**
  Sessions in the VS Code extension and in the desktop app draw no terminal.
- `e.surface` "is what the client declared … not a trust signal: do not key policy on it".
  The terminal's own attachment raises no `session.attach`. A remote client attaching raises
  `session.attach` with the surface it claims.
- **Decision**: reveal only on `terminal`. If any client attaches claiming `terminal`
  (possible only for a remote client), stop revealing for the rest of the session and show a
  notice. Mobile and other remote views of a terminal session show stand-ins.
- **Sessions without a terminal** (spec FR-031, clarified 2026-10-18): when
  `$.session.surfaces()` does not list `terminal` (VS Code extension, desktop app, `-p`), the
  guard blocks every question and withholds every protected result, with a message to use
  Claude Code in a terminal. This is checked at `session.start` and again in each guard hook,
  because the result of that call can change during a session.
- **Later**: if the VS Code extension gains a render surface, or applies the classic
  `MessageDisplay` hook (display-only), FR-031 can be relaxed for it by a spec change.

**Rejected alternatives**: classic shell hooks only (`UserPromptSubmit`, `PostToolUse`). They
can add context and block, but cannot rewrite the question or the display. A proxy MCP server
that wraps the others: it needs changes to the MCP configuration (FR-001) and cannot see the
questions or the display.

**Verify at implementation**:
- the shape of `result` for an MCP tool from core (expected: `McpToolResult` with `content`,
  `isError`, `structuredContent`), and the shape a hook must return for `{ result }`;
- whether a hook can replace an errored MCP result with `{ result }`. Fallback: deliver the
  pseudonymized error text through `{ deny: text }`;
- how to map a tool name `mcp__<server>__<tool>` to the server name when names contain `__`
  (expected: the connected-tool listing `ContextMcpTool { name, server }`);
- pin the minimum Claude Code version in the manifest.

## R2. Engine placement and process model

- **Decision**: one Python engine, `mcp-privacy-guard`, called by the plugin through
  `$.process.run`, with one short-lived process per call (JSON on stdin and stdout). There is
  no daemon and no listener (Principles II and VII).
- Calls per protected tool call: `args` before the tool, `result` after it. Each returns the
  reveal-table entries added since the plugin's last revision, so no separate sync call is
  needed.
- **Cost**: Python start-up with stdlib imports and SQLite is about 50–100 ms on the
  developer's machine (Python 3.14). Two calls plus processing of 500 records must stay under
  1 s (SC-006). A benchmark test enforces it.
- **Alternative held in reserve**: a long-lived helper over `$.process.spawn` stdio. It would
  be adopted only if the benchmark fails, and recorded in Complexity Tracking.
- **Rejected**: the engine as an MCP server (the model would see its tools); logic in
  TypeScript (two implementations, Principle V).

## R3. Engine language, packaging and dependencies

- **Decision**: Python ≥ 3.11 (needed for `tomllib`), **standard library only at runtime**:
  `hmac`, `hashlib`, `secrets`, `ipaddress`, `sqlite3`, `json`, `tomllib`, `re`, `base64`.
  Packaged with `pyproject.toml` (hatchling build backend, a build-time dependency only).
  Installed with `uv tool install` or `pipx`, which puts `mcp-privacy-guard` on `PATH`.
- The plugin calls the command named by its user option `enginePath` (default
  `mcp-privacy-guard`). If the engine is missing, too old or broken, `session.start` reports
  it, and every protected result and every question is blocked (fail closed).
- **Dev dependencies**: `pytest`, `hypothesis` (property tests), `ruff`, `mypy`, and `mcp`
  (the Python SDK, only for the generic test MCP server used in end-to-end tests).
- **Rejected**: bundling the engine inside the plugin folder as a zipapp. It would be one
  install instead of two, but the interaction of `python -I` with zipapps and the choice of
  interpreter need checking. Kept as a possible later improvement.

## R4. Classifying values without typed models

The engine sees JSON (structured content, or text blocks that parse as JSON) or plain text.
It never knows a server's types, so classification comes from the server's profile (R5) and,
failing that, from shape.

For each JSON string value, in order:

1. **Hide list** (operator) → `TEXT`.
2. **Keep list** (operator) → passed through unchanged.
3. **Profile field rule** matching the value's path → that rule's kind, or its enum (R5).
4. **Built-in safe forms** → unchanged: RFC 3339 / ISO 8601 timestamps, durations, numbers
   written as strings with up to 6 digits, booleans and `null` spelled as strings, and the
   profile's and built-in vocabulary (`allow`, `deny`, `tcp`, `udp`, `info`, `critical`,
   well-known service names, …).
5. **Whole-value shape** → IP / prefix / range / wildcard, URL, e-mail, MAC, `DOMAIN\user`,
   FQDN (ends in a public suffix), digit strings of 7 or more digits (`DIGITS`).
6. **Single token** (no whitespace) → `NAME` (`n-…`).
7. **Text with whitespace** → `MIXED` (R6).

JSON numbers, booleans and `null` pass unchanged. Arrays and objects are walked.

**Object keys**: kept when they look like a schema field name: at most 4 tokens after
splitting on `_`, `-`, `.` and camelCase, no digits, every token in the bundled common-word
list or in the vocabulary (`source_address`, `ruleName`). Otherwise the key is pseudonymized
like a value. A profile can force either behaviour for a path (`keys = "keep" | "hide"`).
**Residual risk**: an identifying key made only of common words (a host called `mercury`
used as a dict key) passes in the default profile. This is documented, and profiles can
close it.

**Rejected**: regex-only rewriting of the JSON text. It cannot tell an enum from a name, and
it fails open.

## R5. Profiles

- **Format**: TOML (stdlib `tomllib`, easy to read and comment). One file per profile.
  Profiles ship in the package (`default`, `panos-mcp`), and operators add theirs in
  `<home>/profiles/`. The format is in [contracts/profile-format.md](./contracts/profile-format.md).
- **Selection**: the operator config maps a server alias to a profile explicitly. Otherwise
  the profile whose `servers` globs match the alias wins (a user profile beats a bundled one).
  Otherwise the default profile is used.
- **Field rules** use path patterns over JSON (`**.rules[].name`, `entries[].source`) with an
  optional tool filter. The first match wins, and tool-specific rules are tried before
  general ones.
- **A profile cannot weaken protection (FR-014)**. A profile cannot declare "keep this
  field". It can only:
  - give a field a kind (making it more precise);
  - declare an `enum` for a field: values in the enum pass, and **any other value is
    pseudonymized as `NAME`**;
  - add vocabulary words: closed lists of values that pass anywhere.

  Shape detection still runs inside enum and vocabulary values (a vocabulary entry that is an
  IP or e-mail is refused when the profile loads). So a profile can make results more
  readable only by listing safe values explicitly.
- **Name kinds**: a profile declares its own name kinds (for `panos-mcp`: `RULE_NAME`,
  `ADDRESS`, `ZONE`, `DEVICE_NAME`, …) with cue words for recognising names in questions.
  Kinds do **not** change the stand-in: every name is `n-<token>` (spec FR-009, clarified
  2026-10-18). A kind still matters: it marks the value as a name to learn for questions,
  and it selects the cue words.
- **Invalid profile** → default profile for that server, plus a toast and a status line
  (FR-015). A `check-profile` subcommand validates a file before use (SC-008).

## R6. Free text and plain-text results

- **MIXED** (spec edge case "values inside free text"): replace embedded values found by shape
  (IP, CIDR, URL, e-mail, MAC, FQDN, `DOMAIN\user`, long digit runs) and names learned in the session (R9). Then
  check every remaining word against the vocabulary plus the common-word list. If all are
  known, keep the text with its replacements. Otherwise the whole unit becomes `text-…`.
- **Unit**: a JSON string value, or one line of a plain-text block. Line granularity keeps
  plain-text output partly readable instead of hiding a whole block. A profile can set
  `text.mode = "whole"` to hide whole blocks.
- **Text block that parses as JSON**: walked as JSON and re-serialised with the same
  formatting style (compact or indented).
- **Non-text blocks** (image, audio, resource, resource_link with embedded data): removed and
  replaced by one text block "[privacy-guard: n non-text item(s) withheld]".
- **Limits**: a result over 2 MB of text, or one whose processing passes its timeout (10 s),
  is withheld as a whole (FR-007).

## R7. Stand-in formats

The full table is in [contracts/standin-formats.md](./contracts/standin-formats.md).

- **IPs: keyed prefix-preserving permutation** (Crypto-PAn construction with HMAC-SHA256 as
  the pseudo-random function, so no AES dependency). It is a bijection that keeps the length
  of every shared prefix (subnet containment, range order), and can be inverted with the
  key. The class of special blocks is preserved by fixing the block's bits (RFC 1918,
  CGNAT, loopback, link-local, multicast, documentation ranges, ULA, link-local v6). Public
  IPv4 addresses keep their first octet and global IPv6 addresses their first 16 bits, so
  they stay public. **Residual risk**: this reveals the /8 (/16 for IPv6) of public addresses,
  which identifies a registry allocation, not an organisation. Documented. Masks,
  `0.0.0.0/0` and `any` pass unchanged. Results are cached per process.
- **Names**: `n-<token>`, where the token is `t(6)` of HMAC(session secret, `name` ‖ real).
  It does not depend on the kind, the field or the server, so one real name has exactly one
  stand-in everywhere in the session. The model correlates configuration, logs and servers
  by plain string equality (FR-008, FR-009, clarified 2026-10-18; constitution IV v2.0.0),
  and it infers the kind from context (the field name, the surrounding words). A collision
  lengthens the token by 2. Every stand-in of the session is in the session's mapping, so
  every collision is detected (R13).
- **Rejected**: kind prefixes (`rule-…`, `fw-…`). The same value could then appear with two
  prefixes when profiles or fields disagree, which breaks correlation, the end goal.
- **FQDN**: each label below the public suffix is replaced by a token keyed on its parent
  chain (`h-` for the leftmost label, `d-` for the others). The public suffix is kept, and
  labels that share a parent keep sharing it.
- **URL**: scheme kept, host as FQDN or IP, port kept, path, query and fragment replaced by
  `/p-<token>`.
- **E-mail**: `u-<token>@<fqdn stand-in>`. **User**: `DOMAIN\user` → `dom-<t>\u-<t>`.
- **MAC**: locally administered `02:` plus a keyed Feistel permutation of the other 40
  bits. **DIGITS**: a keyed Feistel permutation over the strings of the same length whose
  first digit is non-zero. Both are bijections, so they never collide.
- **TEXT**: `text-<t(8)>`. The model learns only that two texts are equal or different.
- **Ambiguity**: a stand-in IP may equal some real IP. This is harmless because every value
  coming from the model is read as a stand-in (spec edge case).

## R8. Translating tool arguments

- `args` walks every string in the arguments, for protected and exempt servers alike:
  - IP forms (also inside strings: filters, ranges) → inverted with the key, whether or not
    they were issued;
  - `n-<token>` with a known token → real value;
  - FQDN, e-mail, user, URL and TEXT stand-ins → through the table;
  - anything else → unchanged.
- An unknown stand-in is passed as typed. The server then answers "not found", and that
  answer is pseudonymized like any result, so no mapping leaks (FR-012).
- Argument keys are never changed.

## R9. Questions (FR-017–FR-020)

- **Shapes**: as in R4 step 5, applied inside the text, with the same functions as for
  results, so the stand-ins match (SC-007).
- **Names**: whole-token, case-sensitive match against the session's name dictionary (the
  `names` table of the session mapping, R13). It is deleted with the session, so every
  session learns its names again. The dictionary is filled:
  1. from every result the engine pseudonymizes (names of every kind, with the server and
     the kind);
  2. by an optional **warm-up**. A profile may list read-only tools to call at session start
     (for `panos-mcp`: device groups, templates, devices, zones, tags, rules and objects
     listings). The plugin calls them with `$.mcp.call` and passes the results to
     `mcp-privacy-guard learn`, which records names and returns nothing. The results never
     reach the model. The engine itself contacts no data source (Principle II).
- **Common words**: a known name that is also in the common-word list (`web`, `test`,
  `inside`) is replaced only when it is quoted or back-ticked, or preceded within three
  tokens by a cue word of its kind (the profile's `cues`, plus generic ones: `server`,
  `host`, `object`, `group`, `rule`).
- **Questions wait for the warm-up** (FR-034, decided 2026-10-19). Otherwise a name typed
  before the warm-up finishes would reach the model:
  - `begin --session <id> --servers <aliases>` records `warmup_state: not-started` for each
    protected, non-exempt server whose profile declares a warm-up.
  - The plugin reports each server's progress to the engine (`warmup --state running`, then
    `complete` or `failed` with a reason code), and passes each result to `learn`.
  - `prompt` (and `prompt --command`) **exits 4** with code `warmup-pending` while any
    recorded warm-up is `not-started` or `running`, and `warmup-failed` once one has failed.
    The engine decides, the plugin only relays it (Principle V). The plugin drops the
    question with "privacy guard: loading names for <alias>, try again in a moment", or
    with the failure reason and its fix. It shows a toast "privacy guard: names loaded,
    questions accepted" when the last warm-up completes.
  - **Time limits**: 30 s per warm-up call and 120 s per server. Past either, the plugin
    reports `failed` (`timeout`). Other reason codes: `tool-missing` (the server lacks a
    profile's warm-up tool), `tool-error`, `learn-failed`, `not-connected`. Reasons never hold values.
  - **Fix for a failed warm-up**: `/clear` or a restart runs it again. If it keeps failing,
    the operator fixes the warm-up list (a user profile may replace the bundled warm-up
    tools, but cannot remove the warm-up) or exempts the server. Questions stay blocked meanwhile, because an incomplete name list cannot
    check them (constitution I: "a question that cannot be checked is not sent").
  - **Servers still connecting at session start**: `begin --servers` receives every
    *configured* MCP server, connected or not. The plugin reads them from the host's MCP
    server list, including pending connections. A server that is still connecting stays
    `not-started`, so questions wait. Its warm-up starts once it connects. If it fails to
    connect within 30 s, it becomes `failed` (`not-connected`), which keeps questions
    blocked and says to fix or exempt the server.
  - A server added mid-session (`/mcp`) is registered by its first `warmup --state running`.
    Questions wait again until its warm-up completes.
  - Tool results are not held. They are pseudonymized whatever the state of the name list.
- **Servers without a warm-up** (default profile, or a profile without `warmup`): their names
  are learned only as their tools return them, so a name typed before that is sent as typed.
  **Residual risk**: documented. The user sees every replacement (FR-020), so they can spot
  a missed name.
- **Pasted text** is part of `e.text` and is handled like typed text (FR-017).
- **Attachments**: when `e.attachments` is present (images or other non-text items), the
  plugin drops the submission with "paste the text instead" (FR-032). The engine is not
  called.
- **Slash commands**: when `e.command` is set, the engine checks the line. If it holds an
  identifying value, the submission is dropped with "ask as a plain question". Otherwise it
  passes.
- **Bundled lists**: common words (about 5,000 lower-case English words, with no proper
  nouns, plus networking terms) and the Public Suffix List (MPL-2.0, snapshot updated by a
  script and attributed in NOTICE).

## R10. Reveal

- The plugin holds the reveal table (`stand-in → real, kind`) **in module memory only**. It is
  filled from the `table` field that every engine reply carries, and fully at
  `session.start` (`table --since 0`). It is never in `$.store` or `$.state` and never on
  disk. It belongs to one session: when `$.session.id()` changes (after `/clear`) the plugin
  empties it and starts again from revision 0 (R13).
- `ui.render` on `terminal` (R1): longest-match substitution of known stand-ins in the text
  or props. Revealed values are highlighted. Unknown stand-ins that match the recognition
  pattern (from the engine's `status`) are marked with a dim `(?)`.
- **Budget** (SC-005, "no visible delay", made measurable): at most 4 ms per rendered row of
  up to 4 KB, with a 100k-entry table, on the reference machine. One frame at 60 Hz is
  16 ms, so this leaves room for several rows per frame. The substitution uses one compiled
  alternation (or a trie) built when the table changes, not a pass per entry. A plugin
  benchmark test enforces it (R12, constitution VI).
- **Unissued IPs**: the model may write a stand-in IP that was never issued (the next address
  in a stand-in subnet). At `turn.complete` the plugin sends the final assistant text to
  `mcp-privacy-guard observe`, which inverts IP forms with the key, records them, and returns
  the new table entries. The plugin then invalidates the rows it drew.
- **Manual reveal** (fallback, e.g. text copied from a transcript): `mcp-privacy-guard
  reveal`, run by the user in their own terminal, reads text on stdin and prints it revealed.
  It reads a live session's mapping and secret (`--session <id>`, or the only live session).
  Once the session has ended, nothing can be revealed, IPs included: the secret is gone.

## R11. Self-protection (FR-024–FR-026)

- **Store**: one folder per live session, `<home>/store/sessions/<session-id>/`, holding
  `secret.key` (32 random bytes) and `mapping.sqlite` (R13). `<home>` defaults to
  `~/.config/mcp-privacy-guard` (or `$MCP_PRIVACY_GUARD_HOME`). Files `0600`, directories
  `0700`. If permissions are broader, or the session's secret is missing or unreadable, the
  engine exits with code 3 and the plugin blocks. Only `begin` creates a secret. The store is
  refused inside a git work tree that does not ignore it.
- **The model's tools**: a `tool.call` guard on built-in tools (`Bash`, `Read`, `Grep`, `Glob`,
  `Edit`, `Write`, `NotebookEdit`, and any tool with a path argument) denies inputs that name
  the guard's home, the engine command, or the plugin's own folder. Without the last one,
  the model could edit the plugin and have it hot-reload. It also denies writes (`Edit`,
  `Write`, `NotebookEdit`, and `Bash` commands naming them) to Claude Code's settings and
  plugin state: `~/.claude/settings*.json`, `<project>/.claude/settings*.json`,
  `~/.claude/plugins/` and `~/.claude.json`. Through those the model could disable the
  plugin (`enabledPlugins`) or the sandbox, which would leave nothing protected in the next
  session (analysis H5, constitution II and VII). This is best effort, because spellings
  vary. `docs/install.md` also gives managed (`policy`) settings that pin the plugin enabled
  and the sandbox on, where the organisation uses them (verified in the R11 check).
- **Sandbox required** (spec FR-026, clarified 2026-10-18): the plugin reads the merged
  settings with `$.settings.read()` at `session.start` and in each guard hook. It requires:
  - the sandbox to be enabled;
  - `<home>` in the sandbox's filesystem read-deny list;
  - unsandboxed commands not allowed.

  If any of these is missing, every question is blocked and every protected result is
  withheld, with the exact settings to add. The built-in tool guard also denies any `Bash`
  call with `dangerouslyDisableSandbox: true`. Permission `deny` rules for `Read`/`Grep`/
  `Glob` on `<home>` are documented as well, because the sandbox covers shell commands.
- **Verify at implementation**: the exact settings keys for sandbox enablement, read-deny
  paths and unsandboxed-command escape in Claude Code 2.1.301, and whether managed (`policy`)
  settings can enforce them.
- **Config tampering**: the operator config (exemptions, keep list) lives in `<home>`, so it is
  covered by the same guard.

## R12. Testing

- **Engine** (pytest, offline, ephemeral store with a fixed test key):
  - unit: each stand-in format, Crypto-PAn inversion and prefix preservation (hypothesis over
    random networks), collisions, classification order, MIXED rule, profile loading and
    refusals, store permissions, prompt recognition, common-word rule;
  - contract: CLI exit codes and JSON shapes, `--help` lists no disable option, and no
    setting turns the guard off;
  - **leak tests**: recorded `panos-mcp` offline-demo results for every tool (fixtures
    captured once from `PANOS_MCP_SAMPLES_SCENARIO`). The guard replaces `panos-mcp`'s own
    runtime pseudonymization (spec Context), so the fixtures must be raw tool output, with no
    runtime pseudonymization on. They are made from `panos-mcp`'s samples: real Panorama data
    pseudonymized by its sample creation, assumed to keep real value shapes. The recording
    script checks that the fixtures contain every FR-004 shape (IPs, FQDNs, serials, users,
    names) and fails if one is missing. Then results of the generic test MCP
    server seeded with known "real" values. Assert that no real value appears in what the
    model would receive, using both the `panos-mcp` profile and the default profile;
  - consistency across engine processes within a session, unrelated stand-ins across
    sessions, and deletion of the session folder at `end` (SC-004); argument round-trips
    (SC-003);
  - benchmark: two engine calls plus 500 records under 1 s (SC-006).
- **Plugin** (`claude plugin validate`, `claude plugin test`, `*.test.ts`): result rewrite,
  withhold on engine failure, throw and timeout, prompt rewrite and drop, slash command
  drop, attachment drop, block in a session without `terminal`, block without the required
  sandbox settings, deny of `dangerouslyDisableSandbox`, reveal on `terminal` and none on
  other surfaces, reveal stopped after a spoofed
  `terminal` attach, unknown stand-ins marked, built-in tool guard (including writes to
  Claude Code settings and plugin state), the per-server status at session start, the
  reveal benchmark (R10). The job is skipped visibly in CI when the `claude` CLI is absent.
- **Fail-closed paths added on 2026-10-19** (constitution VI): session folder missing
  mid-session (exit 3 → block), resumed conversation (FR-033), failing `turns()`, warm-up
  pending and failed (FR-034), ambiguous address in arguments (R15), and `begin` refused on
  a live folder.
- **End to end**: [quickstart.md](./quickstart.md) with `panos-mcp` in offline demo mode and the
  generic test server, the plugin loaded through `--plugin-dir`.

## R13. Session-only stand-ins (owner decision, 2026-10-19)

Input: "Key rotation is not required during a session. Mappings are deleted at the end of the
session." Then: "All stand-ins should be only valid during one session. No persisted ones."
(spec Clarifications 2026-10-19; constitution IV v2.0.0).

- **Decision**: everything that produces or links stand-ins lives in one folder per Claude
  Code session, `<home>/store/sessions/<session-id>/` (mode `0700`):
  - `secret.key`: 32 random bytes, created by `begin` when the session starts;
  - `mapping.sqlite` (WAL): the `standin` rows, the `names` dictionary and the warm-up state.

  At `session.end` the plugin runs `mcp-privacy-guard end --session <id>`, which deletes the
  folder. Nothing outside it is written. No persistent secret, index or state exists.
- **Consequence**: the same real value gets the same stand-in within a session, and an
  unrelated one in the next session (FR-008, SC-004). Two sessions that run at the same time
  have different secrets. A stand-in from an ended session can never be inverted or looked
  up again, by the plugin or by manual `reveal`.
- **No rotation during a session**: only `begin` creates a secret, and it refuses when the
  folder already exists. Every other command exits `3` when the folder or the secret is
  missing or unreadable. It never creates a new one, so stand-ins already in the conversation
  can never be read with a different key.
- **Collisions**: every stand-in of the session is in its mapping, so token collisions are
  always detected and resolved. Tokens keep their original lengths (`t(6)` for names,
  `t(8)` for TEXT). IP, MAC and DIGITS stand-ins are bijections.
- **Warm-up runs in every session** (R9), because the name dictionary goes with the session.
  Questions wait until it completes (FR-034), so the cost is a short wait at the start of
  each session. The status line shows "loading names (k/n)".
- **Facts verified against the 2.1.302 API declarations** (`claude-code.d.ts`):
  - `session.end` fires once when the session ends (exit, `/clear`, resume, logout, signal,
    end of a `-p` run). `e.sessionId` names the ending session. Every hook of the chain
    shares one short wall-clock bound (1.5 s by default, `next.budget`). One engine call
    that deletes a folder fits in it.
  - After `/clear`, the process goes on under a new session id and **no `session.start`
    fires**. So the plugin reads `$.session.id()` at the start of every hook. On a change it
    empties the reveal table and runs `begin` for the new id.
  - `session.start` fires again on a module reload or worker respawn within the same
    session. `begin` for a folder that already exists is then refused. The plugin first asks
    `status --session <id>`, which reports `session: "live"`, and carries on.
  - `$.session.turns()` counts the user turns already in the transcript. No process id is
    exposed.
- **Sessions that end without `session.end`** (crash, SIGKILL, an engine call over the
  budget): `status`, `begin` and `end` delete other sessions' folders untouched for over
  24 hours. A live session idle that long loses its folder. Its next engine call then exits
  3 and the guard blocks with "session expired; start a new conversation (/clear)". It never
  silently re-keys.
- **Not a secure wipe**: deletion is an unlink. On SSDs and copy-on-write file systems the
  blocks may stay until they are reused. Full-disk encryption covers that. Documented in
  `docs/coverage.md`.
- **Rejected**: a persistent secret with a session-scoped mapping (the first 2026-10-19
  revision). Stand-ins would stay valid across sessions, which the owner ruled out. Keeping
  the secret only in plugin memory and passing it to each engine call: it would put key
  material in the shim (Principle V) and on every process's stdin, for no gain over an
  owner-only file that is deleted at session end.

## R14. Resumed conversations (FR-033)

- A resumed or continued conversation (`claude --resume`, `--continue`) holds stand-ins of
  an ended session. Their secret is gone. Name stand-ins could no longer be revealed or
  translated. IP stand-ins would be inverted with the new secret into **wrong** addresses,
  both on screen and in tool arguments.
- **Decision**: at `session.start` (and on a session id change), when `status --session <id>`
  reports no live folder, the plugin reads `$.session.turns()`. If it is above 0, the
  conversation is resumed. The plugin sets the block reason "privacy guard: this
  conversation is from an ended session; start a new one (/clear)" and does not run `begin`.
  `/clear` gives a new session id with 0 turns, so `begin` runs and the block lifts. A
  failing `turns()` call counts as resumed (fail closed).
- **Rejected**: letting a resumed conversation continue with old stand-ins marked unknown.
  The model keeps using old IP stand-ins from the history, and those cannot be told apart
  from new ones.
- **Verify at implementation**: that `$.session.turns()` is above 0 at `session.start` of a
  resumed session, and whether `--resume` keeps the original session id. The rule holds
  either way, because the old folder is deleted at the old session's end.

## R15. Values that reach the model unchanged (analysis H1, constitution IV)

Every value coming back from the model is read as a stand-in (spec edge case). Two kinds of
value reach the model **unchanged** and can then come back:

- operator **keep-list** values (FR-028), for example a public DNS server's IP;
- results of **exempt** servers (FR-002), which may hold real IPs.

If the model reuses such an IP in a tool call, inverting it with the key would send a wrong
address, and revealing it would show a wrong one. Constitution IV: "replace only stand-ins
they know".

- **Decision**: the session mapping records these values as **fixed** entries
  (`standin = real`, `fixed = true`):
  - `begin` records every IP-shaped keep-list value;
  - for an exempt server, the plugin returns the result unchanged and also passes it to
    `result --exempt`, which records its IP forms as fixed and returns only a count. A
    failure there is ignored: the result is not held back, because exempt data passes
    anyway.
- `args`, `observe` and the reveal table check fixed entries before inverting an IP form:
  - fixed and not an issued stand-in → passed unchanged, and shown unchanged;
  - an issued stand-in and not fixed → inverted, as before;
  - **both** (a real IP from an exempt server that equals another value's stand-in) →
    `args` exits 4 with `ambiguous-address`. The plugin denies the call with "privacy guard:
    an address in this call is ambiguous; ask the user to state it", with no value in the
    message. Reveal marks it `(?)`.
- **Keep-list collision at issue time**: when a real IP's stand-in would equal a fixed
  keep-list value, that real IP is pseudonymized as `TEXT` instead (the IP shape is lost for
  it). The keep list is known from `begin`, so this is checked before any stand-in is issued.
- **Rejected**: no IP inversion at all for exempt servers. The model may pass a protected
  server's stand-in IP to an exempt server, and that must still be translated (spec edge
  case).

## R16. Session status per server (analysis D3, FR-029, constitution VII)

- At `session.start`, after `status`, the plugin shows a toast listing each server with its
  profile, or `exempt`, and flags an invalid profile. Example: "privacy guard active ·
  panos: panos-mcp · notion: exempt". Long lists are cut with "… /privacy-guard for all".
- It registers a `/privacy-guard` slash command (`$.command.register` in `session.start`,
  answered by `command.run`). It prints the full status: guard state or block reason, and
  for each server its profile, profile state, exemption and warm-up state. It holds no
  value from the store. Server aliases and profile names are not sensitive: the model
  already sees the aliases in tool names (`mcp__<alias>__…`).
- The status line keeps the short form `privacy-guard: active · n protected · m exempt`.
- **Verify at implementation**: whether the text returned by `command.run` is added to the
  conversation the model reads. It holds nothing sensitive either way.

