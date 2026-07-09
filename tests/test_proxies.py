import socket
from unittest.mock import MagicMock, patch

import pytest

from idgod_order_cli.proxies import ProxyConfig, TorManager, parse_proxy_line


def test_parse_proxy_host_port():
    p = parse_proxy_line("127.0.0.1:9050")
    assert p.host == "127.0.0.1"
    assert p.port == 9050
    assert p.scheme == "http"


def test_parse_proxy_auth():
    p = parse_proxy_line("1.2.3.4:8080:user:pass")
    assert p.username == "user"
    assert p.password == "pass"
    assert "user" in p.to_httpx()


def test_proxy_playwright_dict():
    p = ProxyConfig(host="h", port=1, username="u", password="p", scheme="socks5")
    d = p.to_playwright()
    assert d["server"] == "socks5://h:1"
    assert d["username"] == "u"


def test_tor_manager_stop_cleans_spawned_resources(tmp_path):
    mgr = TorManager()
    mgr._owned = True
    mgr._data_dir = str(tmp_path / "tor-data")
    (tmp_path / "tor-data").mkdir()
    mgr._torrc_path = str(tmp_path / "torrc")
    (tmp_path / "torrc").write_text("SocksPort 9999\n", encoding="utf-8")
    proc = MagicMock()
    proc.poll.return_value = None
    mgr._proc = proc

    mgr.stop()

    assert mgr._proc is None
    assert mgr._owned is False
    assert not (tmp_path / "tor-data").exists()
    assert not (tmp_path / "torrc").exists()
    proc.terminate.assert_called_once()


def test_tor_uses_existing_daemon():
    mgr = TorManager()
    with patch.object(mgr, "_socks_reachable", return_value=True):
        proxy = mgr.start(timeout=1)
    assert proxy.port == 9050
    assert mgr.mode.startswith("existing-tor")
    assert mgr._owned is False
    mgr.stop()


@pytest.mark.integration
def test_tor_probe_idgod():
    """Requires Tor on :9050/:9150 or `tor` binary; hits idgod.ph over Tor."""
    import asyncio

    from idgod_order_cli.proxies import test_proxy_httpx

    mgr = TorManager()
    try:
        proxy = mgr.start(timeout=60)
        result = asyncio.run(
            test_proxy_httpx(proxy, "https://www.idgod.ph/order", timeout=90)
        )
        assert result.get("ok"), result.get("error", result)
        assert result.get("status") == 200
    finally:
        mgr.stop()
