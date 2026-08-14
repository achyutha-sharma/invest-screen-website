"""
Credit ratio extraction from SEC XBRL company facts.

Pulls annual (10-K) figures from SEC's structured data API and computes five
credit ratios across the last three fiscal years. No filing text is parsed.

Extraction and computation are deliberately separate. Filings resolve to a set
of raw inputs, any of which can be overridden by hand before ratios are
computed -- so an untagged or wrongly-tagged line item does not dead-end the
analysis. Manual values are tracked and surfaced, never silently blended in
with filed figures.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

# --------------------------------------------------------------------------
# SEC endpoints
# --------------------------------------------------------------------------

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

DEFAULT_UA = os.environ.get("SEC_USER_AGENT", "ratio-tool your.email@example.com")
CACHE_DIR = Path(os.environ.get("SEC_CACHE_DIR", Path.home() / ".sec_cache"))


# --------------------------------------------------------------------------
# Tag chains
# --------------------------------------------------------------------------

NET_INCOME = [
    "NetIncomeLoss",
    "ProfitLoss",
    "NetIncomeLossAvailableToCommonStockholdersBasic",
]
EQUITY = [
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
]
CURRENT_ASSETS = ["AssetsCurrent"]
CURRENT_LIABILITIES = ["LiabilitiesCurrent"]
TOTAL_ASSETS = ["Assets"]
TOTAL_LIABILITIES = ["Liabilities"]
NONCURRENT_ASSETS = ["AssetsNoncurrent"]
NONCURRENT_LIABILITIES = ["LiabilitiesNoncurrent"]

# Revenue moved to the RevenueFromContractWithCustomer tags under ASC 606, but
# older filings and plenty of current ones still use the legacy names.
REVENUE = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "RevenuesNetOfInterestExpense",
]

INVENTORY = [
    "InventoryNet",
    "InventoryFinishedGoodsNetOfReserves",
    "InventoryGross",
]

# Pretax income is NOT operating income -- it sits after interest expense.
# Kept out of the OPERATING_INCOME chain and used only to derive EBIT by
# adding interest back, which is flagged so the reader knows it is constructed.
PRETAX_INCOME = [
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic",
]

# Depreciation and amortisation are sometimes tagged only as separate lines.
DEPRECIATION_ONLY = ["Depreciation", "DepreciationNonproduction"]
AMORTIZATION_ONLY = [
    "AmortizationOfIntangibleAssets",
    "AmortizationOfDeferredCharges",
    "AmortizationOfFinancingCostsAndDiscounts",
]
OPERATING_INCOME = [
    "OperatingIncomeLoss",
]
DA = [
    "DepreciationDepletionAndAmortization",
    "DepreciationAmortizationAndAccretionNet",
    "DepreciationAndAmortization",
]

# InterestIncomeExpenseNet is a last resort: netting interest income against
# expense shrinks the denominator and overstates coverage.
# Gross interest expense first. Where a filer only reports interest net of
# interest income, coverage is overstated -- badly so for a cash-rich issuer,
# and the net figure can even be negative when interest income exceeds expense.
# InterestPaidNet is cash interest off the cash flow statement: not identical to
# accrued expense, but far closer to gross than any netted P&L line, so it is
# preferred over the netted tags and flagged when used.
INTEREST = [
    "InterestExpense",
    "InterestExpenseDebt",
    "InterestExpenseNonoperating",
    "InterestExpenseBorrowings",
    "InterestPaidNet",
    "InterestPaid",
    "InterestIncomeExpenseNet",
    "InterestIncomeExpenseNonoperatingNet",
]

# Netted against interest income -- coverage from these is an upper bound.
NETTED_INTEREST_TAGS = frozenset(
    {"InterestIncomeExpenseNet", "InterestIncomeExpenseNonoperatingNet"}
)
INTEREST_NETTED = "InterestIncomeExpenseNet"  # kept for callers importing the old name

# Cash paid rather than accrued expense.
CASH_INTEREST_TAGS = frozenset({"InterestPaidNet", "InterestPaid"})

DEBT_COMPONENTS = [
    [
        "LongTermDebtNoncurrent",
        "LongTermDebtAndCapitalLeaseObligations",
        "LongTermDebtAndFinanceLeaseObligation",
        "LongTermDebt",
        "OtherLongTermDebtNoncurrent",
    ],
    [
        "LongTermDebtCurrent",
        "LongTermDebtAndCapitalLeaseObligationsCurrent",
        "LongTermDebtAndFinanceLeaseObligationCurrent",
        "DebtCurrent",
    ],
    [
        "ShortTermBorrowings",
        "OtherShortTermBorrowings",
        "CommercialPaper",
        "ShortTermBankLoansAndNotesPayable",
    ],
]
DEBT_COMBINED = ["DebtLongtermAndShorttermCombinedAmount"]
LEASE_COMPONENTS = [
    ["OperatingLeaseLiabilityNoncurrent"],
    ["OperatingLeaseLiabilityCurrent"],
]

# Tags essentially only banks, insurers and other financial institutions file.
# Their presence means several ratios below stop transferring: for a lender,
# interest expense is the cost of revenue rather than a financing charge, so
# adding it back to build EBITDA deletes the main cost line instead of
# isolating operations. Banks do not report EBITDA and analysts do not compute
# one for them.
FINANCIAL_TAGS = frozenset({
    "Deposits",
    "InterestExpenseDeposits",
    "InterestAndDividendIncomeOperating",
    "RevenuesNetOfInterestExpense",
    "LoansAndLeasesReceivableNetReportedAmount",
    "FinancingReceivableExcludingAccruedInterestBeforeAllowanceForCreditLoss",
    "FederalFundsSoldAndSecuritiesPurchasedUnderAgreementsToResell",
    "PremiumsEarnedNet",
    "LiabilityForFuturePolicyBenefit",
    "PolicyholderFunds",
})

# What a lender is actually judged on, named in the flag so the reader is
# pointed somewhere useful rather than just told a number is unavailable.
FINANCIAL_MEASURES = (
    "net interest margin, the efficiency ratio, CET1 capital, return on "
    "tangible common equity, and loan loss provisions"
)


# --------------------------------------------------------------------------
# Input schema
# --------------------------------------------------------------------------
# Every ratio is computed from these ten fields and nothing else. Anything the
# filing does not supply can be typed in against the same names.


@dataclass(frozen=True)
class InputField:
    key: str
    label: str
    hint: str


INPUT_FIELDS: list[InputField] = [
    InputField("net_income", "Net income", "Bottom line, income statement"),
    InputField("revenue", "Revenue", "Top line, income statement"),
    InputField("equity", "Stockholders' equity", "Balance sheet, period end"),
    InputField("total_assets", "Total assets", "Everything the company owns"),
    InputField("current_assets", "Current assets", "Absent on unclassified balance sheets"),
    InputField("inventory", "Inventory", "Zero is assumed if the filing does not tag it"),
    InputField("current_liabilities", "Current liabilities", "Absent on unclassified balance sheets"),
    InputField("total_liabilities", "Total liabilities", "Derived from assets less equity if untagged"),
    InputField("ebit", "Operating income", "EBIT, before interest and tax"),
    InputField("da", "Depreciation & amortisation", "Usually off the cash flow statement"),
    InputField("interest", "Interest expense", "Gross, not net of interest income"),
    InputField("total_debt", "Total debt", "Long-term plus current maturities plus short-term"),
    InputField("lease_liabilities", "Operating lease liabilities", "Optional, for lease-adjusted leverage"),
]

FIELD_KEYS = [f.key for f in INPUT_FIELDS]
FIELD_LABELS = {f.key: f.label for f in INPUT_FIELDS}

MISSING = "not tagged"
MANUAL = "manual entry"
DERIVED = "derived"


# --------------------------------------------------------------------------
# SEC client
# --------------------------------------------------------------------------


class SecClient:
    """Fetches SEC data with on-disk caching."""

    def __init__(self, user_agent: str = DEFAULT_UA, cache_dir: Path = CACHE_DIR):
        self.headers = {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_json(self, url: str, cache_name: str) -> dict:
        cached = self.cache_dir / cache_name
        if cached.exists():
            return json.loads(cached.read_text())

        import requests  # lazy so offline tests need no network deps

        resp = requests.get(url, headers=self.headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        cached.write_text(json.dumps(data))
        return data

    def cik_for_ticker(self, ticker: str) -> str:
        data = self._get_json(TICKERS_URL, "company_tickers.json")
        target = ticker.strip().upper()
        for row in data.values():
            if row["ticker"].upper() == target:
                return str(row["cik_str"]).zfill(10)
        raise LookupError(f"No SEC filer found for ticker {target}")

    def search(self, query: str, limit: int = 12) -> list[dict]:
        """Find filers by ticker or company name, forgivingly.

        Four tiers, best first: an exact ticker, a name or ticker that starts
        with the query, a name that contains it at a word boundary, and finally
        a fuzzy match for near-misses.

        Comparison strips spaces, dots and ampersands, so "jp morgan" reaches
        JPMORGAN CHASE and "at&t" reaches AT&T INC. The fuzzy tier only runs
        when the strict tiers come up short, because it is slower and looser --
        it is there to rescue "walmrt", not to pad good results with noise.
        """
        data = self._get_json(TICKERS_URL, "company_tickers.json")
        raw = query.strip()
        if not raw:
            return []
        q, qn = raw.lower(), _norm(raw)

        # Word-boundary match, so "NKE" does not match BRI-NKE-R or BA-NKE-RS.
        inner = re.compile(r"\b" + re.escape(q))

        exact, starts, contains, rest = [], [], [], []
        for row in data.values():
            entry = {
                "ticker": row["ticker"].upper(),
                "name": row["title"],
                "cik": str(row["cik_str"]).zfill(10),
            }
            ticker_l, name_l = entry["ticker"].lower(), entry["name"].lower()
            name_n = _norm(entry["name"])
            if ticker_l == q or _norm(entry["ticker"]) == qn:
                exact.append(entry)
            elif name_n.startswith(qn) or ticker_l.startswith(q):
                starts.append(entry)
            elif inner.search(name_l) or (len(qn) >= 5 and qn in name_n):
                # The normalised test ignores word boundaries, which is how
                # "jpmorgan" reaches "JPMORGAN CHASE & CO" -- but it is also how
                # a short query like "nke" would reach BRI-NKE-R. Five
                # characters is short enough for real names, long enough that
                # mid-word collisions stop happening.
                contains.append(entry)
            else:
                rest.append((entry, name_n))

        starts.sort(key=lambda e: len(e["name"]))
        contains.sort(key=lambda e: len(e["name"]))
        found = exact + starts + contains

        # Fuzzy rescue for typos, only when the strict tiers are thin.
        if len(found) < 5 and len(qn) >= 4:
            scored = []
            for entry, name_n in rest:
                if abs(len(name_n) - len(qn)) > max(8, len(qn)):
                    continue  # cheap length filter before the costly compare
                # Against the whole name, and against its first word. A
                # transposition like "nkie" scores poorly against "nikeinc"
                # but well against "nike", which is what was actually mistyped.
                head = _norm(entry["name"].split()[0]) if entry["name"].split() else ""
                score = max(
                    SequenceMatcher(None, qn, name_n[: len(qn) + 4]).ratio(),
                    SequenceMatcher(None, qn, head).ratio() if head else 0.0,
                )
                if score >= 0.72:
                    scored.append((score, len(entry["name"]), entry))
            scored.sort(key=lambda t: (-t[0], t[1]))
            found += [e for _, _, e in scored[:8]]

        # One row per filer. Preferred and multi-class shares list the same CIK
        # under several tickers (CFR and CFR-PB); keep the plainest.
        seen, out = set(), []
        for e in found:
            if e["cik"] in seen:
                continue
            seen.add(e["cik"])
            out.append(e)
        return out[:limit]

    def cik_for_query(self, query: str) -> str:
        """Accept a ticker, a company name, or any SEC URL containing a CIK."""
        from_url = parse_cik_from_url(query)
        if from_url:
            return from_url
        matches = self.search(query, limit=1)
        if not matches:
            raise LookupError(f"No SEC filer found for '{query}'")
        return matches[0]["cik"]

    def company_facts(self, cik: str) -> dict:
        return self._get_json(FACTS_URL.format(cik=cik), f"facts_{cik}.json")

    def company_profile(self, cik: str) -> dict:
        """Registration details, including the SEC's industry classification.

        SIC is the SEC's own code for what a filer does -- Home Depot is 5211,
        "Retail-Lumber & Other Building Materials". Useful for judging whether
        two companies belong in the same peer set, which the tool otherwise has
        no way to check.

        Never raises. A missing profile costs a caption, not the page.
        """
        try:
            d = self._get_json(SUBMISSIONS_URL.format(cik=cik), f"sub_{cik}.json")
        except Exception:
            return {}
        return {
            "name": d.get("name", ""),
            "sic": str(d.get("sic") or ""),
            "industry": d.get("sicDescription") or "",
            "fiscal_year_end": d.get("fiscalYearEnd") or "",
            "exchanges": d.get("exchanges") or [],
        }

    def facts_for_ticker(self, ticker: str) -> dict:
        return self.company_facts(self.cik_for_ticker(ticker))

    def facts_for_cik(self, cik: str) -> dict:
        return self.company_facts(str(cik).zfill(10))


def _norm(text: str) -> str:
    """Lowercase, letters and digits only.

    Company names carry punctuation that people do not type: "JPMORGAN CHASE &
    CO" against "jp morgan", "AT&T INC." against "at&t". Stripping everything
    but alphanumerics makes those match without loosening the comparison.
    """
    return re.sub(r"[^a-z0-9]", "", text.lower())


def parse_cik_from_url(text: str) -> str | None:
    """Pull a CIK out of a pasted SEC link.

    Handles the two shapes people copy: filing archive paths that carry the CIK
    as a path segment, and EDGAR browse pages that carry it as a query
    parameter. Returns None for anything that is not a SEC URL.
    """
    t = text.strip()
    if "sec.gov" not in t.lower():
        return None
    m = re.search(r"/data/(\d{1,10})", t) or re.search(r"CIK=(\d{1,10})", t, re.I)
    return m.group(1).zfill(10) if m else None


# --------------------------------------------------------------------------
# Fact extraction
# --------------------------------------------------------------------------


def _parse(d: str) -> date:
    return datetime.strptime(d, "%Y-%m-%d").date()


def _is_annual_form(entry: dict) -> bool:
    return str(entry.get("form", "")).startswith("10-K")


def _dedupe_latest(entries: Iterable[dict]) -> dict[date, float]:
    """One value per period end, keeping the most recently filed.

    The same fiscal year is reported and restated across several filings, so a
    naive pass produces duplicates and stale numbers.
    """
    best: dict[date, dict] = {}
    for e in entries:
        end = _parse(e["end"])
        prior = best.get(end)
        if prior is None or e.get("filed", "") > prior.get("filed", ""):
            best[end] = e
    return {end: float(e["val"]) for end, e in best.items()}


class FactStore:
    """Thin wrapper over the us-gaap block of a companyfacts payload."""

    def __init__(self, facts_payload: dict):
        self.entity = facts_payload.get("entityName", "Unknown filer")
        self._gaap = facts_payload.get("facts", {}).get("us-gaap", {})
        self._cache: dict[tuple[str, str], dict[date, float]] = {}

    def _entries(self, tag: str) -> list[dict]:
        return list(self._gaap.get(tag, {}).get("units", {}).get("USD", []))

    def has_any(self, tags) -> bool:
        """True if the filer uses any of these tags at all."""
        return any(t in self._gaap for t in tags)

    def instant(self, tag: str) -> dict[date, float]:
        """Balance sheet items: point-in-time, no start date."""
        rows = [e for e in self._entries(tag) if _is_annual_form(e) and not e.get("start")]
        return _dedupe_latest(rows)

    def duration(self, tag: str) -> dict[date, float]:
        """Income and cash-flow items, restricted to ~12-month spans.

        Annual filings also carry quarterly durations for the same tag; without
        this filter you silently pick up a single quarter.
        """
        rows = []
        for e in self._entries(tag):
            if not _is_annual_form(e) or not e.get("start"):
                continue
            span = (_parse(e["end"]) - _parse(e["start"])).days
            if 340 <= span <= 400:
                rows.append(e)
        return _dedupe_latest(rows)

    def resolve(self, chain: list[str], kind: str) -> tuple[str | None, dict[date, float]]:
        """First tag in the chain that has data, with the series it produced."""
        getter = self.instant if kind == "instant" else self.duration
        for tag in chain:
            series = getter(tag)
            if series:
                return tag, series
        return None, {}

    def series(self, tag: str, kind: str) -> dict[date, float]:
        """Cached lookup. Resolution walks chains per period now, so the same
        tag is asked for once per year; re-filtering it each time is wasteful."""
        key = (tag, kind)
        if key not in self._cache:
            self._cache[key] = self.instant(tag) if kind == "instant" else self.duration(tag)
        return self._cache[key]

    def resolve_at(
        self, chain: list[str], kind: str, target: date
    ) -> tuple[str | None, float | None]:
        """First tag in the chain with a value at THIS period end.

        Resolving a chain once for the whole company is wrong: filers switch
        tags between years. A company reporting InterestExpense one year and
        InterestExpenseNonoperating the next would show the first year and
        blanks after it, because the winning tag has no data for later periods.
        Walking the chain per period fixes that, and lets each year record the
        tag it actually used.
        """
        for tag in chain:
            found = self.series(tag, kind)
            if found:
                value = _pick(found, target)
                if value is not None:
                    return tag, value
        return None, None


def _pick(series: dict[date, float], target: date, tol_days: int = 7) -> float | None:
    """Value at a period end, allowing small fiscal-calendar drift."""
    if target in series:
        return series[target]
    for end, val in series.items():
        if abs((end - target).days) <= tol_days:
            return val
    return None


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------


@dataclass
class YearResult:
    period_end: date
    inputs: dict[str, float | None] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    ratios: dict[str, str] = field(default_factory=dict)
    values: dict[str, float | None] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"FY{self.period_end.year}"

    @property
    def key(self) -> str:
        return self.period_end.isoformat()

    def missing(self) -> list[str]:
        return [k for k in FIELD_KEYS if self.inputs.get(k) is None]

    def manual(self) -> list[str]:
        return [k for k in FIELD_KEYS if self.sources.get(k) == MANUAL]


@dataclass
class Analysis:
    entity: str
    years: list[YearResult]
    is_financial: bool = False

    @property
    def all_flags(self) -> list[str]:
        seen, out = set(), []
        for y in self.years:
            for f in y.flags:
                if f not in seen:
                    seen.add(f)
                    out.append(f)
        return out

    @property
    def has_manual(self) -> bool:
        return any(y.manual() for y in self.years)


RATIO_GROUPS: list[tuple[str, list[str]]] = [
    ("Liquidity", ["Current ratio", "Quick ratio"]),
    ("Leverage", [
        "Debt / equity",
        "Debt / assets",
        "Debt / EBITDA",
        "Debt / EBITDA (lease-adj.)",
        "Interest coverage",
    ]),
    ("Profitability", [
        "Net profit margin",
        "EBITDA margin",
        "Return on assets",
        "Return on equity",
    ]),
    ("Efficiency", ["Asset turnover"]),
]

RATIO_ORDER = [name for _, names in RATIO_GROUPS for name in names]


def _fmt(value: float, suffix: str = "x") -> str:
    return f"{value:,.2f}{suffix}"


# --------------------------------------------------------------------------
# Grading
# --------------------------------------------------------------------------
# (strong_cut, weak_cut, direction). These are broad corporate-credit rules of
# thumb, not standards. A regulated utility at 4.5x leverage is unremarkable;
# a software company at the same level is stretched. Treat the colour as a
# prompt to look closer, never as a verdict.

GOOD, WATCH, WEAK = "good", "watch", "weak"

THRESHOLDS: dict[str, tuple[float, float, str]] = {
    "Current ratio": (1.5, 1.0, "higher"),
    "Quick ratio": (1.0, 0.5, "higher"),
    "Debt / equity": (1.0, 2.0, "lower"),
    "Debt / assets": (0.5, 0.7, "lower"),
    "Debt / EBITDA": (2.5, 4.0, "lower"),
    "Debt / EBITDA (lease-adj.)": (3.0, 4.5, "lower"),
    "Interest coverage": (4.0, 2.0, "higher"),
    "Net profit margin": (10.0, 3.0, "higher"),
    "EBITDA margin": (20.0, 8.0, "higher"),
    "Return on assets": (5.0, 1.5, "higher"),
    "Return on equity": (15.0, 5.0, "higher"),
    # Asset turnover is deliberately absent. A utility runs near 0.3 and a
    # grocer near 3.0, both perfectly healthy, so there is no honest universal
    # band -- grading it would manufacture a verdict rather than report one.
}

THRESHOLD_NOTES: dict[str, str] = {
    "Current ratio": "Strong above 1.5x, weak below 1.0x — under 1.0 means bills due this year exceed the assets on hand.",
    "Quick ratio": "Strong above 1.0x, weak below 0.5x — the current ratio with inventory stripped out, since stock is the slowest thing to turn into cash.",
    "Debt / equity": "Strong below 1.0x, weak above 2.0x. Banks run far higher by design.",
    "Debt / assets": "Strong below 0.5, weak above 0.7 — the share of everything owned that is funded by what is owed.",
    "Debt / EBITDA": "Strong below 2.5x, weak above 4.0x — most loan covenants sit near 3.5x.",
    "Debt / EBITDA (lease-adj.)": "Same idea with leases capitalised, so the cutoffs sit higher.",
    "Interest coverage": "Strong above 4x, weak below 2x — under 2x is distressed territory.",
    "Net profit margin": "Strong above 10%, weak below 3%. Varies enormously by industry.",
    "EBITDA margin": "Strong above 20%, weak below 8%. Software runs high, grocery runs thin.",
    "Return on assets": "Strong above 5%, weak below 1.5%. Banks sit near 1% and are not comparable.",
    "Return on equity": "Strong above 15%, weak below 5%.",
    "Asset turnover": "Not graded — a utility near 0.3 and a grocer near 3.0 are both healthy, so there is no honest universal band.",
}


def grade(ratio_name: str, value: float | None) -> str | None:
    """Bucket a ratio as good / watch / weak, or None if not gradeable."""
    if value is None or ratio_name not in THRESHOLDS:
        return None
    strong, weak, direction = THRESHOLDS[ratio_name]
    if direction == "higher":
        if value >= strong:
            return GOOD
        return WATCH if value >= weak else WEAK
    if value <= strong:
        return GOOD
    return WATCH if value <= weak else WEAK


# --------------------------------------------------------------------------
# Health bands
# --------------------------------------------------------------------------
# (higher_is_better, good_at, poor_at). A ratio is GOOD past good_at, POOR past
# poor_at, MODERATE in between.
#
# These are screening heuristics, not credit policy. What counts as safe
# leverage is industry-specific: a regulated utility runs comfortably at levels
# that would be distress signals for a software company, because its cash flows
# are stable and its assets are financeable. Pick the profile that fits the
# borrower, and treat the colour as a prompt to look closer, never a verdict.

GOOD, MODERATE, POOR, UNRATED = "good", "moderate", "poor", "unrated"

THRESHOLD_PROFILES: dict[str, dict[str, tuple[bool, float, float]]] = {
    "General corporate": {
        "Return on equity": (True, 15.0, 8.0),
        "Current ratio": (True, 1.50, 1.00),
        "Debt / equity": (False, 1.00, 2.50),
        "Interest coverage": (True, 6.00, 2.00),
        "Debt / EBITDA": (False, 2.50, 4.00),
        "Debt / EBITDA (lease-adj.)": (False, 3.00, 4.50),
    },
    "Capital intensive (utilities, telecom, transport)": {
        "Return on equity": (True, 10.0, 5.0),
        "Current ratio": (True, 1.20, 0.80),
        "Debt / equity": (False, 1.50, 3.50),
        "Interest coverage": (True, 3.50, 1.50),
        "Debt / EBITDA": (False, 4.00, 6.00),
        "Debt / EBITDA (lease-adj.)": (False, 4.50, 6.50),
    },
    "Asset light (software, services)": {
        "Return on equity": (True, 20.0, 10.0),
        "Current ratio": (True, 1.80, 1.20),
        "Debt / equity": (False, 0.75, 2.00),
        "Interest coverage": (True, 10.00, 3.00),
        "Debt / EBITDA": (False, 1.50, 3.00),
        "Debt / EBITDA (lease-adj.)": (False, 2.00, 3.50),
    },
}

DEFAULT_PROFILE = "General corporate"


def rating(ratio_name: str, value: float | None, profile: str = DEFAULT_PROFILE) -> str:
    """Classify one ratio as good, moderate, poor, or unrated."""
    if value is None:
        return UNRATED
    band = THRESHOLD_PROFILES.get(profile, {}).get(ratio_name)
    if band is None:
        return UNRATED
    higher_is_better, good_at, poor_at = band
    if higher_is_better:
        if value >= good_at:
            return GOOD
        return MODERATE if value > poor_at else POOR
    if value <= good_at:
        return GOOD
    return MODERATE if value < poor_at else POOR


def band_text(ratio_name: str, profile: str = DEFAULT_PROFILE) -> str:
    """Plain-language description of where the cut-offs sit."""
    band = THRESHOLD_PROFILES.get(profile, {}).get(ratio_name)
    if band is None:
        return ""
    higher_is_better, good_at, poor_at = band
    unit = "%" if ratio_name == "Return on equity" else "x"
    if higher_is_better:
        return f"green at or above {good_at:g}{unit}, red at or below {poor_at:g}{unit}"
    return f"green at or below {good_at:g}{unit}, red at or above {poor_at:g}{unit}"


# --------------------------------------------------------------------------
# Step 1: extract raw inputs
# --------------------------------------------------------------------------


def _sum_components(
    store: FactStore, chains: list[list[str]], target: date
) -> tuple[float | None, str]:
    """Sum optional balance sheet components, reporting the tags used."""
    total, used = 0.0, []
    for chain in chains:
        tag, series = store.resolve(chain, "instant")
        val = _pick(series, target) if series else None
        if val is not None:
            total += val
            used.append(tag)
    if not used:
        return None, MISSING
    return total, " + ".join(used)


def _sum_at(store: FactStore, chains: list[list[str]], target: date) -> tuple[float | None, str]:
    """Sum optional balance sheet components at one period end."""
    total, used = 0.0, []
    for chain in chains:
        tag, value = store.resolve_at(chain, "instant", target)
        if value is not None:
            total += value
            used.append(tag)
    if not used:
        return None, MISSING
    return total, " + ".join(used)


FIELD_CHAINS = [
    ("net_income", NET_INCOME, "duration"),
    ("revenue", REVENUE, "duration"),
    ("equity", EQUITY, "instant"),
    ("total_assets", TOTAL_ASSETS, "instant"),
    ("current_assets", CURRENT_ASSETS, "instant"),
    ("inventory", INVENTORY, "instant"),
    ("current_liabilities", CURRENT_LIABILITIES, "instant"),
    ("total_liabilities", TOTAL_LIABILITIES, "instant"),
    ("ebit", OPERATING_INCOME, "duration"),
    ("da", DA, "duration"),
    ("interest", INTEREST, "duration"),
]


def _derive(store: FactStore, r: YearResult, pe: date) -> None:
    """Fill gaps from other tagged figures, in place.

    Most "missing" inputs are not actually absent from the filing -- they are
    simply not tagged under the name the chain looked for, while the pieces
    needed to reconstruct them are tagged. Each derivation records how it was
    built, so a constructed figure is never mistaken for a filed one.

    Order matters. Derivations read only filed values, never other derived
    ones, so nothing compounds: equity from assets less liabilities and
    liabilities from assets less equity can never both fire.
    """
    inputs, sources = r.inputs, r.sources

    def filed(key: str) -> float | None:
        """Value only if it came from a tag, not from an earlier derivation."""
        if sources.get(key, MISSING) in (MISSING, MANUAL) or sources.get(key, "").startswith(DERIVED):
            return None
        return inputs.get(key)

    def note(key: str, value: float, how: str) -> None:
        inputs[key] = value
        sources[key] = f"{DERIVED}: {how}"

    _, assets = store.resolve_at(TOTAL_ASSETS, "instant", pe)

    # Balance sheet identity, in whichever direction is missing.
    if inputs.get("total_liabilities") is None and assets is not None and filed("equity") is not None:
        note("total_liabilities", assets - inputs["equity"], "assets less equity")
    elif inputs.get("equity") is None and assets is not None and filed("total_liabilities") is not None:
        note("equity", assets - inputs["total_liabilities"], "assets less liabilities")
    elif inputs.get("total_assets") is None and filed("total_liabilities") is not None and filed("equity") is not None:
        note("total_assets", inputs["total_liabilities"] + inputs["equity"],
             "liabilities plus equity")

    # Current items, where the filer split only the non-current side.
    if inputs.get("current_assets") is None and assets is not None:
        _, noncurrent = store.resolve_at(NONCURRENT_ASSETS, "instant", pe)
        if noncurrent is not None:
            note("current_assets", assets - noncurrent, "assets less non-current")

    if inputs.get("current_liabilities") is None and inputs.get("total_liabilities") is not None:
        _, noncurrent = store.resolve_at(NONCURRENT_LIABILITIES, "instant", pe)
        if noncurrent is not None:
            note("current_liabilities", inputs["total_liabilities"] - noncurrent,
                 "liabilities less non-current")

    # EBIT from pretax income by adding interest back. Pretax income sits
    # after interest, so using it directly as EBIT understates coverage.
    if inputs.get("ebit") is None and inputs.get("interest") is not None:
        _, pretax = store.resolve_at(PRETAX_INCOME, "duration", pe)
        if pretax is not None:
            note("ebit", pretax + abs(inputs["interest"]), "pretax income plus interest")

    # D&A tagged only as separate depreciation and amortisation lines.
    if inputs.get("da") is None:
        _, dep = store.resolve_at(DEPRECIATION_ONLY, "duration", pe)
        _, amort = store.resolve_at(AMORTIZATION_ONLY, "duration", pe)
        if dep is not None or amort is not None:
            note("da", (dep or 0.0) + (amort or 0.0),
                 "depreciation plus amortisation" if dep and amort
                 else "depreciation only" if dep else "amortisation only")


def extract(facts_payload: dict, years: int = 3) -> Analysis:
    """Resolve filings into raw inputs. No ratios computed yet."""
    store = FactStore(facts_payload)

    _, net_income = store.resolve(NET_INCOME, "duration")
    if not net_income:
        raise ValueError(
            "No annual net income found. The filer may report in a currency other "
            "than USD, or may not file 10-Ks."
        )

    period_ends = sorted(net_income.keys(), reverse=True)[:years]

    results = []
    for pe in period_ends:
        r = YearResult(period_end=pe)

        for key, chain, kind in FIELD_CHAINS:
            tag, value = store.resolve_at(chain, kind, pe)
            r.inputs[key] = value
            r.sources[key] = tag if value is not None else MISSING

        debt, debt_src = _sum_at(store, DEBT_COMPONENTS, pe)
        if debt is None:
            tag, value = store.resolve_at(DEBT_COMBINED, "instant", pe)
            if value is not None:
                debt, debt_src = value, tag
        r.inputs["total_debt"], r.sources["total_debt"] = debt, debt_src

        leases, lease_src = _sum_at(store, LEASE_COMPONENTS, pe)
        r.inputs["lease_liabilities"], r.sources["lease_liabilities"] = leases, lease_src

        # Reconstruct what the filing did not tag directly.
        _derive(store, r, pe)

        results.append(r)

    return Analysis(
        entity=store.entity,
        years=results,
        is_financial=store.has_any(FINANCIAL_TAGS),
    )


# --------------------------------------------------------------------------
# Step 2: apply manual overrides
# --------------------------------------------------------------------------


def apply_overrides(analysis: Analysis, overrides: dict[str, dict[str, float | None]]) -> Analysis:
    """Replace inputs with hand-entered values.

    Keyed by ISO period end, then field key; values in dollars. Passing None
    clears a field back to missing, so a wrongly-tagged figure can be removed
    as well as replaced.
    """
    for year in analysis.years:
        for key, val in (overrides.get(year.key) or {}).items():
            if key not in FIELD_KEYS:
                raise KeyError(f"Unknown input field: {key}")
            year.inputs[key] = val
            year.sources[key] = MANUAL if val is not None else MISSING
    return analysis


# --------------------------------------------------------------------------
# Step 3: compute ratios
# --------------------------------------------------------------------------


def compute(analysis: Analysis) -> Analysis:
    """Compute ratios from whatever inputs are present, filed or manual."""
    fin = analysis.is_financial

    for r in analysis.years:
        r.ratios, r.values, r.flags = {}, {}, []
        i = r.inputs

        def put(name: str, value: float | None, text: str) -> None:
            """Record a ratio twice: as a number for colouring, as text to show."""
            r.values[name] = value
            r.ratios[name] = text

        ni, eq = i.get("net_income"), i.get("equity")
        rev, assets = i.get("revenue"), i.get("total_assets")
        ca, cl = i.get("current_assets"), i.get("current_liabilities")
        inv = i.get("inventory")
        liab, ebit = i.get("total_liabilities"), i.get("ebit")
        da, interest = i.get("da"), i.get("interest")
        debt, leases = i.get("total_debt"), i.get("lease_liabilities")

        # --- Return on equity -------------------------------------------
        # Near-zero equity is a third case, distinct from negative. Home Depot
        # has bought back so much stock that equity is a rounding error against
        # earnings, so ROE runs into the hundreds of percent. The figure is
        # arithmetically real but says nothing about profitability and must not
        # be coloured "strong" -- so it prints ungraded, with a warning.
        if ni is None or eq is None:
            put("Return on equity", None, MISSING)
        elif eq <= 0:
            put("Return on equity", None, "n/m - negative equity")
            r.flags.append(
                "Equity is negative, typically from sustained buybacks. ROE and D/E "
                "are not meaningful; read leverage off Debt/EBITDA instead."
            )
        elif 100 * ni / eq > 100:
            put("Return on equity", None, f"{100 * ni / eq:,.0f}% - n/m")
            r.flags.append(
                "Equity is near zero after years of buybacks, so ROE runs to several "
                "hundred percent. The figure is real but not comparable to peers, so "
                "it is left ungraded. Judge profitability on margins and coverage."
            )
        else:
            roe = 100 * ni / eq
            put("Return on equity", roe, _fmt(roe, "%"))

        # --- Current ratio ----------------------------------------------
        if ca is None or cl is None:
            put("Current ratio", None, "n/a - unclassified balance sheet")
            r.flags.append(
                "No current asset/liability split. Banks and insurers file "
                "unclassified balance sheets; liquidity needs a different lens."
            )
        elif cl == 0:
            put("Current ratio", None, MISSING)
        else:
            put("Current ratio", ca / cl, _fmt(ca / cl))

        # --- Quick ratio -------------------------------------------------
        # Inventory stripped out, since stock is the slowest current asset to
        # turn into cash. Where the filing tags no inventory it is treated as
        # zero -- true for most service businesses, and flagged either way so
        # the assumption is never silent.
        if ca is None or cl is None or cl == 0:
            put("Quick ratio", None, "n/a - unclassified balance sheet"
                if ca is None or cl is None else MISSING)
        else:
            quick = (ca - (inv or 0.0)) / cl
            put("Quick ratio", quick, _fmt(quick))
            if inv is None:
                r.flags.append(
                    "No inventory was tagged, so the quick ratio treats it as zero. "
                    "That holds for most service businesses; for a retailer or "
                    "manufacturer, enter the inventory figure to get a true reading."
                )

        # --- Debt / equity ----------------------------------------------
        if liab is None or eq is None:
            put("Debt / equity", None, MISSING)
        elif eq <= 0:
            put("Debt / equity", None, "n/m - negative equity")
        elif liab / eq > 20:
            # Same near-zero-equity distortion as ROE: the denominator is too
            # small to carry meaning, and grading it red would misread a
            # buyback programme as distress.
            put("Debt / equity", None, f"{liab / eq:,.0f}x - n/m")
        elif fin:
            # A lender funded by deposits sits above 10x by design. The figure
            # describes the business; scoring it against an industrial band
            # would call every healthy bank distressed.
            put("Debt / equity", None, f"{liab / eq:,.2f}x - n/m")
        else:
            put("Debt / equity", liab / eq, _fmt(liab / eq))

        # --- Debt / assets -----------------------------------------------
        # Unlike D/E this one survives a near-zero or negative equity line,
        # because the denominator is everything owned rather than what is left
        # over for owners. That makes it the readable leverage figure exactly
        # when D/E stops being one.
        if liab is None or assets is None or assets == 0:
            put("Debt / assets", None, MISSING)
        elif fin:
            put("Debt / assets", None, f"{liab / assets:,.2f} - n/m")
        else:
            put("Debt / assets", liab / assets, f"{liab / assets:,.2f}")

        # --- Interest coverage ------------------------------------------
        src_int = r.sources.get("interest")
        if fin:
            # For a lender, interest paid to depositors is the cost of the
            # product, not a financing charge on top of operations. Coverage
            # compares two figures that are not separable here.
            put("Interest coverage", None, "n/a - interest is a cost of revenue")
        elif ebit is None:
            put("Interest coverage", None, MISSING)
        elif interest is None or interest == 0:
            put("Interest coverage", None, "n/m - no interest expense reported")
        elif interest < 0 and src_int in NETTED_INTEREST_TAGS:
            # Net interest income exceeds net interest expense. There is no
            # denominator here -- dividing by it would invert the meaning.
            put("Interest coverage", None, "n/m - net interest income")
            r.flags.append(
                "This filer reports interest net of interest income, and the net "
                "figure is income rather than expense, so no coverage ratio exists. "
                "Enter gross interest expense from the filing to compute one."
            )
        else:
            cov = ebit / abs(interest)
            put("Interest coverage", cov, _fmt(cov))
            if src_int in NETTED_INTEREST_TAGS:
                r.flags.append(
                    "Interest is reported net of interest income, so coverage is "
                    "overstated. Enter gross interest expense to correct it."
                )
            elif src_int in CASH_INTEREST_TAGS:
                r.flags.append(
                    "No gross interest expense was tagged, so coverage uses cash "
                    "interest paid from the cash flow statement. Close, but it "
                    "excludes accrued and non-cash interest."
                )

        # --- Debt / EBITDA ----------------------------------------------
        ebitda = None if (ebit is None or da is None) else ebit + da
        if fin:
            put("Debt / EBITDA", None, "n/a - banks do not report EBITDA")
        elif ebitda is None or debt is None:
            put("Debt / EBITDA", None, MISSING)
        elif ebitda <= 0:
            put("Debt / EBITDA", None, "n/m - negative EBITDA")
        else:
            put("Debt / EBITDA", debt / ebitda, _fmt(debt / ebitda))
            if leases:
                lev = (debt + leases) / ebitda
                put("Debt / EBITDA (lease-adj.)", lev, _fmt(lev))
                r.flags.append(
                    "Lease-adjusted leverage adds capitalised operating leases to debt, "
                    "as rating agencies do. It matters most for retail and airlines."
                )

        # --- Margins, returns, efficiency --------------------------------
        if ni is None or rev is None or rev == 0:
            put("Net profit margin", None, MISSING)
        else:
            put("Net profit margin", 100 * ni / rev, _fmt(100 * ni / rev, "%"))

        ebitda_m = None if (ebit is None or da is None) else ebit + da
        if fin:
            put("EBITDA margin", None, "n/a - banks do not report EBITDA")
        elif ebitda_m is None or rev is None or rev == 0:
            put("EBITDA margin", None, MISSING)
        else:
            put("EBITDA margin", 100 * ebitda_m / rev, _fmt(100 * ebitda_m / rev, "%"))

        if ni is None or assets is None or assets == 0:
            put("Return on assets", None, MISSING)
        elif fin:
            # A bank holding vast assets against thin spreads earns around 1%
            # and is perfectly healthy. The industrial band would call that weak.
            put("Return on assets", None, f"{100 * ni / assets:,.2f}% - n/m")
        else:
            put("Return on assets", 100 * ni / assets, _fmt(100 * ni / assets, "%"))

        # Ungraded on purpose -- see THRESHOLDS. Reported, never scored.
        if rev is None or assets is None or assets == 0:
            put("Asset turnover", None, MISSING)
        else:
            put("Asset turnover", rev / assets, f"{rev / assets:,.2f}")

        # --- Provenance --------------------------------------------------
        if fin:
            r.flags.append(
                "This is a bank or insurer, so several ratios above are left "
                "unscored rather than computed. Interest paid to depositors is the "
                "cost of the product, not a financing charge, which is why EBITDA "
                "is neither reported nor meaningful here — and leverage above 10x "
                "is the business model, not distress. Lenders are judged on "
                f"{FINANCIAL_MEASURES}."
            )
        derived = [
            (FIELD_LABELS[k], r.sources[k].split(": ", 1)[-1])
            for k in FIELD_KEYS
            if r.sources.get(k, "").startswith(DERIVED)
        ]
        if derived:
            built = "; ".join(f"{name} ({how})" for name, how in derived)
            r.flags.append(
                f"Not tagged in the filing, so reconstructed from other figures: {built}. "
                "Check these against the statements before quoting them."
            )
        if r.manual():
            names = ", ".join(FIELD_LABELS[k] for k in r.manual())
            r.flags.append(f"{r.label} uses hand-entered figures for: {names}.")

    return analysis


def analyze(
    facts_payload: dict,
    years: int = 3,
    overrides: dict[str, dict[str, float | None]] | None = None,
) -> Analysis:
    """Extract, override, compute."""
    a = extract(facts_payload, years=years)
    if overrides:
        a = apply_overrides(a, overrides)
    return compute(a)


def to_table(analysis: Analysis) -> tuple[list[str], list[list[str]]]:
    """(header, rows) with fiscal years as columns, oldest first."""
    years = sorted(analysis.years, key=lambda y: y.period_end)
    header = ["Ratio"] + [y.label for y in years]
    present = [r for r in RATIO_ORDER if any(r in y.ratios for y in years)]
    rows = [[r] + [y.ratios.get(r, MISSING) for y in years] for r in present]
    return header, rows


def ratings_table(analysis: Analysis, profile: str = DEFAULT_PROFILE) -> list[list[str]]:
    """Health class per cell, matching the shape of to_table's rows."""
    years = sorted(analysis.years, key=lambda y: y.period_end)
    present = [r for r in RATIO_ORDER if any(r in y.ratios for y in years)]
    return [[rating(r, y.values.get(r), profile) for y in years] for r in present]


def inputs_table(analysis: Analysis) -> tuple[list[str], list[list[str]]]:
    """Raw inputs in $ millions, with the tag or source behind each figure."""
    years = sorted(analysis.years, key=lambda y: y.period_end)
    header = ["Input"] + [y.label for y in years] + ["Source (latest year)"]
    rows = []
    for f in INPUT_FIELDS:
        cells = []
        for y in years:
            v = y.inputs.get(f.key)
            cells.append("--" if v is None else f"{v / 1e6:,.0f}")
        rows.append([f.label] + cells + [years[-1].sources.get(f.key, MISSING)])
    return header, rows


# --------------------------------------------------------------------------
# Peer comparison
# --------------------------------------------------------------------------
# Absolute thresholds cannot honestly grade a margin or an asset turnover,
# because what counts as good depends on the industry. A peer set answers the
# same question without inventing a band: compare the borrower to companies
# that face the same economics, and the industry cancels out.

# Which way is better, used only for standing against peers. Distinct from
# THRESHOLDS, which is about absolute levels -- asset turnover appears here
# because more sales per dollar of assets is genuinely better within a peer
# group, even though no universal cut-off exists.
RATIO_DIRECTION: dict[str, str] = {
    "Current ratio": "higher",
    "Quick ratio": "higher",
    "Debt / equity": "lower",
    "Debt / assets": "lower",
    "Debt / EBITDA": "lower",
    "Debt / EBITDA (lease-adj.)": "lower",
    "Interest coverage": "higher",
    "Net profit margin": "higher",
    "EBITDA margin": "higher",
    "Return on assets": "higher",
    "Return on equity": "higher",
    "Asset turnover": "higher",
}

BETTER, INLINE, WORSE = "better", "in line", "worse"

# Below this the gap is noise rather than signal, so the standing reads "in
# line" instead of manufacturing a distinction from a rounding difference.
PEER_TOLERANCE = 0.10


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def standing(name: str, value: float | None, median: float | None) -> str | None:
    """Where one company sits against the peer median for this ratio."""
    if value is None or median is None or median == 0:
        return None
    gap = (value - median) / abs(median)
    if abs(gap) < PEER_TOLERANCE:
        return INLINE
    better_when_higher = RATIO_DIRECTION.get(name, "higher") == "higher"
    return BETTER if (gap > 0) == better_when_higher else WORSE


@dataclass
class PeerCell:
    text: str
    value: float | None = None
    standing: str | None = None


@dataclass
class PeerRow:
    ratio: str
    cells: list[PeerCell]
    median_text: str = "--"


@dataclass
class PeerComparison:
    names: list[str]
    periods: list[str]
    rows: list[PeerRow]
    notes: list[str] = field(default_factory=list)


def _short(entity: str) -> str:
    """Trim the legal suffix so column headers stay narrow."""
    head = entity.split(",")[0]
    for suffix in (" INC", " CORP", " CORPORATION", " CO", " PLC", " LTD", " LLC", " & CO"):
        if head.upper().endswith(suffix):
            head = head[: -len(suffix)]
    return head.strip().title() or entity


def compare(analyses: list[Analysis]) -> PeerComparison:
    """Latest year of each company, side by side, scored against the median.

    The first analysis is the subject; the rest are peers. Standing is measured
    against the median of everyone shown, which is stable with small sets and
    not thrown by one outlier the way a mean would be.
    """
    if not analyses:
        raise ValueError("Nothing to compare.")

    latest = [max(a.years, key=lambda y: y.period_end) for a in analyses]
    comp = PeerComparison(
        names=[_short(a.entity) for a in analyses],
        periods=[y.label for y in latest],
        rows=[],
    )

    for name in RATIO_ORDER:
        if not any(name in y.ratios for y in latest):
            continue
        values = [y.values.get(name) for y in latest]
        med = _median([v for v in values if v is not None])
        cells = [
            PeerCell(
                text=y.ratios.get(name, MISSING),
                value=v,
                standing=standing(name, v, med),
            )
            for y, v in zip(latest, values)
        ]
        row = PeerRow(ratio=name, cells=cells)
        if med is not None:
            row.median_text = (
                f"{med:,.2f}%" if "margin" in name.lower() or name.startswith("Return")
                else f"{med:,.2f}"
            )
        comp.rows.append(row)

    # Things that would quietly distort the read.
    if len({y.label for y in latest}) > 1:
        comp.notes.append(
            "Fiscal years do not line up across these companies, so the columns "
            "cover slightly different periods."
        )
    kinds = {a.is_financial for a in analyses}
    if len(kinds) > 1:
        comp.notes.append(
            "This set mixes a bank or insurer with ordinary companies. They are "
            "not comparable on leverage or margins; read only the ratios that "
            "carry a figure for every column."
        )
    graded = sum(1 for r in comp.rows for c in r.cells if c.standing)
    if len(analyses) < 3 and graded:
        comp.notes.append(
            "With only two companies the median sits between them, so every "
            "ratio reads as better or worse. Add a third for a steadier picture."
        )
    return comp


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------


def to_csv(analysis: Analysis, ticker: str = "", cik: str = "") -> str:
    """The whole analysis as CSV: ratios, inputs, and where each figure came from.

    The source column travels with the export on purpose. A spreadsheet of bare
    numbers loses the one thing that makes these trustworthy -- whether a figure
    was filed, reconstructed, or typed in by hand.
    """
    import csv
    import io
    from datetime import date as _date

    years = sorted(analysis.years, key=lambda y: y.period_end)
    labels = [y.label for y in years]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")

    w.writerow(["Credit Screen - ratio export"])
    w.writerow(["Company", analysis.entity])
    if ticker:
        w.writerow(["Ticker", ticker])
    if cik:
        w.writerow(["CIK", cik])
    w.writerow(["Periods", *labels])
    w.writerow(["Filing", "Form 10-K"])
    w.writerow(["Source", "SEC XBRL company facts"])
    w.writerow(["Exported", _date.today().isoformat()])
    w.writerow([])

    w.writerow(["Ratios"])
    w.writerow(["Group", "Ratio", *labels, f"Standing ({labels[-1]})"])
    for group, names in RATIO_GROUPS:
        for name in names:
            if not any(name in y.ratios for y in years):
                continue
            w.writerow([
                group, name,
                *[y.ratios.get(name, MISSING) for y in years],
                grade(name, years[-1].values.get(name)) or "not scored",
            ])
    w.writerow([])

    w.writerow(["Inputs ($ millions)"])
    w.writerow(["Figure", *labels, f"Source ({labels[-1]})"])
    for f in INPUT_FIELDS:
        w.writerow([
            f.label,
            *["" if y.inputs.get(f.key) is None else round(y.inputs[f.key] / 1e6)
              for y in years],
            years[-1].sources.get(f.key, MISSING),
        ])

    if analysis.all_flags:
        w.writerow([])
        w.writerow(["Notes"])
        for flag in analysis.all_flags:
            w.writerow([flag])

    return buf.getvalue()
