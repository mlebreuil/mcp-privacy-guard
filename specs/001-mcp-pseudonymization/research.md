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
  (IP, CIDR, URL, e-mail, MAC, FQDN, `DOMAIN\user`, long digit runs) and dictionary names. Then
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
- **Names**: `n-<token>`, where the token is `t(6)` of HMAC(secret, `name` ‖ real). It does
  not depend on the kind, the field or the server, so one real name has exactly one stand-in
  everywhere. The model correlates configuration, logs and servers by plain string equality
  (FR-008, FR-009, clarified 2026-10-18), and it infers the kind from context (the field
  name, the surrounding words). A collision lengthens the token by 2.
- **Rejected**: kind prefixes (`rule-…`, `fw-…`). The same value could then appear with two
  prefixes when profiles or fields disagree, which breaks correlation, the end goal.
- **FQDN**: each label below the public suffix is replaced by a token keyed on its parent
  chain (`h-` for the leftmost label, `d-` for the others). The public suffix is kept, and
  labels that share a parent keep sharing it.
- **URL**: scheme kept, host as FQDN or IP, port kept, path, query and fragment replaced by
  `/p-<token>`.
- **E-mail**: `u-<token>@<fqdn stand-in>`. **User**: `DOMAIN\user` → `dom-<t>\u-<t>`.
- **MAC**: locally administered `02:` plus keyed bytes. **DIGITS**: same length, keyed,
  first digit non-zero.
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
- **Names**: whole-token, case-sensitive match against the name dictionary (store `names`
  table). The dictionary is filled:
  1. from every result the engine pseudonymizes (names of every kind, with the server and
     the kind);
  2. by an optional **warm-up**. A profile may list read-only tools to call at session start
     (for `panos-mcp`: device groups, templates, devices, zones, tags, rules and objects
     listings). The plugin calls them with `$.mcp.call` and passes the results to
     `mcp-privacy-guard learn`, which records names and returns nothing. The results never
     reach the model. The engine itself contacts no data source (Principle II).
- **Common words**: a dictionary name that is also in the common-word list (`web`, `test`,
  `inside`) is replaced only when it is quoted or back-ticked, or preceded within three
  tokens by a cue word of its kind (the profile's `cues`, plus generic ones: `server`,
  `host`, `object`, `group`, `rule`).
- **Before warm-up ends** (or with no warm-up), names never seen are not recognised. The
  status line says "name list loading". **Residual risk**: documented. The user sees every
  replacement (FR-020), so they can spot a missed name.
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
  disk.
- `ui.render` on `terminal` (R1): longest-match substitution of known stand-ins in the text
  or props. Revealed values are highlighted. Unknown stand-ins that match the recognition
  pattern (from the engine's `status`) are marked with a dim `(?)`.
- **Unissued IPs**: the model may write a stand-in IP that was never issued (the next address
  in a stand-in subnet). At `turn.complete` the plugin sends the final assistant text to
  `mcp-privacy-guard observe`, which inverts IP forms with the key, records them, and returns
  the new table entries. The plugin then invalidates the rows it drew.
- **Manual reveal** (fallback, e.g. text copied from a transcript): `mcp-privacy-guard
  reveal`, run by the user in their own terminal, reads text on stdin and prints it revealed.

## R11. Self-protection (FR-024–FR-026)

- **Store**: `<home>/store/secret.key` (32 random bytes) and `<home>/store/mapping.sqlite`,
  where `<home>` defaults to `~/.config/mcp-privacy-guard` (or `$MCP_PRIVACY_GUARD_HOME`).
  Files `0600`, directories `0700`. If permissions are broader, or the secret exists but
  cannot be read, the engine exits with code 3 and the plugin blocks. A missing secret is
  created on first use. The store is refused inside a git work tree that does not ignore it.
- **The model's tools**: a `tool.call` guard on built-in tools (`Bash`, `Read`, `Grep`, `Glob`,
  `Edit`, `Write`, `NotebookEdit`, and any tool with a path argument) denies inputs that name
  the guard's home, the engine command, or the plugin's own folder. Without the last one,
  the model could edit the plugin and have it hot-reload. This is best effort, because
  spellings vary.
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
    captured once from `PANOS_MCP_SAMPLES_SCENARIO`), and results of the generic test MCP
    server seeded with known "real" values. Assert that no real value appears in what the
    model would receive, using both the `panos-mcp` profile and the default profile;
  - consistency across processes and restarts (SC-004), and argument round-trips (SC-003);
  - benchmark: two engine calls plus 500 records under 1 s (SC-006).
- **Plugin** (`claude plugin validate`, `claude plugin test`, `*.test.ts`): result rewrite,
  withhold on engine failure, throw and timeout, prompt rewrite and drop, slash command
  drop, attachment drop, block in a session without `terminal`, block without the required
  sandbox settings, deny of `dangerouslyDisableSandbox`, reveal on `terminal` and none on
  other surfaces, reveal stopped after a spoofed
  `terminal` attach, unknown stand-ins marked, built-in tool guard. The job is skipped
  visibly in CI when the `claude` CLI is absent.
- **End to end**: [quickstart.md](./quickstart.md) with `panos-mcp` in offline demo mode and the
  generic test server, the plugin loaded through `--plugin-dir`.
