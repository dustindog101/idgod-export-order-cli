from idgod_order_cli.http_forms import (
    detect_coupon_rejection,
    extract_csrf,
    find_form,
    form_post_data,
    parse_forms,
    read_cart_total,
    select_value_by_label,
)


def test_parse_order_form():
    html = """
    <form id="order-form" method="post" enctype="multipart/form-data">
      <input name="csrfmiddlewaretoken" value="tok123">
      <select name="state"><option value="371">Washington</option></select>
    </form>
    """
    forms = parse_forms(html)
    form = find_form(forms, "order-form")
    assert form is not None
    assert extract_csrf(html, form) == "tok123"
    assert select_value_by_label(form["selects"][0], "Washington") == "371"


def test_read_cart_total_nonempty():
    html = '<div id="total">$110.00</div> cart contents (1)'
    total, count, empty = read_cart_total(html)
    assert total == 110.0
    assert count == 1
    assert empty is False


def test_form_post_data_scrapes_hidden_and_select():
    html = """
    <form id="order-form" method="post">
      <input type="hidden" name="csrfmiddlewaretoken" value="tok">
      <input type="hidden" name="line_id" value="99">
      <input name="email" value="old@example.com">
      <select name="priority">
        <option value="9" selected>Standard</option>
        <option value="6">Express</option>
      </select>
    </form>
    """
    forms = parse_forms(html)
    form = find_form(forms, "order-form")
    data = form_post_data(form, html)
    assert data["csrfmiddlewaretoken"] == "tok"
    assert data["line_id"] == "99"
    assert data["email"] == "old@example.com"
    assert data["priority"] == "9"


def test_detect_coupon_rejection():
    html = "<div class='error'>Coupon code invalid or expired</div>"
    assert detect_coupon_rejection(html, "hartlr")


def test_finalize_coupon_result():
    from idgod_order_cli.http_forms import finalize_coupon_result

    applied, msg, savings, inv = finalize_coupon_result("hartlr", 480.0, "$260.00")
    assert applied is True
    assert savings == 220.0
    assert inv == 260.0

    applied2, msg2, _, inv2 = finalize_coupon_result("hartlr", 480.0, "$500.00")
    assert applied2 is False
    assert inv2 == 500.0
    assert "not on invoice" in msg2


def test_coupon_savings_message():
    from idgod_order_cli.http_forms import coupon_savings_message, invoice_reflects_discount

    applied, msg, savings = coupon_savings_message("hartlr", 480.0, 480.0, invoice_fiat="$260.00")
    assert applied is True
    assert savings == 220.0
    assert "invoice $260.00" in msg

    applied2, msg2, savings2 = coupon_savings_message("hartlr", 480.0, 480.0, invoice_fiat="$500.00")
    assert applied2 is False
    assert "not on invoice" in msg2

    assert invoice_reflects_discount(480.0, "$260.00") is True
    assert invoice_reflects_discount(480.0, "$500.00") is False
    assert invoice_reflects_discount(130.0, "$85.00") is True


def test_captcha_hash_from_image_url():
    from idgod_order_cli.http_forms import captcha_hash_from_image_url

    url = "https://www.idgod.ph/captcha/image/abc123def456/"
    assert captcha_hash_from_image_url(url) == "abc123def456"
    assert captcha_hash_from_image_url("") == ""
