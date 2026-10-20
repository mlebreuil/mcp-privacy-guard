// Reveal on the user's own terminal: stand-ins in drawn rows become real values (FR-021..FR-023).
// A render rewrite changes the drawing only; the model and the transcript keep the stand-ins.
import type { EngineInterface, On } from 'claude-code'
import { runEngine } from './engine'
import { state } from './state'

const UNKNOWN = '(?)'
// Characters a stand-in can sit between; a candidate starts and ends at one of them.
const RUN = /[^\s"'<>(),;=[\]{}|*`]+/g
const SEPARATOR = /[/@:\\.-]/
const TRAILING = /[.,:;!?]+$/
const MAX_BOUNDARIES = 32

let recogniseSource = ''
let recogniseRegex: RegExp | null = null

function recognise(): RegExp | null {
  if (state.recognise === '') return null
  if (state.recognise !== recogniseSource) {
    recogniseSource = state.recognise
    try {
      recogniseRegex = new RegExp(`^(?:${state.recognise})$`)
    } catch {
      recogniseRegex = null
    }
  }
  return recogniseRegex
}

export type Segment = { text: string; revealed: boolean }

function candidateEdges(run: string): { starts: number[]; ends: number[] } {
  const starts = [0]
  const ends: number[] = []
  for (let i = 0; i < run.length && starts.length < MAX_BOUNDARIES; i++) {
    if (SEPARATOR.test(run[i] as string)) {
      starts.push(i + 1)
      ends.push(i)
    }
  }
  ends.push(run.length)
  const trimmed = run.replace(TRAILING, '').length
  if (trimmed !== run.length) ends.push(trimmed)
  return { starts, ends: [...new Set(ends)].sort((a, b) => b - a) }
}

/** Splits `text` into plain and revealed pieces; also counts unknown name-shaped stand-ins. */
export function revealSegments(text: string, mark = true): Segment[] {
  const map = state.reveal.map
  const known = recognise()
  const out: Segment[] = []
  let plain = 0
  const flush = (to: number) => {
    if (to > plain) out.push({ text: text.slice(plain, to), revealed: false })
  }
  for (const run of text.matchAll(RUN)) {
    const base = run.index ?? 0
    const word = run[0]
    if (map.size === 0 && known === null) continue
    const { starts, ends } = candidateEdges(word)
    let at = 0
    while (at < word.length) {
      let hit: { from: number; to: number; real: string } | null = null
      for (const from of starts) {
        if (from < at) continue
        for (const to of ends) {
          if (to <= from) continue
          const entry = map.get(word.slice(from, to))
          if (entry !== undefined) {
            hit = { from, to, real: entry.real }
            break
          }
        }
        if (hit !== null) break
      }
      if (hit === null) break
      flush(base + hit.from)
      out.push({ text: hit.real, revealed: true })
      plain = base + hit.to
      at = hit.to
    }
    if (mark && known !== null) {
      // unknown name-shaped stand-ins left in the part of the run not revealed
      for (const piece of word.slice(at).split(/[/@:\\.]/)) {
        const bare = piece.replace(TRAILING, '')
        if (bare !== '' && known.test(bare) && !map.has(bare)) {
          const end = base + word.indexOf(bare, at) + bare.length
          if (end > plain) {
            flush(end)
            out.push({ text: UNKNOWN, revealed: false })
            plain = end
          }
        }
      }
    }
  }
  flush(text.length)
  return out
}

export function revealText(text: string, mark = true): string {
  return revealSegments(text, mark).map(s => s.text).join('')
}

const FENCE = /(```[\s\S]*?```|`[^`\n]*`)/

/** Markdown: revealed values outside code are bold, inside code they stay plain. */
function revealMarkdown(text: string): string {
  return text
    .split(FENCE)
    .map((part, i) =>
      i % 2 === 1
        ? revealText(part)
        : revealSegments(part).map(s => (s.revealed ? `**${s.text}**` : s.text)).join(''),
    )
    .join('')
}

function revealDeep(value: unknown, depth = 0): unknown {
  if (typeof value === 'string') return revealText(value)
  if (depth > 32 || typeof value !== 'object' || value === null) return value
  if (Array.isArray(value)) return value.map(v => revealDeep(v, depth + 1))
  return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, revealDeep(v, depth + 1)]))
}

async function mayReveal($: EngineInterface, surface: string): Promise<boolean> {
  if (surface !== 'terminal' || !state.revealAllowed || state.sessionId === null) return false
  return (await $.session.id()) === state.sessionId
}

/** Ask the rows drawn so far to draw again after new table entries arrived. Never throws. */
export async function invalidateRows($: EngineInterface, since: number): Promise<void> {
  if (state.reveal.rev === since) return
  try {
    $.ui.invalidate('ui.render')
  } catch {
    // only the display is affected
  }
}

export function registerReveal(on: On): void {
  on('session.attach', { surface: 'terminal' }, async ($, e, next) => {
    state.revealAllowed = false
    try {
      await $.ui.toast('privacy guard: another client claims to be a terminal; reveal is off')
    } catch {
      // the reveal is off whether or not the toast shows
    }
    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    if (state.sessionId === null || !state.ready || e.answer === '') return result
    const before = state.reveal.rev
    try {
      await runEngine($, ['observe', '--session', state.sessionId, '--since', String(before)], {
        text: e.answer,
      })
      await invalidateRows($, before)
    } catch {
      // it only affects display
    }
    return result
  })

  on('ui.render', { component: 'AssistantMessage' }, async ($, e, next) => {
    if (!(await mayReveal($, e.surface))) return next(e)
    return next({ ...e, props: { ...e.props, text: revealMarkdown(e.props.text) } } as typeof e)
  }).catch((_$, e, next) => next(e))

  on('ui.render', { component: 'ToolUse' }, async ($, e, next) => {
    if (!(await mayReveal($, e.surface))) return next(e)
    const props = { ...e.props, input: revealDeep(e.props.input), output: revealDeep(e.props.output) }
    return next({ ...e, props } as typeof e)
  }).catch((_$, e, next) => next(e))

  on('ui.render', { component: 'ToolResult' }, async ($, e, next) => {
    if (!(await mayReveal($, e.surface))) return next(e)
    return next({ ...e, props: { ...e.props, output: revealDeep(e.props.output) } } as typeof e)
  }).catch((_$, e, next) => next(e))

  on('ui.render', { component: 'UserMessage' }, async ($, e, next) => {
    if (!(await mayReveal($, e.surface))) return next(e)
    const segments = revealSegments(e.props.text)
    if (!segments.some(s => s.revealed || s.text === UNKNOWN)) return next(e)
    if (e.props.origin.kind !== 'composer') {
      return next({ ...e, props: { ...e.props, text: segments.map(s => s.text).join('') } } as typeof e)
    }
    const { Box, Text } = $.ui.resolve(e)
    return h(
      Box,
      { flexDirection: 'row' },
      h(Text, { dimColor: true }, '> '),
      h(
        Text,
        null,
        ...segments.map(s =>
          s.revealed
            ? h(Text, { underline: true }, s.text)
            : s.text === UNKNOWN
              ? h(Text, { dimColor: true }, s.text)
              : s.text,
        ),
      ),
    ) as never
  }).catch((_$, e, next) => next(e))
}
