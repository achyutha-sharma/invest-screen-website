"""
Offline checks for the equity layer. No network needed.

Run:  python3 test_equity.py
"""

from sec_equity import (
    FIELDS,
    Equity,
    extract_equity,
    pe_history,
    value,
)


def dur(start, end, val, form="10-K", filed="2026-02-01"):
    return {"start": start, "end": end, "val": val, "form": form, "filed": filed}


def inst(end, val, form="10-K", filed="2026-02-01"):
    return {"end": end, "val": val, "form": form, "filed": filed}


def units(**kw):
    return {"units": {k.replace("_", "/"): v for k, v in kw.items()}}


def build(name, tags):
    return {"entityName": name, "facts": {"us-gaap": tags}}


# ---------------------------------------------------------------------------
# A well-behaved filer: ten years, everything tagged.
# ---------------------------------------------------------------------------
def make_clean():
    rev, ni, eps, dps, sh, ocf, capex, gp, ebit, da, bb, debt, csh = ([] for _ in range(13))
    for i in range(10):
        y = 2017 + i
        s, e = f"{y}-01-01", f"{y}-12-31"
        rev.append(dur(s, e, 10_000 + 800 * i))
        ni.append(dur(s, e, 900 + 90 * i))
        gp.append(dur(s, e, 4_200 + 340 * i))
        ebit.append(dur(s, e, 1_400 + 120 * i))
        da.append(dur(s, e, 300 + 12 * i))
        ocf.append(dur(s, e, 1_500 + 130 * i))
        capex.append(dur(s, e, 400 + 10 * i))
        bb.append(dur(s, e, 500 + 40 * i))
        eps.append(dur(s, e, round(1.80 + 0.22 * i, 2)))
        dps.append(dur(s, e, round(0.50 + 0.08 * i, 2)))
        sh.append(dur(s, e, 500 - 8 * i))
        debt.append(inst(e, 2_000 + 50 * i))
        csh.append(inst(e, 1_200 + 90 * i))
    return build("CLEAN INDUSTRIAL CORP", {
        "Revenues": {"units": {"USD": rev}},
        "NetIncomeLoss": {"units": {"USD": ni}},
        "GrossProfit": {"units": {"USD": gp}},
        "OperatingIncomeLoss": {"units": {"USD": ebit}},
        "DepreciationDepletionAndAmortization": {"units": {"USD": da}},
        "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": ocf}},
        "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": capex}},
        "PaymentsForRepurchaseOfCommonStock": {"units": {"USD": bb}},
        "EarningsPerShareDiluted": {"units": {"USD/shares": eps}},
        "CommonStockDividendsPerShareDeclared": {"units": {"USD/shares": dps}},
        "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": sh}},
        "LongTermDebtNoncurrent": {"units": {"USD": debt}},
        "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": csh}},
    })


def test_clean():
    eq = extract_equity(make_clean(), cik="0000000001")
    assert eq.entity == "CLEAN INDUSTRIAL CORP"
    assert len(eq.years) == 10
    assert eq.years[0].label == "FY2017" and eq.years[-1].label == "FY2026"

    last = eq.latest
    assert last.get("revenue") == 17_200
    assert last.get("eps") == 3.78, last.get("eps")
    assert last.get("dps") == 1.22, last.get("dps")
    assert last.get("shares") == 428
    assert last.get("total_debt") == 2_450
    assert last.get("cash") == 2_010
    assert last.get("gross_profit") == 7_260
    assert not last.missing(), last.missing()

    # Ten-year series, oldest first, for the chart.
    eps_series = eq.series("eps")
    assert len(eps_series) == 10
    assert eps_series[0] == ("FY2017", 1.80)
    assert eps_series[-1][1] > eps_series[0][1]
    print("clean filer ok")


def test_valuation():
    eq = extract_equity(make_clean())
    v = value(eq, price=68.00, day_change_pct=-1.4)
    assert v.available
    assert round(v.pe, 2) == round(68 / 3.78, 2)
    assert round(v.dividend_yield, 2) == round(100 * 1.22 / 68, 2)
    assert round(v.earnings_yield, 2) == round(100 * 3.78 / 68, 2)
    assert v.market_cap == 68 * 428
    assert v.day_change_pct == -1.4

    # No price: everything price-dependent goes quiet, nothing raises.
    n = value(eq, price=None)
    assert not n.available
    assert n.pe is None and n.dividend_yield is None and n.market_cap is None

    # P/E history skips years without a price, and loss years.
    hist = pe_history(eq, {"FY2017": 30.0, "FY2026": 68.0})
    assert [h[0] for h in hist] == ["FY2017", "FY2026"]
    assert round(hist[0][1], 2) == round(30 / 1.80, 2)
    print("valuation ok")


# ---------------------------------------------------------------------------
# A messier filer: no diluted EPS, no share count, no gross profit tag.
# ---------------------------------------------------------------------------
def test_derivation():
    payload = build("SPARSE CO", {
        "Revenues": {"units": {"USD": [dur("2026-01-01", "2026-12-31", 8_000)]}},
        "NetIncomeLoss": {"units": {"USD": [dur("2026-01-01", "2026-12-31", 640)]}},
        "CostOfRevenue": {"units": {"USD": [dur("2026-01-01", "2026-12-31", 5_200)]}},
        "OperatingIncomeLoss": {"units": {"USD": [dur("2026-01-01", "2026-12-31", 1_100)]}},
        # Only basic EPS, and no share count at all.
        "EarningsPerShareBasic": {"units": {"USD/shares": [dur("2026-01-01", "2026-12-31", 2.00)]}},
    })
    eq = extract_equity(payload)
    last = eq.latest

    assert last.get("eps") == 2.00
    assert "Basic" in last.sources["eps"]
    # Shares rebuilt from profit ÷ EPS, and labelled as rebuilt.
    assert last.get("shares") == 320, last.get("shares")
    assert last.sources["shares"].startswith("derived")
    # Gross profit rebuilt from revenue less cost of revenue.
    assert last.get("gross_profit") == 2_800
    assert last.sources["gross_profit"].startswith("derived")

    assert any("rebuilt from other figures" in n for n in eq.notes), eq.notes
    assert any("basic EPS is shown" in n for n in eq.notes), eq.notes
    print("derivation ok")


# ---------------------------------------------------------------------------
# Quarterly progress through the current year.
# ---------------------------------------------------------------------------
def test_quarters():
    tags = {
        "Revenues": {"units": {"USD": [
            dur("2025-01-01", "2025-12-31", 16_000),
            # Three quarters of the new year, filed on 10-Qs.
            dur("2026-01-01", "2026-03-31", 4_100, form="10-Q", filed="2026-05-01"),
            dur("2026-04-01", "2026-06-30", 4_300, form="10-Q", filed="2026-08-01"),
            dur("2026-07-01", "2026-09-30", 4_500, form="10-Q", filed="2026-11-01"),
        ]}},
        "NetIncomeLoss": {"units": {"USD": [
            dur("2025-01-01", "2025-12-31", 1_600),
            dur("2026-01-01", "2026-03-31", 400, form="10-Q", filed="2026-05-01"),
            dur("2026-04-01", "2026-06-30", 430, form="10-Q", filed="2026-08-01"),
            dur("2026-07-01", "2026-09-30", 450, form="10-Q", filed="2026-11-01"),
        ]}},
        "EarningsPerShareDiluted": {"units": {"USD/shares": [
            dur("2025-01-01", "2025-12-31", 3.20),
            dur("2026-01-01", "2026-03-31", 0.80, form="10-Q", filed="2026-05-01"),
            dur("2026-04-01", "2026-06-30", 0.86, form="10-Q", filed="2026-08-01"),
            dur("2026-07-01", "2026-09-30", 0.90, form="10-Q", filed="2026-11-01"),
        ]}},
    }
    eq = extract_equity(build("QUARTERLY CO", tags))

    assert len(eq.years) == 1 and eq.years[0].label == "FY2025"
    assert len(eq.quarters) == 3, [q.label for q in eq.quarters]
    assert [q.fp for q in eq.quarters] == ["Q1", "Q2", "Q3"]
    assert eq.quarters[0].get("revenue") == 4_100
    assert eq.quarters[2].get("eps") == 0.90
    assert eq.quarters[1].get("net_income") == 430

    # The run-rate the page shows: arithmetic, not a forecast.
    ytd = sum(q.get("revenue") for q in eq.quarters)
    run_rate = ytd / len(eq.quarters) * 4
    assert ytd == 12_900
    assert round(run_rate) == 17_200
    assert run_rate > eq.years[-1].get("revenue")      # ahead of last year

    assert any("quarter(s) of the current year" in n for n in eq.notes)
    print("quarters ok")


# ---------------------------------------------------------------------------
# Guards.
# ---------------------------------------------------------------------------
def test_guards():
    # A filer with nothing usable must raise clearly, not return an empty shell.
    try:
        extract_equity(build("EMPTY CO", {}))
        raise AssertionError("expected ValueError for a filer with no revenue")
    except ValueError as e:
        assert "revenue" in str(e).lower()

    # Loss-making year: EPS is negative, so no P/E rather than a negative one.
    payload = build("LOSS CO", {
        "Revenues": {"units": {"USD": [dur("2026-01-01", "2026-12-31", 5_000)]}},
        "NetIncomeLoss": {"units": {"USD": [dur("2026-01-01", "2026-12-31", -300)]}},
        "EarningsPerShareDiluted": {"units": {"USD/shares": [dur("2026-01-01", "2026-12-31", -1.20)]}},
        "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": [dur("2026-01-01", "2026-12-31", 250)]}},
    })
    eq = extract_equity(payload)
    v = value(eq, price=14.00)
    assert eq.latest.get("eps") == -1.20
    assert v.pe is None, "a loss must not produce a P/E"
    assert v.market_cap == 14 * 250
    assert pe_history(eq, {"FY2026": 14.0}) == []

    # Every field carries a professional label and a plain gloss.
    for f in FIELDS:
        assert f.label and f.gloss and f.label != f.gloss
        assert len(f.gloss) < 60, f.gloss
    print("guards ok")


if __name__ == "__main__":
    test_clean()
    test_valuation()
    test_derivation()
    test_quarters()
    test_guards()
    print("\nAll equity checks passed.")


# ---------------------------------------------------------------------------
# Scorecard
# ---------------------------------------------------------------------------
def make_scorable(eps_growth=True, margin_up=True, cash_good=True, debt_low=True):
    """A ten-year filer whose five components can be dialled up or down."""
    rev, ni, eps, ocf, capex, debt, cash = ([] for _ in range(7))
    for i in range(10):
        y = 2017 + i
        s, e = f"{y}-01-01", f"{y}-12-31"
        r = 10_000 + 700 * i
        m = (0.06 + 0.010 * i) if margin_up else (0.16 - 0.010 * i)
        rev.append(dur(s, e, r))
        ni.append(dur(s, e, round(r * m)))
        base = 1.50 * (1.12 ** i) if eps_growth else 3.00 * (0.97 ** i)
        eps.append(dur(s, e, round(base, 2)))
        prof = r * m
        ocf.append(dur(s, e, round(prof * (1.45 if cash_good else 0.85))))
        capex.append(dur(s, e, round(prof * 0.35)))
        debt.append(inst(f"{y}-12-31", 1_500 if debt_low else 22_000))
        cash.append(inst(f"{y}-12-31", 3_000 if debt_low else 400))
    return build("SCORABLE CO", {
        "Revenues": {"units": {"USD": rev}},
        "NetIncomeLoss": {"units": {"USD": ni}},
        "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": ocf}},
        "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": capex}},
        "LongTermDebtNoncurrent": {"units": {"USD": debt}},
        "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": cash}},
        "EarningsPerShareDiluted": {"units": {"USD/shares": eps}},
        "WeightedAverageNumberOfDilutedSharesOutstanding":
            {"units": {"shares": [dur(f"{2017+i}-01-01", f"{2017+i}-12-31", 500) for i in range(10)]}},
    })


def test_scorecard():
    from scorecard import score
    from sec_equity import value

    strong = extract_equity(make_scorable())
    eps_now = strong.latest.get("eps")
    v = value(strong, price=eps_now * 18)
    card = score(strong, v, pe_history=[20.0] * 10)

    assert len(card.components) == 5, [c.name for c in card.components]
    assert card.stars >= 4, (card.stars, [(c.name, c.score) for c in card.components])
    assert card.verdict == "The filings look strong"
    assert card.tone == "good"
    # Every component explains itself in a sentence a reader can check.
    for c in card.components:
        assert c.why and len(c.why) > 25, c
        assert c.tone in ("good", "mid", "bad")

    weak = extract_equity(make_scorable(False, False, False, False))
    wv = value(weak, price=weak.latest.get("eps") * 40)
    wcard = score(weak, wv, pe_history=[18.0] * 10)
    assert wcard.stars <= 1.5, (wcard.stars, [(c.name, c.score) for c in wcard.components])
    assert wcard.verdict == "The filings look weak"

    # No price: four components still score, the fifth is reported as skipped.
    npc = score(strong, value(strong, price=None))
    assert len(npc.components) == 4
    assert any("no share price" in u for u in npc.unscored), npc.unscored
    assert npc.stars > 0

    # A loss-making filer must not be given a growth rate.
    loss = extract_equity(build("LOSSY CO", {
        "Revenues": {"units": {"USD": [dur(f"{2017+i}-01-01", f"{2017+i}-12-31", 5_000) for i in range(6)]}},
        "NetIncomeLoss": {"units": {"USD": [dur(f"{2017+i}-01-01", f"{2017+i}-12-31", 200 - 90 * i) for i in range(6)]}},
        "EarningsPerShareDiluted": {"units": {"USD/shares":
            [dur(f"{2017+i}-01-01", f"{2017+i}-12-31", round(1.0 - 0.45 * i, 2)) for i in range(6)]}},
    }))
    lcard = score(loss, value(loss, price=12.0))
    assert any("loss and profit" in u for u in lcard.unscored), lcard.unscored
    assert not any(c.name == "Long-run growth" for c in lcard.components)

    # Stars stay on the half-point grid and inside the range.
    for card_ in (card, wcard, npc, lcard):
        assert 0 <= card_.stars <= 5 and (card_.stars * 2) % 1 == 0, card_.stars
    print("scorecard ok")
