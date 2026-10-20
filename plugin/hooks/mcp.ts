// MCP tool calls: the model reads only what the engine pseudonymized (FR-003, FR-007).
import type { EngineInterface, On } from 'claude-code'
import { EngineError, runEngine } from './engine'
import { blockedReason, connectedServers, onEngineExit3 } from './preconditions'
import { invalidateRows } from './reveal'
import { currentSession } from './session'
import { state, WITHHELD } from './state'

const COMPOSE_ID = 'privacy-guard'
const COMPOSE_TEXT =
  "Values from MCP tools and in the user's messages are pseudonymized stand-ins, not real " +
  'data (for example 10.83.4.12 or n-k3f7qa). You must not present them as real values or try ' +
  'to guess the real ones; use them exactly as given in tool calls. The user sees the real ' +
  'values on their own screen.'

const normalise = (name: string) => name.replace(/[^A-Za-z0-9_-]/g, '_')

/** The server alias (as /mcp lists it) and the tool name of `mcp__<server>__<tool>`. */
export function splitTool(tool: string, servers: readonly string[]): { server: string; name: string } {
  let best: { server: string; name: string } | null = null
  for (const server of servers) {
    const prefix = `mcp__${normalise(server)}__`
    if (tool.startsWith(prefix) && (best === null || server.length > best.server.length)) {
      best = { server, name: tool.slice(prefix.length) }
    }
  }
  if (best !== null) return best
  const match = /^mcp__(.+?)__(.+)$/.exec(tool)
  return match ? { server: match[1] ?? '', name: match[2] ?? '' } : { server: tool, name: tool }
}

function textOf(result: unknown): string {
  const content = (result as { content?: unknown } | null)?.content
  if (!Array.isArray(content)) return ''
  return content
    .map(block => (block as { type?: string; text?: unknown }))
    .filter(block => block.type === 'text' && typeof block.text === 'string')
    .map(block => block.text as string)
    .join('\n')
}

const RESERVED = new Set(['tool', 'tool_use_id', 'agentId', 'consent', 'requestMeta'])
const AMBIGUOUS =
  'privacy guard: an address in this call is ambiguous; ask the user to state it'
const NOT_CHECKED = 'privacy guard: the arguments could not be checked, so the tool did not run'

/** The tool's own arguments with every stand-in the engine knows turned back into its real value. */
async function translateArguments(
  $: EngineInterface,
  e: Record<string, unknown>,
  server: string,
  name: string,
): Promise<Record<string, unknown>> {
  const given = Object.fromEntries(Object.entries(e).filter(([key]) => !RESERVED.has(key)))
  const reply = await runEngine(
    $,
    ['args', '--session', state.sessionId ?? '', '--server', server, '--tool', name,
     '--since', String(state.reveal.rev)],
    { args: given },
  )
  const out = reply.args
  if (typeof out !== 'object' || out === null) throw new EngineError(5, 'bad-reply')
  return Object.fromEntries(
    Object.entries(out as Record<string, unknown>).filter(([key]) => !RESERVED.has(key)),
  )
}

async function withhold($: EngineInterface, error: unknown): Promise<{ deny: string }> {
  if (error instanceof EngineError && error.exitCode === 3) onEngineExit3($)
  return { deny: WITHHELD }
}

export function registerMcp(on: On): void {
  on('tool.call', { tool: /^mcp__/ }, async ($, e, next) => {
    await currentSession($)
    const reason = blockedReason()
    if (reason !== null) return { deny: reason }
    const before = state.reveal.rev
    const { server, name } = splitTool(String(e.tool), await connectedServers($))
    let rewritten: Record<string, unknown>
    try {
      rewritten = await translateArguments($, e as unknown as Record<string, unknown>, server, name)
    } catch (error) {
      if (error instanceof EngineError && error.exitCode === 3) onEngineExit3($)
      const ambiguous = error instanceof EngineError && error.code === 'ambiguous-address'
      return { deny: ambiguous ? AMBIGUOUS : NOT_CHECKED }
    }
    await invalidateRows($, before)
    const translated = { ...e, ...rewritten } as typeof e
    if (state.servers[server]?.exempt === true) return next(translated)

    const ran = await next(translated)
    if (ran.deny !== undefined) return ran
    try {
      const reply = await runEngine(
        $,
        ['result', '--session', state.sessionId ?? '', '--server', server, '--tool', name,
         '--since', String(state.reveal.rev)],
        { result: ran.result, is_error: ran.isError === true },
      )
      await invalidateRows($, before)
      if (ran.isError === true) {
        // a hook cannot return an errored result: the pseudonymized text goes out as a denial
        return { deny: textOf(reply.result) || WITHHELD }
      }
      const notices = Array.isArray(reply.notices) ? (reply.notices as string[]) : []
      return {
        result: reply.result as never,
        ...(notices.length > 0 ? { context: notices.map(n => `privacy guard: ${n}`) } : {}),
      }
    } catch (error) {
      return withhold($, error)
    }
  }).catch(() => ({ deny: WITHHELD }))

  on('prompt.compose', async ($, e, next) => {
    const composed = await next(e)
    return {
      sections: [
        ...composed.sections,
        { id: COMPOSE_ID, text: COMPOSE_TEXT, scope: 'session' as const },
      ],
    }
  })
}
