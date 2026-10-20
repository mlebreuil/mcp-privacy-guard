import { expect, test } from 'claude-code/testing'
import { revealText } from './reveal'
import { clearReveal, mergeTable } from './state'

// SC-005, research R10: a 4 KB row with a 100k-entry table is revealed in at most 4 ms.
test('revealing a 4 KB row with 100k table entries takes at most 4 ms (median of 50)', () => {
  clearReveal()
  const entries = Array.from({ length: 100_000 }, (_, i) => ({
    standin: `n-${i.toString(32).padStart(6, 'a')}`.replace(/[0189]/g, 'b'),
    real: `Real Name ${i}`,
    kind: 'NAME',
  }))
  mergeTable({ rev: 1, entries })
  const row = Array.from({ length: 160 }, (_, i) => `rule n-${'abcdef'.slice(i % 3)}${i} ok`).join('; ')
    .padEnd(4096, ' filler text, 10.83.4.12 and n-zzzzzz')
    .slice(0, 4096)
  revealText(row) // warm the compiled structures
  const times: number[] = []
  for (let i = 0; i < 50; i++) {
    const start = performance.now()
    revealText(row)
    times.push(performance.now() - start)
  }
  times.sort((a, b) => a - b)
  expect(times[25] ?? Infinity).toBeLessThanOrEqual(4)
  clearReveal()
})
