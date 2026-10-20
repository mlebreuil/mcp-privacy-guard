// The user's question: real values become the stand-ins the tool results use (FR-017..FR-020).
import type { EngineInterface, On } from 'claude-code'
import { EngineError, runEngine } from './engine'
import { blockedReason, onEngineExit3, REASON } from './preconditions'
import { currentSession } from './session'
import { state } from './state'
import { gateMessage, refreshServers } from './warmup'

const ATTACHMENT =
  'privacy guard: a question with an image, file or document cannot be checked; paste the text instead'
const NOT_CHECKED = 'privacy guard: question not checked'

/** What the user reads when the engine could not check a question or a command. */
export function dropText($: EngineInterface, error: unknown): string {
  if (error instanceof EngineError && error.exitCode === 3) {
    onEngineExit3($)
    return REASON.expired
  }
  return gateMessage(error) ?? NOT_CHECKED
}

export const sinceArgs = () => ['--session', state.sessionId ?? '', '--since', String(state.reveal.rev)]

export function registerPrompt(on: On): void {
  on('prompt.submit', async ($, e, next) => {
    await currentSession($)
    const reason = blockedReason()
    if (reason !== null) return { drop: reason }
    if (e.attachments !== undefined && e.attachments.length > 0) return { drop: ATTACHMENT }
    await refreshServers($)

    if (e.command !== undefined) {
      // the arguments were masked at command.run; here only the warm-up gate applies
      try {
        await runEngine($, ['prompt', ...sinceArgs(), '--command'], { text: e.text })
      } catch (error) {
        return { drop: dropText($, error) }
      }
      return next(e)
    }

    let reply
    try {
      reply = await runEngine($, ['prompt', ...sinceArgs()], { text: e.text })
    } catch (error) {
      return { drop: dropText($, error) }
    }
    if (typeof reply.text !== 'string') return { drop: NOT_CHECKED }
    const entered = await next({ ...e, text: reply.text })
    const replaced = Array.isArray(reply.replacements) ? reply.replacements.length : 0
    if (replaced > 0) await $.ui.toast(`privacy guard: ${replaced} value(s) replaced`)
    return entered
  }).catch(($, e, next) => (next.called ? next(e) : { drop: NOT_CHECKED }))
}
