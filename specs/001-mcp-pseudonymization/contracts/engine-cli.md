# Contract: `mcp-privacy-guard` Engine CLI

The local command the Claude Code plugin calls through `$.process.run` (research R2). Users run
`status`, `reveal` and `check-profile` themselves. It reads and writes `<home>`
(`$MCP_PRIVACY_GUARD_HOME`, default `~/.config/mcp-privacy-guard`). It contacts no data source,
opens no listener, and logs only to stderr, never with values.

Every subcommand reads at most one JSON object on stdin and writes one JSON object on stdout.

**Sessions** (research R13): every secret and mapping belongs to one Claude Code session and
lives in `<home>/store/sessions/<id>/`. `begin`, `result`, `args`, `prompt`, `learn`,
`observe`, `table` and `end` take `--session <id>` (`[A-Za-z0-9_-]{1,128}`, else exit 2).
Only `begin` creates a session's secret. Every other command exits 3 when the session folder
is missing, so a secret is never replaced during a session. Revisions (`rev`, `--since`)
count per session from 0. Nothing is shared between sessions.

## Exit codes

| Code | Meaning | Plugin action |
|---|---|---|
| `0` | Success | use the reply |
| `2` | Bad input (JSON, arguments) | block / withhold |
| `3` | Store unavailable: session folder missing (not begun, ended or swept), secret unreadable, permissions too broad, store in an unignored git tree | block / withhold, tell the user how to fix it (expired session → start a new conversation) |
| `4` | Refused: content cannot be safely pseudonymized (too large, unsupported); a question while a warm-up is pending or failed (`warmup-pending`, `warmup-failed`); an ambiguous address in arguments (`ambiguous-address`); `begin` on a live session | withhold / drop the question with the message |
| `5` | Internal error | block / withhold |

On a non-zero exit, stdout is `{"error": {"code", "message", "hint"}}`, with no value from the
input. A process that does not answer within the plugin's timeout counts as a failure.

Replies of `result`, `args`, `prompt`, `observe` and `table` carry
`"table": {"rev": n, "entries": [{"standin", "real", "kind"}]}` with the entries after
`--since`.

## `status [--servers <alias,...>] [--session <id>]`

- **stdout**:
  ```json
  {"engine": "1.0.0", "store": "ready|unreadable|too-permissive|in-git-tree",
   "session": "live|none|unreadable|too-permissive",
   "rev": 1234, "swept": 1,
   "servers": {"panos": {"profile": "panos-mcp", "profile_state": "valid", "exempt": false,
                         "warmup": [{"tool": "list_device_groups", "args": {}}],
                         "warmup_state": "not-started|running|complete|failed",
                         "warmup_reason": null},
               "notion": {"profile": "default", "profile_state": "valid", "exempt": true}},
   "recognise": "<regex for name-shaped stand-ins>",
   "kinds": ["IP", "FQDN", "..."], "keep_entries": 3, "hide_entries": 0}
  ```
- `store` describes `<home>/store/` itself (permissions, git tree). `session`, `rev` and
  `warmup_state` describe the given session and are omitted without `--session`. `swept`
  counts other sessions' folders deleted because they were untouched for over 24 hours.
- Never creates anything and never prints a value from the store. Always exits `0` unless
  its input is invalid.

## `begin --session <id> --servers <alias,...>`

Called by the plugin when a session starts, or when the session id changes after `/clear`
(research R13). It sweeps expired folders, then creates `<home>/store/sessions/<id>/`
(`0700`) with a new `secret.key` (`0600`) and an empty `mapping.sqlite`. It records the
IP-shaped keep-list values as fixed entries (research R15). It records
`warmup_state: not-started` for every listed server that is protected, not exempt, and whose
profile declares a warm-up (research R9, FR-034). **stdin**: none. **stdout**:
`{"session": "live", "swept": n, "warmup": ["panos"]}`. Exit `4` if the folder already exists (the
plugin checks `status` first; a reload of the plugin must not re-key a live session).

## `result --session <id> --server <alias> --tool <name> [--since <rev>]`

Pseudonymize one MCP tool result (FR-003–FR-010).

- **stdin**: `{"result": <McpToolResult as core gave it>, "is_error": false}`
- **stdout**: `{"result": <same shape, pseudonymized>, "withheld": 0, "notices": [], "table": …}`
- Text blocks that parse as JSON are walked and re-serialised. Other text is handled by the
  MIXED rule (or `whole`). `structuredContent` is walked. Non-text blocks are replaced by one
  notice block, and `withheld` counts them.
- Exit `4` when the result is over 2 MB of text or processing exceeds 10 s.
- `--exempt`: for an exempt server (research R15). The result is not changed and not
  returned. Its IP forms are recorded as fixed entries. **stdout**: `{"fixed": n}`.

## `args --session <id> --server <alias> --tool <name> [--since <rev>]`

Translate stand-ins in tool arguments to real values (FR-011, FR-012).

- **stdin**: `{"args": {…}}`
- **stdout**: `{"args": {…}, "translated": 2, "table": …}`. `translated` counts values only.
- Unknown stand-ins are left as typed. The reply never says which ones were unknown.
- Fixed entries (keep-list values, IPs from exempt servers) are passed unchanged. An IP form
  that is both fixed and an issued stand-in exits `4` with code `ambiguous-address`, and no
  value in the error (research R15).

## `prompt --session <id> [--since <rev>] [--command]`

Pseudonymize a question (FR-017–FR-020).

- **stdin**: `{"text": "<as typed>"}`
- **stdout**:
  ```json
  {"text": "<with stand-ins>",
   "replacements": [{"start": 7, "end": 16, "kind": "IP", "standin": "10.83.4.12",
                     "reason": "shape"}],
   "warnings": [], "table": …}
  ```
- `--command`: the text is a slash-command line. The engine replaces nothing and returns
  `{"identifying": true|false}`. The plugin drops the submission when it is `true`.
- **Warm-up gate** (FR-034): with or without `--command`, exits `4` while any warm-up
  recorded for the session is `not-started` or `running`, with
  `{"error": {"code": "warmup-pending", "message", "hint", "servers": ["panos"]}}`. Once one
  has `failed`, it exits `4` with code `warmup-failed`, the server, its reason code and a
  hint. Nothing is replaced or recorded in either case.

## `learn --session <id> --server <alias> --tool <name>`

Warm-up (research R9). **stdin**: `{"result": <McpToolResult>}`. Records names in the
session's dictionary and stand-ins in its mapping. Progress is recorded separately with
`warmup`. **stdout**: `{"names": <count>}`, never values.

## `warmup --session <id> --server <alias> --state running|complete|failed [--reason <code>]`

Records a server's warm-up progress for the session (research R9). `running` also registers
a server that was not listed at `begin` (connected mid-session). `--reason` is required with
`failed`: `timeout`, `tool-missing`, `tool-error`, `learn-failed` or `not-connected`. **stdin**: none.
**stdout**: `{"pending": ["…"], "failed": ["…"]}`, the servers still holding questions back.

## `observe --session <id> [--since <rev>]`

**stdin**: `{"text": "<assistant text with stand-ins>"}`. Inverts IP forms with the key and
records them, so the plugin can reveal unissued stand-in IPs (research R10).
**stdout**: `{"table": …}`.

## `table --session <id> --since <rev>`

**stdout**: `{"table": …}`. **The output contains real values.** It is meant only for the
plugin. The plugin's guard denies the model's tools any call that runs it (research R11).

## `end --session <id>`

Called by the plugin at `session.end` (research R13). Deletes the folder
`<home>/store/sessions/<id>/` (secret, mapping and its `-wal`/`-shm` files), then sweeps other
sessions' folders untouched for over 24 hours. **stdin**: none. **stdout**:
`{"deleted": true|false, "swept": n}`. Exit `0` when the folder is gone afterwards, whether
or not it existed. Must finish well within the `session.end` budget (1.5 s for the whole
chain): no secret read, no profile load.

## `reveal [--session <id>]`

For users, in their own terminal (fallback, e.g. text copied from a transcript). It reads
the secret and mapping of the given session, or of the only live session. With no live
session, or several and no `--session`, it exits 3: stand-ins of an ended session can never
be revealed (FR-008).
**stdin**: raw text (not JSON) or `{"text": "…"}`.
**stdout**: the revealed text. Unknown stand-ins stay in place, marked `⟨?⟩`. With `--json`:
`{"text", "revealed": n, "unknown": ["n-zzzzzzzz7q"]}`.

## `check-profile <file>`

Validates a profile ([profile-format.md](./profile-format.md)). **stdout**:
`{"valid": true}` or `{"valid": false, "errors": [{"path", "message"}]}`. Exit `0` either way.

## Not provided (by design)

No `--disable`, `--passthrough`, `--off` or similar, and no environment variable with that
effect (FR-027). A contract test asserts this against `--help` and the config schema.
