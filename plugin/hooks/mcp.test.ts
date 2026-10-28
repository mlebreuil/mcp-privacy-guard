import type { Engine } from 'claude-code/testing'
import { expect, test } from 'claude-code/testing'
import { register } from './register'
import { GOOD_SETTINGS, SESSION_START, SID, fakeHost, type Host } from './test-support'

void register

const REAL = { content: [{ type: 'text', text: 'REAL 10.1.2.15' }], isError: false }
const MASKED = { content: [{ type: 'text', text: 'PSEUDONYMIZED' }], isError: false }

const callMcp = (
  $: Engine,
  tool = 'mcp__generic__list',
  args: Record<string, unknown> = {},
) =>
  ($.tool as unknown as { call: (i: unknown) => Promise<Record<string, unknown>> }).call({
    ...args,
    tool,
    tool_use_id: 't1',
  })

test('a protected MCP result is the engine\'s pseudonymized result', async ($, on) => {
  const h = fakeHost(on)
  await $.session.start(SESSION_START)
  const out = await callMcp($)
  expect(out.deny).toBeUndefined()
  expect(out.result).toBe('PSEUDONYMIZED') // never an object: the host refuses one (live check 3)
  const [call] = h.called('result')
  expect(call?.argv).toEqual(
    expect.arrayContaining(['--session', SID, '--server', 'generic', '--tool', 'list']),
  )
  expect(call?.stdin).toEqual({ result: REAL, is_error: false })
})

test('the since revision is passed so the reply carries only new table entries', async ($, on) => {
  const h = fakeHost(on)
  await $.session.start(SESSION_START)
  await callMcp($)
  const [call] = h.called('result')
  expect(call?.argv).toContain('--since')
})

test('a server name containing double underscores maps by the connected list', async ($, on) => {
  const h = fakeHost(on, {
    servers: { 'my__server': { exempt: false } },
    connected: ['my__server'],
  })
  await $.session.start(SESSION_START)
  await callMcp($, 'mcp__my__server__do_it')
  const [call] = h.called('result')
  expect(call?.argv).toEqual(expect.arrayContaining(['--server', 'my__server', '--tool', 'do_it']))
})

const failures: [string, Host['engine']][] = [
  ['exit 3', { result: () => ({ exit: 3 }) }],
  ['exit 4', { result: () => ({ exit: 4, out: { error: { code: 'too-large' } } }) }],
  ['exit 5', { result: () => ({ exit: 5 }) }],
  ['invalid JSON', { result: () => ({ raw: 'nope' }) }],
  ['no engine', { result: () => ({ reject: true }) }],
]
for (const [name, engine] of failures) {
  test(`an engine failure (${name}) withholds the result`, async ($, on) => {
    const h = fakeHost(on, { engine })
    await $.session.start(SESSION_START)
    const out = await callMcp($)
    expect(out.deny).toContain('withheld')
    expect(out.result).toBeUndefined()
    expect(JSON.stringify(out)).not.toContain('10.1.2.15')
    if (name === 'exit 3') expect(h.status()).toContain('session expired')
  })
}

test('a throw in the hook withholds the result', async ($, on) => {
  const h = fakeHost(on)
  await $.session.start(SESSION_START)
  h.idFails = true
  const out = await callMcp($)
  expect(out.deny).toContain('withheld')
})

test('a block reason denies before the tool runs', async ($, on) => {
  const h = fakeHost(on, { settings: {} })
  await $.session.start(SESSION_START)
  const runs = h.toolRuns
  const out = await callMcp($)
  expect(out.deny).toContain('privacy guard')
  expect(h.toolRuns).toBe(runs)
  expect(h.called('result').length).toBe(0)
})

test('a guard that never started denies too', async ($, on) => {
  const h = fakeHost(on, { engine: { status: () => ({ reject: true }) } })
  await $.session.start(SESSION_START)
  const out = await callMcp($)
  expect(out.deny).toContain('privacy guard')
  expect(h.toolRuns).toBe(0)
})

test('an errored result goes out as a denial with the pseudonymized text', async ($, on) => {
  const h = fakeHost(on, {
    mcpResult: () => ({
      result: { content: [{ type: 'text', text: 'Object web-srv-01 not found' }], isError: true },
      isError: true,
    }),
    engine: {
      result: () => ({
        out: {
          result: { content: [{ type: 'text', text: 'Object n-abcdef not found' }], isError: true },
          withheld: 0,
          notices: [],
        },
      }),
    },
  })
  await $.session.start(SESSION_START)
  const out = await callMcp($)
  expect(out.result).toBeUndefined()
  expect(out.deny).toContain('Object n-abcdef not found')
  expect(JSON.stringify(out)).not.toContain('web-srv-01')
  expect(h.called('result')[0]?.stdin).toMatchObject({ is_error: true })
})

test('withheld non-text items are noted for the model', async ($, on) => {
  fakeHost(on, {
    engine: {
      result: () => ({
        out: { result: MASKED, withheld: 2, notices: ['2 non-text item(s) withheld'] },
      }),
    },
  })
  await $.session.start(SESSION_START)
  const out = await callMcp($)
  expect(out.context).toEqual(['privacy guard: 2 non-text item(s) withheld'])
})

test('an exit 3 for a too open store says the store is unusable', async ($, on) => {
  const h = fakeHost(on, {
    engine: { result: () => ({ exit: 3, out: { error: { code: 'too-permissive' } } }) },
  })
  await $.session.start(SESSION_START)
  await callMcp($)
  expect(h.status()).toContain('the session store is unusable')
  expect(h.status()).not.toContain('expired')
})

test('an exempt server\'s result is returned unchanged', async ($, on) => {
  const h = fakeHost(on, { servers: { generic: { exempt: true } } })
  await $.session.start(SESSION_START)
  const out = await callMcp($)
  expect(out.result).toEqual(REAL)
  expect(h.called('result').filter(c => !c.argv.includes('--exempt')).length).toBe(0)
})

test('prompt.compose tells the model the values are stand-ins', async ($, on) => {
  fakeHost(on, { settings: GOOD_SETTINGS })
  await $.session.start(SESSION_START)
  const out = await ($.prompt as unknown as { compose: (i: unknown) => Promise<{ sections: { scope: string; text: string }[] }> }).compose({
    model: 'm',
    promptModel: 'm',
    surfaces: ['terminal'],
    tools: [],
    outputStyle: null,
    traits: [],
  })
  const ours = out.sections.find(s => s.text.includes('stand-in'))
  expect(ours?.scope).toBe('session')
  expect(ours?.text).toContain('must not')
})

// -- arguments (task T058) ---------------------------------------------------------------

test('arguments are rewritten with the engine before the tool runs', async ($, on) => {
  const h = fakeHost(on)
  await $.session.start(SESSION_START)
  await callMcp($, 'mcp__generic__list', { query: 'n-abcdef', limit: 5 })
  const [call] = h.called('args')
  expect(call?.argv).toEqual(
    expect.arrayContaining(['--session', SID, '--server', 'generic', '--tool', 'list']),
  )
  expect(call?.stdin).toEqual({ args: { query: 'n-abcdef', limit: 5 } }) // no reserved keys
  const reached = h.toolInputs.at(-1)
  expect(reached).toMatchObject({
    tool: 'mcp__generic__list',
    tool_use_id: 't1',
    query: 'REAL-NAME',
    limit: 5,
  })
  const order = h.calls.map(c => c.sub)
  expect(order.indexOf('args')).toBeLessThan(order.indexOf('result'))
})

for (const [name, reply] of [
  ['exit 5', { exit: 5 }],
  ['invalid JSON', { raw: 'nope' }],
  ['no engine', { reject: true }],
  ['exit 4 ambiguous', { exit: 4, out: { error: { code: 'ambiguous-address' } } }],
] as const) {
  test(`an args failure (${name}) denies before the tool runs`, async ($, on) => {
    const h = fakeHost(on, { engine: { args: () => reply } })
    await $.session.start(SESSION_START)
    const runs = h.toolRuns
    const out = await callMcp($, 'mcp__generic__list', { query: 'n-abcdef' })
    expect(out.deny).toContain('privacy guard')
    expect(h.toolRuns).toBe(runs)
    expect(h.called('result').length).toBe(0)
  })
}

test('an args exit 3 reports the expired session', async ($, on) => {
  const h = fakeHost(on, { engine: { args: () => ({ exit: 3 }) } })
  await $.session.start(SESSION_START)
  const out = await callMcp($, 'mcp__generic__list', { query: 'n-abcdef' })
  expect(out.deny).toContain('privacy guard')
  expect(h.status()).toContain('session expired')
})

test("an exempt server still gets its arguments translated", async ($, on) => {
  const h = fakeHost(on, { servers: { generic: { exempt: true } } })
  await $.session.start(SESSION_START)
  const out = await callMcp($, 'mcp__generic__list', { query: 'n-abcdef' })
  expect(h.toolInputs.at(-1)).toMatchObject({ query: 'REAL-NAME' })
  expect(out.result).toEqual(REAL)
})

// Live check 8: the host's `next(e).result` for an MCP tool is typed `unknown`. Whatever form it
// has, the engine must get an object with `content`, or it refuses (bad-json) and the result is lost.
const forms: [string, unknown, unknown, unknown][] = [
  [
    'a bare string',
    'REAL 10.1.2.15',
    { content: [{ type: 'text', text: 'REAL 10.1.2.15' }], isError: false },
    'PSEUDONYMIZED',
  ],
  [
    'a list of content blocks',
    [{ type: 'text', text: 'REAL 10.1.2.15' }],
    { content: [{ type: 'text', text: 'REAL 10.1.2.15' }], isError: false },
    [{ type: 'text', text: 'PSEUDONYMIZED' }],
  ],
  [
    'an object with structured content only',
    { structuredContent: { ip: '10.1.2.15' } },
    { content: [], structuredContent: { ip: '10.1.2.15' }, isError: false },
    'PSEUDONYMIZED',
  ],
  [
    'nothing but the joined text',
    undefined,
    { content: [{ type: 'text', text: 'ran' }], isError: false },
    'PSEUDONYMIZED',
  ],
]

for (const [label, shape, expected, returned] of forms) {
  test(`the engine gets an object result when the host returns ${label}`, async ($, on) => {
    const h = fakeHost(on, { mcpResult: () => ({ result: shape }) })
    await $.session.start(SESSION_START)
    const out = await callMcp($)
    expect(out.deny).toBeUndefined()
    // the host takes a string, a list of blocks or nothing as an MCP result, never `{ content }`
    expect(out.result).toEqual(returned)
    expect(h.called('result')[0]?.stdin).toEqual({ result: expected, is_error: false })
  })
}

test('an errored result of any form reaches the engine as an object and goes out as a denial', async ($, on) => {
  const h = fakeHost(on, {
    mcpResult: () => ({ result: 'Object web-srv-01 not found', isError: true }),
  })
  await $.session.start(SESSION_START)
  const out = await callMcp($)
  expect(out.deny).toBe('PSEUDONYMIZED')
  expect(h.called('result')[0]?.stdin).toEqual({
    result: { content: [{ type: 'text', text: 'Object web-srv-01 not found' }], isError: true },
    is_error: true,
  })
})

test('a refusal by the engine names its code, never a value', async ($, on) => {
  fakeHost(on, { engine: { result: () => ({ exit: 2, out: { error: { code: 'bad-json' } } }) } })
  await $.session.start(SESSION_START)
  const out = await callMcp($)
  expect(out.deny).toBe('privacy guard: result withheld by privacy guard (bad-json)')
})
