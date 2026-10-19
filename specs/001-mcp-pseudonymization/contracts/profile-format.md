# Contract: Profile Format

A profile describes one MCP server's data so it is handled more precisely than with the
default profile (research R5, FR-013–FR-016). Profiles are TOML. Bundled profiles live in the
engine package (`default.toml`, `panos-mcp.toml`). Operator profiles go in `<home>/profiles/`.
Validate with `mcp-privacy-guard check-profile <file>`.

## Example (excerpt of `panos-mcp.toml`)

```toml
[profile]
id = "panos-mcp"
version = 1
description = "Palo Alto Networks Panorama MCP server"
servers = ["panos", "panos-*", "panos-mcp"]

[kinds.RULE_NAME]
cues = ["rule", "policy"]

[kinds.DEVICE_NAME]
cues = ["firewall", "device"]

[vocabulary]
files = ["panos-mcp/builtin.txt", "panos-mcp/applications.txt"]
values = ["any", "application-default", "intrazone", "interzone", "universal"]

[[fields]]
path = "**.rules[].name"
kind = "RULE_NAME"

[[fields]]
path = "**.rules[].action"
enum = ["allow", "deny", "drop", "reset-client", "reset-server", "reset-both"]

[[fields]]
path = "**.description"
kind = "TEXT"

[[fields]]
path = "entries[].*"
tools = ["query_logs"]
keys = "keep"

[text]
mode = "mixed"

[[warmup]]
tool = "list_device_groups"
args = {}
```

## Fields

| Key | Required | Meaning |
|---|---|---|
| `profile.id` | yes | `[a-z0-9-]+`, unique |
| `profile.version` | yes | integer; the format version is 1 |
| `profile.servers` | yes | glob patterns on the server alias |
| `kinds.<KIND>` | per kind | declares a name kind (`[A-Z][A-Z0-9_]*`). Every name kind gets the same `n-…` stand-in; the kind marks values as names to learn for questions |
| `kinds.<KIND>.cues` | no | words that, within 3 tokens before a common-word name, make it count as a name in questions |
| `vocabulary.values`, `vocabulary.files` | no | closed lists of safe values (one per line in files) |
| `fields[].path` | yes | path pattern (below) |
| `fields[].tools` | no | restrict the rule to these tool names |
| `fields[].kind` | one of | a core or profile kind |
| `fields[].enum` | one of | allowed safe values; **any other value becomes `NAME`** |
| `fields[].keys` | one of | `keep` or `hide` for the keys of objects at this path. `keep` never keeps a key of identifying shape (IP, FQDN, e-mail, MAC, URL, `DOMAIN\user`, 7+ digits) or a key on the hide list: those are pseudonymized as usual |
| `text.mode` | no | `mixed` (default) or `whole` for plain-text blocks |
| `warmup[].tool`, `.args` | no | read-only tools the plugin calls at session start to learn names. Questions are held until they all complete in the session, and stay blocked if one fails (FR-034), so list only tools that exist and answer quickly |

## Path patterns

Dotted keys over the JSON value. `name` matches a key, `*` any one key, `[]` any array
element, `**` any depth (zero or more steps). Text blocks that parse as JSON are matched from
their root. Examples: `**.name`, `rules[].source[]`, `data.*.hostname`.

Rules are tried in file order, tool-specific rules first. The first match wins. Values that
no rule matches use the default classification (research R4).

## What a profile cannot do (FR-014)

- Mark a field as "keep". Only `enum` and `vocabulary` let values through, and only the
  values listed.
- Keep an object key of identifying shape. `keys = "keep"` applies only to keys with no
  identifying shape (FR-004 floor, analysis H3).
- List a vocabulary or enum value that has an identifying shape (IP, FQDN, e-mail, MAC,
  URL, `DOMAIN\user`, 7+ digits). This is refused when the profile loads.
- Override the operator hide list, or affect another server's data.
- Drop a warm-up. A user profile or a `servers.<alias>.profile` override that applies to a
  server whose bundled profile declares a `warmup` must declare one too. Otherwise it is
  invalid (the bundled profile applies, with a notice, reason `warmup-required`). The only
  way to stop holding questions for a server is `exempt = true`, which is shown in the status
  (FR-002).

## Errors

An unreadable or invalid profile is not applied. The server uses the default profile, and
the reason appears in `status` (`profile_state: "invalid"`) and in a toast.
