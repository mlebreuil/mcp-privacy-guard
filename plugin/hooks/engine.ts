// The only way the plugin talks to the engine: a local command, JSON over stdin and stdout.
import type { EngineInterface } from 'claude-code'
import { mergeTable, state, type TableEntry } from './state'

export class EngineError extends Error {
  constructor(
    readonly exitCode: number,
    readonly code: string,
    /** The engine's error object: `servers`, `reason`, `hint`. Never a value from the input. */
    readonly details: Record<string, unknown> = {},
  ) {
    super(code)
  }
}

/** Per-call timeouts in milliseconds (contracts/claude-code-plugin.md). */
export const TIMEOUTS: Record<string, number> = {
  prompt: 5000,
  args: 5000,
  result: 15000,
  begin: 5000,
  warmup: 5000,
  end: 1000,
}
const DEFAULT_TIMEOUT = 30000

export type Reply = Record<string, unknown> & {
  table?: { rev: number; entries: TableEntry[] }
}

/**
 * Runs `<enginePath> <subcommand> ...args`. Resolves with the parsed reply (the reveal-table
 * entries it carries are merged into module memory) or throws an EngineError on a non-zero
 * exit, a timeout, a command that cannot start or a reply that is not JSON.
 */
export async function runEngine(
  $: EngineInterface,
  args: readonly string[],
  stdin?: unknown,
  timeoutMs?: number,
): Promise<Reply> {
  const sub = args[0] ?? ''
  const argv = [state.config.enginePath, ...args]
  let done: { exitCode: number; stdout: string }
  try {
    done = await $.process.run(argv, {
      stdin: stdin === undefined ? undefined : JSON.stringify(stdin),
      timeoutMs: timeoutMs ?? TIMEOUTS[sub] ?? DEFAULT_TIMEOUT,
    })
  } catch {
    throw new EngineError(-1, 'engine-unavailable')
  }
  let body: unknown
  try {
    body = JSON.parse(done.stdout)
  } catch {
    throw new EngineError(done.exitCode || 5, 'bad-reply')
  }
  if (done.exitCode !== 0) {
    const error = (body as { error?: Record<string, unknown> } | null)?.error ?? {}
    throw new EngineError(
      done.exitCode,
      typeof error.code === 'string' ? error.code : 'error',
      error,
    )
  }
  if (typeof body !== 'object' || body === null) throw new EngineError(5, 'bad-reply')
  const reply = body as Reply
  mergeTable(reply.table)
  return reply
}
