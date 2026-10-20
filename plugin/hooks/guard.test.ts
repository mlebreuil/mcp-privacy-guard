import type { On } from 'claude-code'
import { expect, test } from 'claude-code/testing'
import type { Engine } from 'claude-code/testing'
import { register } from './register'
import { HOME, SESSION_START, SID, fakeHost } from './test-support'

void register

const STORE = `${HOME}/store/sessions/${SID}`
let host: ReturnType<typeof fakeHost>

async function setup($: Engine, on: On) {
  host = fakeHost(on)
  await $.session.start(SESSION_START)
}

const call = ($: Engine, input: Record<string, unknown>) =>
  ($.tool as unknown as { call: (i: unknown) => Promise<{ deny?: string }> }).call({
    tool_use_id: 't1',
    ...input,
  })

const denied: [string, Record<string, unknown>][] = [
  ['Read of the mapping', { tool: 'Read', file_path: `${STORE}/mapping.sqlite` }],
  ['Read of the secret', { tool: 'Read', file_path: `${STORE}/secret.key` }],
  ['Read with a tilde path', { tool: 'Read', file_path: '~/.config/mcp-privacy-guard/store/x' }],
  ['Grep under home', { tool: 'Grep', pattern: 'a', path: HOME }],
  ['Glob under home', { tool: 'Glob', pattern: `${HOME}/**` }],
  ['Bash table', { tool: 'Bash', command: 'mcp-privacy-guard table --session s-1 --since 0' }],
  ['Bash reveal', { tool: 'Bash', command: 'echo n-abc | mcp-privacy-guard reveal' }],
  ['Bash module', { tool: 'Bash', command: 'python3 -m mcp_privacy_guard status' }],
  ['Edit settings.json (project)', { tool: 'Edit', file_path: '/proj/.claude/settings.json', old_string: 'a', new_string: 'b' }],
  ['Edit settings.local.json', { tool: 'Edit', file_path: '/proj/.claude/settings.local.json', old_string: 'a', new_string: 'b' }],
  ['Write user settings', { tool: 'Write', file_path: '~/.claude/settings.json', content: '{}' }],
  ['Write claude.json', { tool: 'Write', file_path: '~/.claude.json', content: '{}' }],
  ['Write under plugins', { tool: 'Write', file_path: '~/.claude/plugins/x/y.json', content: '{}' }],
  ['Bash writing user settings', { tool: 'Bash', command: 'echo {} > ~/.claude/settings.json' }],
  ['Bash escaping the sandbox', { tool: 'Bash', command: 'ls', dangerouslyDisableSandbox: true }],
]

for (const [name, input] of denied) {
  test(`denies ${name}`, async ($, on) => {
    await setup($, on)
    const out = await call($, input)
    expect(out.deny).toContain('privacy guard')
  })
}

test('denies edits inside the plugin folder', async ($, on) => {
  await setup($, on)
  const root = host.pluginRoot
  expect(root).not.toBe('')
  for (const tool of ['Edit', 'Write']) {
    const out = await call($, { tool, file_path: `${root}/hooks/guard.ts`, old_string: 'a', new_string: 'b', content: 'x' })
    expect(out.deny).toContain('privacy guard')
  }
})

test('lets an unrelated Read through', async ($, on) => {
  await setup($, on)
  const out = await call($, { tool: 'Read', file_path: '/proj/README.md' })
  expect(host.called('status').length).toBeGreaterThan(0) // the plugin's hooks ran
  expect(out.deny).toBeUndefined()
})

test('a throw inside the guard still denies', async ($, on) => {
  const h = fakeHost(on)
  await $.session.start(SESSION_START)
  h.idFails = true // the guard reads the session id first, which now fails
  const out = await call($, { tool: 'Read', file_path: '/proj/README.md' })
  expect(out.deny).toContain('privacy guard')
})
