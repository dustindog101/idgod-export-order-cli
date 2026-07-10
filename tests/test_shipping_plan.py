"""Tests for multi-address shipping resolution."""

import argparse

from idgod_order_cli.cli import _resolve_batch_plan
from idgod_order_cli.parser import (
    merge_batches,
    parse_export_file,
    shipping_choices_from_batches,
)
from idgod_order_cli.models import OrderBatch

FIXTURES = __import__("pathlib").Path(__file__).parent / "fixtures"


def _args(**kwargs):
    base = argparse.Namespace(
        shipping="",
        multi_checkout=False,
        single_checkout=False,
        yes=True,
        dry_run=True,
    )
    for key, value in kwargs.items():
        setattr(base, key, value)
    return base


def test_shipping_override_collapses_batches():
    bundle = parse_export_file(FIXTURES / "example-multi-order-different-addresses.json")
    batches = bundle.batches
    assert len(shipping_choices_from_batches(batches)) == 2

    override = "Warehouse, 500 Main St, Oakland, CA, 94619, USA"
    resolved, notes = _resolve_batch_plan(
        _args(shipping=override),
        batches,
        bundle,
    )
    assert len(resolved) == 1
    assert len(resolved[0].people) == 3
    assert resolved[0].shipping_raw == override
    assert any("overrides all export" in n for n in notes)


def test_multi_checkout_keeps_batches():
    bundle = parse_export_file(FIXTURES / "example-multi-order-different-addresses.json")
    resolved, notes = _resolve_batch_plan(
        _args(multi_checkout=True),
        bundle.batches,
        bundle,
    )
    assert len(resolved) == 2
    assert any("separate checkout" in n for n in notes)


def test_single_checkout_uses_first_address():
    bundle = parse_export_file(FIXTURES / "example-multi-order-different-addresses.json")
    resolved, notes = _resolve_batch_plan(
        _args(single_checkout=True),
        bundle.batches,
        bundle,
    )
    assert len(resolved) == 1
    assert len(resolved[0].people) == 3
    assert "Springfield" in resolved[0].shipping_raw
    assert any("single checkout" in n for n in notes)


def test_merge_batches_preserves_people():
    bundle = parse_export_file(FIXTURES / "example-multi-order-different-addresses.json")
    merged = merge_batches(bundle.batches, "One Addr, 1 St, City, ST, 00000, USA")
    assert len(merged) == 1
    assert len(merged[0].people) == 3
