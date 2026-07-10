"""httpx session for idgod.ph with Django CSRF handling."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import httpx

from .http_forms import BASE_URL, extract_csrf, find_form, parse_forms
from .orderer import CART_URL, ORDER_URL, USER_AGENT


class IdGodHttpSession:
    def __init__(self, *, proxy: Any = None, timeout: float = 60.0) -> None:
        self._proxy = proxy
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> IdGodHttpSession:
        kwargs: dict[str, Any] = {
            "follow_redirects": True,
            "timeout": self._timeout,
            "headers": {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
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
        headers = {"Referer": referer, "Origin": BASE_URL}
        if token:
            headers["X-CSRFToken"] = token
        return headers

    async def get_page(self, url: str) -> tuple[httpx.Response, str, list[dict[str, Any]]]:
        resp = await self.client.get(url)
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
        resp = await self.client.get(url, headers=self.csrf_headers(referer))
        resp.raise_for_status()
        return resp.content

    async def refresh_captcha(self) -> dict[str, str]:
        for path in ("/captcha/refresh/", "/captcha/refresh"):
            try:
                resp = await self.client.get(
                    urljoin(BASE_URL, path),
                    headers=self.csrf_headers(CART_URL),
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
