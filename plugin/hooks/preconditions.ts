// What must hold before the guard may touch a question or a result (contracts/claude-code-plugin.md).
import type { EngineInterface } from 'claude-code'
import { runEngine, EngineError, type Reply } from './engine'
import { state, type ServerInfo } from './state'

export const MIN_VERSION: readonly [number, number, number] = [2, 1, 303]
export const MIN_VERSION_TEXT = MIN_VERSION.join('.')

export const REASON = {
  terminal: 'privacy guard: use Claude Code in a terminal',
  resumed:
    'privacy guard: this conversation is from an ended session; start a new one (/clear)',
  expired: 'privacy guard: session expired; start a new conversation (/clear)',
  store: 'privacy guard: the session store is unusable; start a new conversation (/clear)',
}

let inflight: Promise<string | null> | null = null

function isOldVersion(version: string): boolean | null {
  const match = /^(\d+)\.(\d+)\.(\d+)/.exec(version)
  if (match === null) return null
  const found = [Number(match[1]), Number(match[2]), Number(match[3])]
  for (let i = 0; i < 3; i++) {
    if ((found[i] ?? 0) !== MIN_VERSION[i]) return (found[i] ?? 0) < (MIN_VERSION[i] ?? 0)
  }
  return false
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {}
}

function covers(entry: unknown, home: string, userHome: string): boolean {
  if (typeof entry !== 'string' || home === '') return false
  const expanded = entry.startsWith('~') && userHome !== '' ? userHome + entry.slice(1) : entry
  const trimmed = expanded.replace(/\/+$/, '')
  return home === trimmed || home.startsWith(`${trimmed}/`)
}

/** The sandbox settings the guard needs and does not find (research R11, FR-026). */
export function sandboxProblems(settings: unknown, home: string, userHome: string): string[] {
  const sandbox = asRecord(asRecord(settings).sandbox)
  const filesystem = asRecord(sandbox.filesystem)
  const problems: string[] = []
  const list = (value: unknown): unknown[] => (Array.isArray(value) ? value : [])
  if (sandbox.enabled !== true) problems.push('sandbox.enabled = true')
  if (!list(filesystem.denyRead).some(entry => covers(entry, home, userHome))) {
    problems.push(`sandbox.filesystem.denyRead += ["${home}"]`)
  }
  if (sandbox.allowUnsandboxedCommands !== false) {
    problems.push('sandbox.allowUnsandboxedCommands = false')
  }
  if (sandbox.failIfUnavailable !== true) problems.push('sandbox.failIfUnavailable = true')
  if (filesystem.disabled === true) problems.push('sandbox.filesystem.disabled = false')
  if (list(filesystem.allowRead).some(entry => covers(entry, home, userHome))) {
    problems.push('sandbox.filesystem.allowRead: remove the entry that covers the guard folder')
  }
  if (
    list(sandbox.excludedCommands).some(
      entry => typeof entry === 'string' && /mcp[-_]privacy[-_]guard/.test(entry),
    )
  ) {
    problems.push('sandbox.excludedCommands: remove the entry that names the guard')
  }
  return problems
}

async function connectedServers($: EngineInterface): Promise<string[]> {
  const usage = await $.session.usage({ breakdown: 'summary' })
  const tools = usage.context.breakdown?.mcpTools ?? []
  return [...new Set(tools.map(tool => tool.serverName))]
}

function countLine(servers: Record<string, ServerInfo>): string {
  const all = Object.values(servers)
  const exempt = all.filter(s => s.exempt).length
  return `privacy-guard: active · ${all.length - exempt} protected · ${exempt} exempt`
}

function show($: EngineInterface, reason: string | null): void {
  state.blockReason = reason
  state.ready = reason === null
  $.ui.status(reason ?? countLine(state.servers))
}

async function run($: EngineInterface): Promise<string | null> {
  const id = await $.session.id()
  const version = (await $.session.version()).version
  const old = isOldVersion(version)
  if (old === null || old) {
    return `privacy guard: Claude Code ${MIN_VERSION_TEXT} or newer is required`
  }
  if (!(await $.session.surfaces()).includes('terminal')) return REASON.terminal

  let servers: string[]
  try {
    servers = await connectedServers($)
  } catch {
    return 'privacy guard: cannot list the MCP servers; restart Claude Code'
  }
  const list = servers.join(',')
  let status: Reply
  try {
    status = await runEngine($, ['status', '--session', id, '--servers', list])
  } catch {
    return 'privacy guard: the engine is unavailable; install it or set the engine option'
  }
  state.home = typeof status.home === 'string' ? status.home : ''
  state.recognise = typeof status.recognise === 'string' ? status.recognise : ''
  state.servers = (asRecord(status.servers) as Record<string, ServerInfo>) ?? {}
  if (state.home === '') return 'privacy guard: the engine did not report its folder'
  if (status.store !== 'ready') return REASON.store

  const userHome = (await $.env.get('HOME')) ?? ''
  const problems = sandboxProblems(await $.settings.read(), state.home, userHome)
  if (problems.length > 0) {
    return `privacy guard: turn on Claude Code's sandbox and protect the guard folder: ${problems.join('; ')}`
  }

  switch (status.session) {
    case 'live':
      return null
    case 'none': {
      let turns: number
      try {
        turns = await $.session.turns()
      } catch {
        return REASON.resumed
      }
      if (turns > 0) return REASON.resumed
      try {
        await runEngine($, ['begin', '--session', id, '--servers', list])
      } catch (error) {
        return error instanceof EngineError && error.exitCode === 4
          ? null // a reload raced us: the session is live
          : REASON.store
      }
      return null
    }
    default:
      return REASON.store
  }
}

/**
 * Runs every precondition and shows the result in the status line. Never throws: a check that
 * cannot be made is a reason to block. Concurrent callers share one run.
 */
export function checkPreconditions($: EngineInterface): Promise<string | null> {
  inflight ??= (async () => {
    let reason: string | null
    try {
      reason = await run($)
    } catch {
      reason = 'privacy guard: the startup checks failed; restart Claude Code'
    }
    show($, reason)
    return reason
  })().finally(() => {
    inflight = null
  })
  return inflight
}

/** Why a question or protected result must not go through now, or null when the guard is active. */
export function blockedReason(): string | null {
  return state.blockReason ?? (state.ready ? null : 'privacy guard: not started; restart Claude Code')
}

/** An engine reply of exit 3 later in the session: the folder was swept or deleted. */
export function onEngineExit3($: EngineInterface): void {
  show($, REASON.expired)
}
