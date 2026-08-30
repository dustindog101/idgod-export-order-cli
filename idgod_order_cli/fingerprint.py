"""Browser fingerprint generator for rotating realistic client identities."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BrowserFingerprint:
    user_agent: str
    headers: dict[str, str] = field(default_factory=dict)
    viewport: dict[str, int] = field(default_factory=lambda: {"width": 1920, "height": 1080})
    device_scale_factor: float = 1.0
    is_mobile: bool = False
    platform: str = "Windows"
    browser_family: str = "chrome"

    def to_playwright_context_options(self) -> dict[str, Any]:
        """Convert to kwargs for playwright.browser.new_context()."""
        return {
            "user_agent": self.user_agent,
            "viewport": self.viewport,
            "device_scale_factor": self.device_scale_factor,
            "is_mobile": self.is_mobile,
            "extra_http_headers": {
                k: v for k, v in self.headers.items()
                if k.lower() not in ("user-agent", "host", "connection", "content-length")
            },
        }


# Coherent device & OS definitions
_PLATFORM_PROFILES = [
    # 1. Windows Chrome
    {
        "family": "chrome",
        "platform": "Windows",
        "is_mobile": False,
        "os_str": "Windows NT 10.0; Win64; x64",
        "sec_platform": '"Windows"',
        "viewports": [
            (1920, 1080, 1.0),
            (1536, 864, 1.25),
            (1440, 900, 1.0),
            (1366, 768, 1.0),
            (2560, 1440, 1.0),
            (1600, 900, 1.0),
        ],
    },
    # 2. Windows Edge
    {
        "family": "edge",
        "platform": "Windows",
        "is_mobile": False,
        "os_str": "Windows NT 10.0; Win64; x64",
        "sec_platform": '"Windows"',
        "viewports": [
            (1920, 1080, 1.0),
            (1536, 864, 1.25),
            (1440, 900, 1.0),
            (2560, 1440, 1.0),
        ],
    },
    # 3. macOS Chrome
    {
        "family": "chrome",
        "platform": "macOS",
        "is_mobile": False,
        "os_str": "Macintosh; Intel Mac OS X 10_15_7",
        "sec_platform": '"macOS"',
        "viewports": [
            (1440, 900, 2.0),
            (1680, 1050, 2.0),
            (1920, 1080, 1.0),
            (2560, 1440, 2.0),
            (1728, 1117, 2.0),
        ],
    },
    # 4. macOS Safari
    {
        "family": "safari",
        "platform": "macOS",
        "is_mobile": False,
        "os_str": "Macintosh; Intel Mac OS X 10_15_7",
        "sec_platform": None,
        "viewports": [
            (1440, 900, 2.0),
            (1680, 1050, 2.0),
            (1728, 1117, 2.0),
            (2560, 1440, 2.0),
        ],
    },
    # 5. Linux Chrome
    {
        "family": "chrome",
        "platform": "Linux",
        "is_mobile": False,
        "os_str": "X11; Linux x86_64",
        "sec_platform": '"Linux"',
        "viewports": [
            (1920, 1080, 1.0),
            (2560, 1440, 1.0),
            (1440, 900, 1.0),
        ],
    },
    # 6. Windows Firefox
    {
        "family": "firefox",
        "platform": "Windows",
        "is_mobile": False,
        "os_str": "Windows NT 10.0; Win64; x64; rv:{ff_version}.0",
        "sec_platform": None,
        "viewports": [
            (1920, 1080, 1.0),
            (1536, 864, 1.25),
            (1440, 900, 1.0),
        ],
    },
    # 7. Android Chrome Mobile
    {
        "family": "chrome_mobile",
        "platform": "Android",
        "is_mobile": True,
        "os_str": "Linux; Android 14; K",
        "sec_platform": '"Android"',
        "viewports": [
            (412, 915, 2.625),
            (393, 873, 2.75),
            (390, 844, 3.0),
            (412, 892, 2.625),
        ],
    },
]

_LANGUAGES = [
    "en-US,en;q=0.9",
    "en-US,en;q=0.8,en-GB;q=0.7",
    "en-US,en;q=0.9,es;q=0.8",
    "en-US,en;q=0.9,fr;q=0.8",
    "en-CA,en-US;q=0.9,en;q=0.8",
]

_CHROME_VERSIONS = ["129.0.6668.100", "130.0.6723.116", "131.0.6778.85", "132.0.6834.110", "133.0.6943.53"]
_FIREFOX_VERSIONS = ["131", "132", "133", "134"]
_SAFARI_VERSIONS = [("17.6", "605.1.15"), ("18.0", "605.1.15"), ("18.1.1", "605.1.15"), ("18.2", "605.1.15")]


def generate_browser_fingerprint(*, profile_index: int | None = None) -> BrowserFingerprint:
    """Generate a coherent, realistic browser fingerprint."""
    if profile_index is not None and 0 <= profile_index < len(_PLATFORM_PROFILES):
        p = _PLATFORM_PROFILES[profile_index]
    else:
        p = random.choice(_PLATFORM_PROFILES)

    family = p["family"]
    platform = p["platform"]
    is_mobile = p["is_mobile"]
    v_w, v_h, scale = random.choice(p["viewports"])
    lang = random.choice(_LANGUAGES)

    headers: dict[str, str] = {
        "Accept-Language": lang,
        "Upgrade-Insecure-Requests": "1",
    }

    if family in ("chrome", "chrome_mobile", "edge"):
        chrome_ver = random.choice(_CHROME_VERSIONS)
        major_ver = chrome_ver.split(".")[0]

        if family == "edge":
            ua = (
                f"Mozilla/5.0 ({p['os_str']}) AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{chrome_ver} Safari/537.36 Edg/{major_ver}.0.0.0"
            )
            sec_ch_ua = f'"Microsoft Edge";v="{major_ver}", "Chromium";v="{major_ver}", "Not A(Brand";v="24"'
        elif family == "chrome_mobile":
            ua = (
                f"Mozilla/5.0 ({p['os_str']}) AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{chrome_ver} Mobile Safari/537.36"
            )
            sec_ch_ua = f'"Google Chrome";v="{major_ver}", "Chromium";v="{major_ver}", "Not_A Brand";v="24"'
        else:
            ua = (
                f"Mozilla/5.0 ({p['os_str']}) AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{chrome_ver} Safari/537.36"
            )
            sec_ch_ua = f'"Google Chrome";v="{major_ver}", "Chromium";v="{major_ver}", "Not_A Brand";v="24"'

        headers.update(
            {
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "sec-ch-ua": sec_ch_ua,
                "sec-ch-ua-mobile": "?1" if is_mobile else "?0",
                "sec-ch-ua-platform": p["sec_platform"],
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "none",
                "sec-fetch-user": "?1",
            }
        )

    elif family == "safari":
        saf_ver, webkit_ver = random.choice(_SAFARI_VERSIONS)
        ua = (
            f"Mozilla/5.0 ({p['os_str']}) AppleWebKit/{webkit_ver} (KHTML, like Gecko) "
            f"Version/{saf_ver} Safari/{webkit_ver}"
        )
        headers.update(
            {
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "none",
            }
        )

    elif family == "firefox":
        ff_ver = random.choice(_FIREFOX_VERSIONS)
        os_formatted = p["os_str"].format(ff_version=ff_ver)
        ua = f"Mozilla/5.0 ({os_formatted}) Gecko/20100101 Firefox/{ff_ver}.0"
        headers.update(
            {
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "none",
                "sec-fetch-user": "?1",
            }
        )
    else:
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
        headers["User-Agent"] = ua

    return BrowserFingerprint(
        user_agent=ua,
        headers=headers,
        viewport={"width": v_w, "height": v_h},
        device_scale_factor=scale,
        is_mobile=is_mobile,
        platform=platform,
        browser_family=family,
    )
