// Slash-command arguments and skill text reach the model without `prompt.submit` on some paths
// (research R1, "Slash commands and skills"), so they are masked where they are expanded.
import type { EngineInterface, On } from 'claude-code'
import { runEngine } from './engine'
import { blockedReason } from './preconditions'
import { dropText, sinceArgs } from './prompt'
import { currentSession } from './session'
import { refreshServers } from './warmup'

const OWN = 'privacy-guard'
const REFUSED = 'privacy guard: not run, its text could not be checked'

/** The text with its identifying values replaced, or the refusal the user and model read. */
async function masked(
  $: EngineInterface,
  text: string,
): Promise<{ text: string } | { refusal: string }> {
  await currentSession($)
  const reason = blockedReason()
  if (reason !== null) return { refusal: reason }
  await refreshServers($)
  try {
    const reply = await runEngine($, ['prompt', ...sinceArgs()], { text })
    return typeof reply.text === 'string' ? { text: reply.text } : { refusal: REFUSED }
  } catch (error) {
    return { refusal: dropText($, error) }
  }
}

export function registerCommand(on: On): void {
  on('command.run', async ($, e, next) => {
    if (e.command === OWN) return next(e)
    if (e.args === '') return next(e)
    const out = await masked($, e.args)
    if ('refusal' in out) return { text: out.refusal } // answered without next: the command does not run
    return next({ ...e, args: out.text })
  }).catch(($, e, next) => (next.called ? next(e) : { text: REFUSED }))

  on('skill.prompt', async ($, e, next) => {
    if (e.text === '') return next(e)
    const out = await masked($, e.text)
    if ('refusal' in out) return { text: out.refusal }
    return next({ ...e, text: out.text })
  }).catch(($, e, next) => (next.called ? next(e) : { text: REFUSED }))
}
