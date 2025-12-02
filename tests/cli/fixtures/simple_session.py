from protest import ProTestSession

session = ProTestSession()


@session.test()
def test_passing() -> None:
    assert True


@session.test()
def test_also_passing() -> None:
    assert 1 + 1 == 2
