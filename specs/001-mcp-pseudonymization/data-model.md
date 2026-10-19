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

## Pseudonymization secret

| Field | Rule |
|---|---|
| `key` | 32 bytes from `secrets.token_bytes` |
| file | `<home>/store/secret.key`, mode `0600`, directory `0700` |

**States**: `absent` → (first use) → `ready`. `unreadable` or `too-permissive` →
every engine command except `status` exits with code 3, and the plugin blocks questions and
protected results (FR-025). A new secret means a new store: earlier stand-ins become
"unknown, issued with another secret".

## Mapping store (`<home>/store/mapping.sqlite`, mode `0600`, WAL)

### `standin`

| Column | Type | Rule |
|---|---|---|
| `standin` | text | unique; the full stand-in string as issued |
| `token` | text, nullable | name token without the `n-` prefix (name kinds); unique per real |
| `kind` | text | |
| `real` | text | |
| `rev` | integer | strictly increasing; the plugin syncs with `since` |
| `first_seen` | text (UTC ISO 8601) | |

Unique `(kind, real)`. One row per issued stand-in, including IPs (computed from the key but
recorded so the plugin's table can reveal them) and the label-level FQDN stand-ins.

**Invariants**:
- the same `(kind, real)` always gives the same `standin` (FR-008);
- the same `real` gives the same name stand-in under every name kind, field and server;
- different reals never share a token or a stand-in.

### `names` (name dictionary for questions)

| Column | Type | Rule |
|---|---|---|
| `real` | text | |
| `kind` | text | name kinds, `USER`, `GROUP` |
| `server` | text | the alias it was seen on |
| `common_word` | bool | `real` is in the common-word list |

Unique `(real, kind)`. Filled by `result` and `learn`.

### `meta`

`schema_version`, and per server: `warmup_state` (`not-started` → `running` → `complete` or
`failed`), `warmup_reason`.

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
| `warmup[]` | read-only tool calls (`tool`, `args`) the plugin runs at session start |

**Validation** (on load, and by `check-profile`):
- the TOML parses and the schema matches;
- kind names are `[A-Z][A-Z0-9_]*` and do not redefine a core kind;
- path patterns parse;
- no vocabulary or enum value has an identifying shape;
- warm-up tools exist in the profile's own `fields` tool list or are declared read-only.

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
| reveal table | `Map<standin, { real, kind }>` and `rev` |
| server map | alias → `{ profile, exempt, status }` from `status` |
| recognition pattern | regex string from `status` for unknown stand-ins |
| reveal allowed | `false` after a spoofed `terminal` attach |
| block reason | `null`, or why the guard blocks: no terminal surface, sandbox settings missing, engine unavailable, host too old |

Nothing is stored in `$.store`, `$.state` or on disk by the plugin.

## Relationships

```
secret ──derives──▶ standin rows ──table──▶ plugin reveal table ──▶ terminal rows
profile ─classifies─▶ result values ──▶ standin rows, names rows
names ──recognises──▶ question values ──▶ standin rows
warm-up ($.mcp.call) ──learn──▶ names rows
tool arguments ──args (key + table)──▶ real values ──▶ MCP server
```
