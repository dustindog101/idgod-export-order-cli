"""httpx session for idgod.ph with Django CSRF handling and randomized client fingerprints."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import httpx

from .fingerprint import BrowserFingerprint, generate_browser_fingerprint
from .http_forms import BASE_URL, extract_csrf, find_form, parse_forms
from .orderer import CART_URL, ORDER_URL


class IdGodHttpSession:
    def __init__(
        self,
        *,
        proxy: Any = None,
        timeout: float = 60.0,
        fingerprint: BrowserFingerprint | None = None,
    ) -> None:
        self._proxy = proxy
        self._timeout = timeout
        self.fingerprint = fingerprint or generate_browser_fingerprint()
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> IdGodHttpSession:
        kwargs: dict[str, Any] = {
            "follow_redirects": True,
            "timeout": self._timeout,
            "headers": dict(self.fingerprint.headers),
        }
        if self._proxy is not None:
            kwargs["proxy"] = self._proxy.to_httpx()
        self._client = httpx.AsyncClient(**kwargs)
        return self

    async def __aexit__(self, *args) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("IdGodHttpSession not started")
        return self._client

    def csrf_headers(self, referer: str) -> dict[str, str]:
        token = self.client.cookies.get("csrftoken", "")
        headers = dict(self.fingerprint.headers)
        headers["Referer"] = referer
        headers["Origin"] = BASE_URL
        if "sec-fetch-site" in headers:
            headers["sec-fetch-site"] = "same-origin"
        if token:
            headers["X-CSRFToken"] = token
        return headers

    async def get_page(self, url: str) -> tuple[httpx.Response, str, list[dict[str, Any]]]:
        headers = dict(self.fingerprint.headers)
        if "sec-fetch-site" in headers and url != ORDER_URL:
            headers["sec-fetch-site"] = "same-origin"
        resp = await self.client.get(url, headers=headers)
        html = resp.text
        return resp, html, parse_forms(html)

    async def post_form(
        self,
        url: str,
        *,
        referer: str,
        data: dict[str, Any],
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> httpx.Response:
        return await self.client.post(
            url,
            data=data,
            files=files,
            headers=self.csrf_headers(referer),
        )

    async def get_bytes(self, url: str, *, referer: str = CART_URL) -> bytes:
        headers = self.csrf_headers(referer)
        if "Accept" in headers:
            headers["Accept"] = "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
        if "sec-fetch-dest" in headers:
            headers["sec-fetch-dest"] = "image"
        if "sec-fetch-mode" in headers:
            headers["sec-fetch-mode"] = "no-cors"
        resp = await self.client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.content

    async def refresh_captcha(self) -> dict[str, str]:
        headers = self.csrf_headers(CART_URL)
        headers["Accept"] = "application/json, text/javascript, */*; q=0.01"
        headers["X-Requested-With"] = "XMLHttpRequest"
        if "sec-fetch-dest" in headers:
            headers["sec-fetch-dest"] = "empty"
        if "sec-fetch-mode" in headers:
            headers["sec-fetch-mode"] = "cors"
        for path in ("/captcha/refresh/", "/captcha/refresh"):
            try:
                resp = await self.client.get(
                    urljoin(BASE_URL, path),
                    headers=headers,
                )
                if resp.status_code < 400:
                    data = resp.json()
                    if data.get("key"):
                        return {
                            "key": str(data["key"]),
                            "image_url": urljoin(BASE_URL, str(data.get("image_url", ""))),
                        }
            except Exception:
                continue
        return {}
