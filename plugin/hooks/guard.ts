// Keeps the model's own tools away from the secret, the mapping, the engine and Claude Code's
// settings (research R11, FR-026). Best effort: spellings vary, the sandbox is the other layer.
import type { EngineInterface, On } from 'claude-code'
import { currentSession } from './session'
import { state } from './state'

const REFUSED = 'privacy guard: refused, this would expose or change the guard'
const ENGINE = /mcp[-_]privacy[-_]guard/i
const SETTINGS = /\.claude\/settings(?:\.local)?\.json|\.claude\.json|\.claude\/plugins\//i
const WRITERS = new Set(['Edit', 'Write', 'NotebookEdit', 'MultiEdit'])

function strings(value: unknown, out: string[] = []): string[] {
  if (typeof value === 'string') out.push(value)
  else if (Array.isArray(value)) for (const item of value) strings(item, out)
  else if (typeof value === 'object' && value !== null) {
    for (const item of Object.values(value)) strings(item, out)
  }
  return out
}

function homeForms(home: string, userHome: string): string[] {
  if (home === '') return []
  const forms = [home]
  if (userHome !== '' && home.startsWith(userHome)) {
    const rest = home.slice(userHome.length)
    forms.push(`~${rest}`, `$HOME${rest}`, `\${HOME}${rest}`)
  }
  return forms.map(form => form.toLowerCase())
}

async function mentionsGuard($: EngineInterface, input: Record<string, unknown>): Promise<boolean> {
  const { tool, tool_use_id: _id, ...args } = input
  const texts = strings(args)
  const userHome = (await $.env.get('HOME')) ?? ''
  const forms = [...homeForms(state.home, userHome), $.plugin.root.toLowerCase()]
  const writes = WRITERS.has(String(tool))
  return texts.some(text => {
    const lower = text.toLowerCase()
    return (
      ENGINE.test(text) ||
      forms.some(form => lower.includes(form)) ||
      (SETTINGS.test(text) && (writes || tool === 'Bash'))
    )
  })
}

export function registerGuard(on: On): void {
  on('tool.call', async ($, e, next) => {
    await currentSession($) // a failure here is refused by the .catch below
    const input = e as unknown as Record<string, unknown>
    if (String(e.tool).startsWith('mcp__')) return next(e)
    if (e.tool === 'Bash' && input.dangerouslyDisableSandbox === true) return { deny: REFUSED }
    if (await mentionsGuard($, input)) return { deny: REFUSED }
    return next(e)
  }).catch(($, e, next) => (next.called ? next(e) : { deny: REFUSED }))
}
