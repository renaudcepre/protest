import { state } from './state.js'
import { dom } from './dom.js'
import {
  clearAll,
  renderSessionInfo,
  renderStats,
  renderProgress,
  renderTimer,
  appendTest,
  appendFailure,
  renderFinalSummary,
} from './render.js'

export const handlers = {
  SESSION_START(payload) {
    clearAll()
    state.sessionTarget = payload.target
    state.totalTests = payload.totalTests
    state.startTime = Date.now()
    state.timerInterval = setInterval(renderTimer, 100)
    dom.timer.classList.add('timer-running')
    dom.emptyState.style.display = 'none'
    renderSessionInfo(payload.target)
    renderProgress()
  },

  TEST_PASS(payload) {
    state.stats.pass++
    appendTest({ ...payload, outcome: 'pass' })
    renderStats()
    renderProgress()
  },

  TEST_FAIL(payload) {
    state.stats.fail++
    appendTest({ ...payload, outcome: 'fail' })
    appendFailure(payload)
    renderStats()
    renderProgress()
  },

  TEST_SKIP(payload) {
    state.stats.skip++
    appendTest({ ...payload, outcome: 'skip' })
    renderStats()
    renderProgress()
  },

  TEST_XFAIL(payload) {
    state.stats.xfail++
    appendTest({ ...payload, outcome: 'xfail' })
    renderStats()
    renderProgress()
  },

  TEST_ERROR(payload) {
    state.stats.error++
    appendTest({ ...payload, outcome: 'error' })
    appendFailure(payload)
    renderStats()
    renderProgress()
  },

  SESSION_END(payload) {
    renderFinalSummary()
    renderConnection(false)
  },
}

export function handleMessage(msg) {
  const handler = handlers[msg.type]
  if (handler) {
    handler(msg.payload)
  } else {
    console.warn('Unknown message type:', msg.type)
  }
}
