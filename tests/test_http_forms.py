from idgod_order_cli.http_forms import (
    extract_csrf,
    find_form,
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
