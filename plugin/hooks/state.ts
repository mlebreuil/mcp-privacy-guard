// Module memory only. Nothing here is written to `$.store`, `$.state` or disk (Principle II).

export type ServerInfo = {
  profile: string
  profile_state: string
  profile_reason?: string
  exempt: boolean
  warmup_state?: string
  warmup?: { tool: string; args: Record<string, unknown> }[]
}

export type TableEntry = { standin: string; real: string; kind: string }

export const state = {
  /** The session the reveal table and the checks belong to; null before the first check. */
  sessionId: null as string | null,
  /** The last session id this process saw, and the ids that followed another one (a /clear). */
  priorId: null as string | null,
  clearedIds: new Set<string>(),
  /** true only after every precondition passed in this process; a failed start leaves it false. */
  ready: false,
  /** Why the guard blocks questions and protected results; null when it is active. */
  blockReason: null as string | null,
  /** `<home>` as the engine reports it, once known. */
  home: '',
  servers: {} as Record<string, ServerInfo>,
  /** The MCP servers seen connected at the last listing (sorted, joined by a comma). */
  connected: '',
  /** Servers whose warm-up this process is running now, and the progress of the batch. */
  warming: new Set<string>(),
  warmDone: 0,
  warmTotal: 0,
  recognise: '',
  /** false after a remote client attached claiming to be a terminal (research R1). */
  revealAllowed: true,
  config: { enginePath: 'mcp-privacy-guard' },
  /** The reveal table: stand-in -> real value, for the current session only. */
  reveal: { rev: 0, map: new Map<string, { real: string; kind: string }>() },
}

export function clearReveal(): void {
  state.reveal.rev = 0
  state.reveal.map.clear()
}

export function mergeTable(table: { rev: number; entries: TableEntry[] } | undefined): void {
  if (table === undefined) return
  for (const entry of table.entries) {
    state.reveal.map.set(entry.standin, { real: entry.real, kind: entry.kind })
  }
  state.reveal.rev = table.rev
}

/** What the model reads when a protected result is withheld. */
export const WITHHELD = 'privacy guard: result withheld by privacy guard'
