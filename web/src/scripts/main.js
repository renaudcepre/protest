import '../styles/main.css'
import { initDom, dom } from './dom.js'
import { connectWebSocket } from './websocket.js'

function initSuiteToggle() {
  dom.suitesContainer.addEventListener('click', (event) => {
    const header = event.target.closest('.suite-header')
    if (!header) return
    const suite = header.closest('.suite')
    suite.classList.toggle('expanded')
  })
}

function initHidePassedToggle() {
  const checkbox = document.getElementById('hide-passed')
  checkbox.addEventListener('change', () => {
    document.body.classList.toggle('hide-passed', checkbox.checked)
  })
}

function initTooltip() {
  const tooltip = document.getElementById('tooltip')

  dom.suitesContainer.addEventListener('mouseover', (event) => {
    const cell = event.target.closest('.test-cell')
    if (!cell || !cell.dataset.tooltip) return

    tooltip.textContent = cell.dataset.tooltip
    tooltip.classList.add('visible')

    const rect = cell.getBoundingClientRect()
    let left = rect.left + rect.width / 2 - tooltip.offsetWidth / 2
    let top = rect.top - tooltip.offsetHeight - 4

    if (left < 4) left = 4
    if (left + tooltip.offsetWidth > window.innerWidth - 4) {
      left = window.innerWidth - tooltip.offsetWidth - 4
    }
    if (top < 4) {
      top = rect.bottom + 4
    }

    tooltip.style.left = `${left}px`
    tooltip.style.top = `${top}px`
  })

  dom.suitesContainer.addEventListener('mouseout', (event) => {
    const cell = event.target.closest('.test-cell')
    if (!cell) return
    tooltip.classList.remove('visible')
  })

  dom.suitesContainer.addEventListener('click', (event) => {
    const cell = event.target.closest('.test-cell')
    if (!cell) return

    const nodeId = cell.dataset.nodeId
    const testEl = dom.suitesContainer.querySelector(`.test[data-node-id="${CSS.escape(nodeId)}"]`)
    if (testEl) {
      const suite = testEl.closest('.suite')
      if (suite) suite.classList.add('expanded')
      testEl.setAttribute('open', '')
      testEl.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  })
}

function init() {
  initDom()
  initSuiteToggle()
  initHidePassedToggle()
  initTooltip()
  connectWebSocket()
}

document.addEventListener('DOMContentLoaded', init)
