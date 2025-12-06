from protest import ProTestSession, ProTestSuite

session = ProTestSession()

api_suite = ProTestSuite("API")
users_suite = ProTestSuite("Users")
orders_suite = ProTestSuite("Orders")
other_suite = ProTestSuite("Other")

api_suite.add_suite(users_suite)
api_suite.add_suite(orders_suite)

session.add_suite(api_suite)
session.add_suite(other_suite)


@session.test()
def test_standalone() -> None:
    assert True


@api_suite.test()
def test_api() -> None:
    assert True


@users_suite.test()
def test_users_list() -> None:
    assert True


@users_suite.test()
def test_users_create() -> None:
    assert True


@orders_suite.test()
def test_orders() -> None:
    assert True


@other_suite.test()
def test_other() -> None:
    assert True
