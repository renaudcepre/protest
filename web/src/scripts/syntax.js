import { escapeHtml } from './utils.js'

export function highlightTraceback(code) {
  const escaped = escapeHtml(code)
  const patterns = [
    [/^(\s*File\s+)(&quot;[^&]*&quot;)(,\s+line\s+)(\d+)/gm,
     '$1<span class="syn-path">$2</span>$3<span class="syn-number">$4</span>'],
    [/^((?:AssertionError|ValueError|TypeError|RuntimeError|KeyError|AttributeError|TimeoutError|Exception|Error)[^:]*:)/gm,
     '<span class="syn-error">$1</span>'],
    [/^(\s*\^+\s*)$/gm, '<span class="syn-caret">$1</span>'],
  ]
  let result = escaped
  for (const [pattern, replacement] of patterns) {
    result = result.replace(pattern, replacement)
  }
  return result
}
