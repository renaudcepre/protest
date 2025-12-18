from protest import ProTestSession

session = ProTestSession()
session.register_default_plugins()


@session.test()
def test_fail_first() -> None:
    raise AssertionError("first failure")


@session.test()
def test_fail_second() -> None:
    raise AssertionError("second failure")


@session.test()
def test_passing() -> None:
    assert True
