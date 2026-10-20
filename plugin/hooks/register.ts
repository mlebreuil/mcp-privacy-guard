import type { Register } from 'claude-code'
import { registerGuard } from './guard'
import { registerSession } from './session'
import { state } from './state'

export const register: Register = (on, options) => {
  const path = options.enginePath
  state.config.enginePath = typeof path === 'string' && path !== '' ? path : 'mcp-privacy-guard'
  registerSession(on)
  registerGuard(on)
}
