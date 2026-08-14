"""
The scorecard.

Five things the filings can answer, scored 0-2 each, summed to a mark out of
five. Every component is a figure shown elsewhere on the page, so a reader can
check the score rather than trust it.

What this deliberately is not: a forecast, a recommendation, or a claim about
future returns. It scores the evidence a company has already reported. A high
score at the wrong price still loses money and a low score can rise for years,
which the disclaimer at the bottom of the page says in as many words.
"""

from __future__ import annotations

from dataclasses import dataclass

from sec_equity import Equity, Valuation

GOOD, MID, BAD = "good", "mid", "bad"


# Component text is rendered as HTML, so any currency figure uses the &#36;
# entity: Streamlit treats a pair of bare dollar signs as a LaTeX expression
# and eats the markup between them.
@dataclass
class Component:
    name: str
    score: int              # 0, 1 or 2
    why: str                # one sentence, with the figures in it

    @property
    def tone(self) -> str:
        return GOOD if self.score == 2 else MID if self.score == 1 else BAD


@dataclass
class Scorecard:
    components: list[Component]
    unscored: list[str]     # components skipped for want of data

    @property
    def stars(self) -> float:
        """Out of five. Averaged over what could be scored, so a filer missing
        one input is not punished for the gap -- it is reported instead."""
        if not self.components:
            return 0.0
        got = sum(c.score for c in self.components)
        return round(5 * got / (2 * len(self.components)) * 2) / 2

    @property
    def verdict(self) -> str:
        s = self.stars
        return ("The filings look strong" if s >= 4
                else "The filings look mixed" if s >= 2.5
                else "The filings look weak")

    @property
    def tone(self) -> str:
        s = self.stars
        return GOOD if s >= 4 else MID if s >= 2.5 else BAD


def _cagr(first: float, last: float, years: int) -> float | None:
    """Compound annual growth. None where the sign flips, because a percentage
    between a loss and a profit is arithmetic without meaning."""
    if years <= 0 or first is None or last is None or first <= 0 or last <= 0:
        return None
    return (last / first) ** (1 / years) - 1


def score(eq: Equity, val: Valuation, pe_history: list[float] | None = None) -> Scorecard:
    comps: list[Component] = []
    skipped: list[str] = []

    years = eq.years
    latest = eq.latest
    if latest is None:
        return Scorecard([], ["No annual figures were found."])

    # --- 1. long-run growth in profit per share ---------------------------
    eps_series = [p.get("eps") for p in years if p.get("eps") is not None]
    if len(eps_series) >= 4:
        g = _cagr(eps_series[0], eps_series[-1], len(eps_series) - 1)
        if g is None:
            skipped.append(
                "Long-run growth: profit per share crossed between loss and profit, "
                "so a growth rate would be meaningless."
            )
        else:
            pts = 2 if g > 0.08 else 1 if g > 0.02 else 0
            comps.append(Component(
                "Long-run growth", pts,
                f"Profit per share has {'grown' if g >= 0 else 'fallen'} "
                f"<b>{abs(g) * 100:.1f}% a year</b> over {len(eps_series) - 1} years."))
    else:
        skipped.append("Long-run growth: fewer than four years of EPS are filed.")

    # --- 2. margin direction ----------------------------------------------
    def margin(p) -> float | None:
        ni, rev = p.get("net_income"), p.get("revenue")
        return 100 * ni / rev if ni is not None and rev else None

    now = margin(years[-1])
    then = margin(years[-4]) if len(years) >= 4 else None
    if now is not None and then is not None:
        move = now - then
        pts = 2 if move > 1 else 1 if move > -1.5 else 0
        comps.append(Component(
            "Profitability trend", pts,
            f"Net margin is <b>{now:.1f}%</b>, against {then:.1f}% three years ago — "
            f"{'holding up' if move >= 0 else 'eroding'}."))
    elif now is not None:
        skipped.append("Profitability trend: not enough history to compare margins.")
    else:
        skipped.append("Profitability trend: revenue or profit was not tagged.")

    # --- 3. does profit become cash ---------------------------------------
    ni = latest.get("net_income")
    ocf, capex = latest.get("ocf"), latest.get("capex")
    if ni and ocf is not None and capex is not None and ni > 0:
        conv = (ocf - capex) / ni
        pts = 2 if conv > 0.9 else 1 if conv > 0.6 else 0
        comps.append(Component(
            "Cash quality", pts,
            f"<b>&#36;{conv:.2f}</b> of free cash for every &#36;1 of reported profit. "
            + ("Profit is turning into money." if conv > 0.9
               else "Some reported profit is not arriving as cash.")))
    else:
        skipped.append("Cash quality: cash flow or capital spending was not tagged.")

    # --- 4. balance sheet --------------------------------------------------
    # Debt is measured against free cash flow rather than earnings, because
    # cash is what actually repays it.
    debt = latest.get("total_debt")
    cash = latest.get("cash")
    if debt is not None and ocf is not None and capex is not None:
        fcf = ocf - capex
        net = debt - (cash or 0.0)
        if fcf <= 0:
            comps.append(Component(
                "Balance sheet", 0,
                "The business did not generate free cash last year, so debt cannot "
                "be measured against it."))
        elif net <= 0:
            comps.append(Component(
                "Balance sheet", 2,
                "Holds <b>more cash than debt</b>. Nothing owed on a net basis."))
        else:
            x = net / fcf
            pts = 2 if x < 2 else 1 if x < 4 else 0
            comps.append(Component(
                "Balance sheet", pts,
                f"Net debt is <b>{x:.1f}×</b> yearly free cash flow. "
                + ("Comfortably covered." if x < 2
                   else "Manageable." if x < 4
                   else "Heavy — little room in a bad year.")))
    else:
        skipped.append("Balance sheet: borrowings or cash flow was not tagged.")

    # --- 5. price against its own history ---------------------------------
    # Compared with the company's own past, never a fixed target: what counts
    # as a normal multiple differs completely between industries.
    if val.pe and pe_history and len(pe_history) >= 5:
        srt = sorted(pe_history)
        med = srt[len(srt) // 2] if len(srt) % 2 else (srt[len(srt) // 2 - 1] + srt[len(srt) // 2]) / 2
        gap = (val.pe - med) / med
        pts = 2 if gap < 0.10 else 1 if gap < 0.25 else 0
        comps.append(Component(
            "Price vs its own past", pts,
            f"The P/E is <b>{val.pe:.1f}×</b> against a ten-year usual of {med:.1f}× — "
            + ("about normal." if abs(gap) < 0.10
               else f"<b>{abs(gap) * 100:.0f}% {'pricier' if gap > 0 else 'cheaper'}</b> "
                    "than this stock usually trades.")))
    elif val.pe:
        skipped.append("Price vs its own past: not enough price history to compare.")
    elif val.available:
        skipped.append("Price vs its own past: the company made a loss, so there is no P/E.")
    else:
        skipped.append("Price vs its own past: no share price available.")

    return Scorecard(comps, skipped)
