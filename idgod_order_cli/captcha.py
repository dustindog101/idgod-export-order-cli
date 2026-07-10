"""Captcha solving for django-simple-captcha image fields on idgod.ph cart.

Local: ppllocr (~67MB wheel, ONNX, maintained 2026) — use raw PNG bytes, not screenshots.
Cloud: 2captcha API via httpx (set TWOCAPTCHA_API_KEY or --2captcha-key).
"""

from __future__ import annotations

import asyncio
import base64
import os
import re
import time
from abc import ABC, abstractmethod
from collections import Counter
from typing import Any


class CaptchaSolverError(Exception):
    pass


_ALNUM_RE = re.compile(r"[^a-zA-Z0-9]+")
CAPTCHA_LEN_MIN = 4
CAPTCHA_LEN_MAX = 6


def normalize_captcha_text(text: str) -> str:
    cleaned = _ALNUM_RE.sub("", (text or "").strip())
    return cleaned


def plausible_captcha_length(text: str) -> bool:
    n = len(normalize_captcha_text(text))
    return CAPTCHA_LEN_MIN <= n <= CAPTCHA_LEN_MAX


def captcha_variants(text: str) -> list[str]:
    base = normalize_captcha_text(text)
    if not base:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for candidate in (base, base.lower(), base.upper()):
        if candidate not in seen:
            seen.add(candidate)
            out.append(candidate)
    return out


def captcha_guess_candidates(text: str) -> list[str]:
    """Build submit candidates from raw OCR (trim when model over-reads)."""
    base = normalize_captcha_text(text)
    if not base:
        return []

    seen: set[str] = set()
    out: list[str] = []

    def add(value: str) -> None:
        if not value or value in seen:
            return
        seen.add(value)
        out.append(value)

    for candidate in captcha_variants(base):
        add(candidate)

    if len(base) > CAPTCHA_LEN_MAX:
        for length in range(CAPTCHA_LEN_MAX, CAPTCHA_LEN_MIN - 1, -1):
            for start in range(0, len(base) - length + 1):
                chunk = base[start : start + length]
                add(chunk)
                add(chunk.lower())
                add(chunk.upper())

    return out


def best_captcha_guess(text: str) -> str:
    """Pick one guess to submit for django-simple-captcha (usually 4-6 chars)."""
    base = normalize_captcha_text(text)
    if not base:
        return ""

    if CAPTCHA_LEN_MIN <= len(base) <= CAPTCHA_LEN_MAX:
        return base.lower()

    candidates = captcha_guess_candidates(base)
    for prefer_len in (5, 4, 6):
        for candidate in candidates:
            if len(candidate) == prefer_len:
                return candidate.lower()

    if candidates:
        return candidates[0].lower()

    return base[:CAPTCHA_LEN_MAX].lower()


def preprocess_captcha_variants(image_bytes: bytes) -> list[tuple[str, bytes]]:
    """Generate OCR-friendly views of the same captcha (raw + enhanced)."""
    out: list[tuple[str, bytes]] = [("raw", image_bytes)]
    try:
        import io

        from PIL import Image, ImageEnhance, ImageFilter, ImageOps

        img = Image.open(io.BytesIO(image_bytes))
        if img.mode != "RGB":
            img = img.convert("RGB")
        w, h = img.size

        def _png(im: Image.Image) -> bytes:
            buf = io.BytesIO()
            im.save(buf, format="PNG")
            return buf.getvalue()

        scaled = img.resize(
            (max(w * 2, 140), max(h * 2, 48)),
            Image.Resampling.LANCZOS,
        )
        out.append(("scaled2x", _png(scaled)))

        gray = ImageOps.grayscale(scaled)
        out.append(("gray", _png(gray.convert("RGB"))))

        contrast = ImageEnhance.Contrast(gray).enhance(2.4)
        sharp = ImageEnhance.Sharpness(contrast).enhance(2.2)
        out.append(("contrast", _png(sharp.convert("RGB"))))

        boosted = ImageOps.autocontrast(gray)
        binary = boosted.point(lambda px: 255 if px > 135 else 0)
        out.append(("binary", _png(binary.convert("RGB"))))

        median = sharp.filter(ImageFilter.MedianFilter(3))
        out.append(("median", _png(median.convert("RGB"))))
    except Exception:
        pass

    seen: set[int] = set()
    deduped: list[tuple[str, bytes]] = []
    for label, data in out:
        key = hash(data)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((label, data))
    return deduped


def pick_consensus(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Vote across solvers + preprocess variants; pick the most common guess."""
    if not results:
        return None
    guesses = [r["guess"] for r in results if r.get("guess")]
    if not guesses:
        return None

    counts = Counter(guesses)
    best_guess, votes = counts.most_common(1)[0]
    matching = [r for r in results if r.get("guess") == best_guess]
    priority = {"2captcha": 3, "ddddocr": 2, "ppllocr": 1}
    matching.sort(
        key=lambda r: (priority.get(str(r.get("solver", "")), 0), len(str(r.get("raw_text", "")))),
        reverse=True,
    )
    best = dict(matching[0])
    best["consensus_votes"] = votes
    best["all_guesses"] = dict(counts)
    return best


class CaptchaSolver(ABC):
    name: str = "base"

    @abstractmethod
    async def solve(self, image_bytes: bytes) -> str:
        ...


class PpllocrSolver(CaptchaSolver):
    name = "ppllocr"

    def __init__(self) -> None:
        self._ocr = None

    def _get_ocr(self):
        if self._ocr is None:
            try:
                from ppllocr import OCR
            except ImportError as e:
                raise CaptchaSolverError(
                    "ppllocr not installed. Run: pip install 'idgod-order-cli[captcha]'"
                ) from e
            self._ocr = OCR()
        return self._ocr

    async def solve(self, image_bytes: bytes) -> str:
        ocr = self._get_ocr()

        def _run() -> str:
            return ocr.classification(image_bytes)

        text = normalize_captcha_text(await asyncio.to_thread(_run))
        if not text:
            raise CaptchaSolverError("ppllocr returned empty text")
        return text


class DdddocrSolver(CaptchaSolver):
    name = "ddddocr"

    def __init__(self) -> None:
        self._ocr = None

    def _get_ocr(self):
        if self._ocr is None:
            try:
                import ddddocr
            except ImportError as e:
                raise CaptchaSolverError(
                    "ddddocr not installed. Run: pip install ddddocr"
                ) from e
            self._ocr = ddddocr.DdddOcr(show_ad=False)
        return self._ocr

    async def solve(self, image_bytes: bytes) -> str:
        ocr = self._get_ocr()

        def _run() -> str:
            return ocr.classification(image_bytes)

        text = normalize_captcha_text(await asyncio.to_thread(_run))
        if not text:
            raise CaptchaSolverError("ddddocr returned empty text")
        return text


class TwoCaptchaSolver(CaptchaSolver):
    name = "2captcha"

    def __init__(self, api_key: str, *, timeout: float = 120.0) -> None:
        if not api_key:
            raise CaptchaSolverError(
                "2captcha API key required (TWOCAPTCHA_API_KEY or --2captcha-key)"
            )
        self.api_key = api_key
        self.timeout = timeout

    async def solve(self, image_bytes: bytes) -> str:
        import httpx

        b64 = base64.b64encode(image_bytes).decode("ascii")
        async with httpx.AsyncClient(timeout=30) as client:
            submit = await client.post(
                "https://2captcha.com/in.php",
                data={
                    "key": self.api_key,
                    "method": "base64",
                    "body": b64,
                    "json": 1,
                },
            )
            submit.raise_for_status()
            data = submit.json()
            if data.get("status") != 1:
                raise CaptchaSolverError(f"2captcha submit failed: {data.get('request', data)}")

            task_id = data["request"]
            deadline = time.time() + self.timeout
            while time.time() < deadline:
                await asyncio.sleep(5)
                poll = await client.get(
                    "https://2captcha.com/res.php",
                    params={"key": self.api_key, "action": "get", "id": task_id, "json": 1},
                )
                poll.raise_for_status()
                result = poll.json()
                if result.get("status") == 1:
                    text = normalize_captcha_text(str(result.get("request", "")))
                    if text:
                        return text
                    raise CaptchaSolverError("2captcha returned empty text")
                if result.get("request") != "CAPCHA_NOT_READY":
                    raise CaptchaSolverError(f"2captcha error: {result.get('request', result)}")

        raise CaptchaSolverError("2captcha timed out waiting for solution")


def get_solver(mode: str = "auto", api_key: str = "") -> CaptchaSolver:
    key = api_key or os.environ.get("TWOCAPTCHA_API_KEY", "")

    if mode == "ppllocr":
        return PpllocrSolver()
    if mode == "ddddocr":
        return DdddocrSolver()
    if mode == "2captcha":
        return TwoCaptchaSolver(key)
    if mode == "manual":
        raise CaptchaSolverError("Manual captcha mode — use --headed and solve in browser")

    try:
        import ppllocr  # noqa: F401

        return PpllocrSolver()
    except ImportError:
        pass
    try:
        import ddddocr  # noqa: F401

        return DdddocrSolver()
    except ImportError:
        pass
    if key:
        return TwoCaptchaSolver(key)
    raise CaptchaSolverError(
        "No captcha solver available. Install ppllocr (pip install 'idgod-order-cli[captcha]') "
        "or ddddocr, or set TWOCAPTCHA_API_KEY / --2captcha-key"
    )


def _solver_chain(mode: str, api_key: str) -> list[str]:
    key = api_key or os.environ.get("TWOCAPTCHA_API_KEY", "")
    if mode == "auto":
        chain = ["ddddocr", "ppllocr"]
        if key:
            chain.append("2captcha")
        return chain
    if mode in ("ppllocr", "ddddocr", "2captcha"):
        return [mode]
    return [mode]


async def solve_captcha_image(
    image_bytes: bytes,
    *,
    mode: str = "auto",
    api_key: str = "",
) -> dict[str, Any]:
    errors: list[str] = []
    results: list[dict[str, Any]] = []
    variants = preprocess_captcha_variants(image_bytes)

    for variant_name, variant_bytes in variants:
        for solver_mode in _solver_chain(mode, api_key):
            try:
                solver = get_solver(solver_mode, api_key)
                text = await solver.solve(variant_bytes)
                guess = best_captcha_guess(text)
                if not guess:
                    continue
                results.append(
                    {
                        "solver": solver.name,
                        "text": text,
                        "raw_text": text,
                        "guess": guess,
                        "variant": variant_name,
                    }
                )
            except CaptchaSolverError as e:
                errors.append(f"{solver_mode}/{variant_name}: {e}")

    consensus = pick_consensus(results)
    if consensus:
        return {
            "solver": consensus["solver"],
            "text": consensus["text"],
            "raw_text": consensus["raw_text"],
            "guess": consensus["guess"],
            "variants": captcha_variants(consensus["text"]),
            "consensus_votes": consensus.get("consensus_votes", 1),
            "all_guesses": consensus.get("all_guesses", {}),
            "ocr_reads": len(results),
            "preprocess_variants": len(variants),
        }

    raise CaptchaSolverError("; ".join(errors) or "Captcha solving failed")
