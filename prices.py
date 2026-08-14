"""
Share prices.

The only figure in this tool that does not come from an SEC filing. Kept in one
small module with a single job, so that when the feed changes its terms, breaks,
or rate-limits us, exactly one thing needs fixing and the rest of the page
carries on without it.

Everything here returns None rather than raising. A missing price should cost
the reader the valuation rows, not the whole page.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

# Stooq publishes end-of-day prices as plain CSV with no key and no signup,
# which makes it the least fragile free option: nothing to expire, nothing to
# leak, and if it disappears the tool degrades instead of breaking.
STOOQ_QUOTE = "https://stooq.com/q/l/?s={sym}.us&f=sd2ohlcv&h&e=csv"
STOOQ_HISTORY = "https://stooq.com/q/d/l/?s={sym}.us&i=m"

CACHE_DIR = Path(os.environ.get("PRICE_CACHE_DIR", Path.home() / ".price_cache"))
QUOTE_TTL = 15 * 60          # quotes are end-of-day; refreshing often is pointless
HISTORY_TTL = 24 * 60 * 60


@dataclass
class Quote:
    price: float | None = None
    prev_close: float | None = None
    as_of: str = ""
    source: str = ""

    @property
    def day_change_pct(self) -> float | None:
        if self.price is None or not self.prev_close:
            return None
        return 100 * (self.price - self.prev_close) / self.prev_close

    @property
    def available(self) -> bool:
        return self.price is not None


class PriceClient:
    """Fetches quotes and monthly history, cached on disk."""

    def __init__(self, cache_dir: Path = CACHE_DIR, timeout: int = 12):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout

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
            pass                                   # a failed cache write is not worth an error

    def _get(self, url: str) -> str | None:
        try:
            import requests

            r = requests.get(url, timeout=self.timeout,
                             headers={"User-Agent": "value-screen/1.0"})
            r.raise_for_status()
            return r.text
        except Exception:
            return None

    # -- quotes ------------------------------------------------------------

    def quote(self, ticker: str) -> Quote:
        """Latest close and the one before it, for today's move."""
        sym = ticker.strip().lower()
        if not sym:
            return Quote()

        cached = self._cached(f"q_{sym}.json", QUOTE_TTL)
        if cached:
            return Quote(**cached)

        text = self._get(STOOQ_QUOTE.format(sym=sym))
        q = Quote()
        if text:
            rows = [r for r in text.strip().splitlines() if r]
            if len(rows) >= 2:
                cols = rows[0].lower().split(",")
                vals = rows[1].split(",")
                row = dict(zip(cols, vals))
                try:
                    close = float(row.get("close", ""))
                    open_ = float(row.get("open", ""))
                    q = Quote(price=close, prev_close=open_ or None,
                              as_of=row.get("date", ""), source="Stooq, end of day")
                except ValueError:
                    q = Quote()

        # The day move is more honest against the previous close than against
        # the same session's open, so use history when it is already to hand.
        if q.available:
            hist = self.monthly(ticker)
            if len(hist) >= 2 and hist[-1][1] and abs(hist[-1][1] - q.price) > 1e-9:
                q.prev_close = q.prev_close or hist[-1][1]
            self._store(f"q_{sym}.json", q.__dict__)
        return q

    # -- history -----------------------------------------------------------

    def monthly(self, ticker: str) -> list[tuple[str, float]]:
        """Month-end closes, oldest first, as (YYYY-MM-DD, close)."""
        sym = ticker.strip().lower()
        if not sym:
            return []

        cached = self._cached(f"h_{sym}.json", HISTORY_TTL)
        if cached is not None:
            return [tuple(r) for r in cached]

        text = self._get(STOOQ_HISTORY.format(sym=sym))
        out: list[tuple[str, float]] = []
        if text:
            for line in text.strip().splitlines()[1:]:
                parts = line.split(",")
                if len(parts) < 5:
                    continue
                try:
                    out.append((parts[0], float(parts[4])))
                except ValueError:
                    continue
        if out:
            self._store(f"h_{sym}.json", out)
        return out

    def at_fiscal_ends(self, ticker: str, ends: list[str]) -> dict[str, float]:
        """A price near each fiscal year end, keyed by the period label.

        Used for the company's own P/E history. Takes the closest month-end
        within 45 days, so a year with no nearby data drops out rather than
        being filled with a price from months away.
        """
        from datetime import date, datetime

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
