"""Terminal UI: live progress (stderr) and formatted human output (stdout)."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from time import monotonic
from typing import Any


def _use_color() -> bool:
    return bool(getattr(sys.stderr, "isatty", lambda: False)()) and not _no_color()


def _no_color() -> bool:
    import os

    return os.environ.get("NO_COLOR", "") != ""


def _c(code: str, text: str) -> str:
    if not _use_color():
        return text
    return f"\033[{code}m{text}\033[0m"


def _dim(text: str) -> str:
    return _c("2", text)


def _bold(text: str) -> str:
    return _c("1", text)


def _green(text: str) -> str:
    return _c("32", text)


def _red(text: str) -> str:
    return _c("31", text)


def _yellow(text: str) -> str:
    return _c("33", text)


def _cyan(text: str) -> str:
    return _c("36", text)


def _blue(text: str) -> str:
    return _c("34", text)


@dataclass
class RunUI:
    """Lightweight progress reporter. Live output goes to stderr; final summary to stdout."""

    json_mode: bool = False
    events: list[dict[str, Any]] = field(default_factory=list)
    _started: float = field(default_factory=monotonic, repr=False)
    _phase: str = field(default="", repr=False)

    def _log(self, kind: str, message: str, **extra: Any) -> None:
        entry: dict[str, Any] = {
            "t_ms": int((monotonic() - self._started) * 1000),
            "kind": kind,
            "phase": self._phase,
            "message": message,
        }
        entry.update(extra)
        self.events.append(entry)
        if self.json_mode:
            return
        prefix = {
            "phase": _bold(_cyan("●")),
            "step": _blue("→"),
            "ok": _green("✓"),
            "fail": _red("✗"),
            "warn": _yellow("!"),
            "detail": _dim("·"),
        }.get(kind, "·")
        print(f"  {prefix} {message}", file=sys.stderr, flush=True)

    def banner(self, *, ids: int, routing: str, modes: list[str]) -> None:
        mode_s = " · ".join(modes) if modes else "order only"
        line = f"idgod-order  ·  {ids} ID{'s' if ids != 1 else ''}  ·  {routing}  ·  {mode_s}"
        if not self.json_mode:
            print(file=sys.stderr)
            print(_bold(line), file=sys.stderr, flush=True)
            print(_dim("─" * min(len(line), 72)), file=sys.stderr, flush=True)
        self.events.append(
            {
                "t_ms": 0,
                "kind": "banner",
                "message": line,
                "ids": ids,
                "routing": routing,
                "modes": modes,
            }
        )

    def phase(self, title: str) -> None:
        self._phase = title
        self.events.append(
            {
                "t_ms": int((monotonic() - self._started) * 1000),
                "kind": "phase",
                "phase": title,
                "message": title,
            }
        )
        if self.json_mode:
            return
        print(file=sys.stderr)
        print(_bold(f"── {title} ──"), file=sys.stderr, flush=True)

    def step(self, message: str, **extra: Any) -> None:
        self._log("step", message, **extra)

    def detail(self, message: str, **extra: Any) -> None:
        self._log("detail", message, **extra)

    def ok(self, message: str, **extra: Any) -> None:
        self._log("ok", message, **extra)

    def fail(self, message: str, **extra: Any) -> None:
        self._log("fail", message, **extra)

    def warn(self, message: str, **extra: Any) -> None:
        self._log("warn", message, **extra)

    def progress(self, current: int, total: int, label: str) -> None:
        total = max(total, 1)
        width = 20
        filled = int(width * current / total)
        bar = "█" * filled + "░" * (width - filled)
        msg = f"[{bar}] {current}/{total}  {label}"
        self._log("step", msg, current=current, total=total, label=label)


def _money(value: float | None) -> str:
    return f"${value:.2f}" if value is not None else "—"


def _box_line(inner: str, width: int = 62) -> str:
    return f"│ {inner:<{width - 4}} │"


def format_result_human(result: Any, *, verbose: bool = False) -> str:
    """Render a polished summary for interactive terminals."""
    lines: list[str] = []
    use_box = _use_color()

    success = getattr(result, "success", False)
    dry_run = getattr(result, "dry_run", False)
    status = _green("SUCCESS") if success else _red("FAILED")
    if dry_run:
        title = "Dry run complete"
    else:
        title = "Order complete" if success else "Order failed"

    if use_box:
        lines.append(f"╭{'─' * 60}╮")
        lines.append(_box_line(f"{title}  ·  {status}"))
        lines.append(f"├{'─' * 60}┤")
    else:
        lines.append(f"=== {title} · {('SUCCESS' if success else 'FAILED')} ===")

    if getattr(result, "message", ""):
        lines.append(_box_line(result.message) if use_box else result.message)

    meta: list[str] = []
    if getattr(result, "elapsed_ms", 0):
        meta.append(f"{result.elapsed_ms / 1000:.1f}s")
    if getattr(result, "tor_mode", ""):
        meta.append(result.tor_mode)
    elif getattr(result, "proxy_used", ""):
        meta.append(result.proxy_used)
    if meta:
        lines.append(_box_line(_dim(" · ".join(meta))) if use_box else " · ".join(meta))

    if use_box:
        lines.append(f"╰{'─' * 60}╯")

    # Payment block
    pd = getattr(result, "payment_details", None)
    if getattr(result, "payment_url", "") or (pd and getattr(pd, "populated", False)):
        lines.append("")
        lines.append(_bold("Payment"))
        lines.append(_dim("─" * 40))
        if getattr(result, "payment_url", ""):
            lines.append(f"  Invoice   {result.payment_url}")
        if pd and getattr(pd, "populated", False):
            if pd.order_number:
                lines.append(f"  Order #   {pd.order_number}")
            if pd.order_status_url:
                lines.append(f"  Status    {pd.order_status_url}")
            if pd.amount_due_display or pd.amount_due_btc:
                lines.append(f"  Amount    {pd.amount_due_display or pd.amount_due_btc}")
            if pd.total_fiat:
                lines.append(f"  Fiat      {pd.total_fiat}")
            if pd.btc_address:
                lines.append(f"  Address   {pd.btc_address}")
            if pd.pay_in_wallet_url:
                lines.append(f"  Wallet    {pd.pay_in_wallet_url}")
            if pd.exchange_rate:
                lines.append(f"  Rate      {pd.exchange_rate}")
            if pd.expiry_text:
                lines.append(f"  Expires   {pd.expiry_text}")
        elif getattr(result, "payment_info", ""):
            for ln in result.payment_info.splitlines()[:6]:
                if ln.strip():
                    lines.append(f"  {ln.strip()}")

    # Totals
    if any(
        getattr(result, k, None) is not None
        for k in ("total_before_discount", "total_after_discount", "total_price", "discount_savings")
    ):
        lines.append("")
        lines.append(_bold("Totals"))
        lines.append(_dim("─" * 40))
        if result.total_before_discount is not None:
            lines.append(f"  Before coupon   {_money(result.total_before_discount)}")
        after = result.total_after_discount if result.total_after_discount is not None else result.total_price
        if after is not None:
            lines.append(f"  After coupon    {_money(after)}")
        if result.discount_savings:
            lines.append(f"  Saved           {_money(result.discount_savings)}")
        if result.price_per_id is not None:
            lines.append(f"  Per ID          {_money(result.price_per_id)}")
        if result.discount_code:
            applied = _green("yes") if result.discount_applied else _yellow("no")
            lines.append(f"  Coupon {result.discount_code}   {applied}")

    # IDs
    orders = getattr(result, "order_results", []) or []
    if orders:
        lines.append("")
        lines.append(_bold(f"IDs ({len(orders)})"))
        lines.append(_dim("─" * 40))
        for o in orders:
            mark = _green("✓") if o.success else _red("✗")
            state = o.state_selected or o.person.state
            price = f" · {_money(o.price)}" if o.price is not None else ""
            lines.append(f"  {mark} {o.person.display_name} · {state}{price}")
            if verbose or not o.success:
                lines.append(_dim(f"      {o.message}"))

    # Checkout / captcha
    if getattr(result, "checkout_attempted", False):
        lines.append("")
        lines.append(_bold("Checkout"))
        lines.append(_dim("─" * 40))
        if result.checkout_completed:
            lines.append(f"  {_green('✓')} Submitted")
        else:
            lines.append(f"  {_red('✗')} Not completed")
        if result.checkout_message:
            lines.append(f"  {result.checkout_message}")
        if result.captcha_solved:
            lines.append(
                f"  Captcha   {result.captcha_solver} "
                f"({result.captcha_attempts_used} attempt(s), {result.captcha_solve_time_ms}ms)"
            )
        elif result.captcha_solver:
            lines.append(f"  Captcha   not solved ({result.captcha_attempts_used} attempt(s))")

    if getattr(result, "cache_path", ""):
        lines.append("")
        lines.append(_dim(f"Cached → {result.cache_path}"))

    if verbose and getattr(result, "timings", None):
        parts = ", ".join(f"{k}={v}ms" for k, v in result.timings.items())
        lines.append(_dim(f"Timings: {parts}"))

    return "\n".join(lines)
