"""Persist order run results (payment URLs, totals, people) for later lookup."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def default_cache_dir() -> Path:
    return Path.home() / ".cache" / "idgod-order-cli"


class OrderCache:
    def __init__(self, cache_dir: str | Path = "") -> None:
        self.root = Path(cache_dir).expanduser() if cache_dir else default_cache_dir()
        self.orders_dir = self.root / "orders"

    def save(self, payload: dict[str, Any]) -> Path:
        self.orders_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        names = "-".join(
            re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")[:20]
            for n in payload.get("submitted_ids", [])[:2]
        )
        suffix = names or "order"
        path = self.orders_dir / f"{stamp}-{suffix}.json"
        record = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        with (self.root / "index.jsonl").open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "path": str(path),
                        "saved_at": record["saved_at"],
                        "success": payload.get("success"),
                        "payment_url": payload.get("payment_url", ""),
                        "submitted_ids": payload.get("submitted_ids", []),
                        "total_after_discount": payload.get("total_after_discount"),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        return path

    def list_entries(self, limit: int = 20) -> list[dict[str, Any]]:
        index = self.root / "index.jsonl"
        if not index.exists():
            return []
        lines = index.read_text(encoding="utf-8").splitlines()
        out: list[dict[str, Any]] = []
        for line in reversed(lines[-limit:]):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
