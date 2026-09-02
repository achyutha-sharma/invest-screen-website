"""
A weighted score for ranking companies against each other.

Six components, each built from several measures, weighted as an analyst
would weight them. Every measure is scored 0-100 against the other companies
in the same comparison rather than against a fixed threshold, because what
counts as a good margin or a normal multiple differs completely between
industries -- and a peer set is the only fair benchmark this tool has.

Three rules hold throughout:

  * A measure that cannot be computed is skipped, and the weights of the
    components that survive are renormalised. A company is never penalised for
    a figure its filings do not contain.
  * A component needs at least one usable measure or it drops out entirely.
  * A company with too little to score gets no score at all, rather than a
    misleading one built from two measures out of fourteen.

The output is an ordering of the evidence already filed. It is not a forecast,
and a high score at the wrong price still loses money.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# What each component contributes. These are judgement calls, and they are
# stated openly on the page so a reader can disagree with them.
WEIGHTS = {
    "valuation": 22,
    "growth": 18,
    "profitability": 18,
    "strength": 14,
    "quality": 9,
    "returns": 9,
    "stability": 10,
}

LABELS = {
    "valuation": "Valuation",
    "growth": "Growth",
    "profitability": "Profitability",
    "strength": "Financial strength",
    "quality": "Earnings quality",
    "returns": "Shareholder returns",
    "stability": "Price stability",
}

MEASURES = {
    "valuation": "P/E, EV/EBITDA, free-cash-flow yield",
    "growth": "3-year revenue, EPS and free-cash-flow growth",
    "profitability": "return on capital, operating margin, net margin",
    "strength": "net debt/EBITDA, interest coverage, current ratio",
    "quality": "cash flow against reported profit, margin stability",
    "returns": "dividend yield, dividend cover, buybacks",
    "stability": "volatility of monthly returns, worst fall from a peak",
}

# Minimum share of the total weight that must be scoreable for a company to
# get a score at all.
MIN_COVERAGE = 0.55


@dataclass
class Figures:
    """One company's inputs, already extracted. None means not filed."""
    ticker: str
    name: str
    cik: str = ""
    price: float | None = None
    eps: float | None = None
    shares: float | None = None
    revenue: list[float] = field(default_factory=list)     # oldest first
    net_income: list[float] = field(default_factory=list)
    fcf: list[float] = field(default_factory=list)
    ebit: float | None = None
    ebitda: float | None = None
    ocf: float | None = None
    debt: float | None = None
    cash: float | None = None
    equity: float | None = None
    interest: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    dps: float | None = None
    buybacks: float | None = None
    # Month-end closes, oldest first. Price, not business -- kept separate in
    # its own component and labelled as such, because a steady share price is
    # not the same thing as a sound company.
    prices: list[float] = field(default_factory=list)

    # ---- derived measures, each None when its inputs are missing ----

    @property
    def market_cap(self) -> float | None:
        if self.price and self.shares:
            return self.price * self.shares
        return None

    @property
    def pe(self) -> float | None:
        if self.price and self.eps and self.eps > 0:
            return self.price / self.eps
        return None

    @property
    def ev_ebitda(self) -> float | None:
        cap = self.market_cap
        if cap is None or not self.ebitda or self.ebitda <= 0:
            return None
        ev = cap + (self.debt or 0) - (self.cash or 0)
        return ev / self.ebitda if ev > 0 else None

    @property
    def fcf_yield(self) -> float | None:
        cap, f = self.market_cap, self.fcf[-1] if self.fcf else None
        if cap and f is not None:
            return 100 * f / cap
        return None

    def _cagr(self, series: list[float], years: int = 3) -> float | None:
        """Compound growth, refusing to compute across a sign change.

        Growing from a loss to a profit has no meaningful percentage, and
        forcing one produces figures that look spectacular and mean nothing.
        """
        if len(series) < years + 1:
            return None
        first, last = series[-(years + 1)], series[-1]
        if first is None or last is None or first <= 0 or last <= 0:
            return None
        return 100 * ((last / first) ** (1 / years) - 1)

    @property
    def revenue_growth(self) -> float | None:
        return self._cagr(self.revenue)

    @property
    def eps_growth(self) -> float | None:
        if self.eps is None or len(self.net_income) < 4 or not self.shares:
            return None
        return self._cagr(self.net_income)

    @property
    def fcf_growth(self) -> float | None:
        return self._cagr(self.fcf)

    @property
    def roic(self) -> float | None:
        """Operating profit against the capital funding the business."""
        if self.ebit is None or self.ebit <= 0:
            return None
        capital = (self.equity or 0) + (self.debt or 0) - (self.cash or 0)
        if capital <= 0:
            return None                    # buybacks can drive equity negative
        return 100 * self.ebit / capital

    @property
    def operating_margin(self) -> float | None:
        rev = self.revenue[-1] if self.revenue else None
        if self.ebit is None or not rev:
            return None
        return 100 * self.ebit / rev

    @property
    def net_margin(self) -> float | None:
        rev = self.revenue[-1] if self.revenue else None
        ni = self.net_income[-1] if self.net_income else None
        if ni is None or not rev:
            return None
        return 100 * ni / rev

    @property
    def net_debt_ebitda(self) -> float | None:
        if not self.ebitda or self.ebitda <= 0:
            return None
        return ((self.debt or 0) - (self.cash or 0)) / self.ebitda

    @property
    def interest_cover(self) -> float | None:
        if self.ebit is None or not self.interest or self.interest <= 0:
            return None
        return self.ebit / self.interest

    @property
    def current_ratio(self) -> float | None:
        if not self.current_liabilities or self.current_assets is None:
            return None
        return self.current_assets / self.current_liabilities

    @property
    def cash_conversion(self) -> float | None:
        ni = self.net_income[-1] if self.net_income else None
        if self.ocf is None or not ni or ni <= 0:
            return None
        return self.ocf / ni

    @property
    def margin_stability(self) -> float | None:
        """How steady the net margin has been. Higher is steadier.

        Scored as the negative of the spread, so the ranking below -- which
        always treats higher as better -- needs no special case.
        """
        pairs = [(n, r) for n, r in zip(self.net_income, self.revenue)
                 if n is not None and r]
        if len(pairs) < 4:
            return None
        margins = [100 * n / r for n, r in pairs[-5:]]
        return -(max(margins) - min(margins))

    @property
    def dividend_yield(self) -> float | None:
        if self.dps and self.price:
            return 100 * self.dps / self.price
        return None

    @property
    def dividend_cover(self) -> float | None:
        """Earnings per share against the dividend paid out of them."""
        if not self.dps or self.eps is None or self.eps <= 0:
            return None
        return self.eps / self.dps

    @property
    def volatility(self) -> float | None:
        """Annualised spread of monthly returns. Lower is steadier.

        Negated so the ranking below, which always treats higher as better,
        needs no special case.
        """
        px = self.prices
        if len(px) < 24:
            return None
        rets = [(b / a - 1) for a, b in zip(px, px[1:]) if a]
        if len(rets) < 12:
            return None
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        return -(var ** 0.5) * (12 ** 0.5) * 100

    @property
    def worst_fall(self) -> float | None:
        """Largest peak-to-trough fall in the period held. Negated, as above.

        The figure that matters more than volatility for most people: not how
        much a share wobbles, but how far it fell and stayed down.
        """
        px = self.prices
        if len(px) < 24:
            return None
        peak, worst = px[0], 0.0
        for p in px:
            peak = max(peak, p)
            if peak:
                worst = min(worst, p / peak - 1)
        return worst * 100

    @property
    def buyback_yield(self) -> float | None:
        cap = self.market_cap
        if cap and self.buybacks:
            return 100 * abs(self.buybacks) / cap
        return None


# Each measure: attribute, whether higher is better, and its share of the
# component. Weights within a component are equal unless stated.
COMPONENTS: dict[str, list[tuple[str, bool]]] = {
    "valuation": [("pe", False), ("ev_ebitda", False), ("fcf_yield", True)],
    "growth": [("revenue_growth", True), ("eps_growth", True), ("fcf_growth", True)],
    "profitability": [("roic", True), ("operating_margin", True), ("net_margin", True)],
    "strength": [("net_debt_ebitda", False), ("interest_cover", True),
                 ("current_ratio", True)],
    "quality": [("cash_conversion", True), ("margin_stability", True)],
    "returns": [("dividend_yield", True), ("dividend_cover", True),
                ("buyback_yield", True)],
    "stability": [("volatility", True), ("worst_fall", True)],
}


def _rank_scores(values: list[float | None], higher_better: bool) -> list[float | None]:
    """Score each value 0-100 by its place among the others.

    Ranked rather than scaled, because one extreme company would otherwise
    compress everyone else into a narrow band. Ties share a score.
    """
    have = [(i, v) for i, v in enumerate(values) if v is not None]
    if len(have) < 2:
        # A single company has nothing to be ranked against.
        return [50.0 if v is not None else None for v in values]

    order = sorted(have, key=lambda p: p[1], reverse=higher_better)
    out: list[float | None] = [None] * len(values)
    n = len(order)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and order[j + 1][1] == order[i][1]:
            j += 1
        # Average position for a tied group, so equal figures score equally.
        score = 100.0 - (100.0 * ((i + j) / 2) / max(n - 1, 1))
        for k in range(i, j + 1):
            out[order[k][0]] = score
        i = j + 1
    return out


@dataclass
class Score:
    ticker: str
    total: float | None
    components: dict[str, float | None]
    coverage: float
    missing: list[str]


def rank(companies: list[Figures]) -> list[Score]:
    """Score every company against the others, in the given order."""
    if not companies:
        return []

    # Score each measure across the whole set first, so every company is
    # judged on the same scale.
    measure_scores: dict[str, list[float | None]] = {}
    for comp, measures in COMPONENTS.items():
        for attr, higher in measures:
            vals = [getattr(c, attr) for c in companies]
            measure_scores[attr] = _rank_scores(vals, higher)

    out: list[Score] = []
    for idx, c in enumerate(companies):
        comps: dict[str, float | None] = {}
        for comp, measures in COMPONENTS.items():
            got = [measure_scores[a][idx] for a, _ in measures
                   if measure_scores[a][idx] is not None]
            comps[comp] = sum(got) / len(got) if got else None

        usable = {k: v for k, v in comps.items() if v is not None}
        weight_have = sum(WEIGHTS[k] for k in usable)
        coverage = weight_have / sum(WEIGHTS.values())

        if coverage < MIN_COVERAGE:
            # Too little of the picture to put a number on.
            total = None
        else:
            total = sum(v * WEIGHTS[k] for k, v in usable.items()) / weight_have

        out.append(Score(
            ticker=c.ticker,
            total=total,
            components=comps,
            coverage=coverage,
            missing=[LABELS[k] for k in WEIGHTS if comps.get(k) is None],
        ))
    return out
