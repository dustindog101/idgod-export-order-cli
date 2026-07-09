import json

from idgod_order_cli.cache import OrderCache


def test_cache_save_and_list(tmp_path):
    cache = OrderCache(tmp_path)
    path = cache.save(
        {
            "success": True,
            "submitted_ids": ["Jane Doe"],
            "payment_url": "https://btcpay.example/i/x",
            "total_after_discount": 85.0,
        }
    )
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["submitted_ids"] == ["Jane Doe"]

    entries = cache.list_entries(limit=5)
    assert len(entries) == 1
    assert entries[0]["payment_url"].endswith("/i/x")
