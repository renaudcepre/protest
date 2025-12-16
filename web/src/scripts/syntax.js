import { escapeHtml } from './utils.js'

const KEYWORDS = new Set([
  'await', 'return', 'raise', 'with', 'as', 'async', 'def', 'class',
  'if', 'else', 'elif', 'for', 'while', 'try', 'except', 'finally',
  'import', 'from', 'in', 'not', 'and', 'or', 'is', 'None', 'True', 'False',
  'assert', 'yield', 'pass', 'break', 'continue', 'lambda', 'self'
])

function span(cls, text) {
  return `<span class="${cls}">${escapeHtml(text)}</span>`
}

function classifyToken(token) {
  if (token.match(/^f?["']/)) return span('syn-string', token)
  if (token.match(/^\d/)) return span('syn-number', token)
  if (token.match(/^[a-zA-Z_]/)) {
    if (KEYWORDS.has(token)) return span('syn-keyword', token)
    return escapeHtml(token)
  }
  return escapeHtml(token)
}

function highlightCodeLine(line) {
  const tokenRegex = /(f?"[^"]*"|f?'[^']*'|[a-zA-Z_][a-zA-Z0-9_]*|\d+\.?\d*|\s+|.)/g
  const tokens = []
  let match
  while ((match = tokenRegex.exec(line)) !== null) {
    tokens.push(classifyToken(match[1]))
  }
  return tokens.join('')
}

function highlightErrorMessage(message) {
  const parts = []
  const stringRegex = /(".*?"|'.*?')/g
  let match
  let lastIndex = 0
  while ((match = stringRegex.exec(message)) !== null) {
    if (match.index > lastIndex) {
      parts.push(escapeHtml(message.slice(lastIndex, match.index)))
    }
    parts.push(span('syn-string', match[1]))
    lastIndex = stringRegex.lastIndex
  }
  if (lastIndex < message.length) {
    parts.push(escapeHtml(message.slice(lastIndex)))
  }
  return parts.join('')
}

function highlightLine(line) {
  if (line.match(/^Traceback \(most recent call last\):/)) {
    return span('syn-dim', line)
  }

  const fileMatch = line.match(/^(\s*)(File )(".*?")(, line )(\d+)(, in )(.+)$/)
  if (fileMatch) {
    const [, indent, fileWord, path, lineWord, lineNum, inWord, funcName] = fileMatch
    return escapeHtml(indent) +
      span('syn-dim', fileWord) +
      span('syn-path', path) +
      span('syn-dim', lineWord) +
      span('syn-number', lineNum) +
      span('syn-dim', inWord) +
      span('syn-function', funcName)
  }

  if (line.match(/^\s*[\^~]+\s*$/)) {
    return span('syn-caret', line)
  }

  const errorMatch = line.match(/^([A-Z][a-zA-Z]*(?:Error|Exception|Warning)):(.*)$/)
  if (errorMatch) {
    const [, errorType, message] = errorMatch
    return span('syn-error', errorType + ':') + highlightErrorMessage(message)
  }

  if (line.match(/^    \S/)) {
    return highlightCodeLine(line)
  }

  return escapeHtml(line)
}

export function highlightTraceback(code) {
  const lines = code.split('\n')
  return lines.map(line => highlightLine(line)).join('\n')
}
