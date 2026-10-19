# Contract: `mcp-privacy-guard` Engine CLI

The local command the Claude Code plugin calls through `$.process.run` (research R2). Users run
`status`, `reveal` and `check-profile` themselves. It reads and writes `<home>`
(`$MCP_PRIVACY_GUARD_HOME`, default `~/.config/mcp-privacy-guard`). It contacts no data source,
opens no listener, and logs only to stderr, never with values.

Every subcommand reads at most one JSON object on stdin and writes one JSON object on stdout.
A missing secret is created on first use by any subcommand except `status`.

## Exit codes

| Code | Meaning | Plugin action |
|---|---|---|
| `0` | Success | use the reply |
| `2` | Bad input (JSON, arguments) | block / withhold |
| `3` | Store unavailable: secret unreadable, permissions too broad, store in an unignored git tree | block / withhold, tell the user how to fix it |
| `4` | Refused: content cannot be safely pseudonymized (too large, unsupported) | withhold |
| `5` | Internal error | block / withhold |

On a non-zero exit, stdout is `{"error": {"code", "message", "hint"}}`, with no value from the
input. A process that does not answer within the plugin's timeout counts as a failure.

Replies of `result`, `args`, `prompt`, `observe` and `table` carry
`"table": {"rev": n, "entries": [{"standin", "real", "kind"}]}` with the entries after
`--since`.

## `status [--servers <alias,...>]`

- **stdout**:
  ```json
  {"engine": "1.0.0", "store": "ready|absent|unreadable|too-permissive|in-git-tree",
   "rev": 1234,
   "servers": {"panos": {"profile": "panos-mcp", "profile_state": "valid", "exempt": false,
                         "warmup": [{"tool": "list_device_groups", "args": {}}],
                         "warmup_state": "complete"},
               "notion": {"profile": "default", "profile_state": "valid", "exempt": true}},
   "recognise": "<regex for name-shaped stand-ins>",
   "kinds": ["IP", "FQDN", "..."], "keep_entries": 3, "hide_entries": 0}
  ```
- Never creates anything and never prints a value from the store. Always exits `0` unless
  its input is invalid.

## `result --server <alias> --tool <name> [--since <rev>]`

Pseudonymize one MCP tool result (FR-003–FR-010).

- **stdin**: `{"result": <McpToolResult as core gave it>, "is_error": false}`
- **stdout**: `{"result": <same shape, pseudonymized>, "withheld": 0, "notices": [], "table": …}`
- Text blocks that parse as JSON are walked and re-serialised. Other text is handled by the
  MIXED rule (or `whole`). `structuredContent` is walked. Non-text blocks are replaced by one
  notice block, and `withheld` counts them.
- Exit `4` when the result is over 2 MB of text or processing exceeds 10 s.
- For an exempt server the plugin does not call `result`.

## `args --server <alias> --tool <name> [--since <rev>]`

Translate stand-ins in tool arguments to real values (FR-011, FR-012).

- **stdin**: `{"args": {…}}`
- **stdout**: `{"args": {…}, "translated": 2, "table": …}`. `translated` counts values only.
- Unknown stand-ins are left as typed. The reply never says which ones were unknown.

## `prompt [--since <rev>] [--command]`

Pseudonymize a question (FR-017–FR-020).

- **stdin**: `{"text": "<as typed>"}`
- **stdout**:
  ```json
  {"text": "<with stand-ins>",
   "replacements": [{"start": 7, "end": 16, "kind": "IP", "standin": "10.83.4.12",
                     "reason": "shape"}],
   "warnings": ["name list loading for panos"], "table": …}
  ```
- `--command`: the text is a slash-command line. The engine replaces nothing and returns
  `{"identifying": true|false}`. The plugin drops the submission when it is `true`.

## `learn --server <alias> --tool <name>`

Warm-up (research R9). **stdin**: `{"result": <McpToolResult>}`. Records names in the
dictionary and stand-ins in the store. **stdout**: `{"names": <count>}`, never values.

## `observe [--since <rev>]`

**stdin**: `{"text": "<assistant text with stand-ins>"}`. Inverts IP forms with the key and
records them, so the plugin can reveal unissued stand-in IPs (research R10).
**stdout**: `{"table": …}`.

## `table --since <rev>`

**stdout**: `{"table": …}`. **The output contains real values.** It is meant only for the
plugin. The plugin's guard denies the model's tools any call that runs it (research R11).

## `reveal`

For users, in their own terminal (fallback, e.g. text copied from a transcript).
**stdin**: raw text (not JSON) or `{"text": "…"}`.
**stdout**: the revealed text. Unknown stand-ins stay in place, marked `⟨?⟩`. With `--json`:
`{"text", "revealed": n, "unknown": ["n-zzzz9q"]}`.

## `check-profile <file>`

Validates a profile ([profile-format.md](./profile-format.md)). **stdout**:
`{"valid": true}` or `{"valid": false, "errors": [{"path", "message"}]}`. Exit `0` either way.

## Not provided (by design)

No `--disable`, `--passthrough`, `--off` or similar, and no environment variable with that
effect (FR-027). A contract test asserts this against `--help` and the config schema.
