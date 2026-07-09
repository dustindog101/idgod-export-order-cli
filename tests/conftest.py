from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def btcpay_html(fixtures_dir: Path) -> str:
    return (fixtures_dir / "btcpay-invoice.html").read_text(encoding="utf-8")


@pytest.fixture
def orders_csv(fixtures_dir: Path) -> Path:
    return fixtures_dir / "orders-two.csv"
