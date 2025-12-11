import { state } from './state.js'
import { dom } from './dom.js'
import { renderConnection } from './render.js'
import { handleMessage } from './handlers.js'

export function connectWebSocket() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${protocol}//${location.host}/ws`

  dom.connectionDot.dataset.state = 'connecting'
  dom.connectionText.textContent = 'Connecting...'

  const ws = new WebSocket(wsUrl)

  ws.onopen = () => {
    state.connected = true
    dom.connectionDot.dataset.state = 'connected'
    dom.connectionText.textContent = 'Waiting...'
  }

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)
      handleMessage(msg)
    } catch (err) {
      console.error('Failed to parse message:', err)
    }
  }

  ws.onclose = () => {
    state.connected = false
    dom.connectionDot.dataset.state = 'disconnected'
    dom.connectionText.textContent = 'Disconnected'
    setTimeout(connectWebSocket, 2000)
  }

  ws.onerror = (err) => {
    console.error('WebSocket error:', err)
  }
}
