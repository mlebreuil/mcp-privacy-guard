// Shared by the plugin tests: a fake host and a fake engine CLI, registered beneath the plugin.
import type { On } from 'claude-code'

export const HOME = '/home/u/.config/mcp-privacy-guard'
export const SID = 's-1'
export const RECOGNISE = '\\b(n|text|h|d|u|g|dom|p)-[a-z2-7]{6,}\\b'

export const GOOD_SETTINGS = {
  sandbox: {
    enabled: true,
    allowUnsandboxedCommands: false,
    failIfUnavailable: true,
    filesystem: { denyRead: [HOME] },
  },
}

export type Call = { sub: string; argv: readonly string[]; stdin: unknown; timeoutMs?: number }
export type Reply = { exit?: number; out?: unknown; raw?: string; reject?: boolean }

export type Host = {
  sessionId: string
  /** Makes `$.session.id()` fail, as a hook's own dependency can. */
  idFails: boolean
  /** Makes `$.ui.toast` fail, which a hook only reaches after `next`. */
  toastFails: boolean
  surfaces: string[]
  version: string
  turns: number | 'throw'
  settings: Record<string, unknown>
  servers: Record<string, { exempt: boolean }>
  connected: string[]
  live: Set<string>
  /** Overrides the default reply of one engine subcommand. */
  engine: Record<string, (call: Call) => Reply>
  calls: Call[]
  statuses: (string | undefined)[]
  toasts: string[]
  /** The last status line shown, or undefined. */
  status: () => string | undefined
  called: (sub: string) => Call[]
  /** What the (fake) MCP tool returns; set `isError` for an errored call. */
  mcpResult: () => { result: unknown; isError?: true }
  /** How many times a tool actually ran beneath the plugin. */
  toolRuns: number
  /** The input each tool call reached the tool with, after the plugin's rewrites. */
  toolInputs: Record<string, unknown>[]
  /** The plugin's own folder, as the engine reports it when the plugin loads. */
  pluginRoot: string
  /** The texts that reached the model's prompt, after the plugin's rewrites. */
  submitted: string[]
  /** Warm-up lists the fake engine reports per server, and the state it keeps. */
  warmups: Record<string, { tool: string; args: Record<string, unknown> }[]>
  warm: Record<string, string>
  /** Tools the model can call (`mcp__<server>__<tool>`). */
  toolNames: string[]
  /** `$.mcp.call` as seen by the (fake) MCP servers, and how it answers. */
  mcpCalls: { server: string; tool: string; args: unknown }[]
  mcpAnswer: (server: string, tool: string) => unknown
  /** How long (milliseconds on the mock clock) `$.mcp.call` takes. */
  mcpDelayMs: number
  clock?: { sleep: (ms: number) => Promise<void> }
  /** What `command.run` and `skill.prompt` received beneath the plugin. */
  commandArgs: string[]
  skillTexts: string[]
}

export function fakeHost(on: On, init: Partial<Host> = {}): Host {
  const h: Host = {
    sessionId: SID,
    idFails: false,
    toastFails: false,
    surfaces: ['terminal'],
    version: '2.1.303',
    turns: 0,
    settings: GOOD_SETTINGS,
    servers: { generic: { exempt: false } },
    connected: ['generic'],
    live: new Set(),
    engine: {},
    calls: [],
    statuses: [],
    toasts: [],
    status: () => h.statuses.at(-1),
    called: sub => h.calls.filter(c => c.sub === sub),
    pluginRoot: '',
    toolRuns: 0,
    toolInputs: [],
    submitted: [],
    warmups: {},
    warm: {},
    toolNames: [],
    mcpCalls: [],
    mcpAnswer: () => ({ content: [{ type: 'text', text: '{}' }], isError: false }),
    mcpDelayMs: 0,
    commandArgs: [],
    skillTexts: [],
    mcpResult: () => ({
      result: { content: [{ type: 'text', text: 'REAL 10.1.2.15' }], isError: false },
    }),
    ...init,
  }

  const defaults = (call: Call): Reply => {
    const sid = call.argv[call.argv.indexOf('--session') + 1]
    switch (call.sub) {
      case 'status':
        return {
          out: {
            engine: '1.0.0',
            home: HOME,
            store: 'ready',
            session: sid && h.live.has(sid) ? 'live' : 'none',
            rev: 0,
            swept: 0,
            servers: Object.fromEntries(
              Object.entries(h.servers).map(([alias, s]) => [
                alias,
                {
                  profile: 'default',
                  profile_state: 'valid',
                  exempt: s.exempt,
                  ...(h.warmups[alias]
                    ? { warmup: h.warmups[alias], warmup_state: h.warm[alias] ?? 'not-started' }
                    : {}),
                },
              ]),
            ),
            recognise: RECOGNISE,
            kinds: ['IP'],
            keep_entries: 0,
            hide_entries: 0,
          },
        }
      case 'begin':
        if (sid) h.live.add(sid)
        for (const alias of Object.keys(h.warmups)) h.warm[alias] ??= 'not-started'
        return { out: { session: 'live', swept: 0, warmup: Object.keys(h.warmups) } }
      case 'end':
        if (sid) h.live.delete(sid)
        return { out: { deleted: true, swept: 0 } }
      case 'prompt': {
        const text = (call.stdin as { text: string }).text
        if (call.argv.includes('--command')) return { out: { identifying: true } }
        const swapped = text.split('10.1.2.15').join('10.83.4.12')
        const n = text.split('10.1.2.15').length - 1
        return {
          out: {
            text: swapped,
            replacements: Array.from({ length: n }, () => ({ kind: 'IP' })),
            warnings: [],
            table: { rev: 0, entries: [] },
          },
        }
      }
      case 'warmup': {
        const server = call.argv[call.argv.indexOf('--server') + 1] ?? ''
        h.warm[server] = call.argv[call.argv.indexOf('--state') + 1] ?? ''
        const pending = Object.keys(h.warm).filter(k => ['not-started', 'running'].includes(h.warm[k] ?? ''))
        const failed = Object.keys(h.warm).filter(k => h.warm[k] === 'failed')
        return { out: { pending, failed } }
      }
      case 'learn':
        return { out: { names: 3 } }
      case 'args': {
        const given = (call.stdin as { args: Record<string, unknown> }).args
        const swapped = Object.fromEntries(
          Object.entries(given).map(([k, v]) => [k, v === 'n-abcdef' ? 'REAL-NAME' : v]),
        )
        return { out: { args: swapped, translated: 1, table: { rev: 0, entries: [] } } }
      }
      case 'result':
        return {
          out: {
            result: { content: [{ type: 'text', text: 'PSEUDONYMIZED' }], isError: false },
            withheld: 0,
            notices: [],
            table: { rev: 0, entries: [] },
          },
        }
      case 'table':
        return { out: { table: { rev: 0, entries: [] } } }
      default:
        return { out: {} }
    }
  }

  on('process.run', (_$, e) => {
    const argv = e.argv
    const call: Call = {
      sub: argv[1] ?? '',
      argv,
      stdin: e.init?.stdin === undefined ? undefined : JSON.parse(e.init.stdin),
      timeoutMs: e.init?.timeoutMs,
    }
    h.calls.push(call)
    const reply = (h.engine[call.sub] ?? defaults)(call)
    if (reply.reject) return { deny: 'engine did not start' }
    return {
      value: {
        exitCode: reply.exit ?? 0,
        stdout: reply.raw ?? JSON.stringify(reply.out ?? {}),
        stderr: '',
        isStdoutTruncated: false,
        isStderrTruncated: false,
      },
    }
  })
  on('plugin.register', (_$, e) => {
    if (e.name === 'mcp-privacy-guard') h.pluginRoot = e.root
    return { allow: true }
  })
  on('session.start', (_$, e) => ({ cwd: e.cwd }))
  on('session.end', (_$, e) => ({ sessionId: e.sessionId }))
  on('tool.call', (_$, e) => {
    h.toolRuns += 1
    h.toolInputs.push({ ...(e as unknown as Record<string, unknown>) })
    if (!String(e.tool).startsWith('mcp__')) return { result: {}, text: 'ran', ref: 1 } as never
    return { ...h.mcpResult(), text: 'ran', ref: 1 } as never
  })
  on('prompt.compose', () => ({ sections: [] }))
  on('prompt.submit', (_$, e) => {
    h.submitted.push(e.text)
    return { text: e.text }
  })
  on('command.run', (_$, e) => {
    h.commandArgs.push(e.args)
    return { text: 'ran' }
  })
  on('skill.prompt', (_$, e) => {
    h.skillTexts.push(e.text)
    return { text: e.text }
  })
  on('tool.list', () => ({
    value: h.toolNames.map(name => ({ name, description: '', mcp: true })),
  }))
  on('mcp.call', async (_$, e) => {
    h.mcpCalls.push({ server: e.server, tool: e.tool, args: e.args })
    if (h.mcpDelayMs > 0) await h.clock?.sleep(h.mcpDelayMs)
    const answer = h.mcpAnswer(e.server, e.tool)
    return answer === 'throw' ? { deny: 'no such tool' } : { value: answer as never }
  })
  on('session.id', () => (h.idFails ? { deny: 'session id unavailable' } : { value: h.sessionId }))
  on('env.get', (_$, e) => ({ value: e.name === 'HOME' ? '/home/u' : undefined }))
  on('session.surfaces', () => ({ value: h.surfaces as never }))
  on('session.version', () => ({ value: { version: h.version, base: h.version } }))
  on('session.turns', () =>
    h.turns === 'throw' ? { deny: 'turns unavailable' } : { value: h.turns },
  )
  on('settings.read', () => ({ value: h.settings }))
  on('session.usage', () => ({
    value: {
      startedAt: 0,
      context: {
        window: 1,
        breakdown: {
          mcpTools: h.connected.map(serverName => ({
            name: `mcp__${serverName}__list`,
            serverName,
            tokens: 1,
            isLoaded: true,
          })),
        },
      },
      rateLimits: [],
    } as never,
  }))
  on('ui.status', (_$, e) => {
    h.statuses.push(e.text)
    return { value: undefined }
  })
  on('ui.toast', (_$, e) => {
    if (h.toastFails) return { deny: 'toast failed' }
    h.toasts.push(e.text)
    return { value: undefined }
  })
  return h
}

export const SESSION_START = { cwd: '/proj', surface: 'terminal', isInteractive: true } as const
