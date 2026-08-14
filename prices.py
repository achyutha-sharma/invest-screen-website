"""
Share prices.

The only figure in this tool that does not come from an SEC filing, so it is
kept in one small module with one job: when the feed changes, breaks, or
rate-limits, exactly one file needs fixing.

Finnhub is used because it is an official API with published terms, rather than
a scraper. That matters less for reliability than it sounds -- any provider can
change -- but it means when it does break, it breaks with a readable error
rather than silently returning a challenge page dressed as data.

Every method returns empty rather than raising. A missing price should cost the
reader the valuation rows, not the page.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

QUOTE_URL = "https://finnhub.io/api/v1/quote"
CANDLE_URL = "https://finnhub.io/api/v1/stock/candle"

CACHE_DIR = Path(os.environ.get("PRICE_CACHE_DIR", Path.home() / ".price_cache"))
QUOTE_TTL = 10 * 60           # free-tier data is delayed anyway
HISTORY_TTL = 24 * 60 * 60


@dataclass
class Quote:
    price: float | None = None
    prev_close: float | None = None
    day_change: float | None = None
    day_change_pct: float | None = None
    as_of: str = ""
    source: str = ""
    problem: str = ""

    @property
    def available(self) -> bool:
        return self.price is not None and self.price > 0


class PriceClient:
    """Quotes and monthly history, cached on disk.

    Without an API key every call returns an empty result carrying a `problem`
    string, so the page can explain the gap instead of showing nothing.
    """

    def __init__(self, api_key: str | None = None, cache_dir: Path = CACHE_DIR,
                 timeout: int = 12):
        self.key = api_key or os.environ.get("FINNHUB_API_KEY", "")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.key)

    # -- cache -------------------------------------------------------------

    def _cached(self, name: str, ttl: int):
        f = self.cache_dir / name
        if f.exists() and time.time() - f.stat().st_mtime < ttl:
            try:
                return json.loads(f.read_text())
            except Exception:
                return None
        return None

    def _store(self, name: str, data) -> None:
        try:
            (self.cache_dir / name).write_text(json.dumps(data))
        except Exception:
            pass                              # a failed cache write is not an error

    def _get(self, url: str, params: dict):
        """Returns (json, problem). Never raises."""
        if not self.key:
            return None, "No price feed is configured."
        try:
            import requests

            r = requests.get(url, params={**params, "token": self.key},
                             timeout=self.timeout)
            if r.status_code == 401:
                return None, "The price feed rejected the API key."
            if r.status_code == 429:
                return None, "The price feed is rate limited; try again shortly."
            r.raise_for_status()
            return r.json(), ""
        except Exception:
            return None, "The price feed could not be reached."

    # -- quotes ------------------------------------------------------------

    def quote(self, ticker: str) -> Quote:
        sym = ticker.strip().upper()
        if not sym:
            return Quote(problem="No ticker given.")

        cached = self._cached(f"q_{sym}.json", QUOTE_TTL)
        if cached:
            return Quote(**cached)

        data, problem = self._get(QUOTE_URL, {"symbol": sym})
        if data is None:
            return Quote(problem=problem)

        # Finnhub: c current, pc previous close, d change, dp change percent,
        # t the quote timestamp. A zero current price means "unknown symbol".
        try:
            price = float(data.get("c") or 0)
        except (TypeError, ValueError):
            price = 0.0
        if price <= 0:
            return Quote(problem=f"No price found for {sym}.")

        def num(key):
            try:
                v = data.get(key)
                return float(v) if v not in (None, "") else None
            except (TypeError, ValueError):
                return None

        ts = data.get("t")
        as_of = ""
        if ts:
            try:
                as_of = datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%d %b %Y")
            except Exception:
                as_of = ""

        q = Quote(price=price, prev_close=num("pc"), day_change=num("d"),
                  day_change_pct=num("dp"), as_of=as_of, source="Finnhub")
        self._store(f"q_{sym}.json", q.__dict__)
        return q

    # -- history -----------------------------------------------------------

    def monthly(self, ticker: str, years: int = 11) -> list[tuple[str, float]]:
        """Month-end closes, oldest first, as (YYYY-MM-DD, close).

        Candle history is not on every free plan. When it is unavailable this
        returns nothing and the caller falls back to showing no P/E history --
        which is why the scorecard treats that component as skippable.
        """
        sym = ticker.strip().upper()
        if not sym:
            return []

        cached = self._cached(f"h_{sym}.json", HISTORY_TTL)
        if cached is not None:
            return [tuple(r) for r in cached]

        now = int(time.time())
        data, _ = self._get(CANDLE_URL, {
            "symbol": sym, "resolution": "M",
            "from": now - years * 365 * 24 * 3600, "to": now,
        })
        out: list[tuple[str, float]] = []
        if data and data.get("s") == "ok":
            for t, c in zip(data.get("t", []), data.get("c", [])):
                try:
                    d = datetime.fromtimestamp(int(t), tz=timezone.utc).strftime("%Y-%m-%d")
                    out.append((d, float(c)))
                except Exception:
                    continue
        self._store(f"h_{sym}.json", out)
        return out

    def at_fiscal_ends(self, ticker: str, ends: list[tuple[str, str]]) -> dict[str, float]:
        """A price near each fiscal year end, keyed by period label.

        Used for a company's own P/E history. Takes the closest month-end
        within 45 days, so a year with no nearby data drops out rather than
        borrowing a price from months away.
        """
        hist = self.monthly(ticker)
        if not hist:
            return {}

        parsed = []
        for d, px in hist:
            try:
                parsed.append((datetime.strptime(d, "%Y-%m-%d").date(), px))
            except ValueError:
                continue

        out: dict[str, float] = {}
        for label, iso in ends:
            try:
                target = datetime.strptime(iso, "%Y-%m-%d").date()
            except ValueError:
                continue
            best, gap = None, None
            for d, px in parsed:
                delta = abs((d - target).days)
                if gap is None or delta < gap:
                    best, gap = px, delta
            if best is not None and gap is not None and gap <= 45:
                out[label] = best
        return out
