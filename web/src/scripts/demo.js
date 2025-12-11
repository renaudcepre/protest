import { handleMessage } from './handlers.js'

const DEMO_TESTS = [
  { nodeId: 'tests/core/test_runner.py::test_simple_pass', outcome: 'pass', duration: 0.012 },
  { nodeId: 'tests/core/test_runner.py::test_another_pass', outcome: 'pass', duration: 0.008 },
  { nodeId: 'tests/core/test_runner.py::test_fast_one', outcome: 'pass', duration: 0.002 },
  {
    nodeId: 'tests/core/test_runner.py::test_assertion_failure',
    outcome: 'fail',
    duration: 0.045,
    message: 'AssertionError: assert 1 == 2',
    traceback: `Traceback (most recent call last):
  File "tests/core/test_runner.py", line 42, in test_assertion_failure
    assert 1 == 2
           ^^^^^^
AssertionError: assert 1 == 2`,
  },
  { nodeId: 'tests/core/test_runner.py::TestSuite::test_in_class', outcome: 'pass', duration: 0.003 },
  { nodeId: 'tests/core/test_runner.py::TestSuite::test_another_in_class', outcome: 'pass', duration: 0.004 },
  {
    nodeId: 'tests/core/test_runner.py::TestSuite::test_skipped_wip',
    outcome: 'skip',
    duration: 0,
    message: 'WIP: not implemented yet',
  },
  { nodeId: 'tests/di/test_resolver.py::test_fixture_resolution', outcome: 'pass', duration: 0.021 },
  { nodeId: 'tests/di/test_resolver.py::test_scope_validation', outcome: 'pass', duration: 0.015 },
  {
    nodeId: 'tests/di/test_resolver.py::test_known_bug',
    outcome: 'xfail',
    duration: 0.018,
    message: 'Known bug #123 - fixture cleanup race condition',
  },
  { nodeId: 'tests/di/test_resolver.py::test_caching', outcome: 'pass', duration: 0.009 },
  {
    nodeId: 'tests/execution/test_timeout.py::test_slow_operation',
    outcome: 'fail',
    duration: 5.001,
    message: 'TimeoutError: Test exceeded 5.0s timeout',
    traceback: `Traceback (most recent call last):
  File "protest/execution/context.py", line 89, in run_with_timeout
    raise TimeoutError(f"Test exceeded {timeout}s timeout")
TimeoutError: Test exceeded 5.0s timeout`,
  },
  { nodeId: 'tests/execution/test_timeout.py::test_fast_enough', outcome: 'pass', duration: 0.5 },
  { nodeId: 'tests/fixtures/test_mocker.py::test_patch_basic', outcome: 'pass', duration: 0.007 },
  { nodeId: 'tests/fixtures/test_mocker.py::test_patch_object', outcome: 'pass', duration: 0.006 },
  { nodeId: 'tests/fixtures/test_mocker.py::test_spy', outcome: 'pass', duration: 0.011 },
  {
    nodeId: 'tests/fixtures/test_mocker.py::test_spy_failure',
    outcome: 'fail',
    duration: 0.008,
    message: "AssertionError: Expected call not found: mock.send('hello')",
    traceback: `Traceback (most recent call last):
  File "tests/fixtures/test_mocker.py", line 78, in test_spy_failure
    spy.assert_called_with("hello")
  File "/usr/lib/python3.12/unittest/mock.py", line 888, in assert_called_with
    raise AssertionError(...)
AssertionError: Expected call not found: mock.send('hello')
Actual calls: [call('world')]`,
  },
  { nodeId: 'tests/tags/test_filter.py::test_include_tags', outcome: 'pass', duration: 0.013 },
  { nodeId: 'tests/tags/test_filter.py::test_exclude_tags', outcome: 'pass', duration: 0.012 },
  { nodeId: 'tests/tags/test_filter.py::test_tag_propagation', outcome: 'pass', duration: 0.019 },
  {
    nodeId: 'tests/tags/test_filter.py::test_complex_filter',
    outcome: 'xfail',
    duration: 0.022,
    message: 'Complex tag expressions not yet implemented',
  },
]

export function runDemo() {
  const totalTests = DEMO_TESTS.length

  handleMessage({
    type: 'SESSION_START',
    payload: { target: 'tests:session', totalTests },
  })

  let index = 0
  const interval = setInterval(() => {
    if (index >= DEMO_TESTS.length) {
      clearInterval(interval)
      handleMessage({ type: 'SESSION_END', payload: {} })
      return
    }

    const test = DEMO_TESTS[index]
    const typeMap = {
      pass: 'TEST_PASS',
      fail: 'TEST_FAIL',
      skip: 'TEST_SKIP',
      xfail: 'TEST_XFAIL',
      error: 'TEST_ERROR',
    }

    handleMessage({
      type: typeMap[test.outcome],
      payload: test,
    })

    index++
  }, 150)
}

export function runDemoInstant() {
  const totalTests = DEMO_TESTS.length

  handleMessage({
    type: 'SESSION_START',
    payload: { target: 'tests:session', totalTests },
  })

  for (const test of DEMO_TESTS) {
    const typeMap = {
      pass: 'TEST_PASS',
      fail: 'TEST_FAIL',
      skip: 'TEST_SKIP',
      xfail: 'TEST_XFAIL',
      error: 'TEST_ERROR',
    }

    handleMessage({
      type: typeMap[test.outcome],
      payload: test,
    })
  }

  handleMessage({ type: 'SESSION_END', payload: {} })
}
