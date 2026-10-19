# Contract: Claude Code Plugin (`mcp-privacy-guard`)

A Claude Code plugin in `plugin/` (research R1). It is a thin shim: every classification,
cryptographic and mapping decision is made by the [engine CLI](./engine-cli.md). The only
logic it holds is applying the engine's reveal table to rows drawn on the terminal (see
plan, Complexity Tracking).

**Files**: `plugin/.claude-plugin/plugin.json`, `plugin/hooks/hooks.json`,
`plugin/hooks/register.ts`, `plugin/hooks/*.test.ts`.
**Install**: `/plugin install mcp-privacy-guard --marketplace <owner>/mcp-privacy-guard`, or
`claude --plugin-dir plugin` for development.
**User option**: `enginePath` (default `mcp-privacy-guard`). There is no option that disables
anything.
**Minimum Claude Code version**: 2.1.301, declared in the manifest and checked at
`session.start`. An older build blocks every question and withholds every protected result.

## Preconditions (block reason)

Checked at `session.start` and again at the start of each guard hook. If any fails, the
plugin sets a block reason. Every question is dropped and every protected result is withheld
with that reason and its fix, and the status line shows it.

1. Host version ≥ 2.1.301.
2. `$.session.surfaces()` lists `terminal` (FR-031). The VS Code extension, the desktop app and
   `-p` runs are refused: "privacy guard: use Claude Code in a terminal".
3. `$.settings.read()` shows the sandbox enabled, `<home>` in its read-deny list, and
   unsandboxed commands not allowed (FR-026). The message gives the settings to add.
4. `status` succeeds and reports `store: ready` (or `absent`, created on first use).

## Engine calls

All go through `$.process.run([enginePath, …], { stdin, timeoutMs })`. Timeouts: `prompt`
5 s, `args` 5 s, `result` 15 s, `status`/`table`/`learn`/`observe` 30 s. A non-zero exit, a
timeout, or unparseable output is a failure.

## Hooks

Every hook marked † is registered with
`.catch(($, e, next) => <refuse>)`, which never calls the engine.

| Event | Matcher | Behaviour | Spec |
|---|---|---|---|
| `session.start` | — | Check the host version. Run `status --servers <connected aliases>` and keep the server map and recognition pattern. Run `table --since 0`. Set the status line to `privacy-guard: active · n protected · m exempt` (or the blocking reason). For each server with `warmup` not `complete`, run its warm-up in the background: `$.mcp.call` → `learn`. | FR-029, R9 |
| `prompt.compose` | — | Append a `session`-scope section: values from MCP tools and in user messages are pseudonymized stand-ins; do not present them as real or try to guess the real ones; use them as given in tool calls. | FR-029 |
| `prompt.submit` † | — | Block reason set: `{ drop: <reason> }`. `e.attachments` present: `{ drop: "…paste the text instead" }` (FR-032). `e.command` set: `prompt --command`. If `identifying`, `{ drop: "…ask as a plain question" }`. Otherwise run `prompt` and `next({ ...e, text })`. Merge the table. Toast `n value(s) replaced` when n > 0. Failure: `{ drop: <reason + fix> }`. `.catch`: `{ drop }` if `!next.called`. | FR-017–FR-020 |
| `tool.call` † | `mcp__*` | Block reason set and server protected: `{ deny: <reason> }` (the tool does not run). Exempt server: `args`, then `next({ ...e, ...args })`, return as is. Protected: `args` → `await next(…)` → `result` → return `{ result, context }`, where `context` notes withheld non-text items. Failure at any step after `next`: `{ deny: "result withheld by privacy guard" }`. Failure before `next`: `{ deny: … }` (the tool does not run). `.catch`: `{ deny }`. Merge the table, then `$.ui.invalidate` rows. | FR-002–FR-012 |
| `tool.call` † | `Bash`, `Read`, `Grep`, `Glob`, `Edit`, `Write`, `NotebookEdit`, `WebFetch`, and any tool with a path argument | `{ deny }` when the input names `<home>`, the engine command, or the plugin folder, or when a `Bash` call sets `dangerouslyDisableSandbox: true`. Otherwise `next(e)`. `.catch`: `{ deny }`. | FR-026, R11 |
| `turn.complete` | — | `observe` the final assistant text. Merge the table and invalidate rows. Failure: ignored (it only affects display). | R10 |
| `session.attach` | `surface: 'terminal'` | Set reveal allowed = false for the session, `$.ui.toast` that reveal is off. | R1 |
| `ui.render` | `AssistantMessage`, `ToolUse`, `ToolResult`, `UserMessage` | Only when `e.surface === 'terminal'` and reveal is allowed: longest-match replace of known stand-ins in `text` / props, highlighted; unknown name-shaped stand-ins get a dim `(?)`. `UserMessage` also underlines the values replaced in the question. Otherwise `next(e)`. A throw draws the engine's row, which shows stand-ins (safe). | FR-021–FR-023 |

## Guarantees

- The model never receives revealed text. Render rewrites change the drawing only. The
  plugin never adds model-visible content (prompt text, `context`, `prompt.compose` section)
  that contains a real value.
- The reveal table lives in module memory only.
- No reveal on `desktop`, `vscode` or `mobile`, nor after a client claimed `terminal`.
- Any failure of a guard hook blocks or withholds. It never passes data through.
- No setting disables the guard (FR-027).

## Tests (`claude plugin test`)

- A protected MCP result is replaced by the engine's result. An engine exit of 3 or 5, a
  timeout, invalid JSON, or a throw in the hook → `{ deny }`.
- An exempt server's result is returned unchanged, and its arguments are still translated.
- A question with an IP is rewritten. Engine failure or a throw → dropped.
- A slash command with an identifying value → dropped; without → passes.
- A question with an attachment → dropped.
- A session whose surfaces do not include `terminal` → questions dropped, MCP calls denied.
- Settings without the sandbox, without `<home>` in its read-deny list, or allowing
  unsandboxed commands → questions dropped, MCP calls denied.
- `Bash` with `dangerouslyDisableSandbox: true` → denied.
- `AssistantMessage` on `terminal` is revealed. On `desktop`, `vscode` and `mobile` it is not.
  After `session.attach { surface: 'terminal' }` it is not.
- An unknown `n-zzzz9q` is marked.
- `Read` of `<home>/store/mapping.sqlite`, and `Bash` running `mcp-privacy-guard table`, are
  denied.
- `prompt.compose` adds the stand-in section.
