from protest import ProTestSession

session = ProTestSession()


@session.test()
def test_passing() -> None:
    assert True


@session.test()
def test_failing() -> None:
    raise AssertionError("intentional failure")


@session.test()
def test_another_passing() -> None:
    assert True
