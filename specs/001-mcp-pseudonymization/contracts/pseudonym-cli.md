# Contract: `panos-mcp pseudonym` CLI

Local command used by the Claude Code companion plugin (research R6) and, for `reveal` and
`status`, by users. Reads and writes the store in `PANOS_MCP_PSEUDONYM_DIR` (default
`~/.config/panos-mcp/pseudonym/`). Never contacts Panorama, opens no listener, and logs to
stderr only, without values.

All subcommands read JSON from stdin where noted and write one JSON object to stdout.

Exit codes:

| Code | Meaning |
|---|---|
| `0` | Success. |
| `2` | Bad input. |
| `3` | Store unavailable: secret missing or unreadable, or permissions too broad. |
| `4` | Refused: the content cannot be safely pseudonymized. |

On any non-zero exit, stdout is `{"error": {"code", "message", "hint"}}`, with no values from
the input.

## `pseudonym prompt`

Pseudonymize a user question (FR-022–FR-025).

- **stdin**: `{"text": "<question as typed>"}`
- **stdout**:
  ```json
  {
    "text": "<question with stand-ins>",
    "replacements": [
      {"start": 7, "end": 16, "kind": "IP", "standin": "10.83.4.12", "reason": "shape"}
    ],
    "warnings": ["name list still loading (warm-up running)"]
  }
  ```
- Offsets refer to the original text. The output contains every identifying value recognised
  by shape and every dictionary name (with the common-word rule).
- Exit `3`: the plugin drops the prompt with the error message.

## `pseudonym table --since <rev>`

Reveal-table sync for the plugin.

- **stdout**:
  `{"rev": <latest>, "entries": [{"standin": "...", "real": "...", "kind": "..."}]}`.
- **Security**: the output contains real values. It is meant only for the plugin; the plugin
  guard denies the model's tools any call that runs it (research R9).

## `pseudonym reveal`

Manual fallback and test helper (FR-016).

- **stdin**: `{"text": "..."}`
- **stdout**: `{"text": "<revealed>", "revealed": <n>, "unknown": ["rule-zzzz9q", ...]}`
- Unknown stand-ins are left in place and listed, never guessed.

## `pseudonym status`

- **stdout**:
  ```json
  {"store": "ready|absent|unreadable|too-permissive", "rev": 1234,
   "warmup": "not-started|running|complete|failed", "warmup_reason": null,
   "kinds": ["IP", "FQDN", "..."], "keep_entries": 3, "hide_entries": 0}
  ```
- No value from the store appears in the output.

## Not provided (by design)

- No `--disable`, no `--passthrough`, no plain-text dump of the store other than `table`
  (FR-017).
