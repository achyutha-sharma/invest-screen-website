"""
What the share price is already assuming.

A discounted cash flow run forwards produces a single number -- "this is
worth $187.42" -- that looks like a fact and is mostly a restatement of the
three assumptions someone typed in. Move the discount rate two points and a
quarter of the value disappears. For a reader who is still learning what
free cash flow is, that number is the most misleading thing a page could"""
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

# Limits on a rate taken from history and carried forward. No company
# compounds cash flow at 40% a year for long, and nothing shrinks 30% a
# year for long either -- a filed rate outside this band is held at the
# edge, and the page says so.
GROWTH_CAP = 0.25
GROWTH_FLOOR = -0.10

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
# The other lines of the business, carried forward the same way
# --------------------------------------------------------------------------
# Cash flow is what the valuation runs on, but it is not what most people
# picture when they think about a company ten years out. Sales and profit
# are, and projecting all three at once shows something a single line
# cannot: whether they move together. A company whose sales grow while its
# cash flow shrinks is telling you something, and it is easier to see when
# the two sit side by side.


@dataclass
class Line:
    """One measure, projected forward at its own filed rate."""

    key: str
    label: str
    gloss: str
    now: float | None = None
    growth: float | None = None
    end: float | None = None
    years: int = 0
    capped: bool = False
    per_share: bool = False
    problem: str = ""


#: What to project, in the order a reader meets them on an income statement.
LINES = [
    ("revenue", "Sales", "what customers paid", False),
    ("net_income", "Profit", "what was left after every cost", False),
    ("eps", "Earnings a share", "that profit, split across the shares", True),
    ("fcf", "Free cash flow", "cash left after running and reinvesting", False),
]


def forecast_line(eq, key: str, label: str, gloss: str, per_share: bool,
                  horizon: int = HORIZON) -> Line:
    """Grow one measure at the rate it has grown at, for `horizon` years."""
    ln = Line(key=key, label=label, gloss=gloss, per_share=per_share)

    series = fcf_series(eq) if key == "fcf" else eq.series(key)

    # Per-share figures carry a split in them. Alphabet's filed EPS runs
    # from $75 to $4 across its twenty-for-one split, and the growth rate
    # off that series came out at -15% a year while profit grew 24%. Only
    # the years on today's share basis can be compared with each other.
    if per_share:
        from sec_equity import split_break
        cut = split_break(eq)
        if cut:
            labels = {p.label for p in eq.years[cut:]}
            series = [(lab, v) for lab, v in series if lab in labels]

    if len(series) < 4:
        ln.problem = ("too few years on one share basis" if per_share
                      else "too few filed years")
        return ln

    if per_share:
        # Per-share figures are small and a three-year average would blunt
        # the very trend being measured, so the latest filed year is used.
        ln.now = series[-1][1]
    else:
        ln.now, _ = base_fcf(series)

    ln.growth, ln.years = cagr(series)
    if ln.growth is None:
        ln.problem = "swung between profit and loss, so there is no rate"
        return ln
    if ln.now is None or ln.now <= 0:
        ln.problem = "negative today, so there is nothing to grow"
        return ln

    g = ln.growth
    if g > GROWTH_CAP:
        g, ln.capped = GROWTH_CAP, True
    elif g < GROWTH_FLOOR:
        g, ln.capped = GROWTH_FLOOR, True
    ln.growth = g
    ln.end = ln.now * (1 + g) ** horizon
    return ln


def forecast_lines(eq, horizon: int = HORIZON, years: int | None = None
                   ) -> list[Line]:
    """Sales, profit, earnings a share and cash flow, all carried forward."""
    n = years if years is not None else horizon
    return [forecast_line(eq, k, lab, gl, ps, n)
            for k, lab, gl, ps in LINES]


# --------------------------------------------------------------------------
# The DCF proper: forecast, discount, value
# --------------------------------------------------------------------------
# Forecasting says how much cash a company might generate. A DCF goes one
# step further and says what that cash is worth today. The difference is
# the discounting: a dollar arriving in 2031 is not a dollar now, and the
# rate you knock off for the wait is what turns a forecast into a value.
#
# Five explicit years then a terminal value, which is the shape every
# textbook and every bank model uses.

FORECAST_YEARS = 5


@dataclass
class Step:
    """One forecast year: the cash, and what it is worth today."""

    year: int
    cash: float
    factor: float
    present: float


@dataclass
class Valuation:
    """A complete DCF, or a plain reason there is not one."""

    steps: list[Step] = field(default_factory=list)
    growth: float = 0.0
    discount: float = DEFAULT_DISCOUNT
    terminal_growth: float = DEFAULT_TERMINAL
    fcf_now: float | None = None
    base_years: int = 0
    history: float | None = None
    history_years: int = 0
    capped: bool = False

    pv_forecast: float = 0.0       # the five discounted years
    terminal: float = 0.0          # the value of everything after them
    pv_terminal: float = 0.0
    enterprise: float = 0.0
    net_debt: float = 0.0
    equity: float = 0.0
    shares: float | None = None
    per_share: float | None = None

    price: float | None = None
    upside: float | None = None    # per share against today's price
    problem: str = ""

    @property
    def available(self) -> bool:
        return self.per_share is not None

    @property
    def terminal_share(self) -> float | None:
        """How much of the answer is the terminal value, as a percentage.

        Worth showing. When four fifths of a valuation sits in the lump at
        the end, the five years of careful forecasting in front of it are
        not doing much work.
        """
        if not self.enterprise:
            return None
        return 100 * self.pv_terminal / self.enterprise


def valuation(eq, price: float | None, shares: float | None,
              debt: float | None, cash: float | None, sic: str = "",
              discount: float = DEFAULT_DISCOUNT,
              terminal_growth: float = DEFAULT_TERMINAL,
              years: int = FORECAST_YEARS) -> Valuation:
    """What the company is worth today, from its own filed cash flow."""
    v = Valuation(discount=discount, terminal_growth=terminal_growth)

    try:
        code = int(str(sic).strip()[:4] or 0)
    except ValueError:
        code = 0
    if code in FINANCIAL_SIC:
        v.problem = ("This does not work on banks or insurers. Their cash "
                     "flow statements measure lending, not spare cash.")
        return v
    if not shares or shares <= 0:
        v.problem = "No share count is filed, so there is nothing to divide by."
        return v
    if discount <= terminal_growth:
        v.problem = "The discount rate has to be above the long-run growth rate."
        return v

    series = fcf_series(eq)
    if len(series) < 4:
        v.problem = ("Fewer than four years of cash flow are filed. There is "
                     "no trend to forecast from.")
        return v

    base, n_base = base_fcf(series)
    v.fcf_now, v.base_years = base, n_base
    v.history, v.history_years = cagr(series)
    v.shares = shares

    if base is None or base <= 0:
        v.problem = ("This company spends more cash than it makes, so there "
                     "is nothing to discount.")
        return v
    if v.history is None:
        v.problem = ("Cash flow has swung between positive and negative, so "
                     "there is no growth rate to forecast with.")
        return v

    g = v.history
    if g > GROWTH_CAP:
        g, v.capped = GROWTH_CAP, True
    elif g < GROWTH_FLOOR:
        g, v.capped = GROWTH_FLOOR, True
    v.growth = g

    # Step 1 and 2 together: forecast each year, then discount it.
    cashflow = base
    for year in range(1, years + 1):
        cashflow *= (1 + g)
        factor = 1 / (1 + discount) ** year
        v.steps.append(Step(year, cashflow, factor, cashflow * factor))
    v.pv_forecast = sum(s.present for s in v.steps)

    # Step 3: everything after year five, in one lump, discounted back.
    last = v.steps[-1].cash
    v.terminal = last * (1 + terminal_growth) / (discount - terminal_growth)
    v.pv_terminal = v.terminal / (1 + discount) ** years

    v.enterprise = v.pv_forecast + v.pv_terminal
    v.net_debt = (debt or 0.0) - (cash or 0.0)
    v.equity = v.enterprise - v.net_debt
    v.per_share = v.equity / shares

    v.price = price
    if price and price > 0 and v.per_share is not None:
        v.upside = v.per_share / price - 1
    return v


def valuation_verdict(v: Valuation) -> tuple[str, str]:
    """One short line on what the number means. Plain words."""
    if not v.available:
        return "", ""
    if v.upside is None:
        return "No price to compare against", (
            "The sum gives a value a share, but there is no market price "
            "today to set it beside.")
    up = v.upside * 100
    if up >= 30:
        return "The sum says it is worth more than it costs", (
            f"About {up:.0f}% more. A gap that wide usually means the market "
            "expects something worse than the past, or the sum is leaning on "
            "a growth rate that will not hold.")
    if up >= 0:
        return "Roughly what it costs today", (
            f"The sum lands about {up:.0f}% above the share price, which is "
            "close enough to call it fair on these assumptions.")
    if up >= -30:
        return "A little less than it costs", (
            f"The sum lands about {abs(up):.0f}% below the share price. The "
            "market is paying for growth beyond what has been filed.")
    return "Well below what it costs", (
        f"The sum lands about {abs(up):.0f}% below the share price. Either "
        "the market expects a lot more than the record shows, or this "
        "company is not one a cash flow model describes well.")


def growth_note(v: Valuation) -> str:
    """Is the cash growing, and why that matters. Two sentences, no jargon."""
    if v.history is None:
        return ""
    h = v.history * 100
    if h > 1:
        return (f"Free cash flow has grown about {h:.0f}% a year across "
                f"{v.history_years} filed years. Growing cash is what pays "
                "for dividends, buybacks and paying down debt — so the same "
                "business is worth more each year without the share price "
                "doing anything.")
    if h >= -1:
        return (f"Free cash flow has been roughly flat across "
                f"{v.history_years} filed years. A business standing still "
                "is not in trouble, but nothing about it is getting more "
                "valuable on its own either.")
    return (f"Free cash flow has shrunk about {abs(h):.0f}% a year across "
            f"{v.history_years} filed years. Falling cash means less to "
            "spend on dividends, buybacks or debt — and a company worth a "
            "little less each year unless something changes.")
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
    spread: float = 0.0
    lines: list = field(default_factory=list)
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

    # Worse and better, not half and half again. Multiplying a negative
    # rate by 1.5 makes it more negative, so a company in decline had its
    # "if growth improves" row showing a steeper fall than the base case
    # -- the table read backwards for exactly the companies where the
    # question matters most. A spread around the filed rate works whichever
    # side of zero that rate sits.
    spread = max(0.03, abs(g) * 0.5)
    f.spread = spread
    f.base = project(base, g, mult, shares, net, price,
                     "If the record repeats", horizon)
    f.slower = project(base, max(g - spread, GROWTH_FLOOR * 2), mult, shares,
                       net, price, "If it does worse", horizon)
    f.faster = project(base, min(g + spread, GROWTH_CAP), mult, shares, net,
                       price, "If it does better", horizon)

    f.lines = forecast_lines(eq, horizon)
    f.notes.append(
        f"Cash flow starts from the average of the last {n_base} filed years, "
        "so one year of heavy building does not set the whole projection.")
    f.notes.append(
        "The share count and net borrowings are held where they are today. "
        "Buybacks would raise the per-share figure and new shares would "
        "lower it.")
    return f


def forecast_verdict(f: Forecast) -> tuple[str, str]:
    """The headline sentence. Short words, one idea."""
    if not f.available or f.base is None:
        return "", ""
    b = f.base
    if b.annual_return is None:
        return "No price to compare against", (
            "The projection gives a value a share, but there is no price "
            "today to measure a return from.")

    ann = b.annual_return * 100
    if ann >= 15:
        return "Far ahead of the market", (
            f"On its own record, the shares work out at about {ann:.1f}% a "
            "year. That is well above what shares have returned on average, "
            "which usually means the market doubts the record continues.")
    if ann >= 8:
        return "About what the market returns", (
            f"On its own record, the shares work out at about {ann:.1f}% a "
            "year — close to what US shares have averaged over decades.")
    if ann >= 0:
        return "Less than the market", (
            f"On its own record, the shares work out at about {ann:.1f}% a "
            "year. That is below the long-run average for shares, so you "
            "would be paying up for growth you could get more cheaply.")
    return "The record does not support the price", (
        f"Even carrying its own record forward for {f.horizon} years, the "
        f"shares land below today's price — about {ann:.1f}% a year. The "
        "price is counting on something better than what has been filed.")


# --------------------------------------------------------------------------
# The other lines of the business, carried forward the same way
# --------------------------------------------------------------------------
# Cash flow is what the valuation runs on, but it is not what most people
# picture when they think about a company ten years out. Sales and profit
# are, and projecting all three at once shows something a single line
# cannot: whether they move together. A company whose sales grow while its
# cash flow shrinks is telling you something, and it is easier to see when
# the two sit side by side.


@dataclass
class Line:
    """One measure, projected forward at its own filed rate."""

    key: str
    label: str
    gloss: str
    now: float | None = None
    growth: float | None = None
    end: float | None = None
    years: int = 0
    capped: bool = False
    per_share: bool = False
    problem: str = ""


#: What to project, in the order a reader meets them on an income statement.
LINES = [
    ("revenue", "Sales", "what customers paid", False),
    ("net_income", "Profit", "what was left after every cost", False),
    ("eps", "Earnings a share", "that profit, split across the shares", True),
    ("fcf", "Free cash flow", "cash left after running and reinvesting", False),
]


def forecast_line(eq, key: str, label: str, gloss: str, per_share: bool,
                  horizon: int = HORIZON) -> Line:
    """Grow one measure at the rate it has grown at, for `horizon` years."""
    ln = Line(key=key, label=label, gloss=gloss, per_share=per_share)

    series = fcf_series(eq) if key == "fcf" else eq.series(key)
    if len(series) < 4:
        ln.problem = "too few filed years"
        return ln

    if per_share:
        # Per-share figures are small and a three-year average would blunt
        # the very trend being measured, so the latest filed year is used.
        ln.now = series[-1][1]
    else:
        ln.now, _ = base_fcf(series)

    ln.growth, ln.years = cagr(series)
    if ln.growth is None:
        ln.problem = "swung between profit and loss, so there is no rate"
        return ln
    if ln.now is None or ln.now <= 0:
        ln.problem = "negative today, so there is nothing to grow"
        return ln

    g = ln.growth
    if g > GROWTH_CAP:
        g, ln.capped = GROWTH_CAP, True
    elif g < GROWTH_FLOOR:
        g, ln.capped = GROWTH_FLOOR, True
    ln.growth = g
    ln.end = ln.now * (1 + g) ** horizon
    return ln


def forecast_lines(eq, horizon: int = HORIZON) -> list[Line]:
    """Sales, profit, earnings a share and cash flow, all carried forward."""
    return [forecast_line(eq, k, lab, gl, ps, horizon)
            for k, lab, gl, ps in LINES]
