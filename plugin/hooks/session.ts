// Session lifecycle: begin at start, end at the end, and follow the session id across /clear.
import type { EngineInterface, On } from 'claude-code'
import { runEngine, TIMEOUTS } from './engine'
import { checkPreconditions } from './preconditions'
import { clearReveal, state } from './state'
import { registerStatusCommand, showOverview } from './status'
import { startWarmups } from './warmup'

async function loadTable($: EngineInterface, id: string): Promise<void> {
  try {
    await runEngine($, ['table', '--session', id, '--since', '0'])
  } catch {
    // an empty table only means nothing is revealed until the next reply carries entries
  }
}

/** A server whose profile is invalid is still protected, by the default or bundled profile. */
async function warnInvalidProfiles($: EngineInterface): Promise<void> {
  for (const [alias, info] of Object.entries(state.servers)) {
    if (info.profile_state !== 'invalid') continue
    try {
      await $.ui.toast(
        `privacy guard: the profile for ${alias} is invalid (${info.profile_reason ?? 'unknown'}); ` +
          'the server is still protected by a safe profile',
      )
    } catch {
      // the server stays protected whether or not the toast shows
    }
  }
}

async function start($: EngineInterface): Promise<void> {
  const id = await $.session.id()
  state.sessionId = id
  clearReveal()
  if ((await checkPreconditions($)) === null) {
    await loadTable($, id)
    await warnInvalidProfiles($)
    try {
      await showOverview($)
    } catch {
      // only the display is affected
    }
    startWarmups($)
  }
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
    await registerStatusCommand($)
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
