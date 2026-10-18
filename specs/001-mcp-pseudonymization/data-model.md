# Data Model: Pseudonymize Data Sent to the Model

**Feature**: `001-mcp-pseudonymization` (carried over from panos-mcp draft 002; to be revised by `/speckit-plan`) |
**Research**: [research.md](./research.md)

## Kind (enumeration)

What an identifying value is. It determines the stand-in format
([contracts/standin-formats.md](./contracts/standin-formats.md)).

| Group | Members |
|---|---|
| Network | `IP` (address, prefix, range, wildcard), `FQDN`, `HOSTNAME`, `URL`, `MAC` |
| Identity | `USER`, `GROUP`, `EMAIL` |
| Device | `SERIAL`, `DEVICE_NAME` |
| Configuration names | `DEVICE_GROUP`, `TEMPLATE`, `TEMPLATE_STACK`, `RULE_NAME`, `ADDRESS`, `ADDRESS_GROUP`, `SERVICE`, `SERVICE_GROUP`, `APP_GROUP`, `TAG`, `ZONE`, `PROFILE_GROUP`, `INTERFACE`, `VSYS` |
| Free text | `TEXT` (whole value), `MIXED` (scan, replace embedded values, else whole value) |

Unannotated string fields default to `TEXT` (fail closed, FR-007).

## Field classification

A marker on each string field of the result models (`models/*.py`) and on each tool argument:

- `Pii(kind)`: pseudonymize as `kind`.
- `Keep`: never pseudonymized (enum-like strings Panorama returns as free strings, e.g.
  `action`, `log_type`, `severity`, application names from the predefined catalogue).

**Validation**: a contract test enumerates every model reachable from every tool's return type
and from `ToolErrorInfo`, and fails if a `str` / `list[str]` / `dict[str, str]` field has
no marker.

## Pseudonymization secret

| Field | Description |
|---|---|
| `key` | 32 random bytes |
| `path` | `<store dir>/secret.key`, mode `0600`, directory `0700` |

**States**: `absent` → created on first start → `ready`. `unreadable` or `too-permissive` →
server refuses data (FR-013), and `pseudonym prompt` exits non-zero so the plugin drops the
prompt (FR-024). Never logged and never returned (FR-012).

## Stand-in record (`standin` table)

| Field | Type | Rules |
|---|---|---|
| `kind` | Kind | |
| `standin` | text | unique; same shape as `real`; never a real *name* (reserved prefix) |
| `real` | text | unique together with `kind` |
| `first_seen` | timestamp | |
| `rev` | integer | monotonically increasing; the plugin syncs with `--since <rev>` |

IP stand-ins are computed from the key and can be inverted without the table. They are still
recorded so that the plugin's reveal table, which has no key, can map them back.

**Invariants**:
- the same `(kind, real)` always gives the same `standin` (FR-004);
- different reals of one kind give different stand-ins;
- name stand-ins are unique across kinds because of their prefix.

## Name dictionary (`names` table)

| Field | Type | Rules |
|---|---|---|
| `kind` | Kind (configuration names, `USER`, `GROUP`, `DEVICE_NAME`) | |
| `real` | text | unique together with `kind` |
| `common_word` | bool | true if `real` is in the bundled common-word list (R8) |

It is filled from results and by the start-up warm-up. The prompt recogniser reads it.

**Warm-up state** (kept in the store, `meta` table): `not-started` → `running` → `complete`
or `failed(reason)`. Reported by `pseudonym status` and shown by the plugin.

## Keep list / hide list (operator)

| Setting | Meaning |
|---|---|
| `PANOS_MCP_PSEUDONYM_KEEP` | Path to a file, one value per line: always passed through (e.g. public DNS servers). The built-in keep set (shared with the sample sanitizer) is always included. |
| `PANOS_MCP_PSEUDONYM_HIDE` | Path to a file: always pseudonymized as `TEXT` wherever it appears, even inside built-in-looking or `Keep` fields. |
| `PANOS_MCP_PSEUDONYM_DIR` | Store directory (default `~/.config/panos-mcp/pseudonym/`). |

There is no setting that turns pseudonymization off (FR-017). A contract test asserts that no
such setting exists.

## Replacement (prompt CLI output)

| Field | Description |
|---|---|
| `start`, `end` | Character offsets in the original question |
| `kind` | Kind |
| `standin` | What the model receives |
| `reason` | `shape`, `name`, or `name+cue` (common word matched by a cue) |

The plugin uses the replacements to highlight the replaced values in the user's own row
(FR-025).

## Reveal table (plugin memory only)

`standin → { real, kind }`, synced from `pseudonym table --since <rev>`. It is held in the
plugin module's memory for the session: never in `$.store` and never written to disk by the
plugin. It is rebuilt on `session.start` and after each reload.

## Relationships

```
secret ──derives──▶ standin.standin  ◀──reverse lookup── tool arguments (R5)
standin ──synced──▶ reveal table (plugin) ──used by──▶ AssistantMessage / UserMessage /
                                                      ToolUse / ToolResult rows
names ──used by──▶ prompt recogniser ──writes──▶ standin
```
