export const dom = {
  sessionTarget: null,
  connectionDot: null,
  connectionText: null,
  timer: null,
  progressText: null,
  emptyState: null,
  suitesContainer: null,
  stats: {},
  progress: {},
}

export function initDom() {
  dom.sessionTarget = document.getElementById('session-target')
  dom.connectionDot = document.getElementById('connection-dot')
  dom.connectionText = document.getElementById('connection-text')
  dom.timer = document.getElementById('timer')
  dom.progressText = document.getElementById('progress-text')
  dom.emptyState = document.getElementById('empty-state')
  dom.suitesContainer = document.getElementById('suites-container')

  dom.stats = {
    pass: document.getElementById('stat-pass'),
    fail: document.getElementById('stat-fail'),
    skip: document.getElementById('stat-skip'),
    xfail: document.getElementById('stat-xfail'),
    error: document.getElementById('stat-error'),
  }

  dom.progress = {
    pass: document.getElementById('progress-pass'),
    fail: document.getElementById('progress-fail'),
    skip: document.getElementById('progress-skip'),
    xfail: document.getElementById('progress-xfail'),
    error: document.getElementById('progress-error'),
  }
}
