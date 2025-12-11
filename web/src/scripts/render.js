import { state, resetState } from './state.js'
import { dom } from './dom.js'
import { testCard, suiteCard } from './components.js'
import { extractSuitePath } from './utils.js'

export function clearAll() {
  resetState()
  dom.suitesContainer.innerHTML = ''
  dom.emptyState.style.display = 'flex'
  dom.timer.textContent = '0.00s'
  dom.timer.classList.remove('timer-running')
  dom.sessionTarget.textContent = 'Waiting for session...'
  const checkbox = document.getElementById('hide-passed')
  checkbox.checked = false
  document.body.classList.remove('hide-passed')
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
    state.suites.set(suitePath, { pass: 0, fail: 0, expanded: false })
  }

  const grid = suiteEl.querySelector('.test-grid')
  const nodeIdEscaped = CSS.escape(payload.nodeId)
  let cell = grid.querySelector(`[data-node-id="${nodeIdEscaped}"]`)

  if (!cell) {
    cell = document.createElement('div')
    cell.className = 'test-cell'
    cell.dataset.nodeId = payload.nodeId
    grid.appendChild(cell)
  }
  cell.dataset.state = payload.outcome

  const testName = payload.nodeId.split('::').pop()
  const duration = payload.duration !== undefined ? ` (${payload.duration < 1 ? Math.round(payload.duration * 1000) + 'ms' : payload.duration.toFixed(2) + 's'})` : ''
  cell.dataset.tooltip = `${testName}${duration}`

  const testsContainer = suiteEl.querySelector('.suite-tests')
  const existingTestEl = testsContainer.querySelector(`[data-node-id="${nodeIdEscaped}"]`)
  if (existingTestEl) {
    existingTestEl.outerHTML = testCard(payload)
  } else {
    testsContainer.insertAdjacentHTML('beforeend', testCard(payload))
  }

  const suiteStats = state.suites.get(suitePath)
  if (payload.outcome === 'pass') suiteStats.pass++
  if (payload.outcome === 'fail' || payload.outcome === 'error') suiteStats.fail++

  suiteEl.querySelector('[data-type="pass"]').textContent = suiteStats.pass
  suiteEl.querySelector('[data-type="fail"]').textContent = suiteStats.fail
}

export function renderFinalSummary() {
  if (state.timerInterval) {
    clearInterval(state.timerInterval)
  }
  dom.timer.classList.remove('timer-running')
}

export function updateTestCell(nodeId, cellState) {
  const suitePath = extractSuitePath(nodeId)
  let suiteEl = dom.suitesContainer.querySelector(`[data-suite="${CSS.escape(suitePath)}"]`)

  if (!suiteEl) {
    dom.suitesContainer.insertAdjacentHTML('beforeend', suiteCard(suitePath))
    suiteEl = dom.suitesContainer.querySelector(`[data-suite="${CSS.escape(suitePath)}"]`)
    state.suites.set(suitePath, { pass: 0, fail: 0, expanded: false })
  }

  const grid = suiteEl.querySelector('.test-grid')
  const nodeIdEscaped = CSS.escape(nodeId)
  let cell = grid.querySelector(`[data-node-id="${nodeIdEscaped}"]`)

  if (!cell) {
    cell = document.createElement('div')
    cell.className = 'test-cell'
    cell.dataset.nodeId = nodeId
    const testName = nodeId.split('::').pop()
    cell.dataset.tooltip = testName
    grid.appendChild(cell)
  }

  cell.dataset.state = cellState

  const testsContainer = suiteEl.querySelector('.suite-tests')
  const testElEscaped = CSS.escape(nodeId)
  let testEl = testsContainer.querySelector(`[data-node-id="${testElEscaped}"]`)

  if (!testEl && cellState === 'pending') {
    testsContainer.insertAdjacentHTML('beforeend', testCard({ nodeId, outcome: 'pending' }))
  }

  dom.emptyState.style.display = 'none'
}
