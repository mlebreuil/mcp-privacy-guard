// Session lifecycle: begin at start, end at the end, and follow the session id across /clear.
import type { EngineInterface, On } from 'claude-code'
import { runEngine, TIMEOUTS } from './engine'
import { checkPreconditions } from './preconditions'
import { clearReveal, state } from './state'

async function loadTable($: EngineInterface, id: string): Promise<void> {
  try {
    await runEngine($, ['table', '--session', id, '--since', '0'])
  } catch {
    // an empty table only means nothing is revealed until the next reply carries entries
  }
}

async function start($: EngineInterface): Promise<void> {
  const id = await $.session.id()
  state.sessionId = id
  clearReveal()
  if ((await checkPreconditions($)) === null) await loadTable($, id)
}

/**
 * Called at the start of every hook: a changed session id (a /clear raises no session.start)
 * empties the reveal table and runs the preconditions again, which `begin` the new session.
 */
export async function currentSession($: EngineInterface): Promise<void> {
  const id = await $.session.id()
  if (id !== state.sessionId) await start($)
}

export function registerSession(on: On): void {
  on('session.start', async ($, e, next) => {
    try {
      await start($)
    } catch {
      state.ready = false // the guard stays blocked until a check passes
    }
    return next(e)
  })

  on('session.end', async ($, e, next) => {
    const left = next.budget.remainingMs
    const timeoutMs = Math.max(100, Math.min(TIMEOUTS.end ?? 1000, left - 200))
    try {
      await runEngine($, ['end', '--session', e.sessionId], undefined, timeoutMs)
    } catch {
      // the folder is swept later (research R13); the exit is never held back
    }
    clearReveal()
    if (state.sessionId === e.sessionId) state.sessionId = null
    return next(e)
  })
}
