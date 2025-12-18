from protest import ProTestSession, ProTestSuite

session = ProTestSession()
session.register_default_plugins()
api_suite = ProTestSuite("API", tags=["api"])
session.add_suite(api_suite)


@session.test(tags=["unit"])
def test_unit() -> None:
    assert True


@session.test(tags=["unit", "fast"])
def test_unit_fast() -> None:
    assert True


@api_suite.test(tags=["slow"])
def test_slow_api() -> None:
    assert True


@api_suite.test()
def test_api_default() -> None:
    assert True
