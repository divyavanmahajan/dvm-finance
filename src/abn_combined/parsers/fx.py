"""Euro reference rates from the European Central Bank (ECB).

The SEB parser, the First Tech parser and the PayPal parser (for a payment
with no EUR funding row) store each transaction in EUR. They get the EUR
reference rates from the ECB XML feed (no API key required):

    90-day:  https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml
    history: https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.xml

Each rate is the number of currency units for one euro, so
``EUR = native amount / rate``.

Rate lookup order:
  1. Exact date from the ECB feed
  2. Most recent earlier business day in the cache (the ECB does not publish
     on weekends or holidays)
  3. If all fetches fail, the parser stores the native currency
"""

import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

_ECB_NS = "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"
_ECB_90D_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"
_ECB_HIST_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.xml"


def parse_ecb_xml(url: str, currency: str) -> dict[date, float]:
    """Fetch and parse an ECB eurofxref XML file, returning {date: EUR/<currency> rate}."""
    cache: dict[date, float] = {}
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            tree = ET.parse(resp)
        root = tree.getroot()
        for day_cube in root.findall(f".//{{{_ECB_NS}}}Cube[@time]"):
            day_str = day_cube.get("time")
            if not day_str:
                continue
            try:
                d = datetime.strptime(day_str, "%Y-%m-%d").date()
            except ValueError:
                continue
            for ccy_cube in day_cube.findall(f"{{{_ECB_NS}}}Cube"):
                if ccy_cube.get("currency") == currency:
                    try:
                        cache[d] = float(ccy_cube.get("rate", "0"))
                    except (TypeError, ValueError):
                        pass
                    break
    except Exception:
        pass
    return cache


def build_rate_cache(dates: list[date], currency: str) -> dict[date, float]:
    """Return a {date: EUR→<currency> rate} cache covering the given dates.

    Fetches the 90-day ECB XML first. If the oldest date in the file predates
    the 90-day window, also fetches the full history XML.
    """
    cache = parse_ecb_xml(_ECB_90D_URL, currency)

    if dates and cache:
        oldest_needed = min(dates)
        oldest_cached = min(cache)
        if oldest_needed < oldest_cached:
            hist = parse_ecb_xml(_ECB_HIST_URL, currency)
            cache.update(hist)

    return cache


def best_rate(cache: dict[date, float], target: date) -> float | None:
    """Return the rate for target, or the most recent earlier rate (weekend/holiday fallback)."""
    if target in cache:
        return cache[target]
    earlier = [d for d in cache if d <= target]
    if earlier:
        return cache[max(earlier)]
    # If target is before all cached dates, use the oldest
    if cache:
        return cache[min(cache)]
    return None


def to_eur(amount: Decimal, rate: float) -> float:
    """Convert an exact native amount to EUR, rounded one time to 2 places, half up."""
    return float((amount / Decimal(str(rate))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
