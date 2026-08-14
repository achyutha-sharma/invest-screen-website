"""
Equity figures from SEC XBRL company facts.

Sits on top of sec_ratios.py, which handles fetching, tag resolution and the
awkwardness of real filings. This module adds what a shareholder needs and a
lender does not: per-share figures, dividends, the share count, quarterly
progress through the current year, and ten years of price-free history.

The one thing not here is the share price. Nothing in a filing carries it, so
it arrives separately and every price-dependent figure degrades to None when it
is missing, rather than the page falling over.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sec_ratios import (
    DA,
    DEBT_COMPONENTS,
    DERIVED,
    MANUAL,
    MISSING,
    NET_INCOME,
    OPERATING_INCOME,
    REVENUE,
    FactStore,
    _parse,
    _pick,
    _sum_at,
)

# --------------------------------------------------------------------------
# Tag chains specific to equity
# --------------------------------------------------------------------------

# Diluted first: it assumes options and convertibles are exercised, which is
# the count a share is actually competing with. Basic flatters the figure.
EPS_DILUTED = [
    "EarningsPerShareDiluted",
    "IncomeLossFromContinuingOperationsPerDilutedShare",
]
EPS_BASIC = ["EarningsPerShareBasic", "EarningsPerShareBasicAndDiluted"]

SHARES_DILUTED = [
    "WeightedAverageNumberOfDilutedSharesOutstanding",
    "WeightedAverageNumberOfSharesOutstandingDiluted",
]
SHARES_BASIC = ["WeightedAverageNumberOfSharesOutstandingBasic"]
SHARES_ENTITY = ["CommonStockSharesOutstanding", "EntityCommonStockSharesOutstanding"]

# Declared, not paid: the paid figure lags and can double-count across a year
# boundary. Declared is what a holder is entitled to for the period.
DPS = [
    "CommonStockDividendsPerShareDeclared",
    "CommonStockDividendsPerShareCashPaid",
]
DIVIDENDS_PAID = [
    "PaymentsOfDividendsCommonStock",
    "PaymentsOfDividends",
]

BUYBACKS = [
    "PaymentsForRepurchaseOfCommonStock",
    "TreasuryStockValueAcquiredCostMethod",
]

OPERATING_CASH = [
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
]
CAPEX = [
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
]

GROSS_PROFIT = ["GrossProfit"]
CASH = [
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
]
COST_OF_REVENUE = ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"]

# --------------------------------------------------------------------------
# Field schema
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Field:
    key: str
    label: str          # the professional term, shown first
    gloss: str          # one short line of plain English underneath


FIELDS: list[Field] = [
    Field("eps", "EPS", "earnings per share — profit split per share"),
    Field("dps", "Dividend per share", "cash paid out per share, declared"),
    Field("shares", "Shares outstanding", "how many slices the company is cut into"),
    Field("revenue", "Revenue", "everything customers paid, before costs"),
    Field("net_income", "Net income", "what was left after every cost"),
    Field("gross_profit", "Gross profit", "revenue less the direct cost of making it"),
    Field("ebit", "Operating income", "profit before interest and tax"),
    Field("da", "D&A", "depreciation and amortisation — wear on assets"),
    Field("ocf", "Operating cash flow", "cash the business actually took in"),
    Field("capex", "Capital expenditure", "spent on buildings, equipment, technology"),
    Field("buybacks", "Buybacks", "cash spent repurchasing its own shares"),
    Field("total_debt", "Total debt", "everything the company has borrowed"),
    Field("cash", "Cash", "cash and equivalents on the balance sheet"),
]

FIELD_LABELS = {f.key: f.label for f in FIELDS}
FIELD_GLOSS = {f.key: f.gloss for f in FIELDS}


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------


@dataclass
class Period:
    """One fiscal period -- a full year, or a quarter."""

    end: date
    fy: int
    fp: str                                   # "FY", "Q1", "Q2", "Q3", "Q4"
    inputs: dict[str, float | None] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return f"FY{self.fy}" if self.fp == "FY" else f"{self.fp} FY{self.fy}"

    def get(self, key: str) -> float | None:
        return self.inputs.get(key)

    def missing(self) -> list[str]:
        return [f.key for f in FIELDS if self.inputs.get(f.key) is None]


@dataclass
class Equity:
    entity: str
    cik: str
    years: list[Period]                       # oldest first, up to ten
    quarters: list[Period]                    # current fiscal year, in order
    fiscal_year_end: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def latest(self) -> Period | None:
        return self.years[-1] if self.years else None

    def series(self, key: str) -> list[tuple[str, float]]:
        """Ten-year history for one field, skipping years it is missing."""
        return [(p.label, p.inputs[key]) for p in self.years if p.inputs.get(key) is not None]


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------

# EPS and dividends per share are tagged in shares, not dollars, so the USD
# unit lookup FactStore uses would miss them entirely.
_PER_SHARE_UNITS = ("USD/shares", "USD-per-shares")
_SHARE_UNITS = ("shares",)


class EquityStore(FactStore):
    """FactStore that can also read per-share and share-count units."""

    def _entries_in(self, tag: str, units: tuple[str, ...]) -> list[dict]:
        blocks = self._gaap.get(tag, {}).get("units", {})
        for u in units:
            if u in blocks:
                return list(blocks[u])
        return []

    def _annual(self, rows: list[dict], quarterly: bool) -> dict[date, float]:
        """Keep ~90-day or ~365-day spans, newest filing wins on ties."""
        lo, hi = (60, 110) if quarterly else (340, 400)
        best: dict[date, dict] = {}
        for e in rows:
            if not e.get("start"):
                continue
            span = (_parse(e["end"]) - _parse(e["start"])).days
            if not (lo <= span <= hi):
                continue
            end = _parse(e["end"])
            prior = best.get(end)
            if prior is None or e.get("filed", "") > prior.get("filed", ""):
                best[end] = e
        return {k: float(v["val"]) for k, v in best.items()}

    def per_share(self, chain: list[str], target: date, quarterly: bool = False):
        for tag in chain:
            rows = self._entries_in(tag, _PER_SHARE_UNITS)
            if not rows:
                continue
            val = _pick(self._annual(rows, quarterly), target)
            if val is not None:
                return tag, val
        return None, None

    def share_count(self, target: date):
        """Weighted average first -- it matches the EPS denominator."""
        for chain, quarterly in ((SHARES_DILUTED, False), (SHARES_BASIC, False)):
            for tag in chain:
                rows = self._entries_in(tag, _SHARE_UNITS)
                if rows:
                    val = _pick(self._annual(rows, quarterly), target)
                    if val is not None:
                        return tag, val
        # Fall back to the point-in-time count on the cover page.
        for tag in SHARES_ENTITY:
            rows = [e for e in self._entries_in(tag, _SHARE_UNITS) if not e.get("start")]
            if rows:
                best: dict[date, dict] = {}
                for e in rows:
                    end = _parse(e["end"])
                    if end not in best or e.get("filed", "") > best[end].get("filed", ""):
                        best[end] = e
                val = _pick({k: float(v["val"]) for k, v in best.items()}, target, tol_days=200)
                if val is not None:
                    return tag, val
        return None, None

    def quarterly(self, chain: list[str], target: date):
        """A ~90-day figure in USD, for the quarterly progress panel."""
        for tag in chain:
            rows = [e for e in self._entries(tag) if e.get("start")]
            if not rows:
                continue
            val = _pick(self._annual(rows, quarterly=True), target)
            if val is not None:
                return tag, val
        return None, None


_ANNUAL_USD = [
    ("revenue", REVENUE, "duration"),
    ("net_income", NET_INCOME, "duration"),
    ("gross_profit", GROSS_PROFIT, "duration"),
    ("ebit", OPERATING_INCOME, "duration"),
    ("da", DA, "duration"),
    ("ocf", OPERATING_CASH, "duration"),
    ("capex", CAPEX, "duration"),
    ("buybacks", BUYBACKS, "duration"),
]

_ANNUAL_INSTANT = [
    ("cash", CASH),
]


def _period_ends(store: EquityStore, years: int) -> list[date]:
    """Fiscal year ends, newest first, anchored on revenue then net income."""
    for chain in (REVENUE, NET_INCOME):
        _, series = store.resolve(chain, "duration")
        if series:
            return sorted(series.keys(), reverse=True)[:years]
    return []


def extract_equity(payload: dict, cik: str = "", years: int = 10) -> Equity:
    """Ten years of annual figures, plus this year's quarters so far."""
    store = EquityStore(payload)
    ends = _period_ends(store, years)
    if not ends:
        raise ValueError(
            "No annual revenue or net income found. The filer may report in a "
            "currency other than USD, or may not file with the SEC."
        )

    annual: list[Period] = []
    for end in ends:
        p = Period(end=end, fy=end.year, fp="FY")
        for key, chain, kind in _ANNUAL_USD:
            tag, val = store.resolve_at(chain, kind, end)
            p.inputs[key], p.sources[key] = val, tag or MISSING

        for key, chain in _ANNUAL_INSTANT:
            tag, val = store.resolve_at(chain, "instant", end)
            p.inputs[key], p.sources[key] = val, tag or MISSING

        debt, debt_src = _sum_at(store, DEBT_COMPONENTS, end)
        p.inputs["total_debt"], p.sources["total_debt"] = debt, debt_src

        tag, val = store.per_share(EPS_DILUTED, end)
        if val is None:
            tag, val = store.per_share(EPS_BASIC, end)
        p.inputs["eps"], p.sources["eps"] = val, tag or MISSING

        tag, val = store.per_share(DPS, end)
        p.inputs["dps"], p.sources["dps"] = val, tag or MISSING

        tag, val = store.share_count(end)
        p.inputs["shares"], p.sources["shares"] = val, tag or MISSING

        _derive_equity(store, p, end)
        annual.append(p)

    annual.reverse()                                    # oldest first
    quarters = _current_year_quarters(store, ends[0]) if ends else []

    return Equity(
        entity=store.entity,
        cik=cik,
        years=annual,
        quarters=quarters,
        notes=_notes(annual, quarters),
    )


def _derive_equity(store: EquityStore, p: Period, end: date) -> None:
    """Rebuild what the filing left untagged, and label it as rebuilt."""

    def note(key: str, value: float, how: str) -> None:
        p.inputs[key] = value
        p.sources[key] = f"{DERIVED}: {how}"

    ni, rev = p.inputs.get("net_income"), p.inputs.get("revenue")
    eps, shares = p.inputs.get("eps"), p.inputs.get("shares")

    # The three-way relationship between profit, share count and EPS: any two
    # give the third. Only ever fired from filed values, never chained.
    if eps is None and ni is not None and shares:
        note("eps", ni / shares, "net income ÷ shares")
    elif shares is None and ni is not None and eps:
        note("shares", ni / eps, "net income ÷ EPS")

    # Gross profit is often left untagged even when its parts are present.
    if p.inputs.get("gross_profit") is None and rev is not None:
        _, cost = store.resolve_at(COST_OF_REVENUE, "duration", end)
        if cost is not None:
            note("gross_profit", rev - cost, "revenue less cost of revenue")


def _current_year_quarters(store: EquityStore, latest_fy_end: date) -> list[Period]:
    """Quarters filed since the last annual report closed.

    A company three quarters into its year has filed three 10-Qs and no 10-K,
    so this is how far through the current year it is -- the basis for the
    run-rate rather than any forecast.
    """
    rows = []
    for tag in REVENUE:
        blocks = store._gaap.get(tag, {}).get("units", {}).get("USD", [])
        for e in blocks:
            if not e.get("start") or not str(e.get("form", "")).startswith("10-Q"):
                continue
            end = _parse(e["end"])
            if end <= latest_fy_end:
                continue
            span = (end - _parse(e["start"])).days
            if 60 <= span <= 110:
                rows.append((end, e))
        if rows:
            break

    best: dict[date, dict] = {}
    for end, e in rows:
        if end not in best or e.get("filed", "") > best[end].get("filed", ""):
            best[end] = e

    out = []
    for i, end in enumerate(sorted(best), start=1):
        p = Period(end=end, fy=end.year, fp=f"Q{i}")
        p.inputs["revenue"] = float(best[end]["val"])
        p.sources["revenue"] = "10-Q"
        for key, chain in (("net_income", NET_INCOME), ("ebit", OPERATING_INCOME)):
            tag, val = store.quarterly(chain, end)
            p.inputs[key], p.sources[key] = val, tag or MISSING
        tag, val = store.per_share(EPS_DILUTED, end, quarterly=True)
        p.inputs["eps"], p.sources["eps"] = val, tag or MISSING
        out.append(p)
    return out


def _notes(years: list[Period], quarters: list[Period]) -> list[str]:
    notes = []
    if years:
        latest = years[-1]
        derived = [
            FIELD_LABELS[k] for k in latest.inputs
            if latest.sources.get(k, "").startswith(DERIVED)
        ]
        if derived:
            notes.append(
                "Not tagged in the filing, so rebuilt from other figures: "
                + ", ".join(derived) + "."
            )
        if latest.sources.get("eps", "") in EPS_BASIC:
            notes.append(
                "Diluted EPS was not tagged, so basic EPS is shown. Basic ignores "
                "options and convertibles, so it flatters the figure slightly."
            )
    if len(years) < 5:
        notes.append(
            f"Only {len(years)} years of filings are available, so long-run "
            "comparisons are thin."
        )
    if quarters:
        notes.append(
            f"{len(quarters)} quarter(s) of the current year filed so far."
        )
    return notes


# --------------------------------------------------------------------------
# Price-dependent figures
# --------------------------------------------------------------------------


@dataclass
class Valuation:
    """Everything that needs a share price. None throughout when it is absent."""

    price: float | None = None
    day_change_pct: float | None = None
    pe: float | None = None
    pe_median: float | None = None
    pe_vs_median: float | None = None          # fraction above/below
    dividend_yield: float | None = None
    market_cap: float | None = None
    earnings_yield: float | None = None

    @property
    def available(self) -> bool:
        return self.price is not None


def value(eq: Equity, price: float | None, day_change_pct: float | None = None) -> Valuation:
    """Combine filed figures with a price from outside.

    Kept separate on purpose: if the price feed is down, everything else on the
    page still works and only this block goes quiet.
    """
    v = Valuation(price=price, day_change_pct=day_change_pct)
    latest = eq.latest
    if price is None or latest is None:
        return v

    eps = latest.get("eps")
    if eps and eps > 0:
        v.pe = price / eps
        v.earnings_yield = 100 * eps / price

    # The company's own ten-year P/E needs a price per year, which we do not
    # have historically -- so this is filled in by the caller when a price
    # history is supplied, and left None otherwise.
    dps = latest.get("dps")
    if dps:
        v.dividend_yield = 100 * dps / price

    shares = latest.get("shares")
    if shares:
        v.market_cap = price * shares
    return v


def pe_history(eq: Equity, prices: dict[str, float]) -> list[tuple[str, float]]:
    """P/E per year, given a price for each fiscal year label.

    Only years with both a price and positive EPS appear, so a loss-making year
    drops out rather than producing a negative multiple.
    """
    out = []
    for p in eq.years:
        eps = p.get("eps")
        px = prices.get(p.label)
        if eps and eps > 0 and px:
            out.append((p.label, px / eps))
    return out
