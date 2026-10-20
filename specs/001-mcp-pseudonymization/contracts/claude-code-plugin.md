# Contract: Claude Code Plugin (`mcp-privacy-guard`)

A Claude Code plugin in `plugin/` (research R1). It is a thin shim: every classification,
cryptographic and mapping decision is made by the [engine CLI](./engine-cli.md). The only
logic it holds is applying the engine's reveal table to rows drawn on the terminal (see
plan, Complexity Tracking).

**Files**: `plugin/.claude-plugin/plugin.json`, `plugin/hooks/hooks.json`,
`plugin/hooks/register.ts` (registrations), one module per concern (`engine.ts`,
`preconditions.ts`, `session.ts`, `guard.ts`, `mcp.ts`, `prompt.ts`, `warmup.ts`, `reveal.ts`,
`status.ts`), and `plugin/hooks/*.test.ts` (plan, Project Structure).
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
4. `status --session <id>` succeeds and reports `store: ready`.
5. The session is live (research R13, R14):
   - `session: "live"` → continue (also after a plugin reload within the session);
   - `session: "none"` and `$.session.turns()` = 0 → run `begin --session <id> --servers
     <configured aliases>` (connected or still connecting, R9);
   - `session: "none"` and `turns()` > 0, or `turns()` fails → resumed conversation
     (FR-033): "privacy guard: this conversation is from an ended session; start a new one
     (/clear)";
   - an engine exit 3 later in the session (folder swept) → "privacy guard: session
     expired; start a new conversation (/clear)".

## Session id

Every engine call that touches a session passes `--session <$.session.id()>`. The plugin
reads the id at the start of every hook. After `/clear` the id changes with no
`session.start`. On a change the plugin empties the reveal table, resets `rev` to 0, and
re-runs the preconditions, which run `begin` for the new id (research R13).

## Engine calls

All go through `$.process.run([enginePath, …], { stdin, timeoutMs })`. Timeouts: `prompt`
5 s, `args` 5 s, `result` 15 s, `end` 1 s, `status`/`table`/`learn`/`observe` 30 s. A non-zero exit, a
timeout, or unparseable output is a failure.

## Hooks

Every hook marked † is registered with
`.catch(($, e, next) => <refuse>)`, which never calls the engine.

| Event | Matcher | Behaviour | Spec |
|---|---|---|---|
| `session.start` | — | Check the host version. Run `status --servers <configured aliases> --session <id>`, then precondition 5 (`begin` for a new session), and keep the server map and recognition pattern. Run `table --session <id> --since 0` (empty for a new session; the full table after a plugin reload). Set the status line to `privacy-guard: active · n protected · m exempt` (or the blocking reason), show the per-server toast (each server with its profile or `exempt`, invalid profiles flagged), and register the `/privacy-guard` command (research R16). For each server that `begin` (or `status`) lists with `warmup_state` not `complete`, run its warm-up in the background: `warmup --state running`, then for each warm-up tool `$.mcp.call` (30 s) → `learn`, then `warmup --state complete`, or `failed` with a reason code (`timeout` past 30 s per call or 120 s per server, `tool-missing`, `tool-error`, `learn-failed`, or `not-connected` when a configured server has not connected within 30 s). Status line `privacy-guard: loading names (k/n)` meanwhile. When `warmup` reports no pending server: toast "privacy guard: names loaded, questions accepted" and the normal status line. On `failed`: status line and toast with the reason and the fix (`/clear` to retry; fix the profile or exempt the server). Warm-up runs in every new session (R13). A server first seen mid-session gets the same treatment. | FR-029, FR-034, R9 |
| `session.end` | — | Run `end --session <e.sessionId>` within `next.budget`, then `next(e)`. Empty the reveal table. Failure or timeout: ignored here; the folder is swept later (R13). Never blocks the exit. | FR-008, FR-025, R13 |
| `command.run` | `privacy-guard` | Return `{ text }`: guard state or block reason, and for each server its profile, profile state, exemption and warm-up state, from the last `status`. No store value. | FR-029, R16 |
| `command.run` † | every command except `privacy-guard` | Block reason set: refuse the run. Otherwise run `prompt` on `e.args` and `next({ ...e, args })`; failure, timeout or `identifying` that cannot be rewritten: refuse. Merge the table. `.catch`: refuse. To be confirmed by task T103 (R1, "Slash commands and skills"). | FR-017, FR-019, R1 |
| `skill.prompt` † | — | Block reason set: refuse. Otherwise run `prompt` on `e.text` and return `{ text }`. Failure: refuse. `.catch`: refuse. To be confirmed by task T103. | FR-017, FR-019, R1 |
| `prompt.compose` | — | Append a `session`-scope section: values from MCP tools and in user messages are pseudonymized stand-ins; do not present them as real or try to guess the real ones; use them as given in tool calls. | FR-029 |
| `prompt.submit` † | — | Block reason set: `{ drop: <reason> }`. `e.attachments` present: `{ drop: "…paste the text instead" }` (FR-032). `e.command` set: `prompt --command`. If `identifying`, `{ drop: "…ask as a plain question" }`. Otherwise run `prompt` and `next({ ...e, text })`. Engine exit 4 `warmup-pending`: `{ drop: "privacy guard: loading names for <servers>, try again in a moment" }`. Exit 4 `warmup-failed`: `{ drop: <reason + fix> }` (FR-034). The same applies to `prompt --command`. Merge the table. Toast `n value(s) replaced` when n > 0. Failure: `{ drop: <reason + fix> }`. `.catch`: `{ drop }` if `!next.called`. | FR-017–FR-020 |
| `tool.call` † | `mcp__*` | Block reason set and server protected: `{ deny: <reason> }` (the tool does not run). Exempt server: `args`, then `next({ ...e, ...args })`, then `result --exempt` (records its IP forms as fixed; failure ignored), and return the result as is (R15). `args` exit 4 `ambiguous-address` (any server): `{ deny: "privacy guard: an address in this call is ambiguous; ask the user to state it" }`. Protected: `args` → `await next(…)` → `result` → return `{ result, context }`, where `context` notes withheld non-text items. Failure at any step after `next`: `{ deny: "result withheld by privacy guard" }`. Failure before `next`: `{ deny: … }` (the tool does not run). `.catch`: `{ deny }`. Merge the table, then `$.ui.invalidate` rows. | FR-002–FR-012 |
| `tool.call` † | `Bash`, `Read`, `Grep`, `Glob`, `Edit`, `Write`, `NotebookEdit`, `WebFetch`, and any tool with a path argument | `{ deny }` when the input names `<home>`, the engine command, or the plugin folder; when it writes Claude Code settings or plugin state (`~/.claude/settings*.json`, `<project>/.claude/settings*.json`, `~/.claude/plugins/`, `~/.claude.json`); or when a `Bash` call sets `dangerouslyDisableSandbox: true` (R11). Otherwise `next(e)`. `.catch`: `{ deny }`. | FR-026, R11 |
| `turn.complete` | — | `observe` the final assistant text. Merge the table and invalidate rows. Failure: ignored (it only affects display). | R10 |
| `session.attach` | `surface: 'terminal'` | Set reveal allowed = false for the session, `$.ui.toast` that reveal is off. | R1 |
| `ui.render` | `AssistantMessage`, `ToolUse`, `ToolResult`, `UserMessage` | Only when `e.surface === 'terminal'` and reveal is allowed: longest-match replace of known stand-ins in `text` / props, highlighted; unknown name-shaped stand-ins get a dim `(?)`. `UserMessage` also underlines the values replaced in the question. Otherwise `next(e)`. A throw draws the engine's row, which shows stand-ins (safe). | FR-021–FR-023 |

## Guarantees

- The model never receives revealed text. Render rewrites change the drawing only. The
  plugin never adds model-visible content (prompt text, `context`, `prompt.compose` section)
  that contains a real value.
- The reveal table lives in module memory only, for the current session id.
- The session's secret and mapping are deleted at `session.end`, or swept within 24 hours if
  the session ended without it. No stand-in is ever revealed or translated outside the
  session that issued it.
- No reveal on `desktop`, `vscode` or `mobile`, nor after a client claimed `terminal`.
- Any failure of a guard hook blocks or withholds. It never passes data through.
- No setting disables the guard (FR-027).

## Tests (`claude plugin test`)

- A protected MCP result is replaced by the engine's result. An engine exit of 3 or 5, a
  timeout, invalid JSON, or a throw in the hook → `{ deny }`.
- An exempt server's result is returned unchanged, and its arguments are still translated.
- A question with an IP is rewritten. Engine failure or a throw → dropped.
- A slash command with an identifying value in its arguments → the arguments are rewritten at
  `command.run` (T104); one that cannot be checked → refused; without → passes.
- A question with an attachment → dropped.
- A session whose surfaces do not include `terminal` → questions dropped, MCP calls denied.
- Settings without the sandbox, without `<home>` in its read-deny list, or allowing
  unsandboxed commands → questions dropped, MCP calls denied.
- `Bash` with `dangerouslyDisableSandbox: true` → denied.
- `AssistantMessage` on `terminal` is revealed. On `desktop`, `vscode` and `mobile` it is not.
  After `session.attach { surface: 'terminal' }` it is not.
- An unknown `n-zzzzzzzz7q` is marked.
- Session start shows the per-server toast, and `/privacy-guard` lists every server with its
  profile, exemption and warm-up state.
- `Edit` of `.claude/settings.json` and `Bash` writing `~/.claude/settings.json` are denied.
- An exempt server's result is passed to `result --exempt`. `args` exit 4
  `ambiguous-address` → `{ deny }` before the tool runs.
- Reveal benchmark: a 4 KB row with a 100k-entry table is drawn in at most 4 ms (R10).
- `Read` of `<home>/store/sessions/<id>/mapping.sqlite` or `…/secret.key`, and `Bash` running `mcp-privacy-guard table`, are
  denied.
- `prompt.compose` adds the stand-in section.
- `session.end` calls `end` with the ending session id. A failing or slow `end` does not
  delay the exit past the budget.
- A changed `$.session.id()` (after `/clear`) empties the reveal table and runs `begin` for
  the new id, and the next engine call uses it.
- `session.start` with `session: "live"` (plugin reload) does not call `begin`.
- A question while a warm-up is pending → dropped with "loading names"; after the last
  warm-up completes → a toast, and questions pass. A warm-up call that times out or errors
  → `warmup --state failed`, and questions stay dropped with the reason (FR-034).
- A slash command while a warm-up is pending → dropped.
- `session: "none"` with `turns()` > 0, or a failing `turns()` → questions dropped, MCP calls
  denied, with the `/clear` hint (FR-033).
- An engine exit 3 mid-session → questions dropped, MCP calls denied, "session expired".
