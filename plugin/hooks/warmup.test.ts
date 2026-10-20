import { expect, mock, test } from 'claude-code/testing'
import { register } from './register'
import { SESSION_START, SID, fakeHost } from './test-support'

void register

const LIST = { tool: 'list_device_groups', args: {} }
const RULES = { tool: 'get_security_rules', args: { scope: 'shared' } }
const TOOLS = ['mcp__generic__list_device_groups', 'mcp__generic__get_security_rules']
const OK = { content: [{ type: 'text', text: '{"items":[]}' }], isError: false }

function setup(on: Parameters<typeof mock.clock>[0], init: Parameters<typeof fakeHost>[1] = {}) {
  const clock = mock.clock(on)
  const h = fakeHost(on, {
    warmups: { generic: [LIST, RULES] },
    toolNames: TOOLS,
    mcpAnswer: () => OK,
    clock,
    ...init,
  })
  return { clock, h }
}

const subs = (h: ReturnType<typeof fakeHost>) => h.calls.map(c => c.sub)

test('a server with a pending warm-up is warmed up in the background', async ($, on) => {
  const { clock, h } = setup(on)
  await $.session.start(SESSION_START)
  await clock.settle()
  expect(h.mcpCalls.map(c => c.tool)).toEqual(['list_device_groups', 'get_security_rules'])
  expect(h.mcpCalls[1]?.args).toEqual({ scope: 'shared' })
  expect(h.mcpCalls.every(c => c.server === 'generic')).toBe(true)
  const states = h.called('warmup').map(c => c.argv[c.argv.indexOf('--state') + 1])
  expect(states).toEqual(['running', 'complete'])
  const learned = h.called('learn')
  expect(learned.length).toBe(2)
  expect(learned[0]?.argv).toEqual(expect.arrayContaining(['--session', SID, '--server', 'generic', '--tool', 'list_device_groups']))
  expect(learned[0]?.stdin).toEqual({ result: OK })
  expect(h.toasts).toContain('privacy guard: names loaded, questions accepted')
  expect(h.status()).toBe('privacy-guard: active · 1 protected · 0 exempt')
})

test('the status line shows the progress while names load', async ($, on) => {
  const { clock, h } = setup(on, { mcpDelayMs: 1000 })
  await $.session.start(SESSION_START)
  await clock.settle()
  expect(h.status()).toBe('privacy-guard: loading names (0/1)')
  await clock.advance(5000)
  expect(h.status()).toBe('privacy-guard: active · 1 protected · 0 exempt')
})

test('nothing from the warm-up reaches the conversation', async ($, on) => {
  const { clock, h } = setup(on)
  await $.session.start(SESSION_START)
  await clock.settle()
  expect(h.submitted).toEqual([])
  expect(JSON.stringify(h.toasts)).not.toContain('items')
})

test('a call over 30 s fails the warm-up with a timeout', async ($, on) => {
  const { clock, h } = setup(on, { mcpDelayMs: 10 ** 9 })
  await $.session.start(SESSION_START)
  await clock.settle()
  await clock.advance(31_000)
  const failed = h.called('warmup').at(-1)
  expect(failed?.argv).toEqual(expect.arrayContaining(['--state', 'failed', '--reason', 'timeout']))
  expect(h.status()).toContain('generic')
  expect(h.status()).toContain('timeout')
  expect(h.status()).toContain('/clear')
  expect(h.toasts.at(-1)).toContain('timeout')
})

test('a server that takes over 120 s in total fails with a timeout', async ($, on) => {
  const { clock, h } = setup(on, {
    warmups: { generic: [LIST, RULES, LIST, RULES, LIST] },
    mcpDelayMs: 29_000,
  })
  await $.session.start(SESSION_START)
  await clock.settle()
  await clock.advance(125_000)
  expect(h.called('warmup').at(-1)?.argv).toEqual(expect.arrayContaining(['--state', 'failed', '--reason', 'timeout']))
})

test('a missing tool fails with tool-missing', async ($, on) => {
  const { clock, h } = setup(on, { toolNames: [] })
  await $.session.start(SESSION_START)
  await clock.settle()
  expect(h.called('warmup').at(-1)?.argv).toEqual(expect.arrayContaining(['--state', 'failed', '--reason', 'tool-missing']))
  expect(h.mcpCalls).toEqual([])
})

test('a tool error fails with tool-error', async ($, on) => {
  const { clock, h } = setup(on, {
    mcpAnswer: () => ({ content: [{ type: 'text', text: 'denied' }], isError: true }),
  })
  await $.session.start(SESSION_START)
  await clock.settle()
  expect(h.called('warmup').at(-1)?.argv).toEqual(expect.arrayContaining(['--state', 'failed', '--reason', 'tool-error']))
  expect(h.called('learn').length).toBe(0)
})

test('a call that cannot be made fails with tool-error', async ($, on) => {
  const { clock, h } = setup(on, { mcpAnswer: () => 'throw' })
  await $.session.start(SESSION_START)
  await clock.settle()
  expect(h.called('warmup').at(-1)?.argv).toEqual(expect.arrayContaining(['--reason', 'tool-error']))
})

test('a learn failure fails with learn-failed', async ($, on) => {
  const { clock, h } = setup(on, { engine: { learn: () => ({ exit: 5 }) } })
  await $.session.start(SESSION_START)
  await clock.settle()
  expect(h.called('warmup').at(-1)?.argv).toEqual(expect.arrayContaining(['--state', 'failed', '--reason', 'learn-failed']))
})

test('a server that is already complete is not warmed up again', async ($, on) => {
  const { clock, h } = setup(on, { warm: { generic: 'complete' } })
  await $.session.start(SESSION_START)
  await clock.settle()
  expect(h.mcpCalls).toEqual([])
  expect(subs(h)).not.toContain('warmup')
})

test('an exempt server is not warmed up', async ($, on) => {
  const { clock, h } = setup(on, { servers: { generic: { exempt: true } } })
  await $.session.start(SESSION_START)
  await clock.settle()
  expect(h.mcpCalls).toEqual([])
})

test('a server that connects later is found at the next hook and warmed up', async ($, on) => {
  const { clock, h } = setup(on, {
    servers: { generic: { exempt: false } },
    connected: ['generic'],
    warmups: {},
  })
  await $.session.start(SESSION_START)
  await clock.settle()
  expect(h.mcpCalls).toEqual([])
  h.servers = { generic: { exempt: false }, late: { exempt: false } }
  h.connected = ['generic', 'late']
  h.warmups = { late: [LIST] }
  h.toolNames = ['mcp__late__list_device_groups']
  await ($.prompt as unknown as { submit: (i: unknown) => Promise<unknown> }).submit({
    text: 'hello',
    wait: false,
    origin: { kind: 'composer' },
  })
  await clock.settle()
  expect(h.mcpCalls).toEqual([{ server: 'late', tool: 'list_device_groups', args: {} }])
  expect(h.called('warmup').at(-1)?.argv).toEqual(expect.arrayContaining(['--server', 'late', '--state', 'complete']))
})
