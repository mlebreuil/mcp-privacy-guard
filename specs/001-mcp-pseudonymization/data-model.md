# Data Model: Pseudonymize MCP Data Sent to the Model

**Feature**: `001-mcp-pseudonymization` | **Research**: [research.md](./research.md)

`<home>` is `$MCP_PRIVACY_GUARD_HOME`, default `~/.config/mcp-privacy-guard`.

## Kind

What an identifying value is. It decides the stand-in format
([contracts/standin-formats.md](./contracts/standin-formats.md)).

| Group | Kinds | Defined by |
|---|---|---|
| Network | `IP` (address, prefix, range, wildcard), `FQDN`, `URL`, `MAC` | core |
| Identity | `EMAIL`, `USER`, `GROUP` | core |
| Generic | `NAME` (prefix `n`), `DIGITS` | core |
| Text | `TEXT` (whole value), `MIXED` (scan, else whole) | core |
| Profile name kinds | e.g. `RULE_NAME`, `ADDRESS`, `DEVICE_NAME` | profile |

Every name kind produces the same stand-in as `NAME` (`n-<token>`). A kind only marks the
value as a name to learn for questions and selects cue words (FR-009). The stand-in prefixes
are fixed: `n`, `text`, `h`, `d`, `u`, `g`, `dom`, `p`.

## Session folder (`<home>/store/sessions/<session-id>/`, mode `0700`)

Everything that produces or links stand-ins, for one Claude Code session (research R13).
Nothing else in `<home>/store/` is persistent. `<session-id>` must match
`[A-Za-z0-9_-]{1,128}`. Anything else is exit 2.

**States**: `none` → (`begin`) → `live` → (`end` at `session.end`, or swept after 24 h
untouched) → `none`. While `live`, `unreadable` or `too-permissive` makes every command except
`status` exit 3. A command other than `begin` that finds `none` exits 3 ("session expired or
not started"). It never creates a folder. `begin` on a `live` folder exits 4.

## Pseudonymization secret (`secret.key` in the session folder)

| Field | Rule |
|---|---|
| `key` | 32 bytes from `secrets.token_bytes`, created by `begin` only |
| file | `<home>/store/sessions/<session-id>/secret.key`, mode `0600` |

One secret per session. It is never replaced during the session (FR-025) and is deleted
with the folder.

## Session mapping (`mapping.sqlite` in the session folder, mode `0600`, WAL)

### `standin`

| Column | Type | Rule |
|---|---|---|
| `standin` | text | unique; the full stand-in string as issued |
| `token` | text, nullable | name token without the `n-` prefix (name kinds); unique per real |
| `kind` | text | |
| `real` | text | |
| `rev` | integer | strictly increasing within the session, from 1; the plugin syncs with `since` |
| `first_seen` | text (UTC ISO 8601) | |
| `fixed` | bool | `true` for values that reach the model unchanged (keep-list IPs, IPs from exempt servers): `standin = real`, never inverted (research R15) |

Unique `(kind, real)`. One row per issued stand-in, including IPs (computed from the key but
recorded so the plugin's table can reveal them) and the label-level FQDN stand-ins.

**Invariants**:
- within the session, the same `(kind, real)` always gives the same `standin` (FR-008);
- the same `real` gives the same name stand-in under every name kind, field and server;
- different reals never share a token or a stand-in (every collision is detected here);
- no row, and nothing derived from one, outlives the session.

### `names` (name dictionary for questions)

| Column | Type | Rule |
|---|---|---|
| `real` | text | |
| `kind` | text | name kinds, `USER`, `GROUP` |
| `server` | text | the alias it was seen on |
| `common_word` | bool | `real` is in the common-word list |

Unique `(real, kind)`. Filled by `result` and `learn` during the session.

### `meta`

`schema_version`, `session_id`, `created_at`, and per server: `warmup_state`
(`not-started` → `running` → `complete` or `failed`), `warmup_reason` (`timeout`,
`tool-missing`, `tool-error`, `learn-failed`, `not-connected`). Servers are recorded by `begin` (those whose
profile declares a warm-up) or by their first `warmup --state running`. While any is
`not-started` or `running`, `prompt` refuses with `warmup-pending`. Once one is `failed`, it
refuses with `warmup-failed` (FR-034).

## Profile

Loaded from TOML ([contracts/profile-format.md](./contracts/profile-format.md)).

| Field | Meaning |
|---|---|
| `id`, `version`, `description` | identity |
| `servers` | glob list matched against the server alias |
| `kinds` | name kinds: `cues` |
| `vocabulary` | closed list of values that pass anywhere in this server's data |
| `fields[]` | `path`, optional `tools`, then one of `kind`, `enum`, `keys` |
| `text.mode` | `mixed` (default) or `whole` for plain-text blocks |
| `warmup[]` | read-only tool calls (`tool`, `args`) the plugin runs at session start; questions wait until they complete (FR-034) |

**Validation** (on load, and by `check-profile`):
- the TOML parses and the schema matches;
- kind names are `[A-Z][A-Z0-9_]*` and do not redefine a core kind;
- path patterns parse;
- no vocabulary or enum value has an identifying shape;
- warm-up tools exist in the profile's own `fields` tool list or are declared read-only;
- a profile that applies to a server whose bundled profile declares a warm-up declares one
  too (`warmup-required`).

**States**: `valid` → applied. `invalid` → the default profile applies for that server, and
the reason is reported (FR-015).

## Operator config (`<home>/config.toml`)

| Key | Meaning |
|---|---|
| `keep.values`, `keep.files` | values always passed through (FR-028) |
| `hide.values`, `hide.files` | values always pseudonymized as `TEXT`, even when a profile would keep them |
| `servers.<alias>.profile` | force a profile for an alias |
| `servers.<alias>.exempt` | `true`: results pass unchanged; arguments are still translated |

There is **no** key that disables pseudonymization globally (FR-027). A contract test reads
the config schema and fails if one appears.

## Classification decision (per string value)

Order, first match wins (research R4): hide list → keep list → profile field rule (kind or
enum) → built-in safe forms and vocabulary → whole-value shape → single token `NAME` →
`MIXED`.

## Engine reply envelope

Every engine reply that can issue stand-ins carries:

| Field | Meaning |
|---|---|
| `table.rev` | latest revision |
| `table.entries[]` | `{ standin, real, kind }` added since the `--since` the plugin passed |

## Replacement (question)

| Field | Meaning |
|---|---|
| `start`, `end` | offsets in the question as typed |
| `kind`, `standin` | |
| `reason` | `shape`, `name`, `name+cue`, `name+quote` |

## Plugin state (module memory only)

| Item | Content |
|---|---|
| session id | `$.session.id()` the table belongs to. On change (`/clear`), the table is emptied and `rev` reset to 0 |
| reveal table | `Map<standin, { real, kind }>` and `rev`, for the current session only |
| server map | alias → `{ profile, exempt, status }` from `status` |
| recognition pattern | regex string from `status` for unknown stand-ins |
| reveal allowed | `false` after a spoofed `terminal` attach |
| warm-up progress | per server: calls done / total, for the status line (the engine holds the state that gates questions) |
| block reason | `null`, or why the guard blocks: no terminal surface, sandbox settings missing, engine unavailable, host too old, resumed conversation (FR-033), session expired |

Nothing is stored in `$.store`, `$.state` or on disk by the plugin.

## Relationships

```
session.start ──begin──▶ session folder (secret + mapping)
secret ──derives──▶ standin rows ──table──▶ plugin reveal table ──▶ terminal rows
profile ─classifies─▶ result values ──▶ standin rows, names rows
names ──recognises──▶ question values ──▶ standin rows
warm-up ($.mcp.call) ──learn──▶ names rows
tool arguments ──args (key + table)──▶ real values ──▶ MCP server
session.end ──end──▶ session folder deleted
```

## Lifecycle

| Item | Created | Deleted |
|---|---|---|
| `sessions/<id>/` (secret, mapping, names, warm-up state) | `begin` at `session.start` or on a new session id | `end` at `session.end`; sweep after 24 h untouched |
| plugin reveal table | `session.start` / session id change | process exit, session id change |
