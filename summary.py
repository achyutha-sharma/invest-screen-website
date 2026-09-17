"""
A plain-language summary of how something has behaved.

Everything here is arithmetic on a price series and on figures already
extracted from filings. No forecasts, no ratings -- the aim is to say what
happened in sentences someone can read once and understand, rather than a
table they have to interpret.

Three things shape the wording:

  * Volatility is described by what it felt like to hold, not by a number.
    "Fell more than 40% at one point" tells a reader more than a standard
    deviation of 0.31, and it is the same fact.
  * Every claim is tied to a figure, so nothing reads as opinion.
  * Where the data cannot support a sentence, the sentence is omitted rather
    than hedged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date


@dataclass
class PriceShape:
    """How a price has behaved, from a series of month-end closes."""
    years: float
    cagr: float | None                  # compound annual return, percent
    ytd: float | None                   # this calendar year so far, percent
    best_year: float | None
    worst_year: float | None
    max_drop: float | None              # largest peak-to-trough fall, percent
    drop_months: int | None             # how long that fall took to recover
    volatility: float | None            # annualised, percent
    down_years: int | None
    total_years: int | None


def _annual_returns(hist: list[tuple[str, float]]) -> list[tuple[int, float]]:
    """Calendar-year returns from month-end closes."""
    by_year: dict[int, list[tuple[str, float]]] = {}
    for d, v in hist:
        by_year.setdefault(int(d[:4]), []).append((d, v))

    out = []
    years = sorted(by_year)
    for i, y in enumerate(years):
        rows = sorted(by_year[y])
        # Start from December of the previous year where it exists, so a
        # calendar year is measured end to end rather than from January.
        prev = sorted(by_year[years[i - 1]])[-1][1] if i else rows[0][1]
        last = rows[-1][1]
        if prev and prev > 0 and len(rows) >= (12 if i else 6):
            out.append((y, 100 * (last / prev - 1)))
    return out


def shape(hist: list[tuple[str, float]]) -> PriceShape | None:
    """Describe a price series. None when there is too little to describe."""
    if not hist or len(hist) < 24:
        return None

    vals = [v for _, v in hist]
    years = len(vals) / 12

    first, last = vals[0], vals[-1]
    cagr = (100 * ((last / first) ** (1 / years) - 1)
            if first and first > 0 and years >= 2 else None)

    # This calendar year, measured from the last close of the year before.
    this_year = int(hist[-1][0][:4])
    prior = [v for d, v in hist if int(d[:4]) < this_year]
    ytd = (100 * (last / prior[-1] - 1)) if prior and prior[-1] else None

    annual = _annual_returns(hist)
    complete = [r for y, r in annual if y < this_year]
    best = max(complete) if complete else None
    worst = min(complete) if complete else None
    down = sum(1 for r in complete if r < 0) if complete else None

    # Largest peak-to-trough fall, and how long it took to get back.
    peak, max_drop, trough_i, peak_i = vals[0], 0.0, 0, 0
    cur_peak_i = 0
    for i, v in enumerate(vals):
        if v > peak:
            peak, cur_peak_i = v, i
        elif peak:
            drop = 100 * (v / peak - 1)
            if drop < max_drop:
                max_drop, trough_i, peak_i = drop, i, cur_peak_i

    recover = None
    if max_drop < 0:
        target = vals[peak_i]
        for i in range(trough_i, len(vals)):
            if vals[i] >= target:
                recover = i - peak_i
                break

    # Annualised volatility from monthly moves. Reported only to give the
    # wording a threshold; the text describes the falls instead.
    rets = [vals[i] / vals[i - 1] - 1
            for i in range(1, len(vals)) if vals[i - 1]]
    vol = None
    if len(rets) >= 12:
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        vol = 100 * math.sqrt(var) * math.sqrt(12)

    return PriceShape(
        years=years, cagr=cagr, ytd=ytd, best_year=best, worst_year=worst,
        max_drop=max_drop if max_drop < 0 else None,
        drop_months=recover, volatility=vol,
        down_years=down, total_years=len(complete) if complete else None,
    )


def steadiness(vol: float | None) -> str:
    """Volatility as a word, with the bands stated on the page."""
    if vol is None:
        return ""
    if vol < 15:
        return "steadier than most shares"
    if vol < 25:
        return "about as bumpy as the market overall"
    if vol < 40:
        return "bumpier than the market"
    return "very volatile"


def price_sentences(name: str, shape_: PriceShape | None, price: float | None,
                    day: float | None, money=str) -> list[str]:
    """How the price has behaved, in sentences."""
    out: list[str] = []
    if price is not None and day is not None:
        out.append(f"{name} trades at <b>{money(price)}</b>, "
                   f"{'up' if day >= 0 else 'down'} <b>{abs(day):.2f}%</b> today.")

    if not shape_:
        return out

    if shape_.ytd is not None:
        out.append(f"So far this year it is "
                   f"<b>{'up' if shape_.ytd >= 0 else 'down'} "
                   f"{abs(shape_.ytd):,.1f}%</b>.")

    if shape_.cagr is not None:
        out.append(
            f"Over about {shape_.years:.0f} years the price has compounded at "
            f"<b>{shape_.cagr:+,.1f}% a year</b>. That is the average; almost no "
            "individual year looks like it.")

    if shape_.best_year is not None and shape_.worst_year is not None:
        # A company that never had a losing year needs different wording, or
        # the sentence claims a loss that did not happen.
        worst = (f"its worst still gained <b>{shape_.worst_year:,.1f}%</b>"
                 if shape_.worst_year >= 0 else
                 f"its worst lost <b>{abs(shape_.worst_year):,.1f}%</b>")
        tail = "."
        if shape_.down_years is not None and shape_.total_years:
            tail = (f", with <b>{shape_.down_years} of {shape_.total_years}</b> years "
                    "finishing lower." if shape_.down_years else
                    f" — <b>none</b> of the last {shape_.total_years} full years "
                    "finished lower.")
        out.append(f"Its best full year gained <b>{shape_.best_year:+,.1f}%</b> and "
                   + worst + tail)

    if shape_.max_drop is not None:
        line = (f"At its worst it fell <b>{abs(shape_.max_drop):,.0f}%</b> from a "
                "previous high")
        if shape_.drop_months:
            line += (f" and took <b>{shape_.drop_months} months</b> to get back to "
                     "that level")
        elif shape_.drop_months is None:
            line += " and has not returned to that level since"
        out.append(line + ". <b>That is the part worth imagining before buying "
                          "anything</b> — it is what holding it actually felt like.")

    word = steadiness(shape_.volatility)
    if word:
        out.append(f"Month to month its price swings make it <b>{word}</b>.")

    return out
