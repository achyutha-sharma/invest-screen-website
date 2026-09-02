"""
What a share price is assuming.

Every site prints a P/E. Almost none translate it into the thing a reader
actually wants to know: how much of what you are paying rests on profits that
have not been earned yet, and how hard the share reacts when something moves.

Both are arithmetic on figures already on the page. Neither is a forecast --
the point is to make an assumption visible, not to endorse it.
"""

from __future__ import annotations

from dataclasses import dataclass

# What a business with no growth ahead of it would fetch. Roughly the multiple
# a stable, ex-growth company trades at once investors stop paying for a
# future. Used only as a reference point, never as a target.
NO_GROWTH_MULTIPLE = 10.0


@dataclass
class Expectations:
    price: float
    eps: float
    justified: float          # price today's earnings alone would support
    expectation: float        # the rest -- what is being paid for growth
    pct: float                # that rest, as a share of the price

    @property
    def heavy(self) -> bool:
        return self.pct >= 60

    @property
    def light(self) -> bool:
        return self.pct <= 25


def expectations(price: float | None, eps: float | None) -> Expectations | None:
    """Split a price into earned profit and expected profit.

    Returns None for a loss-maker: with negative earnings there is no
    "justified by today's profit" figure, and the whole price is expectation
    by definition -- which the page says in words instead.
    """
    if not price or not eps or eps <= 0:
        return None
    justified = min(eps * NO_GROWTH_MULTIPLE, price)
    expectation = max(price - justified, 0.0)
    return Expectations(
        price=price, eps=eps, justified=justified,
        expectation=expectation, pct=100 * expectation / price,
    )


@dataclass
class Sensitivity:
    name: str
    value: str
    what: str                 # what the figure is
    why: str                  # why it moves the share


def operating_leverage(revenues: list[float], ebits: list[float]) -> float | None:
    """Median percent change in operating profit per percent change in sales.

    This is why small news lands hard: fixed costs stay put when sales fall, so
    profit drops faster than revenue -- and a share price follows profit.
    Median rather than mean, because one bad year would otherwise dominate.
    """
    ratios = []
    for i in range(1, min(len(revenues), len(ebits))):
        r0, r1 = revenues[i - 1], revenues[i]
        e0, e1 = ebits[i - 1], ebits[i]
        if not r0 or not e0 or e0 <= 0:
            continue
        dr = (r1 - r0) / r0
        de = (e1 - e0) / e0
        if abs(dr) < 0.005:               # a flat year says nothing about leverage
            continue
        ratios.append(de / dr)
    if not ratios:
        return None
    ratios.sort()
    mid = len(ratios) // 2
    return ratios[mid] if len(ratios) % 2 else (ratios[mid - 1] + ratios[mid]) / 2


def build(price, eps, revenues, ebits, debt, cash, shares,
          foreign_pct: float | None = None) -> list[Sensitivity]:
    """The structural exposures a filing can actually establish."""
    out: list[Sensitivity] = []

    exp = expectations(price, eps)
    if exp:
        out.append(Sensitivity(
            "Price resting on expectations",
            f"{exp.pct:.0f}%",
            f"At ${eps:,.2f} of earnings a share, a business expected to grow at all "
            f"would fetch roughly ${exp.justified:,.0f}. The price is ${price:,.2f}, so "
            f"about ${exp.expectation:,.0f} of it is paying for profits that have not "
            "been earned yet.",
            "This is the part that moves. Last year's earnings are banked; expectations "
            "are not. The higher this share, the more the price can swing on news that "
            "changes nothing about what the company actually reported.",
        ))

    lev = operating_leverage(revenues, ebits)
    if lev is not None and abs(lev) < 25:      # a wild ratio means a distorted year
        out.append(Sensitivity(
            "Profit swing per 1% of sales",
            f"{abs(lev):.1f}×",
            f"Over the filed years, each 1% move in sales moved operating profit about "
            f"{abs(lev):.1f}%.",
            "Why small news lands hard. Fixed costs stay put when sales fall, so profit "
            "drops faster than revenue — and a share price follows profit, not revenue.",
        ))

    if debt is not None and shares:
        net = debt - (cash or 0.0)
        if net > 0 and price:
            per_share = net / shares
            out.append(Sensitivity(
                "Debt behind each share",
                f"${per_share:,.2f}",
                f"Every share carries ${per_share:,.2f} of net borrowings, against a "
                f"${price:,.2f} price.",
                "Lenders are paid before shareholders, in good years and bad. In a poor "
                "year the interest is still owed and whatever is left over is what your "
                "share is worth.",
            ))

    if foreign_pct:
        out.append(Sensitivity(
            "Sales earned abroad",
            f"{foreign_pct:.0f}%",
            f"{foreign_pct:.0f}% of sales are made outside the United States, in other "
            "currencies.",
            "Those sales are converted back into dollars. A stronger dollar shrinks them "
            "before the business has done anything differently.",
        ))

    return out
