"""
What the share price is already assuming.

A discounted cash flow run forwards produces a single number -- "this is
worth $187.42" -- that looks like a fact and is mostly a restatement of the
three assumptions someone typed in. Move the discount rate two points and a
quarter of the value disappears. For a reader who is still learning what
free cash flow is, that number is the most misleading thing a page could
show, because nothing about it looks uncertain.

So this runs the model backwards. The price is a fact: the market has
settled on it. What that price implies about future cash flow is arithmetic
from the price, not an opinion about the company. The question becomes

    "to be worth what it already costs, how fast does this have to grow?"

and the reader checks that answer against what the company has actually
managed. No target, no verdict on whether to buy -- just the assumption the
price contains, made visible, next to the record.

Nothing here is a forecast, and the module refuses rather than guesses:
a company burning cash, a bank, or a price the model cannot reach at any
sane growth rate all return a stated reason instead of a number.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Ten years of explicit forecast, then a terminal value. Ten is the common
# convention: long enough that the terminal value does not swamp everything,
# short enough that nobody pretends to see past it.
HORIZON = 10

# Defaults the reader can change. Nine per cent is a middling cost of equity
# for a large US company; 2.5% is roughly long-run inflation, which is the
# most a mature business can grow for ever without eventually becoming the
# whole economy.
DEFAULT_DISCOUNT = 0.09
DEFAULT_TERMINAL = 0.025

# Growth rates the solver will consider. Outside this range the honest
# answer is that the model cannot explain the price, not a number.
MIN_GROWTH = -0.40
MAX_GROWTH = 0.60

# SIC codes 6000-6799 are finance, insurance and property. A bank's cash
# flow statement does not mean what it means elsewhere -- lending moves
# enormous sums through operating cash flow -- so free cash flow is not a
# valuation input for them and this model does not apply.
FINANCIAL_SIC = range(6000, 6800)


@dataclass
class Reverse:
    """The growth rate implied by today's price, and what to compare it to."""

    implied: float | None = None        # annual FCF growth the price assumes
    fcf_base: float | None = None       # the cash flow it grows from
    base_years: int = 0                 # how many years were averaged into it
    history: float | None = None        # what the company has actually managed
    history_years: int = 0
    market_cap: float | None = None
    net_debt: float | None = None
    enterprise: float | None = None
    discount: float = DEFAULT_DISCOUNT
    terminal: float = DEFAULT_TERMINAL
    horizon: int = HORIZON
    problem: str = ""                   # why there is no number
    notes: list[str] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return self.implied is not None

    @property
    def gap(self) -> float | None:
        """Implied growth less the growth already achieved, in points."""
        if self.implied is None or self.history is None:
            return None
        return 100 * (self.implied - self.history)


# --------------------------------------------------------------------------
# The model
# --------------------------------------------------------------------------


def enterprise_value(price: float, shares: float,
                     debt: float | None, cash: float | None) -> tuple[float, float, float]:
    """Market cap, net debt, and the two added together.

    Free cash flow is paid out before anyone decides whether it goes to
    lenders or owners, so a model built on it values the whole business.
    Comparing that to the share price alone would flatter a company that
    has borrowed heavily, which is exactly the company it should not
    flatter.
    """
    cap = price * shares
    net = (debt or 0.0) - (cash or 0.0)
    return cap, net, cap + net


def value_at(growth: float, fcf: float, discount: float,
             terminal: float, horizon: int = HORIZON) -> float:
    """Present value of cash flow growing at `growth`, then for ever."""
    total = 0.0
    for t in range(1, horizon + 1):
        total += fcf * (1 + growth) ** t / (1 + discount) ** t
    # Gordon growth on the final year's cash flow, discounted back.
    final = fcf * (1 + growth) ** horizon * (1 + terminal)
    total += (final / (discount - terminal)) / (1 + discount) ** horizon
    return total


def implied_growth(target: float, fcf: float, discount: float = DEFAULT_DISCOUNT,
                   terminal: float = DEFAULT_TERMINAL,
                   horizon: int = HORIZON) -> float | None:
    """The growth rate at which the model's value equals `target`.

    Value rises monotonically with growth, so a bisection always converges
    and always converges on the only answer. Returns None when the target
    lies outside the range of growth rates worth entertaining -- a price
    that needs 80% a year for a decade is not telling you the company will
    do that, it is telling you this model does not describe the price.
    """
    if fcf <= 0 or discount <= terminal:
        return None

    lo, hi = MIN_GROWTH, MAX_GROWTH
    if target < value_at(lo, fcf, discount, terminal, horizon):
        return None
    if target > value_at(hi, fcf, discount, terminal, horizon):
        return None

    for _ in range(80):                       # far more than needed; cheap
        mid = (lo + hi) / 2
        if value_at(mid, fcf, discount, terminal, horizon) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# --------------------------------------------------------------------------
# Inputs drawn from the filings
# --------------------------------------------------------------------------


def fcf_series(eq) -> list[tuple[str, float]]:
    """Free cash flow per filed year, oldest first.

    Operating cash flow less the money spent on the assets needed to keep
    producing it. Both are tagged in the cash flow statement, so this is
    arithmetic on filed figures rather than an estimate.
    """
    out = []
    for p in eq.years:
        ocf, capex = p.get("ocf"), p.get("capex")
        if ocf is None or capex is None:
            continue
        out.append((p.label, ocf - capex))
    return out


def base_fcf(series: list[tuple[str, float]], years: int = 3
             ) -> tuple[float | None, int]:
    """A starting cash flow, averaged over the last few years.

    Capital spending is lumpy. A company that happened to build a factory
    last year shows a free cash flow that says more about the factory than
    about the business, and starting a ten-year projection from it carries
    that one year all the way to the terminal value. Averaging three years
    is the standard way to take the edge off.
    """
    if not series:
        return None, 0
    tail = [v for _, v in series[-years:]]
    return sum(tail) / len(tail), len(tail)


def cagr(series: list[tuple[str, float]]) -> tuple[float | None, int]:
    """Compound annual growth across the filed years.

    Needs a positive start and end: a company that was burning cash and now
    generates it has grown by an undefined percentage, and saying "+840%"
    would be worse than saying nothing.
    """
    if len(series) < 4:
        return None, len(series)
    first, last = series[0][1], series[-1][1]
    n = len(series) - 1
    if first <= 0 or last <= 0:
        return None, len(series)
    return (last / first) ** (1 / n) - 1, len(series)


# --------------------------------------------------------------------------
# Putting it together
# --------------------------------------------------------------------------


def reverse(eq, price: float | None, shares: float | None,
            debt: float | None, cash: float | None, sic: str = "",
            discount: float = DEFAULT_DISCOUNT,
            terminal: float = DEFAULT_TERMINAL,
            horizon: int = HORIZON) -> Reverse:
    """Everything the page needs, or a plain reason there is nothing."""
    r = Reverse(discount=discount, terminal=terminal, horizon=horizon)

    try:
        code = int(str(sic).strip()[:4] or 0)
    except ValueError:
        code = 0
    if code in FINANCIAL_SIC:
        r.problem = (
            "This model does not work on banks, insurers or property trusts. "
            "Lending and deposits move enormous sums through operating cash "
            "flow, so free cash flow for a financial company is not the "
            "surplus it is everywhere else — it is mostly an artefact of how "
            "much lending the company did that year.")
        return r

    if not price or price <= 0:
        r.problem = ("There is no share price available, and the whole "
                     "question here is what a price implies.")
        return r
    if not shares or shares <= 0:
        r.problem = "The filings do not give a share count to value against."
        return r

    series = fcf_series(eq)
    if not series:
        r.problem = ("This company has not tagged operating cash flow and "
                     "capital spending in a form the filings expose, so "
                     "there is no free cash flow to work from.")
        return r

    fcf, n_base = base_fcf(series)
    r.fcf_base, r.base_years = fcf, n_base
    r.history, r.history_years = cagr(series)

    cap, net, ev = enterprise_value(price, shares, debt, cash)
    r.market_cap, r.net_debt, r.enterprise = cap, net, ev

    if fcf is None or fcf <= 0:
        r.problem = (
            "This company spent more cash than it generated over the last "
            f"{n_base} year{'s' if n_base != 1 else ''}, so there is no "
            "positive cash flow to grow. That is common for a business "
            "investing heavily, and it is exactly the case a cash flow model "
            "cannot value — which is worth knowing in itself.")
        return r

    if discount <= terminal:
        r.problem = ("The discount rate has to be above the long-run growth "
                     "rate, or the model values the company at infinity.")
        return r

    g = implied_growth(ev, fcf, discount, terminal, horizon)
    if g is None:
        above = ev > value_at(MAX_GROWTH, fcf, discount, terminal, horizon)
        if above:
            r.problem = (
                f"Today's price needs free cash flow to grow faster than "
                f"{MAX_GROWTH * 100:.0f}% a year for {horizon} years. No "
                "sensible growth rate reaches it, which usually means the "
                "market is valuing something this model cannot see — assets "
                "not yet earning, a business about to change shape, or simply "
                "enthusiasm.")
        else:
            r.problem = (
                "Today's price is below what this company's current cash flow "
                "would be worth even in steep decline. Either the market "
                "expects the cash to stop, or something is wrong with the "
                "figures worth checking in the filing itself.")
        return r

    r.implied = g
    if n_base > 1:
        r.notes.append(
            f"Cash flow is averaged over the last {n_base} filed years, "
            "because a single year of heavy building would otherwise set the "
            "whole projection.")
    if net > 0:
        r.notes.append(
            "Net borrowings are added to the market value, because free cash "
            "flow pays lenders before owners.")
    return r


# --------------------------------------------------------------------------
# Saying it in words
# --------------------------------------------------------------------------


def verdict(r: Reverse) -> tuple[str, str]:
    """A short headline and a sentence, from the numbers alone."""
    if not r.available:
        return "", ""
    g = r.implied * 100

    if r.history is None:
        if g <= 0:
            return "The price assumes decline", (
                "The market is priced for cash flow to shrink from here. "
                "There is not enough filed history to say whether it has been "
                "shrinking already.")
        tone = ("modest" if g < 5 else "ordinary" if g < 10
                else "demanding" if g < 20 else "very demanding")
        return f"The price assumes {g:.0f}% a year", (
            f"That is {tone} on its own terms, but this company has not filed "
            "enough years of cash flow to say whether it has done anything "
            "like it before.")

    h = r.history * 100
    gap = g - h

    if g <= 0:
        return "The price assumes decline", (
            f"The market is priced for free cash flow to fall about "
            f"{abs(g):.0f}% a year, even though it has grown about {h:.0f}% a "
            f"year across the {r.history_years} filed years. A price like that "
            "is a forecast that something changes.")
    if gap <= -2:
        return "The price asks for less than it has delivered", (
            f"Today's price needs about {g:.0f}% a year. The company has "
            f"managed about {h:.0f}% a year over {r.history_years} filed "
            "years. Either the market doubts that record continues, or it has "
            "not been noticed.")
    if gap <= 3:
        return "The price assumes more of the same", (
            f"Today's price needs about {g:.0f}% a year, against roughly "
            f"{h:.0f}% a year over {r.history_years} filed years. The market "
            "is broadly asking this company to keep doing what it has done.")
    if gap <= 10:
        return "The price assumes a step up", (
            f"Today's price needs about {g:.0f}% a year. The record is about "
            f"{h:.0f}% a year. The difference is what you would be paying for "
            "— an improvement that has not happened yet.")
    return "The price assumes a transformation", (
        f"Today's price needs about {g:.0f}% a year for {r.horizon} years, "
        f"against about {h:.0f}% a year achieved. Very few companies sustain a "
        "gap that size, which does not make it wrong — it makes it the thing "
        "to have a view on.")


def sensitivity(r: Reverse, rates: tuple = (0.07, 0.08, 0.09, 0.10, 0.11)
                ) -> list[tuple[float, float | None]]:
    """Implied growth at several discount rates.

    The honest companion to any single answer here. The discount rate is
    chosen, not observed, so showing how much the conclusion moves with it
    is the difference between a model and a number.
    """
    if r.fcf_base is None or r.enterprise is None or r.fcf_base <= 0:
        return []
    out = []
    for rate in rates:
        if rate <= r.terminal:
            continue
        out.append((rate, implied_growth(r.enterprise, r.fcf_base, rate,
                                         r.terminal, r.horizon)))
    return out
