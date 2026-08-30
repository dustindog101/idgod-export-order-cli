from idgod_order_cli.fingerprint import (
    BrowserFingerprint,
    generate_browser_fingerprint,
    _PLATFORM_PROFILES,
)


def test_generate_random_fingerprint():
    fp = generate_browser_fingerprint()
    assert isinstance(fp, BrowserFingerprint)
    assert fp.user_agent
    assert "User-Agent" in fp.headers
    assert fp.headers["User-Agent"] == fp.user_agent
    assert "Accept-Language" in fp.headers
    assert fp.viewport["width"] > 0
    assert fp.viewport["height"] > 0
    assert fp.device_scale_factor > 0


def test_generate_all_platform_profiles():
    for i in range(len(_PLATFORM_PROFILES)):
        fp = generate_browser_fingerprint(profile_index=i)
        assert fp.user_agent
        assert fp.headers["User-Agent"] == fp.user_agent
        opts = fp.to_playwright_context_options()
        assert opts["user_agent"] == fp.user_agent
        assert opts["viewport"] == fp.viewport
        assert opts["is_mobile"] == fp.is_mobile


def test_chrome_client_hints_coherence():
    # Profile 0: Windows Chrome
    fp = generate_browser_fingerprint(profile_index=0)
    assert "Windows" in fp.user_agent
    assert "Chrome" in fp.user_agent
    assert fp.headers.get("sec-ch-ua-platform") == '"Windows"'
    assert fp.headers.get("sec-ch-ua-mobile") == "?0"
    assert "Google Chrome" in fp.headers.get("sec-ch-ua", "")


def test_safari_coherence():
    # Profile 3: macOS Safari
    fp = generate_browser_fingerprint(profile_index=3)
    assert "Safari" in fp.user_agent
    assert "Version/" in fp.user_agent
    assert "sec-ch-ua" not in fp.headers


def test_firefox_coherence():
    # Profile 5: Windows Firefox
    fp = generate_browser_fingerprint(profile_index=5)
    assert "Firefox/" in fp.user_agent
    assert "sec-ch-ua" not in fp.headers


def test_android_mobile_coherence():
    # Profile 6: Android Chrome Mobile
    fp = generate_browser_fingerprint(profile_index=6)
    assert "Android" in fp.user_agent
    assert "Mobile" in fp.user_agent
    assert fp.is_mobile is True
    assert fp.headers.get("sec-ch-ua-mobile") == "?1"
    assert fp.headers.get("sec-ch-ua-platform") == '"Android"'


def test_fingerprint_random_diversity():
    uas = {generate_browser_fingerprint().user_agent for _ in range(50)}
    assert len(uas) >= 5, "Expected diversity across randomized fingerprints"
