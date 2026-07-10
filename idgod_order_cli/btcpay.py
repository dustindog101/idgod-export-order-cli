"""Parse BTCPay Server invoice pages (btcpay.idgod.ph) after checkout."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlparse


@dataclass
class PaymentDetails:
    invoice_id: str = ""
    invoice_url: str = ""
    amount_due_btc: str = ""
    amount_due_display: str = ""
    total_price_btc: str = ""
    total_fiat: str = ""
    exchange_rate: str = ""
    network_cost_btc: str = ""
    recommended_fee: str = ""
    btc_address: str = ""
    pay_in_wallet_url: str = ""
    payment_method: str = ""
    expiry_text: str = ""
    order_number: str = ""
    order_status_url: str = ""
    raw_fields: dict[str, str] = field(default_factory=dict)

    @property
    def populated(self) -> bool:
        return bool(self.invoice_id or self.btc_address or self.amount_due_btc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "invoice_id": self.invoice_id,
            "invoice_url": self.invoice_url,
            "amount_due_btc": self.amount_due_btc,
            "amount_due_display": self.amount_due_display,
            "total_price_btc": self.total_price_btc,
            "total_fiat": self.total_fiat,
            "exchange_rate": self.exchange_rate,
            "network_cost_btc": self.network_cost_btc,
            "recommended_fee": self.recommended_fee,
            "btc_address": self.btc_address,
            "pay_in_wallet_url": self.pay_in_wallet_url,
            "payment_method": self.payment_method,
            "expiry_text": self.expiry_text,
            "order_number": self.order_number,
            "order_status_url": self.order_status_url,
            "raw_fields": self.raw_fields,
        }

    def summary_lines(self) -> list[str]:
        lines: list[str] = []
        if self.amount_due_display or self.amount_due_btc:
            lines.append(f"Amount due: {self.amount_due_display or self.amount_due_btc}")
        if self.total_fiat:
            lines.append(f"Fiat total: {self.total_fiat}")
        if self.btc_address:
            lines.append(f"BTC address: {self.btc_address}")
        if self.exchange_rate:
            lines.append(f"Rate: {self.exchange_rate}")
        if self.pay_in_wallet_url:
            lines.append(f"Wallet link: {self.pay_in_wallet_url}")
        if self.expiry_text:
            lines.append(f"Expires in: {self.expiry_text}")
        if self.order_number:
            lines.append(f"Order number: {self.order_number}")
        if self.order_status_url:
            lines.append(f"Order status: {self.order_status_url}")
        return lines


def extract_invoice_id(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "id" in qs and qs["id"]:
        return qs["id"][0]
    parts = [p for p in parsed.path.split("/") if p]
    if parts and parts[0] == "i" and len(parts) > 1:
        return parts[1]
    return ""


def _is_vue_placeholder(value: str) -> bool:
    v = (value or "").strip()
    return bool(v) and ("model." in v or "srvModel." in v or "{{" in v)


def _clean_field(value: str) -> str:
    return "" if _is_vue_placeholder(value) else (value or "").strip()


def _attr(pattern: str, html: str, group: int = 1) -> str:
    m = re.search(pattern, html, re.I | re.S)
    return _clean_field((m.group(group) if m else "").strip())


def _parse_initial_srv_model(html: str) -> dict[str, Any]:
    m = re.search(r"const initialSrvModel = (\{.*?\});\s*\n", html, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}


def parse_btcpay_html(html: str, url: str = "") -> PaymentDetails:
    """Parse BTCPay invoice HTML (works on saved dumps and live page source)."""
    invoice_id = extract_invoice_id(url)
    amount_due_btc = _attr(r'id="AmountDue"[^>]*data-amount-due="([^"]+)"', html)
    amount_due_display = _attr(r'id="AmountDue"[^>]*>([^<]+)</h2>', html)
    total_fiat = _attr(r'id="total_fiat"[^>]*data-clipboard="([^"]+)"', html)
    if not total_fiat:
        total_fiat = _attr(r'id="PaymentDetails-TotalFiat"[^>]*>.*?data-clipboard="([^"]+)"', html)

    total_price_btc = _attr(
        r'id="PaymentDetails-TotalPrice"[^>]*>.*?data-clipboard="([^"]+)"', html
    )
    exchange_rate = _attr(
        r'id="PaymentDetails-ExchangeRate"[^>]*>.*?data-clipboard="([^"]+)"', html
    )
    network_cost = _attr(
        r'id="PaymentDetails-NetworkCost"[^>]*>.*?data-clipboard="([^"]+)"', html
    )
    recommended_fee = _attr(
        r'id="PaymentDetails-RecommendedFee"[^>]*>.*?data-clipboard="([^"]+)"', html
    )
    btc_address = _attr(
        r'id="Address_BTC-CHAIN"[^>]*>.*?data-clipboard="([^"]+)"', html
    )
    if not btc_address:
        btc_address = _attr(r'data-text="(bc1[a-z0-9]+)"', html, 1)
    pay_wallet = _attr(r'id="PayInWallet"[^>]*href="([^"]+)"', html)
    payment_method = _attr(
        r'class="[^"]*payment-method active[^"]*"[^>]*>([^<]+)</a>', html
    )
    expiry = _attr(r'class="expiryTime"[^>]*>([^<]+)</span>', html)

    srv = _parse_initial_srv_model(html)
    order_status_url = str(srv.get("merchantRefLink") or "")
    order_number = str(srv.get("orderId") or "")

    if srv:
        if not amount_due_btc:
            amount_due_btc = str(srv.get("due") or srv.get("orderAmount") or "")
        if not amount_due_display and amount_due_btc:
            amount_due_display = f"{amount_due_btc} BTC"
        if not total_fiat:
            total_fiat = str(srv.get("orderAmountFiat") or "")
        if not btc_address:
            btc_address = str(srv.get("address") or "")
        if not pay_wallet:
            pay_wallet = str(srv.get("invoiceBitcoinUrl") or "")

    raw = {
        k: v
        for k, v in {
            "amount_due_btc": amount_due_btc,
            "total_fiat": total_fiat,
            "btc_address": btc_address,
            "exchange_rate": exchange_rate,
        }.items()
        if v
    }

    return PaymentDetails(
        invoice_id=invoice_id,
        invoice_url=url,
        amount_due_btc=amount_due_btc,
        amount_due_display=amount_due_display,
        total_price_btc=total_price_btc,
        total_fiat=total_fiat,
        exchange_rate=exchange_rate,
        network_cost_btc=network_cost,
        recommended_fee=recommended_fee,
        btc_address=btc_address,
        pay_in_wallet_url=pay_wallet,
        payment_method=payment_method,
        expiry_text=expiry,
        order_number=order_number,
        order_status_url=order_status_url,
        raw_fields=raw,
    )


async def fetch_btcpay_from_page(page, *, timeout_ms: int = 30000) -> PaymentDetails:
    """Load payment fields from an open Playwright page on a BTCPay invoice."""
    url = page.url
    if "btcpay" not in url.lower():
        return PaymentDetails(invoice_url=url)

    try:
        await page.wait_for_selector("#AmountDue", timeout=timeout_ms)
    except Exception:
        return parse_btcpay_html(await page.content(), url)

    toggle = page.locator("#DetailsToggle")
    if await toggle.count():
        try:
            expanded = await toggle.get_attribute("aria-expanded")
            if expanded != "true":
                await toggle.click()
                await page.wait_for_timeout(400)
        except Exception:
            pass

    try:
        await page.wait_for_selector("#Address_BTC-CHAIN", timeout=5000)
    except Exception:
        pass

    return parse_btcpay_html(await page.content(), url)
