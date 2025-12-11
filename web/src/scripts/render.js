import { state, resetState } from './state.js'
import { dom } from './dom.js'
import { testCard, suiteCard, failureCard } from './components.js'
import { extractSuitePath } from './utils.js'

export function clearAll() {
  resetState()
  dom.suitesContainer.innerHTML = ''
  dom.failuresList.innerHTML = ''
  dom.failuresPanel.dataset.state = 'empty'
  dom.failuresCount.textContent = '(0)'
  dom.emptyState.style.display = 'flex'
  dom.timer.textContent = '0.00s'
  dom.timer.classList.remove('timer-running')
  dom.sessionTarget.textContent = 'Waiting for session...'
  renderStats()
  renderProgress()
}

export function renderConnection(connected) {
  const dotState = connected ? 'connected' : 'disconnected'
  const text = connected ? 'Live' : 'Disconnected'
  dom.connectionDot.dataset.state = dotState
  dom.connectionText.textContent = text
}

export function renderSessionInfo(target) {
  dom.sessionTarget.textContent = target
}

export function renderStats() {
  for (const [key, value] of Object.entries(state.stats)) {
    if (dom.stats[key]) {
      dom.stats[key].textContent = value
    }
  }
}

export function renderProgress() {
  const completed = Object.values(state.stats).reduce((acc, val) => acc + val, 0)
  const total = state.totalTests || completed || 1

  for (const [key, value] of Object.entries(state.stats)) {
    if (dom.progress[key]) {
      dom.progress[key].style.width = `${(value / total) * 100}%`
    }
  }

  dom.progressText.textContent = `${completed} / ${state.totalTests || '?'}`
}

export function renderTimer() {
  if (!state.startTime) return
  const elapsed = (Date.now() - state.startTime) / 1000
  dom.timer.textContent = `${elapsed.toFixed(2)}s`
}

export function appendTest(payload) {
  dom.emptyState.style.display = 'none'

  const suitePath = extractSuitePath(payload.nodeId)
  let suiteEl = dom.suitesContainer.querySelector(`[data-suite="${CSS.escape(suitePath)}"]`)

  if (!suiteEl) {
    dom.suitesContainer.insertAdjacentHTML('beforeend', suiteCard(suitePath))
    suiteEl = dom.suitesContainer.querySelector(`[data-suite="${CSS.escape(suitePath)}"]`)
    state.suites.set(suitePath, { pass: 0, fail: 0 })
  }

  const testsContainer = suiteEl.querySelector('.suite-tests')
  testsContainer.insertAdjacentHTML('beforeend', testCard(payload))

  const suiteStats = state.suites.get(suitePath)
  if (payload.outcome === 'pass') suiteStats.pass++
  if (payload.outcome === 'fail' || payload.outcome === 'error') {
    suiteStats.fail++
    suiteEl.setAttribute('open', '')
  }

  suiteEl.querySelector('[data-type="pass"]').textContent = suiteStats.pass
  suiteEl.querySelector('[data-type="fail"]').textContent = suiteStats.fail
}

export function appendFailure(payload) {
  state.failures.push(payload)
  dom.failuresPanel.dataset.state = 'expanded'
  dom.failuresCount.textContent = `(${state.failures.length})`
  dom.failuresList.insertAdjacentHTML('beforeend', failureCard(payload))
}

export function renderFinalSummary() {
  if (state.timerInterval) {
    clearInterval(state.timerInterval)
  }
  dom.timer.classList.remove('timer-running')
}
