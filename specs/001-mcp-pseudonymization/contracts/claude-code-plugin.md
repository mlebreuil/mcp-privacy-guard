# Contract: Claude Code Companion Plugin (`panos-mcp-reveal`)

A Claude Code plugin shipped in this repository (research R1, R10). It holds no
pseudonymization logic; it calls [`panos-mcp pseudonym`](./pseudonym-cli.md).

**Location**: `clients/claude-code/panos-mcp-reveal/` (`.claude-plugin/plugin.json`,
`hooks/hooks.json`, `hooks/register.ts`, `hooks/*.test.ts`). Installed with
`/plugin install` from the repository, or `claude --plugin-dir` for development.

**Minimum Claude Code version**: the build whose API was researched (2.1.301). It is declared
in the manifest and checked on `session.start`; an older build gets a toast and the prompt
guard drops every prompt (fail closed).

## Hooks

| Event | Matcher | Behaviour | Spec |
|---|---|---|---|
| `session.start` | — | Run `pseudonym status`. If the store is not `ready`, set the status line to `panos-mcp: pseudonymization unavailable – prompts blocked`. Otherwise sync the full reveal table (`table --since 0`). Show warm-up state in the status line until `complete`. | FR-013, R8 |
| `prompt.submit` | — | Slash command (`e.command` set) whose line contains an identifying value: `{ drop }` asking to rephrase as a plain question. Otherwise run `pseudonym prompt`. Success: `next({ ...e, text })`, sync the table, then toast `n value(s) replaced` (none if 0). Non-zero exit or timeout (5 s): `{ drop: <message> }`. Wrapped with `.catch(($, e, next) => next.called ? next(e) : { drop: … })` so a throw never lets the original through. | FR-022, FR-024, FR-025 |
| `tool.call` | MCP tools of this server (by tool-name suffix, any server alias) | `await next(e)`, then sync the table (`--since <rev>`), then `$.ui.invalidate` the rows drawn. | FR-015 |
| `tool.call` | `Bash`, `Read`, `Grep`, `Glob`, `Edit`, `Write`, `NotebookEdit`, `WebFetch` | `{ deny }` when the input mentions the store directory, `panos-mcp pseudonym`, or the MCP client config file that holds the server's environment. | R9 |
| `ui.render` | `AssistantMessage`, `ToolUse`, `ToolResult` | Only when `e.surface` is `terminal` or `vscode`: replace every known stand-in in the drawn text or props with its real value and highlight it. Mark unknown name-shaped stand-ins (contract standin-formats §4) with a dim `(?)`. Otherwise `next(e)` unchanged. | FR-015, FR-016, Story 4 |
| `ui.render` | `UserMessage` (`origin.kind` = composer) | Same reveal, so the user sees their question as typed; replaced values underlined. | Story 3 #5, FR-025 |

## Guarantees

- The model never receives revealed text. Render rewrites change the drawing only (API
  contract), and the plugin never calls `$.prompt.submit`, `session.append` or any event
  that adds model-visible content with revealed values.
- The reveal table lives in module memory only (not `$.store`, not `$.state`, not disk).
- No reveal on `mobile` or `desktop` surfaces (remote drawing).
- No setting disables the prompt guard (FR-017).

## Tests (`claude plugin test`)

- A prompt with an IP is rewritten to the CLI's text.
- CLI exit `3` → dropped; CLI throw → dropped; CLI timeout → dropped.
- A slash command with an IP → dropped; without → passes.
- An `AssistantMessage` on `terminal` is revealed; the same on `mobile` is not.
- An unknown `rule-…` is marked.
- `Read` of the store path and `Bash` running `panos-mcp pseudonym table` → denied.
