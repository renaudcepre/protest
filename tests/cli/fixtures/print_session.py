from protest import ProTestSession

session = ProTestSession()


@session.test()
def test_with_print() -> None:
    print("VISIBLE_OUTPUT_FROM_TEST")  # noqa
    assert True
