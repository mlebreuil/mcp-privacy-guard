import type { Engine } from 'claude-code/testing'
import { expect, test } from 'claude-code/testing'
import { register } from './register'
import { SESSION_START, fakeHost, type Host } from './test-support'

void register

const ENTRIES = [
  { standin: '10.83.4.12', real: '10.1.2.15', kind: 'IP' },
  { standin: 'n-abcdef', real: 'Allow-Admin-Web', kind: 'NAME' },
  { standin: 'h-fzpcmm.d-azghso.d-yjklur.com', real: 'app.corp.example.com', kind: 'FQDN' },
  { standin: 'd-azghso.d-yjklur.com', real: 'corp.example.com', kind: 'FQDN_PARENT' },
]
const table = () => ({ table: { rev: 4, entries: ENTRIES } })

type Drawn = { props?: Record<string, unknown> }

/** The bottom `ui.render` hook stands for the engine and records the props it was asked to draw. */
function engineDraws(on: Parameters<typeof fakeHost>[0]): Drawn {
  const drawn: Drawn = {}
  on('ui.render', ($, e) => {
    drawn.props = e.props as Record<string, unknown>
    const { Text } = $.ui.resolve(e)
    return h(Text, null, 'engine') as never
  })
  return drawn
}

const draw = ($: Engine, component: string, props: Record<string, unknown>, surface = 'terminal') =>
  $.ui.mount({ plugin: 'mcp-privacy-guard', component, requestId: 'r1', props, surface } as never)

const host = (init: Partial<Host> = {}) => (on: Parameters<typeof fakeHost>[0]) =>
  fakeHost(on, { engine: { table: () => ({ out: table() }) }, ...init })

test('assistant text, tool rows and results show real values on the terminal', async ($, on) => {
  host()(on)
  const drawn = engineDraws(on)
  await $.session.start(SESSION_START)

  await draw($, 'AssistantMessage', {
    text: 'Rule n-abcdef allows 10.83.4.12 to h-fzpcmm.d-azghso.d-yjklur.com, 3 hits.',
    isFirstOfReply: true,
  })
  const text = String(drawn.props?.text)
  expect(text).toContain('Allow-Admin-Web')
  expect(text).toContain('10.1.2.15')
  expect(text).toContain('app.corp.example.com')
  expect(text).not.toContain('n-abcdef')
  expect(text).toContain('3 hits.')

  await draw($, 'ToolUse', { tool: 'mcp__g__x', input: { host: '10.83.4.12', n: 3 }, output: undefined })
  expect(drawn.props?.input).toEqual({ host: '10.1.2.15', n: 3 })

  await draw($, 'ToolResult', {
    tool: 'mcp__g__x',
    output: { content: [{ type: 'text', text: '{"name":"n-abcdef"}' }] },
  })
  expect(JSON.stringify(drawn.props?.output)).toContain('Allow-Admin-Web')
  expect(JSON.stringify(drawn.props?.output)).not.toContain('n-abcdef')
})

test('the longest stand-in wins and punctuation after it stays', async ($, on) => {
  host()(on)
  const drawn = engineDraws(on)
  await $.session.start(SESSION_START)
  await draw($, 'AssistantMessage', {
    text: 'see d-azghso.d-yjklur.com. Also (n-abcdef), 10.83.4.12:443',
    isFirstOfReply: true,
  })
  expect(drawn.props?.text).toContain('see **corp.example.com**. Also (**Allow-Admin-Web**), **10.1.2.15**:443')
})

for (const surface of ['desktop', 'vscode', 'mobile']) {
  test(`nothing is revealed on ${surface}`, async ($, on) => {
    host()(on)
    const drawn = engineDraws(on)
    await $.session.start({ ...SESSION_START, surface } as never)
    await draw($, 'AssistantMessage', { text: 'n-abcdef 10.83.4.12', isFirstOfReply: true }, surface)
    expect(drawn.props?.text).toBe('n-abcdef 10.83.4.12')
  })
}

test('a client claiming terminal stops the reveal and a toast says so', async ($, on) => {
  const h = host()(on)
  const drawn = engineDraws(on)
  await $.session.start(SESSION_START)
  await ($.session as unknown as { attach: (i: unknown) => Promise<unknown> }).attach({
    surface: 'terminal',
    clientId: 'terminal:x',
  })
  expect(h.toasts.join(' ')).toContain('reveal is off')
  await draw($, 'AssistantMessage', { text: 'n-abcdef', isFirstOfReply: true })
  expect(drawn.props?.text).toBe('n-abcdef')
})

test('an unknown stand-in gets a (?) mark', async ($, on) => {
  host()(on)
  const drawn = engineDraws(on)
  await $.session.start(SESSION_START)
  await draw($, 'AssistantMessage', { text: 'n-zzzzzz and n-abcdef', isFirstOfReply: true })
  expect(drawn.props?.text).toBe('n-zzzzzz(?) and **Allow-Admin-Web**')
})

test('the question from the composer shows real values', async ($, on) => {
  host()(on)
  engineDraws(on)
  await $.session.start(SESSION_START)
  const ui = await draw($, 'UserMessage', {
    text: 'why is 10.83.4.12 blocked?',
    origin: { kind: 'composer' },
    isExpanded: false,
  })
  expect((await ui.find({ type: 'Text', text: /10\.1\.2\.15/ }))?.text).toContain('10.1.2.15')
})

test('a throw while revealing draws the engine\'s row', async ($, on) => {
  const h = host()(on)
  const drawn = engineDraws(on)
  await $.session.start(SESSION_START)
  h.toasts.length = 0
  await draw($, 'AssistantMessage', { text: undefined, isFirstOfReply: true })
  expect(drawn.props).toEqual({ text: undefined, isFirstOfReply: true })
})

test('turn.complete observes the answer and invalidates the rows', async ($, on) => {
  const h = host({
    engine: {
      table: () => ({ out: table() }),
      observe: () => ({ out: { table: { rev: 5, entries: [{ standin: '10.9.9.9', real: '10.2.2.2', kind: 'IP' }] } } }),
    },
  })(on)
  const drawn = engineDraws(on)
  on('turn.complete', () => ({ text: '' }))
  await $.session.start(SESSION_START)
  await ($.turn as unknown as { complete: (i: unknown) => Promise<unknown> }).complete({
    answer: 'try 10.9.9.9', durationMs: 1, isAborted: false, turnId: 't', reason: 'answer',
  })
  const [call] = h.called('observe')
  expect(call?.stdin).toEqual({ text: 'try 10.9.9.9' })
  expect(h.invalidations).toBeGreaterThan(0)
  await draw($, 'AssistantMessage', { text: '10.9.9.9', isFirstOfReply: true })
  expect(drawn.props?.text).toBe('**10.2.2.2**')
})

test('after a session id change the old table reveals nothing', async ($, on) => {
  const h = host()(on)
  const drawn = engineDraws(on)
  await $.session.start(SESSION_START)
  h.sessionId = 's-2'
  h.engine.table = () => ({ out: { table: { rev: 0, entries: [] } } })
  await draw($, 'AssistantMessage', { text: 'n-abcdef', isFirstOfReply: true })
  expect(drawn.props?.text).toBe('n-abcdef')
})

const fresh = { table: { rev: 9, entries: [{ standin: 'n-qqqqqq', real: 'Real', kind: 'NAME' }] } }

test('new table entries from result and prompt replies invalidate the rows', async ($, on) => {
  const h = fakeHost(on, {
    engine: {
      result: () => ({
        out: { result: { content: [], isError: false }, withheld: 0, notices: [], ...fresh },
      }),
      prompt: () => ({ out: { text: 'q', replacements: [], warnings: [], ...fresh } }),
    },
  })
  await $.session.start(SESSION_START)
  expect(h.invalidations).toBe(0)
  await ($.tool as unknown as { call: (i: unknown) => Promise<unknown> }).call({
    tool: 'mcp__generic__list',
    tool_use_id: 't1',
  })
  expect(h.invalidations).toBeGreaterThan(0)
  h.invalidations = 0
  h.engine.prompt = () => ({
    out: { text: 'q', replacements: [], warnings: [], table: { rev: 10, entries: [] } },
  })
  await ($.prompt as unknown as { submit: (i: unknown) => Promise<unknown> }).submit({
    text: 'q', wait: false, origin: { kind: 'composer' },
  })
  expect(h.invalidations).toBeGreaterThan(0)
})
