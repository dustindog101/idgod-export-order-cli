from idgod_order_cli.models import CheckoutResult


def test_checkout_result_includes_payment_details_dict():
    from idgod_order_cli.btcpay import PaymentDetails

    pd = PaymentDetails(
        invoice_id="abc",
        amount_due_btc="0.01",
        btc_address="bc1qtest",
        total_fiat="$10",
    )
    result = CheckoutResult(
        success=True,
        payment_url="https://btcpay.idgod.ph/invoice?id=abc",
        payment_details=pd,
        total_before_discount=130.0,
        total_after_discount=85.0,
        discount_savings=45.0,
        captcha_solve_time_ms=1200,
        elapsed_ms=45000,
    )
    d = result.to_dict()
    assert d["payment_details"]["invoice_id"] == "abc"
    assert d["total_before_discount"] == 130.0
    assert d["discount_savings"] == 45.0
    assert d["captcha_solve_time_ms"] == 1200
