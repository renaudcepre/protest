export const state = {
  sessionTarget: null,
  totalTests: 0,
  stats: { pass: 0, fail: 0, skip: 0, xfail: 0, error: 0 },
  suites: new Map(),
  startTime: null,
  timerInterval: null,
  connected: false,
}

export function resetState() {
  state.sessionTarget = null
  state.totalTests = 0
  state.stats = { pass: 0, fail: 0, skip: 0, xfail: 0, error: 0 }
  state.suites = new Map()
  state.startTime = null
  if (state.timerInterval) {
    clearInterval(state.timerInterval)
    state.timerInterval = null
  }
  state.connected = false
}
