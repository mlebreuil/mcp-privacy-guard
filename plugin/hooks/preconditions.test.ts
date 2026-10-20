import { expect, test } from 'claude-code/testing'
import { register } from './register'
import { GOOD_SETTINGS, HOME, SESSION_START, SID, fakeHost, type Host } from './test-support'

void register

const REASON = {
  terminal: 'privacy guard: use Claude Code in a terminal',
  resumed:
    'privacy guard: this conversation is from an ended session; start a new one (/clear)',
}

const withSandbox = (patch: Record<string, unknown>) => ({
  sandbox: { ...GOOD_SETTINGS.sandbox, ...patch },
})

// Each case is its own test: the hooks beneath the plugins are registered once per test.
for (const surfaces of [[], ['desktop'], ['vscode']]) {
  test(`a session drawn on [${surfaces.join(',')}] has no terminal and blocks`, async ($, on) => {
    const h = fakeHost(on, { surfaces })
    await $.session.start(SESSION_START)
    expect(h.status()).toContain(REASON.terminal)
  })
}

const sandboxCases: [string, Record<string, unknown>, string][] = [
  ['not enabled', withSandbox({ enabled: false }), 'sandbox.enabled'],
  [
    'home not read-denied',
    withSandbox({ filesystem: { denyRead: ['/other'] } }),
    'sandbox.filesystem.denyRead',
  ],
  [
    'unsandboxed commands allowed',
    withSandbox({ allowUnsandboxedCommands: true }),
    'sandbox.allowUnsandboxedCommands',
  ],
  ['silent fallback allowed', withSandbox({ failIfUnavailable: false }), 'sandbox.failIfUnavailable'],
  [
    'filesystem isolation off',
    withSandbox({ filesystem: { denyRead: [HOME], disabled: true } }),
    'sandbox.filesystem.disabled',
  ],
  [
    'allowRead re-opens home',
    withSandbox({ filesystem: { denyRead: [HOME], allowRead: [HOME] } }),
    'sandbox.filesystem.allowRead',
  ],
  ['no settings at all', {}, 'sandbox.enabled'],
]
for (const [name, settings, key] of sandboxCases) {
  test(`sandbox settings (${name}) block and name ${key}`, async ($, on) => {
    const h = fakeHost(on, { settings })
    await $.session.start(SESSION_START)
    expect(h.status()).toContain(key)
    expect(h.status()).toContain('privacy guard')
  })
}

test('a read-deny on the parent folder or in tilde form counts', async ($, on) => {
  const h = fakeHost(on, {
    settings: withSandbox({ filesystem: { denyRead: ['~/.config'] } }),
  })
  await $.session.start(SESSION_START)
  expect(h.status()).toBe('privacy-guard: active · 1 protected · 0 exempt')
})

test('a host older than 2.1.303 blocks', async ($, on) => {
  const h = fakeHost(on, { version: '2.1.302' })
  await $.session.start(SESSION_START)
  expect(h.status()).toContain('2.1.303')
})

const brokenEngines: [string, Host['engine']][] = [
  ['exit 5', { status: () => ({ exit: 5 }) }],
  ['not JSON', { status: () => ({ raw: 'not json' }) }],
  ['cannot start', { status: () => ({ reject: true }) }],
  ['exit 3', { status: () => ({ exit: 3 }) }],
]
for (const [name, engine] of brokenEngines) {
  test(`an engine that fails (${name}) blocks`, async ($, on) => {
    const h = fakeHost(on, { engine })
    await $.session.start(SESSION_START)
    expect(h.status()).toContain('privacy guard')
    expect(h.status()).not.toContain('active')
    expect(h.called('begin').length).toBe(0)
  })
}

for (const turns of [3, 'throw' as const]) {
  test(`a resumed conversation (turns: ${turns}) blocks and does not begin`, async ($, on) => {
    const h = fakeHost(on, { turns })
    await $.session.start(SESSION_START)
    expect(h.status()).toContain(REASON.resumed)
    expect(h.called('begin').length).toBe(0)
  })
}

test('a fresh session begins with the connected servers', async ($, on) => {
  const h = fakeHost(on, {
    turns: 0,
    servers: { generic: { exempt: false }, notion: { exempt: true } },
    connected: ['generic', 'notion'],
  })
  await $.session.start(SESSION_START)
  const [begin] = h.called('begin')
  expect(begin?.argv[begin.argv.indexOf('--session') + 1]).toBe(SID)
  expect(begin?.argv[begin.argv.indexOf('--servers') + 1]).toBe('generic,notion')
  expect(h.status()).toContain('active')
})

test('a live session neither begins nor blocks', async ($, on) => {
  const h = fakeHost(on, { live: new Set([SID]), turns: 4 })
  await $.session.start(SESSION_START)
  expect(h.called('begin').length).toBe(0)
  expect(h.status()).toContain('active')
})

test('every precondition met clears the block reason', async ($, on) => {
  const h = fakeHost(on, { settings: {} })
  await $.session.start(SESSION_START)
  expect(h.status()).toContain('sandbox.enabled')
  h.settings = GOOD_SETTINGS
  await $.session.start(SESSION_START)
  expect(h.status()).toBe('privacy-guard: active · 1 protected · 0 exempt')
})

test('the plugin calls the engine command named by its option', async ($, on) => {
  const h = fakeHost(on)
  await $.session.start(SESSION_START)
  expect(h.calls.length).toBeGreaterThan(0)
  expect(h.calls.every(c => c.argv[0] === 'mcp-privacy-guard')).toBe(true)
})
