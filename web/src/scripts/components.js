import { escapeHtml, formatDuration, extractTestName } from './utils.js'
import { highlightTraceback } from './syntax.js'

export const ICONS = {
  pass: '\u2713',
  fail: '\u2717',
  skip: '\u25CB',
  xfail: '\u2717',
  xpass: '\u2713',
  error: '!',
  running: '\u25CF',
  chevron: `<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M6 4l4 4-4 4"/></svg>`,
}

export function testCard({ nodeId, outcome, duration, message, traceback }) {
  const testName = extractTestName(nodeId)
  const icon = ICONS[outcome] || '?'
  const hasFailed = outcome === 'fail' || outcome === 'error'

  if (hasFailed) {
    return `
      <div class="test test--failed" data-outcome="${outcome}" data-node-id="${escapeHtml(nodeId)}">
        <span class="test-icon" data-outcome="${outcome}">${icon}</span>
        <span class="test-name">${escapeHtml(testName)}</span>
        ${message ? `<span class="test-message">${escapeHtml(message)}</span>` : ''}
        ${duration !== undefined ? `<span class="test-duration">${formatDuration(duration)}</span>` : ''}
        ${traceback ? tracebackDetails(traceback) : ''}
      </div>
    `
  }

  return `
    <div class="test" data-outcome="${outcome}" data-node-id="${escapeHtml(nodeId)}">
      <span class="test-icon" data-outcome="${outcome}">${icon}</span>
      <span class="test-name">${escapeHtml(testName)}</span>
      ${duration !== undefined ? `<span class="test-duration">${formatDuration(duration)}</span>` : ''}
    </div>
  `
}

export function tracebackDetails(content) {
  return `
    <details class="traceback">
      <summary class="traceback-toggle">
        <span class="chevron">${ICONS.chevron}</span>
        Traceback
      </summary>
      <div class="traceback-content">
        <pre>${highlightTraceback(content)}</pre>
      </div>
    </details>
  `
}

export function suiteCard(name) {
  const displayName = name === '__root__' ? 'Tests' : name
  return `
    <div class="suite" data-suite="${escapeHtml(name)}">
      <div class="suite-header">
        <svg class="suite-chevron" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M6 4l4 4-4 4"/>
        </svg>
        <span class="suite-name">${escapeHtml(displayName)}</span>
        <div class="test-grid"></div>
        <div class="suite-stats">
          <span class="suite-stat" data-type="pass">0</span>
          <span class="suite-stat" data-type="fail">0</span>
        </div>
      </div>
      <div class="suite-tests"></div>
    </div>
  `
}

export function failureCard({ nodeId, location, traceback }) {
  const testName = extractTestName(nodeId)
  return `
    <div class="failure-card" data-node-id="${escapeHtml(nodeId)}">
      <div class="failure-name">${escapeHtml(testName)}</div>
      ${location ? `<div class="failure-location">${escapeHtml(location)}</div>` : ''}
      ${traceback ? `
        <div class="failure-traceback">
          <pre>${highlightTraceback(traceback)}</pre>
        </div>
      ` : ''}
    </div>
  `
}
