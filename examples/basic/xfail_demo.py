"""ProTest Demo - xfail (expected failure) functionality."""

from protest import ProTestSession

session = ProTestSession()


@session.test()
def test_that_passes() -> None:
    assert True


@session.test(xfail=True)
def test_xfail_with_default_reason() -> None:
    raise AssertionError("This failure is expected")


@session.test(xfail="Bug #123: race condition not yet fixed")
def test_xfail_with_custom_reason() -> None:
    raise ValueError("Known issue")


@session.test(xfail="Should fail but doesn't!")
def test_xpass_unexpected_success() -> None:
    assert True


@session.test(xfail="TODO: fix flaky test")
def test_another_xfail() -> None:
    raise RuntimeError("Flaky behavior")
