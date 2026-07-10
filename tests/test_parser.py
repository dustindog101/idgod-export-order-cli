from pathlib import Path

from idgod_order_cli.parser import (
    extract_shipping_text,
    parse_file,
    parse_shipping_text,
    parse_json,
)
from idgod_order_cli.models import EXPORT_ONLY_FIELDS


def test_export_only_fields_include_order_metadata():
    assert "order id" in EXPORT_ONLY_FIELDS
    assert "shipping" in EXPORT_ONLY_FIELDS


def test_parse_csv_two_people_different_fields(orders_csv):
    people = parse_file(orders_csv)
    assert len(people) == 2
    assert people[0].first_name == "Anaya"
    assert people[1].first_name == "Josie"
    assert people[0].eye_color == "Brown"
    assert people[1].eye_color == "Green"
    assert people[0].street != people[1].street
    assert people[0].export_order_id == "batch-1"


def test_shipping_extracted_once_from_csv(orders_csv):
    raw = extract_shipping_text(orders_csv)
    assert "Oakland" in raw
    assert "94619" in raw


def test_parse_shipping_line():
    ship = parse_shipping_text("Name, 123 Main St, Oakland, CA, 94619, USA")
    assert ship.name == "Name"
    assert ship.city == "Oakland"
    assert ship.state == "CA"
    assert ship.zip == "94619"


def test_parse_vendor_column_aliases(tmp_path):
    path = tmp_path / "vendor.csv"
    path.write_text(
        (Path(__file__).parent / "fixtures" / "vendor-order.csv").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    people = parse_file(path)
    assert len(people) == 2
    assert people[0].first_name == "Anaya"
    assert people[0].street == "5125 NE Latimer Place"
    assert people[0].zip == "98105"
    assert people[0].photo == "https://example.com/anaya-photo.webp"
    assert people[0].signature == "https://example.com/anaya-sig.webp"
    assert people[0].issue_date == "05/28/2026"
    assert people[1].photo == "https://example.com/josie-photo.webp"


def test_parse_json_people_list(tmp_path):
    path = tmp_path / "people.json"
    path.write_text(
        """[
          {"first name": "A", "last name": "B", "state": "WA", "dob": "01/01/2000",
           "city": "Seattle", "zip": "98101"}
        ]""",
        encoding="utf-8",
    )
    people = parse_json(path)
    assert len(people) == 1
    assert people[0].display_name == "A B"
