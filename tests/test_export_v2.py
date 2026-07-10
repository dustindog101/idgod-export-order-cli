"""Tests for v2 export format (JSON orders[] + XLSX Orders sheet)."""

import json
from pathlib import Path

from idgod_order_cli.parser import (
    extract_shipping_text,
    parse_export_file,
    parse_shipping_text,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_real_json_export():
    path = Path("/Users/king/Downloads/orders-2026-07-10.json")
    if not path.exists():
        path = FIXTURES / "example-single-order.json"
    bundle = parse_export_file(path)
    people = bundle.people
    assert len(people) >= 1
    assert people[0].photo.startswith("http") or people[0].photo == ""
    if path.name.startswith("orders-"):
        assert len(people) == 4
        assert "Oakland" in people[0].shipping_raw


def test_parse_real_xlsx_export():
    path = Path("/Users/king/Downloads/orders-2026-07-10.xlsx")
    if not path.exists():
        return
    bundle = parse_export_file(path)
    assert len(bundle.people) == 4
    ship = extract_shipping_text(path)
    assert "Oakland" in ship
    parsed = parse_shipping_text(ship)
    assert parsed.city == "Oakland"
    assert parsed.zip == "94619"


def test_multi_order_different_addresses():
    bundle = parse_export_file(FIXTURES / "example-multi-order-different-addresses.json")
    assert bundle.meta.order_count == 2
    assert len(bundle.people) == 3
    assert bundle.batches[0].shipping_raw != bundle.batches[1].shipping_raw
    assert bundle.people[0].state == "Illinois"
    assert bundle.people[2].product_id == "TX:DMV_POLY"


def test_multi_order_shipping_override():
    bundle = parse_export_file(FIXTURES / "example-multi-order-same-address.json")
    assert bundle.meta.shipping_override
    assert "Vegas" in bundle.meta.shipping_override
    assert all("Vegas" in b.shipping_raw for b in bundle.batches)


def test_local_delivery():
    bundle = parse_export_file(FIXTURES / "example-local-delivery.json")
    assert bundle.batches[0].local_delivery is True
    assert bundle.people[0].state == "New York"
    assert bundle.people[0].first_name == "Jamie"


def test_zero_ids_order():
    bundle = parse_export_file(FIXTURES / "example-zero-ids.json")
    assert bundle.meta.order_count == 1
    assert len(bundle.people) == 0
    assert bundle.batches[0].order_id == "ord-007-EMPTY"


def test_single_order_json():
    bundle = parse_export_file(FIXTURES / "example-single-order.json")
    assert len(bundle.people) == 1
    assert bundle.people[0].first_name == "Alex"
    assert bundle.people[0].state == "Massachusetts"


def test_parse_shipping_with_six_parts():
    ship = parse_shipping_text("John Smith, 123 Oak Street, Springfield, IL, 62701, USA")
    assert ship.name == "John Smith"
    assert ship.street == "123 Oak Street"
    assert ship.city == "Springfield"
    assert ship.state == "IL"
    assert ship.zip == "62701"


def test_legacy_json_people_list(tmp_path):
    path = tmp_path / "legacy.json"
    path.write_text(
        json.dumps(
            [{"first name": "A", "last name": "B", "state": "WA", "dob": "01/01/2000",
              "city": "Seattle", "zip": "98101"}]
        ),
        encoding="utf-8",
    )
    bundle = parse_export_file(path)
    assert len(bundle.people) == 1
    assert bundle.people[0].state == "Washington"
