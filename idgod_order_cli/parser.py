from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from .models import EXPORT_ONLY_FIELDS, FIELD_ALIASES, Person, ShippingInfo


def _norm_key(key: str) -> str:
    return re.sub(r"\s+", " ", key.strip().lower())


def _row_to_person(row: dict[str, Any], source_row: int | None = None) -> Person:
    mapped: dict[str, str] = {}
    export_order_id = ""
    for raw_key, raw_val in row.items():
        key = _norm_key(str(raw_key))
        if key in EXPORT_ONLY_FIELDS:
            if key == "order id" and raw_val:
                export_order_id = str(raw_val).strip()
            continue
        field = FIELD_ALIASES.get(key)
        if field and raw_val is not None and str(raw_val).strip():
            mapped[field] = str(raw_val).strip()

    required = ("first_name", "last_name", "state", "dob", "city", "zip")
    missing = [r for r in required if not mapped.get(r)]
    if missing:
        raise ValueError(f"Row {source_row or '?'} missing required fields: {', '.join(missing)}")

    return Person(
        first_name=mapped["first_name"],
        last_name=mapped["last_name"],
        state=mapped["state"],
        dob=mapped["dob"],
        city=mapped["city"],
        zip=mapped["zip"],
        middle_name=mapped.get("middle_name", ""),
        issue_date=mapped.get("issue_date", ""),
        street=mapped.get("street", ""),
        zip4=mapped.get("zip4", ""),
        sex=mapped.get("sex", ""),
        height=mapped.get("height", ""),
        weight=mapped.get("weight", ""),
        eye_color=mapped.get("eye_color", ""),
        hair_color=mapped.get("hair_color", ""),
        photo=mapped.get("photo", ""),
        signature=mapped.get("signature", ""),
        state_variant=mapped.get("state_variant", ""),
        email=mapped.get("email", ""),
        source_row=source_row,
        export_order_id=export_order_id,
    )


def parse_csv(path: Path) -> list[Person]:
    people: list[Person] = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):
            people.append(_row_to_person(row, source_row=i))
    return people


def parse_xlsx(path: Path) -> list[Person]:
    try:
        import openpyxl
    except ImportError as e:
        raise RuntimeError("openpyxl required: pip install openpyxl") from e

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(h or "").strip() for h in rows[0]]
    people: list[Person] = []
    for i, row in enumerate(rows[1:], start=2):
        if not row or all(v is None or str(v).strip() == "" for v in row):
            continue
        data = {headers[j]: row[j] if j < len(row) else "" for j in range(len(headers))}
        people.append(_row_to_person(data, source_row=i))
    return people


def parse_json(path: Path) -> list[Person]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "people" in data:
        items = data["people"]
    elif isinstance(data, list):
        items = data
    else:
        items = [data]
    return [_row_to_person(item, source_row=i + 1) for i, item in enumerate(items)]


def parse_file(path: Path) -> list[Person]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return parse_csv(path)
    if suffix in (".xlsx", ".xls"):
        return parse_xlsx(path)
    if suffix == ".json":
        return parse_json(path)
    raise ValueError(f"Unsupported file type: {suffix} (use .csv, .xlsx, or .json)")


def person_from_flags(args: dict[str, str | None]) -> Person:
    return _row_to_person({k: v for k, v in args.items() if v}, source_row=None)


def _shipping_from_row(row: dict[str, Any]) -> str:
    for raw_key, raw_val in row.items():
        key = _norm_key(str(raw_key))
        if key == "shipping" and raw_val is not None and str(raw_val).strip():
            return str(raw_val).strip()
    return ""


def extract_shipping_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                found = _shipping_from_row(row)
                if found:
                    return found
        return ""

    if suffix in (".xlsx", ".xls"):
        try:
            import openpyxl
        except ImportError as e:
            raise RuntimeError("openpyxl required: pip install openpyxl") from e

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return ""
        headers = [str(h or "").strip() for h in rows[0]]
        for row in rows[1:]:
            data = {headers[j]: row[j] if j < len(row) else "" for j in range(len(headers))}
            found = _shipping_from_row(data)
            if found:
                return found
        return ""

    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "people" in data:
            items = data["people"]
        elif isinstance(data, list):
            items = data
        else:
            items = [data]
        for item in items:
            if isinstance(item, dict):
                found = _shipping_from_row(item)
                if found:
                    return found
        return ""

    return ""


def parse_shipping_text(text: str) -> ShippingInfo:
    raw = text.strip()
    if not raw:
        return ShippingInfo()

    parts = [p.strip() for p in raw.split(",") if p and p.strip()]
    if len(parts) >= 5:
        return ShippingInfo(
            name=parts[0],
            street=parts[1],
            city=parts[2],
            state=parts[3],
            zip=parts[4],
            country=parts[5] if len(parts) > 5 else "USA",
            raw=raw,
        )

    match = re.search(
        r"^(?P<name>.+?),?\s+(?P<street>\d+.+?),?\s+"
        r"(?P<city>[A-Za-z .'-]+),?\s+(?P<state>[A-Za-z]{2,}|[A-Za-z .'-]+)\s+"
        r"(?P<zip>\d{5}(?:-\d{4})?)",
        raw,
    )
    if match:
        data = match.groupdict()
        return ShippingInfo(
            name=data["name"].strip(),
            street=data["street"].strip(),
            city=data["city"].strip(),
            state=data["state"].strip(),
            zip=data["zip"].strip(),
            raw=raw,
        )

    return ShippingInfo(raw=raw)
