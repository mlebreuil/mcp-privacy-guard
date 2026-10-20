import type { Engine } from 'claude-code/testing'
import { expect, test } from 'claude-code/testing'
import { register } from './register'
import { SESSION_START, SID, fakeHost, type Host } from './test-support'

void register

type Submit = { text?: string; drop?: string }
const submit = ($: Engine, text: string, extra: Record<string, unknown> = {}) =>
  ($.prompt as unknown as { submit: (i: unknown) => Promise<Submit> }).submit({
    text,
    wait: false,
    origin: { kind: 'composer' },
    ...extra,
  })

const REAL = 'why is 10.1.2.15 blocked?'

test('a question with an IP reaches the model as the engine rewrote it', async ($, on) => {
  const h = fakeHost(on)
  await $.session.start(SESSION_START)
  const out = await submit($, REAL)
  expect(out.text).toBe('why is 10.83.4.12 blocked?')
  expect(h.submitted).toEqual(['why is 10.83.4.12 blocked?'])
  const [call] = h.called('prompt')
  expect(call?.argv).toEqual(expect.arrayContaining(['--session', SID, '--since']))
  expect(call?.stdin).toEqual({ text: REAL })
  expect(JSON.stringify(h.submitted)).not.toContain('10.1.2.15')
})

test('a toast says how many values were replaced', async ($, on) => {
  const h = fakeHost(on)
  await $.session.start(SESSION_START)
  await submit($, REAL)
  expect(h.toasts).toContain('privacy guard: 1 value(s) replaced')
  h.toasts.length = 0
  await submit($, 'show me the rules')
  expect(h.toasts).toEqual([])
})

const failures: [string, Host['engine']][] = [
  ['exit 5', { prompt: () => ({ exit: 5 }) }],
  ['invalid JSON', { prompt: () => ({ raw: 'nope' }) }],
  ['no engine / timeout', { prompt: () => ({ reject: true }) }],
  ['exit 3', { prompt: () => ({ exit: 3 }) }],
]
for (const [name, engine] of failures) {
  test(`an engine failure (${name}) drops the question`, async ($, on) => {
    const h = fakeHost(on, { engine })
    await $.session.start(SESSION_START)
    const out = await submit($, REAL)
    expect(out.drop).toContain('privacy guard')
    expect(h.submitted).toEqual([])
    if (name === 'exit 3') expect(h.status()).toContain('session expired')
  })
}

test('a throw in the hook drops the question', async ($, on) => {
  const h = fakeHost(on)
  await $.session.start(SESSION_START)
  h.idFails = true
  const out = await submit($, REAL)
  expect(out.drop).toContain('privacy guard')
  expect(h.submitted).toEqual([])
})

test('a pending warm-up holds the question with the servers named', async ($, on) => {
  const h = fakeHost(on, {
    engine: {
      prompt: () => ({
        exit: 4,
        out: { error: { code: 'warmup-pending', message: 'm', hint: 'h', servers: ['panos'] } },
      }),
    },
  })
  await $.session.start(SESSION_START)
  const out = await submit($, REAL)
  expect(out.drop).toBe('privacy guard: loading names for panos, try again in a moment')
  expect(h.submitted).toEqual([])
})

test('a failed warm-up drops the question with its reason and the fix', async ($, on) => {
  fakeHost(on, {
    engine: {
      prompt: () => ({
        exit: 4,
        out: {
          error: { code: 'warmup-failed', message: 'm', hint: 'h', servers: ['panos'], reason: 'timeout' },
        },
      }),
    },
  })
  await $.session.start(SESSION_START)
  const out = await submit($, REAL)
  expect(out.drop).toContain('panos')
  expect(out.drop).toContain('timeout')
  expect(out.drop).toContain('/clear')
})

test('a slash command waits for the warm-up too, and passes once it is done', async ($, on) => {
  const waiting = {
    exit: 4,
    out: { error: { code: 'warmup-pending', message: 'm', hint: 'h', servers: ['panos'] } },
  }
  const h = fakeHost(on, { engine: { prompt: () => waiting } })
  await $.session.start(SESSION_START)
  const command = { command: { name: 'review', args: 'the diff' } }
  expect((await submit($, '/review the diff', command)).drop).toContain('loading names for panos')
  h.engine.prompt = () => ({ out: { identifying: true } }) // the arguments were masked at command.run
  const out = await submit($, '/review the diff', command)
  expect(out.text).toBe('/review the diff')
  expect(h.called('prompt').at(-1)?.argv).toContain('--command')
  expect(h.submitted).toEqual(['/review the diff'])
})

test('a block reason drops the question', async ($, on) => {
  const h = fakeHost(on, { settings: {} })
  await $.session.start(SESSION_START)
  const out = await submit($, REAL)
  expect(out.drop).toContain('privacy guard')
  expect(h.called('prompt').length).toBe(0)
})

test('an attachment drops the question without calling the engine', async ($, on) => {
  const h = fakeHost(on)
  await $.session.start(SESSION_START)
  const out = await submit($, REAL, { attachments: [{ kind: 'image', id: 'a1' }] })
  expect(out.drop).toContain('paste the text instead')
  expect(h.called('prompt').length).toBe(0)
  expect(h.submitted).toEqual([])
})

test('a throw after next was called does not send the question twice', async ($, on) => {
  const h = fakeHost(on)
  await $.session.start(SESSION_START)
  h.toastFails = true // the toast comes after next; its failure must not undo or repeat the send
  const out = await submit($, REAL)
  expect(out.text).toBe('why is 10.83.4.12 blocked?')
  expect(h.submitted).toEqual(['why is 10.83.4.12 blocked?'])
})
