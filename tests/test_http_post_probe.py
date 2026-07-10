import importlib.util
import sys
from pathlib import Path

_probe_path = Path(__file__).resolve().parents[1] / "scripts" / "http-post-probe.py"
_spec = importlib.util.spec_from_file_location("http_post_probe", _probe_path)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["http_post_probe"] = _mod
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

parse_forms = _mod.parse_forms
_verdict = _mod._verdict
ProbeReport = _mod.ProbeReport


def test_parse_order_form_fixture():
    html = """
    <form id="order-form" method="post" enctype="multipart/form-data">
      <input name="csrfmiddlewaretoken" value="abc123">
      <input name="first_name" required>
      <input type="file" name="picture">
      <select name="state"><option value="371">Washington</option></select>
      <button name="action" value="1">Add</button>
    </form>
    """
    parsed = parse_forms(html)
    form = parsed.forms[0]
    assert form["id"] == "order-form"
    assert form["enctype"] == "multipart/form-data"
    assert any(i["name"] == "csrfmiddlewaretoken" for i in form["inputs"])
    assert form["selects"][0]["options"][0]["label"] == "Washington"


def test_verdict_marks_http_add_to_cart_when_cart_has_total():
    reports = [
        ProbeReport("analyze", True, data={"order": {"csrf_present": True}}),
        ProbeReport("submit", True, data={}),
        ProbeReport("cart", True, data={"total": "$110.00"}),
    ]
    v = _verdict(reports)
    assert v["http_viable_for_add_to_cart"] is True
    assert v["http_viable_for_full_checkout"] is False
