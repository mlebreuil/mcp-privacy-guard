import type { Register } from 'claude-code'
import { registerCommand } from './command'
import { registerGuard } from './guard'
import { registerMcp } from './mcp'
import { registerPrompt } from './prompt'
import { registerReveal } from './reveal'
import { registerSession } from './session'
import { state } from './state'
import { registerStatus } from './status'

export const register: Register = (on, options) => {
  const path = options.enginePath
  state.config.enginePath = typeof path === 'string' && path !== '' ? path : 'mcp-privacy-guard'
  state.priorId = null
  state.clearedIds.clear()
  registerSession(on)
  registerGuard(on)
  registerMcp(on)
  registerPrompt(on)
  registerCommand(on)
  registerReveal(on)
  registerStatus(on)
}
