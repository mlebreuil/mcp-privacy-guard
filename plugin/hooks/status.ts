// What the user can see of the guard: a toast per session and the /privacy-guard command (FR-029).
// Aliases and profile names are not sensitive (the model sees the aliases in tool names); no
// value of the store is ever printed here.
import type { EngineInterface, On } from 'claude-code'
import { blockedReason } from './preconditions'
import { state, type ServerInfo } from './state'
import { refreshServers } from './warmup'

const COMMAND = 'privacy-guard'
const SHOWN = 4

function label(info: ServerInfo): string {
  if (info.exempt) return 'exempt'
  return info.profile_state === 'invalid' ? `${info.profile} (invalid)` : info.profile
}

/** One line per session start: each server with its profile or `exempt`, cut when long. */
export async function showOverview($: EngineInterface): Promise<void> {
  const entries = Object.entries(state.servers)
  if (entries.length === 0) {
    await $.ui.toast('privacy guard active · no MCP servers yet')
    return
  }
  const shown = entries.slice(0, SHOWN).map(([alias, info]) => `${alias}: ${label(info)}`)
  const more = entries.length > SHOWN ? ' · … /privacy-guard for all' : ''
  await $.ui.toast(`privacy guard active · ${shown.join(' · ')}${more}`)
}

function serverLine(alias: string, info: ServerInfo): string {
  const profileState =
    info.profile_state === 'invalid' ? `invalid: ${info.profile_reason ?? 'unknown'}` : 'valid'
  const parts = [
    `profile ${info.profile} (${profileState})`,
    info.exempt ? 'exempt' : 'protected',
  ]
  if (!info.exempt && info.warmup !== undefined) {
    parts.push(`warm-up ${info.warmup_state ?? 'not-started'}`)
  }
  return `  ${alias}: ${parts.join(' · ')}`
}

export async function describe($: EngineInterface): Promise<string> {
  const reason = blockedReason()
  if (reason === null) {
    try {
      await refreshServers($)
    } catch {
      // the last known list is shown
    }
  }
  const head = reason ?? 'privacy guard: active'
  const lines = Object.entries(state.servers).map(([alias, info]) => serverLine(alias, info))
  return [head, ...(lines.length > 0 ? ['servers:', ...lines] : ['no MCP servers connected'])].join('\n')
}

/** Called from the `session.start` hook (a second one without a matcher is not allowed). */
export async function registerStatusCommand($: EngineInterface): Promise<void> {
  try {
    await $.command.register({
      name: COMMAND,
      description: 'Show the privacy guard state and what protects each MCP server',
    })
  } catch {
    // the guard works without its status command
  }
}

export function registerStatus(on: On): void {
  on('command.run', { command: COMMAND }, async ($, e) => ({ text: await describe($) })).catch(
    () => ({ text: 'privacy guard: status unavailable' }),
  )
}
