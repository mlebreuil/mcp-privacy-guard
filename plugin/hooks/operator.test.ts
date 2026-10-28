import type { Engine } from 'claude-code/testing'
import { expect, test } from 'claude-code/testing'
import { register } from './register'
import { SESSION_START, SID, fakeHost } from './test-support'

void register

const REAL = { content: [{ type: 'text', text: 'REAL 10.1.2.15' }], isError: false }
const callMcp = ($: Engine, args: Record<string, unknown> = {}) =>
  ($.tool as unknown as { call: (i: unknown) => Promise<Record<string, unknown>> }).call({
    ...args,
    tool: 'mcp__generic__list',
    tool_use_id: 't1',
  })
const runCommand = ($: Engine) =>
  ($.command as unknown as { run: (i: unknown) => Promise<{ text?: string }> }).run({
    command: 'privacy-guard',
    args: '',
  })

test('an exempt server\'s result is unchanged, its arguments are translated and its result is recorded', async ($, on) => {
  const h = fakeHost(on, { servers: { generic: { exempt: true } } })
  await $.session.start(SESSION_START)
  const out = await callMcp($, { name: 'n-abcdef' })
  expect(out.result).toEqual(REAL)
  expect(h.toolInputs.at(-1)?.name).toBe('REAL-NAME')
  const exempt = h.called('result').filter(c => c.argv.includes('--exempt'))
  expect(exempt.length).toBe(1)
  expect(exempt[0]?.argv).toEqual(expect.arrayContaining(['--session', SID, '--server', 'generic']))
  expect(exempt[0]?.stdin).toEqual({ result: REAL })
})

test('a failure of result --exempt is ignored', async ($, on) => {
  const h = fakeHost(on, {
    servers: { generic: { exempt: true } },
    engine: { result: () => ({ exit: 5 }) },
  })
  await $.session.start(SESSION_START)
  const out = await callMcp($)
  expect(out.deny).toBeUndefined()
  expect(out.result).toEqual(REAL)
  expect(h.called('result').length).toBe(1)
})

test('an ambiguous address denies the call before the tool runs', async ($, on) => {
  const h = fakeHost(on, {
    engine: { args: () => ({ exit: 4, out: { error: { code: 'ambiguous-address' } } }) },
  })
  await $.session.start(SESSION_START)
  const out = await callMcp($)
  expect(out.deny).toBe('privacy guard: an address in this call is ambiguous; ask the user to state it')
  expect(h.toolRuns).toBe(0)
})

test('session start shows each server with its profile or exempt, and flags invalid profiles', async ($, on) => {
  const h = fakeHost(on, {
    servers: {
      generic: { exempt: false },
      notion: { exempt: true },
      panos: { exempt: false, invalid: 'warmup-required' },
    },
    connected: ['generic', 'notion', 'panos'],
  })
  await $.session.start(SESSION_START)
  const toast = h.toasts.find(t => t.includes('notion'))
  expect(toast).toContain('generic: default')
  expect(toast).toContain('notion: exempt')
  expect(toast).toContain('panos: default (invalid)')
  expect(toast).not.toContain('/privacy-guard for all')
})

test('a long list is cut', async ($, on) => {
  const servers = Object.fromEntries(['a', 'b', 'c', 'd', 'e', 'f'].map(k => [k, { exempt: false }]))
  const h = fakeHost(on, { servers, connected: Object.keys(servers) })
  await $.session.start(SESSION_START)
  const toast = h.toasts.find(t => t.includes('a: default'))
  expect(toast).toContain('… /privacy-guard for all')
  expect(toast).not.toContain('f: default')
})

test('/privacy-guard reports the guard state and each server, with no store value', async ($, on) => {
  const h = fakeHost(on, {
    servers: { generic: { exempt: false }, notion: { exempt: true } },
    connected: ['generic', 'notion'],
    warmups: { generic: [{ tool: 'list', args: {} }] },
    engine: {
      table: () => ({
        out: { table: { rev: 1, entries: [{ standin: 'n-abcdef', real: 'SECRET-REAL', kind: 'NAME' }] } },
      }),
    },
  })
  await $.session.start(SESSION_START)
  expect(h.commands).toContain('privacy-guard')
  const { text } = await runCommand($)
  expect(text).toContain('active')
  expect(text).toContain('generic')
  expect(text).toMatch(/generic[^\n]*profile default[^\n]*valid[^\n]*protected[^\n]*warm-up (not-started|running|complete|failed)/)
  expect(text).toMatch(/notion[^\n]*exempt/)
  expect(text).not.toContain('SECRET-REAL')
  expect(text).not.toContain('n-abcdef')
})

test('/privacy-guard gives the block reason when the guard blocks', async ($, on) => {
  fakeHost(on, { settings: {} })
  await $.session.start(SESSION_START)
  const { text } = await runCommand($)
  expect(text).toContain('sandbox.enabled')
})

test('the status line shows protected and exempt counts', async ($, on) => {
  const h = fakeHost(on, {
    servers: { generic: { exempt: false }, notion: { exempt: true } },
    connected: ['generic', 'notion'],
  })
  await $.session.start(SESSION_START)
  expect(h.status()).toBe('privacy-guard: active · 1 protected · 1 exempt')
})
