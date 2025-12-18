from protest import ProTestSession

session = ProTestSession()
session.register_default_plugins()


@session.test(tags=["slow"])
def test_slow_fail_1() -> None:
    raise AssertionError("slow failure 1")


@session.test(tags=["slow"])
def test_slow_fail_2() -> None:
    raise AssertionError("slow failure 2")


@session.test(tags=["fast"])
def test_fast_pass() -> None:
    assert True


@session.test(tags=["fast"])
def test_fast_fail() -> None:
    raise AssertionError("fast failure")


@session.test(tags=["unit"])
def test_unit_pass() -> None:
    assert True
