"""Demo of the mocker fixture for mocking and patching."""

from typing import Annotated

from protest import Mocker, ProTestSession, Use, mocker

session = ProTestSession()


class EmailService:
    def send(self, to: str, subject: str, body: str) -> dict[str, str]:
        return {"status": "sent", "to": to}


class PaymentGateway:
    def charge(self, amount: float, card_token: str) -> dict[str, str]:
        return {"status": "charged", "amount": str(amount)}


class OrderService:
    def __init__(
        self, email_service: EmailService, payment_gateway: PaymentGateway
    ) -> None:
        self.email = email_service
        self.payment = payment_gateway

    def process_order(self, amount: float, card_token: str, customer_email: str) -> str:
        payment_result = self.payment.charge(amount, card_token)
        if payment_result["status"] == "charged":
            self.email.send(
                to=customer_email,
                subject="Order Confirmed",
                body=f"Your payment of ${amount} was successful.",
            )
            return "success"
        return "failed"


@session.test()
def test_patch_external_service(mock: Annotated[Mocker, Use(mocker)]) -> None:
    """Patch an external service to avoid real API calls."""
    email = EmailService()
    payment = PaymentGateway()
    order_service = OrderService(email, payment)

    print("  [before patch] payment.charge() ->", payment.charge(10, "tok"))

    mock_charge = mock.patch.object(payment, "charge")
    mock_charge.return_value = {"status": "charged", "amount": "99.99"}
    mock_send = mock.patch.object(email, "send")

    print("  [after patch]  payment.charge() ->", payment.charge(10, "tok"))

    result = order_service.process_order(99.99, "tok_test", "user@test.com")

    print(f"  [result] order processed: {result}")
    assert result == "success"
    mock_charge.assert_called_with(99.99, "tok_test")
    mock_send.assert_called_once()


@session.test()
def test_spy_real_method(mock: Annotated[Mocker, Use(mocker)]) -> None:
    """Use spy to call the real method but track invocations."""
    email = EmailService()

    spy = mock.spy(email.send)  # Modern style: pass the bound method directly

    print("  [spy] calling real email.send()...")
    result = email.send("test@example.com", "Test", "Hello")

    print(f"  [spy] real method returned: {result}")
    print(f"  [spy] spy.spy_return: {spy.spy_return}")
    print(f"  [spy] spy.call_count: {spy.call_count}")

    assert result == {"status": "sent", "to": "test@example.com"}
    spy.assert_called_once_with("test@example.com", "Test", "Hello")


@session.test()
def test_stub_callback(mock: Annotated[Mocker, Use(mocker)]) -> None:
    """Use stub for callback testing."""

    def run_with_callback(on_success: object) -> None:
        on_success("done")  # type: ignore[operator]

    callback = mock.stub("on_success")
    callback.return_value = "ack"

    print("  [stub] running function with stub callback...")
    run_with_callback(callback)

    print(f"  [stub] callback.called: {callback.called}")
    print(f"  [stub] callback.call_args: {callback.call_args}")

    callback.assert_called_once_with("done")


@session.test()
async def test_async_stub(mock: Annotated[Mocker, Use(mocker)]) -> None:
    """Use async_stub for async callback testing."""

    async def run_async(on_complete: object) -> None:
        await on_complete("completed")  # type: ignore[operator]

    async_callback = mock.async_stub("on_complete")
    async_callback.return_value = "async_ack"

    print("  [async_stub] running async function with async stub...")
    await run_async(async_callback)

    print(f"  [async_stub] async_callback.awaited: {async_callback.awaited}")
    print(f"  [async_stub] async_callback.await_args: {async_callback.await_args}")

    async_callback.assert_awaited_once_with("completed")


@session.test()
def test_autospec_type_safety(mock: Annotated[Mocker, Use(mocker)]) -> None:
    """Use create_autospec for type-safe mocking."""
    mock_email = mock.create_autospec(EmailService, instance=True)
    mock_email.send.return_value = {"status": "mocked"}

    print(f"  [autospec] mock has same methods as EmailService: {dir(mock_email)}")
    print("  [autospec] calling mock_email.send()...")

    result = mock_email.send("to@test.com", "Subject", "Body")

    print(f"  [autospec] result: {result}")

    assert result == {"status": "mocked"}
    mock_email.send.assert_called_once_with("to@test.com", "Subject", "Body")


if __name__ == "__main__":
    from protest import run_session

    run_session(session)
