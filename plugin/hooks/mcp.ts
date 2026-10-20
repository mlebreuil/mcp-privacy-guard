// MCP tool calls: the model reads only what the engine pseudonymized (FR-003, FR-007).
import type { EngineInterface, On } from 'claude-code'
import { EngineError, runEngine } from './engine'
import { blockedReason, connectedServers, onEngineExit3 } from './preconditions'
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

async function withhold($: EngineInterface, error: unknown): Promise<{ deny: string }> {
  if (error instanceof EngineError && error.exitCode === 3) onEngineExit3($)
  return { deny: WITHHELD }
}

export function registerMcp(on: On): void {
  on('tool.call', { tool: /^mcp__/ }, async ($, e, next) => {
    await currentSession($)
    const reason = blockedReason()
    if (reason !== null) return { deny: reason }
    const { server, name } = splitTool(String(e.tool), await connectedServers($))
    if (state.servers[server]?.exempt === true) return next(e)

    const ran = await next(e)
    if (ran.deny !== undefined) return ran
    try {
      const reply = await runEngine(
        $,
        ['result', '--session', state.sessionId ?? '', '--server', server, '--tool', name,
         '--since', String(state.reveal.rev)],
        { result: ran.result, is_error: ran.isError === true },
      )
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
