from __future__ import annotations

import re
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse


@dataclass
class ProxyConfig:
    host: str
    port: int
    username: str = ""
    password: str = ""
    scheme: str = "http"
    label: str = ""

    @property
    def server(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"

    @property
    def display(self) -> str:
        auth = f"{self.username}@" if self.username else ""
        return self.label or f"{auth}{self.host}:{self.port}"

    def to_playwright(self) -> dict[str, str]:
        out: dict[str, str] = {"server": self.server}
        if self.username:
            out["username"] = self.username
            out["password"] = self.password
        return out

    def to_httpx(self) -> str:
        if self.username:
            user = quote(self.username, safe="")
            pwd = quote(self.password, safe="")
            return f"{self.scheme}://{user}:{pwd}@{self.host}:{self.port}"
        return self.server


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def parse_proxy_line(line: str) -> ProxyConfig | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    # URL form: http://user:pass@host:port or socks5://host:port
    if "://" in line:
        u = urlparse(line)
        scheme = u.scheme or "http"
        host = u.hostname or ""
        port = u.port or (1080 if scheme.startswith("socks") else 8080)
        return ProxyConfig(host=host, port=port, username=u.username or "", password=u.password or "", scheme=scheme)

    parts = line.split(":")
    if len(parts) == 2:
        return ProxyConfig(host=parts[0], port=int(parts[1]))
    if len(parts) == 4:
        return ProxyConfig(host=parts[0], port=int(parts[1]), username=parts[2], password=parts[3])
    raise ValueError(f"Invalid proxy format: {line!r} (use host:port or host:port:user:pass)")


def load_proxies_from_file(path: Path) -> list[ProxyConfig]:
    proxies: list[ProxyConfig] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            p = parse_proxy_line(line)
            if p:
                p.label = f"file:{path.name}#{i}"
                proxies.append(p)
        except ValueError as e:
            raise ValueError(f"{path}:{i}: {e}") from e
    return proxies


class TorManager:
    """Provide a local SOCKS5 proxy via system tor or embedded torpy."""

    def __init__(self) -> None:
        self.port: int | None = None
        self._proc: subprocess.Popen | None = None
        self._torpy_server = None
        self._torpy_client = None
        self.mode = ""

    def _socks_reachable(self, port: int, timeout: float = 2.0) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=timeout):
                return True
        except OSError:
            return False

    def start(self, timeout: float = 45.0) -> ProxyConfig:
        # 1) Existing Tor daemon
        for port in (9050, 9150):
            if self._socks_reachable(port):
                self.port = port
                self.mode = f"existing-tor:{port}"
                return ProxyConfig(host="127.0.0.1", port=port, scheme="socks5", label=self.mode)

        # 2) Launch system tor binary
        import shutil
        tor_bin = shutil.which("tor")
        if tor_bin:
            port = _free_port()
            data_dir = tempfile.mkdtemp(prefix="idgod-tor-")
            torrc_path = tempfile.mktemp(suffix=".torrc")
            with open(torrc_path, "w", encoding="utf-8") as f:
                f.write(
                    f"SocksPort {port}\n"
                    f"DataDirectory {data_dir}\n"
                    "Log notice stderr\n"
                    "AvoidDiskWrites 1\n"
                )
            self._proc = subprocess.Popen(
                [tor_bin, "-f", torrc_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.time() + timeout
            while time.time() < deadline:
                if self._proc.poll() is not None:
                    break
                if self._socks_reachable(port, timeout=1.0):
                    self.port = port
                    self.mode = f"tor-binary:{port}"
                    return ProxyConfig(host="127.0.0.1", port=port, scheme="socks5", label=self.mode)
                time.sleep(0.5)
            self.stop()
            raise RuntimeError("System tor failed to start SOCKS proxy in time")

        # 3) Embedded torpy (pure Python, no tor install)
        try:
            from torpy import TorClient
            from torpy.socks import SocksServer
        except ImportError as e:
            raise RuntimeError(
                "Tor not running and tor binary not found. Install tor (`brew install tor`) "
                "or embedded support: pip install torpy"
            ) from e

        port = _free_port()
        self._torpy_client = TorClient()
        self._torpy_client.__enter__()
        self._torpy_server = SocksServer(self._torpy_client, host="127.0.0.1", port=port)
        self._torpy_server.start()
        self.port = port
        self.mode = f"torpy-embedded:{port}"
        return ProxyConfig(host="127.0.0.1", port=port, scheme="socks5", label=self.mode)

    def stop(self) -> None:
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
        if self._torpy_server:
            try:
                self._torpy_server.stop()
            except Exception:
                pass
            self._torpy_server = None
        if self._torpy_client:
            try:
                self._torpy_client.__exit__(None, None, None)
            except Exception:
                pass
            self._torpy_client = None


async def test_proxy_httpx(proxy: ProxyConfig, url: str, timeout: float = 20.0) -> dict[str, Any]:
    import httpx

    started = time.time()
    try:
        async with httpx.AsyncClient(
            proxy=proxy.to_httpx(),
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as client:
            resp = await client.get(url)
            return {
                "proxy": proxy.display,
                "ok": resp.status_code < 500,
                "status": resp.status_code,
                "final_url": str(resp.url),
                "bytes": len(resp.content),
                "elapsed_ms": int((time.time() - started) * 1000),
                "title_hint": _extract_title(resp.text),
            }
    except Exception as e:
        return {
            "proxy": proxy.display,
            "ok": False,
            "error": str(e),
            "elapsed_ms": int((time.time() - started) * 1000),
        }


async def test_proxy_playwright(proxy: ProxyConfig, url: str, timeout_ms: int = 25000) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    started = time.time()
    try:
        async with async_playwright() as pw:
            launch_kwargs: dict[str, Any] = {
                "headless": True,
                "proxy": proxy.to_playwright(),
                "args": ["--no-sandbox", "--disable-dev-shm-usage"],
            }
            try:
                browser = await pw.chromium.launch(**launch_kwargs)
            except Exception:
                browser = await pw.chromium.launch(channel="chrome", **launch_kwargs)
            page = await browser.new_page()
            page.set_default_timeout(timeout_ms)
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            title = await page.title()
            fields = await page.locator("input, select, textarea").count()
            wa = await page.evaluate("""() => {
              const sel = document.querySelector('select');
              if (!sel) return [];
              return [...sel.options].map(o => o.text.trim()).filter(t => /washington/i.test(t));
            }""")
            coupon = await page.evaluate("""() => [...document.querySelectorAll('input')].filter(i => /coupon|discount|promo/i.test((i.name||'')+(i.id||'')+(i.placeholder||''))).map(i => ({name:i.name,id:i.id,placeholder:i.placeholder}))""")
            buttons = await page.evaluate("""() => [...document.querySelectorAll('button, input[type=submit]')].map(b => (b.innerText || b.value || '').trim()).filter(Boolean)""")
            await browser.close()
            return {
                "proxy": proxy.display,
                "ok": bool(resp and resp.ok),
                "status": resp.status if resp else None,
                "title": title,
                "form_fields": fields,
                "wa_options": wa,
                "coupon_inputs": coupon,
                "buttons": buttons[:8],
                "elapsed_ms": int((time.time() - started) * 1000),
            }
    except Exception as e:
        return {
            "proxy": proxy.display,
            "ok": False,
            "error": str(e)[:400],
            "elapsed_ms": int((time.time() - started) * 1000),
        }


def _extract_title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip()[:120] if m else ""


async def pick_working_proxy(proxies: list[ProxyConfig], url: str) -> tuple[ProxyConfig | None, list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    for proxy in proxies:
        r = await test_proxy_playwright(proxy, url)
        results.append(r)
        if r.get("ok"):
            return proxy, results
    return None, results
