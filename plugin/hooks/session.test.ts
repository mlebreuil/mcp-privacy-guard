import type { Engine } from 'claude-code/testing'
import { expect, test } from 'claude-code/testing'
import { register } from './register'
import { RECOGNISE, SESSION_START, SID, fakeHost } from './test-support'

void register

const END = (sessionId: string) =>
  ({ reason: 'prompt_input_exit', sessionId, resume: { sessionId } }) as never

test('session.end deletes the session within the budget and still calls next', async ($, on) => {
  const h = fakeHost(on)
  await $.session.start(SESSION_START)
  await $.session.end(END(SID))
  const [end] = h.called('end')
  expect(end?.argv[end.argv.indexOf('--session') + 1]).toBe(SID)
  expect(end?.timeoutMs).toBeLessThanOrEqual(1500)
  expect(h.live.has(SID)).toBe(false)
})

test('a failing end does not stop the session from ending', async ($, on) => {
  const h = fakeHost(on, { engine: { end: () => ({ reject: true }) } })
  await $.session.start(SESSION_START)
  await $.session.end(END(SID))
  expect(h.called('end').length).toBe(1)
})

test('end names the session that ends, not the current one', async ($, on) => {
  const h = fakeHost(on)
  await $.session.start(SESSION_START)
  h.sessionId = 'newer'
  await $.session.end(END(SID))
  const [end] = h.called('end')
  expect(end?.argv[end.argv.indexOf('--session') + 1]).toBe(SID)
})

test('a changed session id (a /clear) begins a new session before the next hook runs', async ($, on) => {
  const h = fakeHost(on)
  await $.session.start(SESSION_START)
  h.sessionId = 'after-clear'
  await ($.tool as unknown as { call: (i: unknown) => Promise<unknown> }).call({
    tool: 'Read',
    tool_use_id: 't1',
    file_path: '/proj/README.md',
  })
  const begins = h.called('begin').map(c => c.argv[c.argv.indexOf('--session') + 1])
  expect(begins).toEqual([SID, 'after-clear'])
})

// Live check 12: after /clear the host's turn count may still be above 0 (or fail). A /clear is not
// a resume, so the new session must begin; the guard must not block it as "ended session".
const callRead = ($: Engine) =>
  ($.tool as unknown as { call: (i: unknown) => Promise<unknown> }).call({
    tool: 'Read',
    tool_use_id: 't1',
    file_path: '/proj/README.md',
  })

for (const turns of [3, 'throw' as const]) {
  test(`a /clear begins a new session even when the host reports turns: ${turns}`, async ($, on) => {
    const h = fakeHost(on)
    await $.session.start(SESSION_START)
    h.turns = turns
    h.sessionId = 'after-clear'
    await callRead($)
    const begins = h.called('begin').map(c => c.argv[c.argv.indexOf('--session') + 1])
    expect(begins).toEqual([SID, 'after-clear'])
    expect(h.status()).toContain('active')
  })

  test(`a /clear lifts the block of a resumed conversation (turns: ${turns})`, async ($, on) => {
    const h = fakeHost(on, { turns })
    await $.session.start(SESSION_START)
    expect(h.status()).toContain('ended session')
    h.sessionId = 'after-clear'
    await callRead($)
    const begins = h.called('begin').map(c => c.argv[c.argv.indexOf('--session') + 1])
    expect(begins).toEqual(['after-clear'])
    expect(h.status()).toContain('active')
  })
}

test('session.start loads the server map, the recognition pattern and the table', async ($, on) => {
  const h = fakeHost(on, {
    servers: { generic: { exempt: false }, notion: { exempt: true } },
    connected: ['generic', 'notion'],
  })
  await $.session.start(SESSION_START)
  const [table] = h.called('table')
  expect(table?.argv).toEqual(expect.arrayContaining(['--session', SID, '--since', '0']))
  expect(h.status()).toBe('privacy-guard: active · 1 protected · 1 exempt')
  expect(RECOGNISE.length).toBeGreaterThan(0)
})

test('the status line is the block reason when the guard blocks', async ($, on) => {
  const h = fakeHost(on, { surfaces: [] })
  await $.session.start(SESSION_START)
  expect(h.status()).toContain('use Claude Code in a terminal')
})
