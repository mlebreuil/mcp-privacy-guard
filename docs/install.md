# Installing the guard

The guard has two parts: the **engine** (a Python command, standard library only) and the
**plugin** for Claude Code. Both are needed. It works in a terminal only.

## Requirements

- Claude Code 2.1.303 or newer, **used in a terminal**. The VS Code extension, the desktop app
  and headless runs are refused.
- Python 3.11 or newer.
- Claude Code's **sandbox**, configured as below.

## 1. Install the engine

From a clone of this repository:

```sh
uv tool install ./engine        # or: pipx install ./engine
mcp-privacy-guard status        # prints the engine version and home folder
```

The engine is not published to a package index yet. When it is, `uv tool install
mcp-privacy-guard` or `pipx install mcp-privacy-guard` will do the same.

`<home>` is `~/.config/mcp-privacy-guard` unless `MCP_PRIVACY_GUARD_HOME` is set. Its sessions
folder holds one folder per live session and is created with owner-only permissions.

## 2. Install the plugin

Load the plugin folder:

```sh
claude --plugin-dir /path/to/mcp-privacy-guard/plugin
```

(A marketplace entry is not published yet.) If the command is not on `PATH` for Claude Code,
set the plugin option `enginePath` to the full path of `mcp-privacy-guard`. No other option
exists; nothing turns the guard off.

## 3. Turn on the sandbox settings

The guard refuses to work without them, because it must keep the model from reading its folder.
Put these in your user settings (`~/.claude/settings.json`) or, better, in managed settings:

```json
{
  "sandbox": {
    "enabled": true,
    "allowUnsandboxedCommands": false,
    "failIfUnavailable": true,
    "filesystem": { "denyRead": ["~/.config/mcp-privacy-guard"] }
  }
}
```

Use the real `<home>` if you changed it. The guard also refuses a `sandbox.filesystem.allowRead`
entry that covers `<home>`, `sandbox.filesystem.disabled = true`, and a
`sandbox.excludedCommands` entry that names the engine.

The sandbox covers shell commands only. Claude's file tools are not inside it, so also add
permission deny rules for them (check the rule syntax against the Claude Code permissions
documentation of your version):

```json
{
  "permissions": {
    "deny": [
      "Read(~/.config/mcp-privacy-guard/**)",
      "Grep(~/.config/mcp-privacy-guard/**)",
      "Glob(~/.config/mcp-privacy-guard/**)"
    ]
  }
}
```

The plugin's own tool guard also denies the model any call that names `<home>`, the engine
command or the plugin folder, and writes to Claude Code's settings and plugin state. That is
best effort, because commands can be spelled many ways.

### Managed (policy) settings

Managed settings sit above every other source, and nothing in user, project or `--settings`
overrides a managed key. Deliver the `sandbox` block above there (managed file, MDM or
server-managed settings) so users cannot weaken it. Pinning the plugin itself as enabled
through managed settings (`enabledPlugins`) was **not confirmed** against the documentation of
Claude Code 2.1.304: check it on your version before relying on it, since an uninstalled guard
protects nothing.

## 4. Check it

Start Claude Code with the plugin and an MCP server. A toast lists each server with its profile
or `exempt`, and the status line shows `privacy-guard: active · n protected · m exempt`. Run
`/privacy-guard` for the state of each server, including its warm-up.

Use `/clear` to start fresh, never `--resume`: the stand-ins of an ended session cannot be
used again, so a resumed conversation is blocked.

## Troubleshooting: block reasons

The status line and `/privacy-guard` show the reason. Nothing reaches the model until it is gone.

| Message starts with | Cause | Fix |
|---|---|---|
| `use Claude Code in a terminal` | the session is not drawn in a terminal | use a terminal session |
| `turn on Claude Code's sandbox and protect the guard folder: …` | a sandbox setting is missing; the message lists each one | add the settings of step 3, restart |
| `the engine is unavailable` | the engine command cannot start | install it (step 1) or set `enginePath` |
| `Claude Code 2.1.303 or newer is required` | the host is too old | update Claude Code |
| `this conversation is from an ended session; start a new one (/clear)` | the conversation was resumed | run `/clear` |
| `session expired; start a new conversation (/clear)` | the session folder was deleted or swept | run `/clear` |
| `the session store is unusable` | permissions on the store are too broad, or it is unreadable or inside an unignored git tree | run `/clear`; fix the folder's permissions or move `MCP_PRIVACY_GUARD_HOME` |
| `loading names for <server>, try again in a moment` | a warm-up is still running | wait; the status line shows progress |
| `loading names for <server> failed (<reason>)` | a warm-up failed (`timeout`, `tool-missing`, `tool-error`, `learn-failed`) | fix the profile's warm-up tools, or exempt the server; then `/clear` |
| `a question with an image, file or document cannot be checked` | an attachment | paste the text instead |

## Uninstalling

Remove the plugin and the engine. `<home>` holds only session folders, deleted at each session
end, plus your own `config.toml` and `profiles/`.
