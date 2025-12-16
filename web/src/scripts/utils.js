export function escapeHtml(text) {
  const div = document.createElement('div')
  div.textContent = text
  return div.innerHTML
}

export function formatDuration(seconds) {
  if (seconds < 0.001) return '<1ms'
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`
  return `${seconds.toFixed(2)}s`
}

export function extractTestName(nodeId) {
  const parts = nodeId.split('::')
  return parts[parts.length - 1]
}

export function extractSuitePath(nodeId) {
  const parts = nodeId.split('::')
  if (parts.length <= 2) return '__root__'
  return parts.slice(1, -1).join('::')
}
