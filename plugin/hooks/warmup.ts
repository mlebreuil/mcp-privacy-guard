// The warm-up (FR-034, research R9): learn each server's names before questions are sent.
// The engine holds the state that gates questions; this only runs the calls and reports progress.
import type { EngineInterface } from 'claude-code'
import { EngineError, runEngine } from './engine'
import { connectedServers, setStatus, showActive } from './preconditions'
import { state, type ServerInfo } from './state'

const CALL_MS = 30_000
const SERVER_MS = 120_000
const FIX = "start a new conversation (/clear) to retry, fix the profile's warm-up, or exempt the server"
const REASON_TEXT: Record<string, string> = {
  timeout: 'it took too long',
  'tool-missing': 'a warm-up tool is missing',
  'tool-error': 'a warm-up tool failed',
  'learn-failed': 'its names could not be learned',
}

const normalise = (name: string) => name.replace(/[^A-Za-z0-9_-]/g, '_')

/** What the user reads when a question is held for, or blocked by, a warm-up; null otherwise. */
export function gateMessage(error: unknown): string | null {
  if (!(error instanceof EngineError)) return null
  const servers = Array.isArray(error.details.servers) ? (error.details.servers as string[]) : []
  if (error.code === 'warmup-pending') {
    return `privacy guard: loading names for ${servers.join(', ')}, try again in a moment`
  }
  if (error.code === 'warmup-failed') {
    const reason = typeof error.details.reason === 'string' ? error.details.reason : 'unknown'
    return `privacy guard: loading names for ${servers.join(', ')} failed (${reason}); ${FIX}`
  }
  return null
}

type Timed<T> = { ok: true; value: T } | { ok: false; reason: 'timeout' | 'error' }

/** Runs `work` for at most `ms` of the plugin's clock. */
async function within<T>($: EngineInterface, ms: number, work: Promise<T>): Promise<Timed<T>> {
  const stop = new AbortController()
  const settled = work.then(
    (value): Timed<T> => ({ ok: true, value }),
    (): Timed<T> => ({ ok: false, reason: 'error' }),
  )
  const late = $.clock.sleep(ms, { signal: stop.signal }).then(
    (): Timed<T> => ({ ok: false, reason: 'timeout' }),
    () => new Promise<Timed<T>>(() => {}), // aborted: the work finished first
  )
  const first = await Promise.race([settled, late])
  stop.abort()
  return first
}

function progress($: EngineInterface): void {
  setStatus($, `privacy-guard: loading names (${state.warmDone}/${state.warmTotal})`)
}

async function fail($: EngineInterface, id: string, alias: string, reason: string): Promise<void> {
  try {
    await runEngine($, ['warmup', '--session', id, '--server', alias, '--state', 'failed', '--reason', reason])
  } catch {
    // the engine keeps questions blocked while the state is not `complete`
  }
  const text = `privacy guard: loading names for ${alias} failed (${REASON_TEXT[reason] ?? reason}, ${reason}); ${FIX}`
  setStatus($, text)
  $.ui.toast(text)
}

async function isListed($: EngineInterface, alias: string, tool: string): Promise<boolean> {
  try {
    const name = `mcp__${normalise(alias)}__${tool}`
    return (await $.tool.list()).some(listed => listed.name === name)
  } catch {
    return true
  }
}

async function runServer($: EngineInterface, alias: string, info: ServerInfo): Promise<void> {
  const id = state.sessionId ?? ''
  const entries = info.warmup ?? []
  const started = await $.clock.now()
  try {
    await runEngine($, ['warmup', '--session', id, '--server', alias, '--state', 'running'])
  } catch {
    return fail($, id, alias, 'tool-error')
  }
  for (const entry of entries) {
    const left = SERVER_MS - ((await $.clock.now()) - started)
    if (left <= 0) return fail($, id, alias, 'timeout')
    const called = await within($, Math.min(CALL_MS, left), $.mcp.call(alias, entry.tool, entry.args))
    if (!called.ok && called.reason === 'timeout') return fail($, id, alias, 'timeout')
    if (!called.ok || called.value.isError) {
      // the host's tool list may leave MCP tools out, so it only names the reason of a failure
      return fail($, id, alias, (await isListed($, alias, entry.tool)) ? 'tool-error' : 'tool-missing')
    }
    try {
      await runEngine($, ['learn', '--session', id, '--server', alias, '--tool', entry.tool], {
        result: called.value,
      })
    } catch {
      return fail($, id, alias, 'learn-failed')
    }
  }
  state.warmDone += 1
  progress($)
  let reply
  try {
    reply = await runEngine($, ['warmup', '--session', id, '--server', alias, '--state', 'complete'])
  } catch {
    return fail($, id, alias, 'tool-error')
  }
  const pending = Array.isArray(reply.pending) ? reply.pending : []
  const failed = Array.isArray(reply.failed) ? reply.failed : []
  if (pending.length === 0 && failed.length === 0) {
    $.ui.toast('privacy guard: names loaded, questions accepted')
    showActive($)
  }
}

/** Starts, in the background, the warm-up of every protected server that has not completed it. */
export function startWarmups($: EngineInterface): void {
  for (const [alias, info] of Object.entries(state.servers)) {
    if (info.exempt || !info.warmup?.length || info.warmup_state === 'complete') continue
    if (state.warming.has(alias)) continue
    if (state.warming.size === 0) {
      state.warmDone = 0
      state.warmTotal = 0
    }
    state.warming.add(alias)
    state.warmTotal += 1
    progress($)
    void runServer($, alias, info)
      .catch(() => fail($, state.sessionId ?? '', alias, 'tool-error'))
      .finally(() => state.warming.delete(alias))
  }
}

/** A server that connected after the last listing is warmed up at the next hook. */
export async function refreshServers($: EngineInterface, force = false): Promise<void> {
  const listed = [...new Set(await connectedServers($))].sort().join(',')
  if (listed === state.connected && !force) return
  const id = state.sessionId ?? ''
  const reply = await runEngine($, ['status', '--session', id, '--servers', listed])
  state.connected = listed
  state.servers = (reply.servers ?? {}) as Record<string, ServerInfo>
  startWarmups($)
}
