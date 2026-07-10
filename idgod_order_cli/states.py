from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class StateOption:
    label: str
    price: float | None = None

    @property
    def normalized_state(self) -> str:
        # Extract base state name from labels like "California Polycarbonate - Official State Material"
        label = self.label.strip()
        for suffix in (
            " Polycarbonate - Official State Material",
            " Polycarbonate - Official Country Material",
            " - Provisional Driver License",
            " Provisional - Polycarbonate",
            " Identification Card Only",
            " CDL",
        ):
            if suffix in label:
                label = label.split(suffix)[0]
        return label.strip()


# Approximate base prices from idgod.ph price list (plain states ~$100-150)
DEFAULT_STATE_PRICES: dict[str, float] = {
    "alabama": 100, "alaska": 100, "arizona": 100, "arkansas": 100,
    "california": 100, "colorado": 100, "connecticut": 100, "delaware": 100,
    "district of columbia": 100, "florida": 100, "georgia": 100, "hawaii": 100,
    "idaho": 100, "illinois": 100, "indiana": 100, "iowa": 100, "kansas": 100,
    "kentucky": 100, "louisiana": 100, "maine": 100, "maryland": 100,
    "massachusetts": 100, "michigan": 100, "minnesota": 100, "mississippi": 100,
    "missouri": 100, "montana": 100, "nebraska": 100, "nevada": 100,
    "new hampshire": 100, "new jersey": 100, "new mexico": 100, "new york": 100,
    "north carolina": 100, "north dakota": 100, "ohio": 100, "oklahoma": 100,
    "oregon": 100, "pennsylvania": 100, "puerto rico": 100, "rhode island": 100,
    "south carolina": 100, "south dakota": 100, "tennessee": 100, "texas": 100,
    "utah": 100, "vermont": 100, "virginia": 100, "washington": 100,
    "west virginia": 100, "wisconsin": 100, "wyoming": 100,
}

PREMIUM_KEYWORDS = ("polycarbonate", "cdl", "provisional", "official", "new ")

US_STATE_CODES: dict[str, str] = {
    "al": "Alabama", "ak": "Alaska", "az": "Arizona", "ar": "Arkansas",
    "ca": "California", "co": "Colorado", "ct": "Connecticut", "de": "Delaware",
    "dc": "District of Columbia", "fl": "Florida", "ga": "Georgia", "hi": "Hawaii",
    "id": "Idaho", "il": "Illinois", "in": "Indiana", "ia": "Iowa", "ks": "Kansas",
    "ky": "Kentucky", "la": "Louisiana", "me": "Maine", "md": "Maryland",
    "ma": "Massachusetts", "mi": "Michigan", "mn": "Minnesota", "ms": "Mississippi",
    "mo": "Missouri", "mt": "Montana", "ne": "Nebraska", "nv": "Nevada",
    "nh": "New Hampshire", "nj": "New Jersey", "nm": "New Mexico", "ny": "New York",
    "nc": "North Carolina", "nd": "North Dakota", "oh": "Ohio", "ok": "Oklahoma",
    "or": "Oregon", "pa": "Pennsylvania", "pr": "Puerto Rico", "ri": "Rhode Island",
    "sc": "South Carolina", "sd": "South Dakota", "tn": "Tennessee", "tx": "Texas",
    "ut": "Utah", "vt": "Vermont", "va": "Virginia", "wa": "Washington",
    "wv": "West Virginia", "wi": "Wisconsin", "wy": "Wyoming",
}

PRODUCT_VARIANT_HINTS: dict[str, str] = {
    "STANDARD": "",
    "DMV_POLY": "Polycarbonate",
    "DMV": "Polycarbonate",
    "POLY": "Polycarbonate",
    "POLYCARBONATE": "Polycarbonate",
    "CDL": "CDL",
    "PROVISIONAL": "Provisional",
}


def expand_state_name(state: str) -> str:
    s = (state or "").strip()
    if not s:
        return s
    if len(s) == 2 and s.isalpha():
        return US_STATE_CODES.get(s.lower(), s)
    return s


def variant_from_product_id(product_id: str) -> str:
    pid = (product_id or "").strip()
    if not pid:
        return ""
    if ":" in pid:
        _state_part, variant = pid.split(":", 1)
        variant = variant.strip().upper()
        hint = PRODUCT_VARIANT_HINTS.get(variant, "")
        if hint:
            return hint
        return variant.replace("_", " ").title()
    return pid


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def parse_height(height: str) -> tuple[str, str]:
    """Parse height like 5'4\" or 5-4 into (feet, inches)."""
    h = height.strip()
    m = re.match(r"(\d+)\s*['\-]\s*(\d+)", h)
    if m:
        return m.group(1), m.group(2)
    m = re.match(r"(\d+)\s*ft\s*(\d+)", h, re.I)
    if m:
        return m.group(1), m.group(2)
    return "5", "6"


def map_sex(sex: str) -> str:
    s = sex.strip().lower()
    if s in ("f", "female", "woman"):
        return "Female"
    if s in ("m", "male", "man"):
        return "Male"
    return sex or "Female"


def map_eye_color(color: str) -> str:
    c = color.strip().title()
    allowed = {"Black", "Brown", "Blue", "Gray", "Green", "Hazel", "Maroon", "Pink", "Multicolor"}
    return c if c in allowed else "Brown"


def map_hair_color(color: str) -> str:
    c = color.strip().title()
    aliases = {"Blond": "Blonde", "Blonde": "Blonde"}
    c = aliases.get(c, c)
    allowed = {"Bald", "Black", "Blonde", "Brown", "Gray", "Red", "Sandy", "White"}
    return c if c in allowed else "Brown"


def estimate_price(label: str) -> float:
    base = _norm(label)
    price = DEFAULT_STATE_PRICES.get(base, 120.0)
    lower = label.lower()
    if any(k in lower for k in PREMIUM_KEYWORDS):
        price += 30.0
    if "cdl" in lower:
        price += 20.0
    return price


def match_state_options(requested: str, options: list[StateOption]) -> list[StateOption]:
    req = _norm(requested)
    exact = [o for o in options if _norm(o.label) == req]
    if exact:
        return exact
    starts = [o for o in options if _norm(o.label).startswith(req)]
    if starts:
        return starts
    contains = [o for o in options if req in _norm(o.label) or _norm(o.normalized_state) == req]
    if contains:
        return contains
    # word match e.g. "Washington" in "Washington Polycarbonate"
    word = [o for o in options if req == _norm(o.normalized_state)]
    return word


def pick_state_option(
    requested: str,
    options: list[StateOption],
    *,
    variant: str = "",
    cheapest: bool = False,
) -> tuple[StateOption | None, str]:
    if not options:
        return None, "No state options found on page"

    if variant:
        v = _norm(variant)
        for o in options:
            if _norm(o.label) == v or v in _norm(o.label):
                return o, ""
        return None, f"State variant '{variant}' not found. Available: {[o.label for o in options]}"

    matches = match_state_options(requested, options)
    if len(matches) == 1:
        return matches[0], ""

    if len(matches) > 1:
        if cheapest:
            best = min(matches, key=lambda o: o.price if o.price is not None else estimate_price(o.label))
            return best, f"Auto-selected cheapest: {best.label}"
        labels = [o.label for o in matches]
        return None, (
            f"Multiple state options for '{requested}': {labels}. "
            f"Use --state-variant or --cheapest-state"
        )

    return None, f"No state option matched '{requested}'. Available sample: {[o.label for o in options[:8]]}"
