import type { Engine } from 'claude-code/testing'
import { expect, test } from 'claude-code/testing'
import { register } from './register'
import { SESSION_START, fakeHost } from './test-support'

void register

type Ran = { text?: string }
const run = ($: Engine, command: string, args: string) =>
  ($.command as unknown as { run: (i: unknown) => Promise<Ran> }).run({
    command,
    args,
    origin: { kind: 'composer' },
    presentation: { isFullscreen: false, columns: 80 },
  })
const skill = ($: Engine, text: string) =>
  ($.skill as unknown as { prompt: (i: unknown) => Promise<{ text: string }> }).prompt({
    skill: 'review',
    text,
    frontmatter: {},
    source: 'built-in',
  })

test('a command with an identifying value has its arguments rewritten before it runs', async ($, on) => {
  const h = fakeHost(on)
  await $.session.start(SESSION_START)
  await run($, 'review', 'check 10.1.2.15 now')
  expect(h.commandArgs).toEqual(['check 10.83.4.12 now'])
  expect(h.called('prompt')[0]?.stdin).toEqual({ text: 'check 10.1.2.15 now' })
})

test('a command without arguments runs as it is', async ($, on) => {
  const h = fakeHost(on)
  await $.session.start(SESSION_START)
  await run($, 'review', '')
  expect(h.commandArgs).toEqual([''])
})

test('the guard\'s own command is not masked', async ($, on) => {
  const h = fakeHost(on)
  await $.session.start(SESSION_START)
  await run($, 'privacy-guard', '10.1.2.15')
  expect(h.commandArgs).toEqual(['10.1.2.15'])
  expect(h.called('prompt').length).toBe(0)
})

const failures = [
  ['exit 5', { prompt: () => ({ exit: 5 }) }],
  ['invalid JSON', { prompt: () => ({ raw: 'nope' }) }],
  ['no engine', { prompt: () => ({ reject: true }) }],
  [
    'warm-up pending',
    {
      prompt: () => ({
        exit: 4,
        out: { error: { code: 'warmup-pending', message: 'm', hint: 'h', servers: ['panos'] } },
      }),
    },
  ],
] as const
for (const [name, engine] of failures) {
  test(`a command whose arguments cannot be checked (${name}) is not run`, async ($, on) => {
    const h = fakeHost(on, { engine })
    await $.session.start(SESSION_START)
    const out = await run($, 'review', 'check 10.1.2.15 now')
    expect(out.text).toContain('privacy guard')
    expect(h.commandArgs).toEqual([])
  })
}

test('a block reason refuses the command', async ($, on) => {
  const h = fakeHost(on, { settings: {} })
  await $.session.start(SESSION_START)
  const out = await run($, 'review', 'check 10.1.2.15 now')
  expect(out.text).toContain('privacy guard')
  expect(h.commandArgs).toEqual([])
})

test('skill text with an identifying value is rewritten the same way', async ($, on) => {
  const h = fakeHost(on)
  await $.session.start(SESSION_START)
  const out = await skill($, 'Review the change on 10.1.2.15 and report.')
  expect(out.text).toBe('Review the change on 10.83.4.12 and report.')
  expect(h.skillTexts).toEqual(['Review the change on 10.83.4.12 and report.'])
})

test('skill text that cannot be checked is replaced by a refusal', async ($, on) => {
  const h = fakeHost(on, { engine: { prompt: () => ({ exit: 5 }) } })
  await $.session.start(SESSION_START)
  const out = await skill($, 'Review the change on 10.1.2.15 and report.')
  expect(out.text).toContain('privacy guard')
  expect(h.skillTexts).toEqual([])
})

test('a throw in either hook refuses', async ($, on) => {
  const h = fakeHost(on)
  await $.session.start(SESSION_START)
  h.idFails = true
  expect((await run($, 'review', 'check 10.1.2.15')).text).toContain('privacy guard')
  expect((await skill($, 'check 10.1.2.15')).text).toContain('privacy guard')
  expect(h.commandArgs).toEqual([])
  expect(h.skillTexts).toEqual([])
})
