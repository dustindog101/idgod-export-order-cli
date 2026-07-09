from idgod_order_cli.models import CheckoutResult, OrderResult, Person
from idgod_order_cli.ui import RunUI, format_result_human


def test_run_ui_collects_events_not_printing_in_json_mode(capsys):
    ui = RunUI(json_mode=True)
    ui.phase("Test")
    ui.step("hello")
    assert len(ui.events) >= 2
    captured = capsys.readouterr()
    assert captured.err == ""


def test_format_result_human_success():
    person = Person(
        first_name="A",
        last_name="B",
        state="Washington",
        dob="01/01/2000",
        city="Seattle",
        zip="98101",
    )
    result = CheckoutResult(
        success=True,
        message="Coupon saved",
        payment_url="https://btcpay.idgod.ph/invoice?id=abc",
        total_after_discount=85.0,
        discount_code="hartlr",
        discount_applied=True,
        order_results=[
            OrderResult(person=person, success=True, message="ok", state_selected="Washington", price=100)
        ],
        captcha_solved=True,
        captcha_solver="ppllocr",
        captcha_attempts_used=1,
        checkout_attempted=True,
        checkout_completed=True,
    )
    text = format_result_human(result)
    assert "Order complete" in text
    assert "btcpay.idgod.ph" in text
    assert "A B" in text
