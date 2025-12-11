import '../styles/main.css'
import { initDom, dom } from './dom.js'
import { connectWebSocket } from './websocket.js'

function initFailuresToggle() {
  document.getElementById('failures-header').addEventListener('click', () => {
    const panel = dom.failuresPanel
    if (panel.dataset.state === 'expanded') {
      panel.dataset.state = 'collapsed'
    } else if (panel.dataset.state === 'collapsed') {
      panel.dataset.state = 'expanded'
    }
  })
}

function init() {
  initDom()
  initFailuresToggle()
  connectWebSocket()
}

document.addEventListener('DOMContentLoaded', init)
