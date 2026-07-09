from idgod_order_cli.btcpay import PaymentDetails, extract_invoice_id, parse_btcpay_html


def test_extract_invoice_id_query():
    url = "https://btcpay.idgod.ph/invoice?id=TCr53ZRiMzJT2JwSrLfnkQ"
    assert extract_invoice_id(url) == "TCr53ZRiMzJT2JwSrLfnkQ"


def test_extract_invoice_id_path():
    assert extract_invoice_id("https://btcpay.idgod.ph/i/ABC123") == "ABC123"


def test_parse_btcpay_fixture(btcpay_html: str):
    details = parse_btcpay_html(
        btcpay_html,
        "https://btcpay.idgod.ph/invoice?id=TCr53ZRiMzJT2JwSrLfnkQ",
    )
    assert details.populated
    assert details.invoice_id == "TCr53ZRiMzJT2JwSrLfnkQ"
    assert details.amount_due_btc == "0.00135466"
    assert details.total_fiat == "$85.00"
    assert details.btc_address.lower().startswith("bc1q")
    assert "bitcoin:" in details.pay_in_wallet_url
    assert details.exchange_rate.startswith("$")
    assert details.summary_lines()


def test_parse_empty_html():
    details = parse_btcpay_html("<html></html>")
    assert not details.populated
    assert isinstance(details, PaymentDetails)
