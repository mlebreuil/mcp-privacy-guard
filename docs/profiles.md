# Writing a server profile

The guard protects every MCP server from the first call, with no setup. A **profile** makes the
result of one server *more readable* without making it less safe. Writing and applying one takes
under 30 minutes. The format is defined in
[`specs/001-mcp-pseudonymization/contracts/profile-format.md`](../specs/001-mcp-pseudonymization/contracts/profile-format.md).

## When a profile helps

Without a profile (the default profile) the guard replaces every identifying shape (addresses,
host names, e-mails, MAC addresses, URLs, `DOMAIN\user`, long digit strings) and hides every
other value that is not a known safe word. Status words such as `connected` or `allow` that the
server returns are then hidden too, and the model sees `n-…` stand-ins where a plain word would
have been enough. A profile tells the guard which fields are:

- **enums**: a closed list of safe values (`state`, `action`);
- **names**: values to hide *and* to learn, so a question that mentions them is recognised;
- **free text**: one `TEXT` stand-in for the whole value;
- **keyed objects**: objects whose keys are plain words, such as `summary`.

If the default output is already usable, you do not need a profile.

## What a profile cannot do

A profile can only let *listed* values through. It can never:

- mark a field "keep". Only `enum` and `vocabulary` let values through, and only those listed;
- list a value of identifying shape in an enum or vocabulary (IP, host name, e-mail, MAC, URL,
  `DOMAIN\user`, 7+ digits). The profile is refused when it loads;
- keep an object key of identifying shape. `keys = "keep"` still hides such keys;
- override the operator hide list or touch another server's data;
- remove a warm-up (see below).

## Where it goes

Put the file in `<home>/profiles/<name>.toml` (`<home>` is `~/.config/mcp-privacy-guard` unless
`MCP_PRIVACY_GUARD_HOME` is set). The guard picks the profile for a server in this order:

1. `servers.<alias>.profile = "<profile id>"` in `<home>/config.toml`;
2. a profile of `<home>/profiles/` whose `servers` globs match the alias;
3. a bundled profile whose globs match (for example `panos-mcp`);
4. the default profile.

A profile that cannot be applied never turns the guard off: the server falls back to the default
profile (or to the bundled one, see warm-up), `status` shows
`profile_state: invalid` with a reason code, and a toast names the server at session start.

## Check it

```sh
mcp-privacy-guard check-profile ~/.config/mcp-privacy-guard/profiles/generic.toml
# {"valid": true}
# {"valid": false, "errors": [{"path": "", "message": "identifying-vocabulary"}]}
```

It exits 0 either way and never prints a value. `mcp-privacy-guard status --servers generic`
shows which profile a server uses.

## Format in five minutes

```toml
[profile]
id = "generic-example"          # [a-z0-9-]+
version = 1
servers = ["generic"]           # globs on the server alias (as /mcp lists it)
```

**Path patterns** are dotted keys over the JSON value: `name` matches a key, `*` any one key,
`[]` any array element, `**` any depth. Examples: `devices[].name`, `rules[].action`,
`**.description`, `data.*.hostname`. Rules are tried in file order, tool-specific rules first;
the first match wins. Add `tools = ["list_devices"]` to restrict a rule to some tools.

**Enum or vocabulary?**

- `enum` belongs to one field: any other value in that field is hidden as a name. Use it for
  `state`, `action`.
- `[vocabulary]` is a closed list of safe words for the whole server (inline `values` or `files`,
  one per line). Use it for words that appear in many places, such as built-in object names.

Either way only the listed words pass, and none may have an identifying shape.

**Names**: `kind = "DEVICE_NAME"` (declare it under `[kinds.DEVICE_NAME]`, with optional `cues`:
words that make a common-word name count as a name in your questions). Every name kind gets an
`n-…` stand-in; the kind only teaches question recognition.

**Free text**: `kind = "TEXT"` gives one `text-…` stand-in per value.

**Keys**: `keys = "keep"` keeps the plain-word keys of the objects at that path, `keys = "hide"`
pseudonymizes all of them. Keys that look like a host name or an address are hidden in both modes.

**Plain text results**: `[text] mode = "mixed"` (default) finds identifying parts inside the
text; `"whole"` replaces a plain-text block as a single value.

## Warm-up

Names that only appear in your questions can be recognised only if the guard has seen them in
results. A profile may list read-only tools the plugin calls at session start to learn the names:

```toml
[[warmup]]
tool = "list_device_groups"
args = {}
```

List only tools that exist and answer quickly. **Questions wait until every warm-up has
finished, and a failed warm-up blocks questions** (FR-034). A user profile for a server whose
bundled profile has a warm-up must keep one: you may change the tools, you cannot remove them
(reason `warmup-required`, the bundled profile keeps applying). If you do not want questions held
for a server, exempt it by name in `config.toml` (`[servers.<alias>] exempt = true`); that is
shown in the status.

## Worked example: the generic test server

[`testservers/generic/profile.example.toml`](../testservers/generic/profile.example.toml)
covers the generic server (`list_devices`, `get_config`, `get_logs`, `keyed`):

```toml
[profile]
id = "generic-example"
version = 1
servers = ["generic"]

[kinds.DEVICE_NAME]
cues = ["device", "firewall", "router"]

[[fields]]
path = "devices[].name"
tools = ["list_devices"]
kind = "DEVICE_NAME"

[[fields]]
path = "devices[].state"
enum = ["connected", "disconnected", "unknown"]

[[fields]]
path = "devices[].environment"
enum = ["prod", "preprod", "lab"]

[[fields]]
path = "rules[].action"
enum = ["allow", "deny", "drop"]

[[fields]]
path = "**.description"
kind = "TEXT"

[[fields]]
path = "*"
tools = ["keyed"]
keys = "keep"
```

1. Run `list_devices` with no profile. `environment: "prod"` comes back as an `n-…` stand-in (the
   built-in vocabulary knows states such as `connected`, but not your own labels).
2. Copy the file to `<home>/profiles/generic.toml` and run `check-profile` on it.
3. Run `list_devices` again. `environment` is readable (and so are `state` and `action`, which the built-in vocabulary already knows); names, addresses, host names and
   descriptions are still stand-ins. The tests in
   `engine/tests/leak/test_generic_profile.py` assert that no seed value leaks with this profile
   and that it produces fewer `n-…` stand-ins than the default.

If a field is still hidden, check the path against the JSON the tool returns (a text block that
parses as JSON is matched from its root) and remember the first matching rule wins.
