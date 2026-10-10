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


# --------------------------------------------------------------------------
# The model run forwards
# --------------------------------------------------------------------------
# What the business is worth in ten years, if the rate it has actually
# grown at carries on. Every input is drawn from the filings: the growth
# rate is the company's own record, and the exit multiple is what the
# market pays for its cash flow today. Nothing here is typed in by hand,
# which is the only thing that makes a ten-year projection worth printing.
#
# It is still a projection. Companies revert to the mean, decades do not
# repeat, and a rate sustained for ten years is rare. So this never shows
# one number on its own -- it shows what happens at half that rate and at
# half again more, and the spread between them is the real answer.

# No company compounds cash flow at 40% for a decade. Rates above this are
# used as the cap, and the page says the cap was applied.
GROWTH_CAP = 0.25
GROWTH_FLOOR = -0.10

# A multiple outside this band says more about today's mood than about what
# the business will fetch in ten years.
MULTIPLE_MIN, MULTIPLE_MAX = 8.0, 30.0


@dataclass
class Projection:
    """One scenario: a growth rate carried forward and valued at the end."""

    name: str = ""
    growth: float = 0.0
    path: list[tuple[int, float]] = field(default_factory=list)
    exit_multiple: float = 0.0
    enterprise_end: float = 0.0
    equity_end: float = 0.0
    per_share_end: float = 0.0
    annual_return: float | None = None
    total_return: float | None = None


@dataclass
class Forecast:
    """Three scenarios, the inputs behind them, or a reason there are none."""

    base: Projection | None = None
    slower: Projection | None = None
    faster: Projection | None = None
    fcf_now: float | None = None
    base_years: int = 0
    history: float | None = None
    history_years: int = 0
    rev_growth: float | None = None
    price: float | None = None
    shares: float | None = None
    net_debt: float | None = None
    exit_multiple: float | None = None
    multiple_now: float | None = None
    capped: bool = False
    horizon: int = HORIZON
    problem: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return self.base is not None


def project(fcf: float, growth: float, multiple: float, shares: float,
            net_debt: float, price: float | None, name: str = "",
            horizon: int = HORIZON) -> Projection:
    """Carry cash flow forward, then value what it has become.

    Share count and net borrowings are held where they are. Both will
    move -- buybacks shrink the count, debt gets repaid out of the very
    cash flow being projected -- but guessing at either would add two more
    invented numbers to a page whose whole claim is that it does not
    invent any.
    """
    path, cash = [], fcf
    for year in range(1, horizon + 1):
        cash *= (1 + growth)
        path.append((year, cash))

    ev_end = cash * multiple
    eq_end = ev_end - net_debt
    per_share = eq_end / shares if shares else 0.0

    ann = tot = None
    if price and price > 0 and per_share > 0:
        tot = per_share / price - 1
        ann = (per_share / price) ** (1 / horizon) - 1

    return Projection(name=name, growth=growth, path=path,
                      exit_multiple=multiple, enterprise_end=ev_end,
                      equity_end=eq_end, per_share_end=per_share,
                      annual_return=ann, total_return=tot)


def forecast(eq, price: float | None, shares: float | None,
             debt: float | None, cash: float | None, sic: str = "",
             horizon: int = HORIZON) -> Forecast:
    """Ten years forward at the rate this company has actually managed."""
    f = Forecast(horizon=horizon)

    try:
        code = int(str(sic).strip()[:4] or 0)
    except ValueError:
        code = 0
    if code in FINANCIAL_SIC:
        f.problem = (
            "This does not work on banks, insurers or property trusts. "
            "Lending and deposits move enormous sums through operating cash "
            "flow, so free cash flow for a financial company is not the "
            "surplus it is everywhere else.")
        return f

    if not shares or shares <= 0:
        f.problem = "The filings do not give a share count to divide by."
        return f

    series = fcf_series(eq)
    if len(series) < 4:
        f.problem = (
            ("No free cash flow has been filed in a form these pages can "
             "read — this company has not tagged operating cash flow and "
             "capital spending."
             if not series else
             f"Only {len(series)} year{'s' if len(series) != 1 else ''} of "
             "free cash flow have been filed.")
            + " A ten-year projection needs a trend to project, and a "
              "handful of years is not one.")
        return f

    base, n_base = base_fcf(series)
    f.fcf_now, f.base_years = base, n_base
    f.history, f.history_years = cagr(series)
    rev = eq.series("revenue")
    f.rev_growth, _ = cagr(rev)

    if base is None or base <= 0:
        f.problem = (
            "This company spent more cash than it generated over the last "
            f"{n_base} years, so there is no positive cash flow to carry "
            "forward. That is common for a business investing heavily, and it "
            "is exactly the case this kind of model cannot handle.")
        return f

    if f.history is None:
        f.problem = (
            "Free cash flow has swung between positive and negative across "
            "the filed years, so there is no growth rate to project. A rate "
            "measured from a loss-making start year would be arithmetic "
            "noise rather than a trend.")
        return f

    g = f.history
    if g > GROWTH_CAP:
        g, f.capped = GROWTH_CAP, True
        f.notes.append(
            f"The filed record is {f.history * 100:.0f}% a year, which is held "
            f"down to {GROWTH_CAP * 100:.0f}% here. Almost no company compounds "
            "cash flow faster than that for a decade, and projecting the raw "
            "rate would produce a number worth nothing.")
    elif g < GROWTH_FLOOR:
        g, f.capped = GROWTH_FLOOR, True
        f.notes.append(
            f"The filed record is {f.history * 100:.0f}% a year. A decline "
            f"that steep compounded for {horizon} years leaves almost nothing, "
            f"so it is held at {GROWTH_FLOOR * 100:.0f}%.")

    net = (debt or 0.0) - (cash or 0.0)
    f.price, f.shares, f.net_debt = price, shares, net

    # What the market pays for this company's cash flow today, carried
    # forward as what it will pay in ten years. Using the company's own
    # multiple rather than a chosen one keeps the projection anchored to
    # something observed -- but a multiple set by today's mood is the
    # weakest link here, so it is held inside a sane band.
    if price and price > 0:
        ev_now = price * shares + net
        f.multiple_now = ev_now / base if base else None
    mult = f.multiple_now or 15.0
    mult = max(MULTIPLE_MIN, min(MULTIPLE_MAX, mult))
    f.exit_multiple = mult
    if f.multiple_now and abs(mult - f.multiple_now) > 0.05:
        f.notes.append(
            f"The market pays {f.multiple_now:.0f} times cash flow for this "
            f"company today. That is held to {mult:.0f} times for the "
            "projection, because a multiple at today's extreme says more "
            "about the present mood than about ten years from now.")

    f.base = project(base, g, mult, shares, net, price,
                     "If the record repeats", horizon)
    f.slower = project(base, g / 2, mult, shares, net, price,
                       "If growth halves", horizon)
    f.faster = project(base, min(g * 1.5, GROWTH_CAP), mult, shares, net,
                       price, "If growth improves", horizon)

    f.notes.append(
        f"Cash flow starts from the average of the last {n_base} filed years, "
        "so one year of heavy building does not set the whole projection.")
    f.notes.append(
        "The share count and net borrowings are held where they are today. "
        "Buybacks would raise the per-share figure and new shares would "
        "lower it.")
    return f


def forecast_verdict(f: Forecast) -> tuple[str, str]:
    """The headline sentence for a completed forecast."""
    if not f.available or f.base is None:
        return "", ""
    b = f.base
    if b.annual_return is None:
        return "No share price to compare against", (
            "The projection gives a value per share, but without a price "
            "today there is nothing to measure a return from.")

    ann = b.annual_return * 100
    hist = f.history * 100 if f.history is not None else None
    hint = (f" That rests on free cash flow growing {b.growth * 100:.0f}% a "
            f"year, which is what it has done over {f.history_years} filed "
            "years." if hist is not None else "")

    if ann >= 15:
        return "Well ahead of the market", (
            f"Carrying the record forward, the shares work out at about "
            f"{ann:.0f}% a year.{hint} A return that far above the market's "
            "long-run average usually means the market disagrees with the "
            "projection somewhere.")
    if ann >= 8:
        return "Around what the market has returned", (
            f"Carrying the record forward gives about {ann:.0f}% a year, "
            f"roughly what US shares have averaged over decades.{hint}")
    if ann >= 0:
        return "Below the market", (
            f"Carrying the record forward gives about {ann:.0f}% a year, "
            f"less than the market's long-run average.{hint} You would be "
            "paying today for growth that mostly arrives anyway.")
    return "The record does not justify today's price", (
        f"Even carrying the filed growth forward for {f.horizon} years, the "
        f"shares come out below today's price — about {ann:.0f}% a year."
        f"{hint} The price is assuming something the record does not show.")
