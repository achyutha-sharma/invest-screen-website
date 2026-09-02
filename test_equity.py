"""
Offline checks for the equity layer. No network needed.

Run:  python3 test_equity.py
"""

import os
import re

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


# ---------------------------------------------------------------------------
# Prices: the one source outside SEC. Must never raise.
# ---------------------------------------------------------------------------
def test_prices():
    """The only sources outside SEC. Both must degrade, never raise."""
    import pathlib, tempfile
    from prices import PriceClient, Quote

    tmp = pathlib.Path(tempfile.mkdtemp())

    # Nothing configured: empty results with a reason, no exception.
    nokey = PriceClient(api_key="", history_key="", cache_dir=tmp)
    assert not nokey.configured and not nokey.has_history
    q = nokey.quote("NKE")
    assert not q.available and "No price feed" in q.problem
    assert nokey.monthly("NKE") == []
    assert nokey.at_fiscal_ends("NKE", [("FY2026", "2026-05-31")]) == {}

    # Quotes configured but history not -- the charts hide, prices still work.
    class QuoteOnly(PriceClient):
        def _get(self, url, params):
            return {"c": 62.0, "d": -1.34, "dp": -2.12, "pc": 63.34, "t": 1786000000}, ""

    qo = QuoteOnly(api_key="x", history_key="",
                   cache_dir=pathlib.Path(tempfile.mkdtemp()))
    assert qo.quote("NKE").available
    assert qo.monthly("NKE") == [], "history must stay empty without its own key"

    # Network down on quotes.
    class Offline(PriceClient):
        def _get(self, url, params):
            return None, "The price feed could not be reached."

    off = Offline(api_key="x", cache_dir=pathlib.Path(tempfile.mkdtemp()))
    assert not off.quote("NKE").available

    # A well-formed Finnhub quote.
    class Fake(PriceClient):
        def _get(self, url, params):
            return {"c": 62.0, "d": -1.34, "dp": -2.12, "pc": 63.34, "t": 1786000000}, ""

    f = Fake(api_key="x", cache_dir=pathlib.Path(tempfile.mkdtemp()))
    fq = f.quote("NKE")
    assert fq.available and fq.price == 62.0 and fq.prev_close == 63.34
    assert round(fq.day_change_pct, 2) == -2.12
    assert fq.source == "Finnhub" and fq.as_of

    # An unknown symbol comes back as zero, not an exception.
    class Zero(PriceClient):
        def _get(self, url, params):
            return {"c": 0, "d": None, "dp": None, "pc": 0, "t": 0}, ""

    zq = Zero(api_key="x", cache_dir=pathlib.Path(tempfile.mkdtemp())).quote("ZZZZ")
    assert not zq.available and "No price found" in zq.problem

    # Rate limiting is reported plainly rather than swallowed.
    class Limited(PriceClient):
        def _get(self, url, params):
            return None, "The price feed is rate limited; try again shortly."

    assert "rate limited" in Limited(api_key="x", cache_dir=tmp).quote("NKE").problem

    # A quote with no move reported stays None rather than defaulting to zero,
    # so the page can hide the badge instead of claiming the price was flat.
    assert Quote(price=62.0).day_change_pct is None
    assert Quote(price=62.0, prev_close=64.0, day_change_pct=-3.12).day_change_pct == -3.12
    assert not Quote(price=0).available
    assert not Quote().available
    print("prices ok")


def test_history():
    """Tiingo history, and the fiscal-year matching built on it."""
    import pathlib, tempfile
    from prices import PriceClient

    rows = [
        {"date": "2025-05-30T00:00:00.000Z", "close": 70.0, "adjClose": 70.50},
        {"date": "2026-05-29T00:00:00.000Z", "close": 63.0, "adjClose": 63.40},
        {"date": "2026-07-31T00:00:00.000Z", "close": 62.0, "adjClose": 62.40},
    ]

    class FakeHist(PriceClient):
        def monthly(self, ticker, years=11):
            # adjClose is preferred, so a split does not look like a halving.
            return sorted((str(r["date"])[:10], float(r["adjClose"])) for r in rows)

    h = FakeHist(api_key="x", history_key="t",
                 cache_dir=pathlib.Path(tempfile.mkdtemp()))
    hist = h.monthly("NKE")
    assert len(hist) == 3 and hist[0] == ("2025-05-30", 70.50)
    assert hist == sorted(hist), "history must be oldest first"

    # Within 45 days matches; a year with no nearby price is dropped rather
    # than borrowing one from months away.
    got = h.at_fiscal_ends("NKE", [("FY2026", "2026-05-31"), ("FY2015", "2015-05-31")])
    assert got == {"FY2026": 63.40}, got

    # No history configured at all.
    bare = PriceClient(api_key="x", history_key="",
                       cache_dir=pathlib.Path(tempfile.mkdtemp()))
    assert bare.monthly("NKE") == []
    assert bare.at_fiscal_ends("NKE", [("FY2026", "2026-05-31")]) == {}
    print("history ok")


FAKE_10K = """
<html><body>
<table><tr><td>Item 1. Business</td><td>3</td></tr>
<tr><td>Item 1A. Risk Factors</td><td>12</td></tr>
<tr><td>Item 7. Management's Discussion and Analysis</td><td>28</td></tr></table>

<p>Item 1. Business</p>
<p>We design and sell athletic footwear and apparel worldwide through our own
stores, digital platforms and wholesale partners.</p>
<p>Competition</p>
<p>The athletic footwear industry is highly competitive. We compete with
Adidas AG, Under Armour Inc. and Skechers USA Inc. on product design, price and
brand strength, as well as with a range of smaller regional brands.</p>

<p>Item 1A. Risk Factors</p>
<p>Our business is affected by consumer discretionary spending</p>
<p>A decline in consumer confidence may reduce demand for our products and
adversely affect results of operations in any period.</p>
<p>Excess inventory could require additional markdowns</p>
<p>If we misjudge demand we may hold inventory that can only be sold at a
discount, which would reduce gross margin.</p>
<p>We depend on a limited number of manufacturing partners</p>
<p>Item 1B. Unresolved Staff Comments</p>
<p>None.</p>

<p>Item 7. Management's Discussion and Analysis of Financial Condition</p>
<p>Revenue decreased 4% in the period, primarily due to lower unit sales in
Greater China and higher promotional activity across our wholesale channel.</p>
<p>Gross margin declined 290 basis points, driven primarily by increased
markdowns on excess inventory and unfavourable foreign currency movements.</p>
<p>These decreases were partially offset by growth in our direct-to-consumer
channel, which increased 6% over the prior year.</p>
<p>The following discussion should be read together with the consolidated
financial statements and the related notes appearing elsewhere in this report,
and contains forward-looking statements that involve risks and uncertainties.
Our fiscal year ends on May 31 of each year. References to fiscal years are to
the twelve months ended on that date. Amounts are presented in millions except
per share data, unless otherwise indicated. Percentage changes have been
calculated using unrounded figures and may not recompute from the rounded
amounts shown in the accompanying tables and discussion below.</p>
<p>See Note 14 for further detail on segment results.</p>
<p>Item 7A. Quantitative and Qualitative Disclosures About Market Risk</p>
<p>We are exposed to interest rate risk.</p>
</body></html>
"""


def test_filing_text():
    from filing_text import extract_competitors, extract_mda, extract_risks, to_text

    text = to_text(FAKE_10K)
    assert "Item 7" in text and "<p>" not in text

    mda, why = extract_mda(text)
    assert not why and len(mda) >= 2, (why, mda)
    assert any("Greater China" in s for s in mda), mda
    assert any("partially offset" in s for s in mda), mda
    # A cross-reference is not an explanation and must be dropped.
    assert not any(s.startswith("See Note") for s in mda), mda
    # Everything is verbatim: each sentence appears in the source.
    flat = " ".join(text.split())
    for s in mda:
        assert s in flat, s

    risks, why = extract_risks(text)
    assert not why and len(risks) >= 2, (why, risks)
    assert any("discretionary spending" in r for r in risks), risks
    # Headings only -- the explanatory paragraphs end in a full stop.
    for r in risks:
        assert not r.endswith("."), r

    peers, note, why = extract_competitors(text)
    assert not why, why
    assert "Adidas AG" in peers and "Under Armour Inc" in peers, peers
    assert not any(p.lower().startswith("the ") for p in peers), peers
    assert "competitive" in note.lower(), note

    # A filing with none of these sections must say so, not guess.
    empty = to_text("<html><body><p>" + "Nothing useful here. " * 200 + "</p></body></html>")
    m, w1 = extract_mda(empty)
    r, w2 = extract_risks(empty)
    c, note2, w3 = extract_competitors(empty)
    assert m == [] and r == [] and c == []
    assert all(w and "could not be located" in w or "does not" in w for w in (w1, w2, w3))
    print("filing text ok")




def test_risk_junk_rejected():
    """Financial-statement rows must never be mistaken for risk headings.

    A real filing put Item 7A tables through the earlier version of this
    parser and got back balance-sheet rows, so each of those shapes is now a
    test case.
    """
    from filing_text import extract_risks, to_text

    junk = to_text("<html><body><p>Item 1A. Risk Factors</p>" + "".join(
        f"<p>{row}</p>" for row in [
            "MAY 31, 2026 MAY 31, 2025",
            "Balance at May 31, 2023 305 $ — 1,227 $ 3 $ 12,412 $ 231 $ 1,358 $ 14,004",
            "EXPECTED MATURITY DATE YEAR ENDING MAY 31",
            "ITEM 7A. QUANTITATIVE AND QUALITATIVE DISCLOSURES ABOUT MARKET RISK",
            "Our material cash requirements as of May 31, 2026, were as follows",
            "Table of Contents",
            "12,412",
        ]) + "<p>A shift in consumer preferences could reduce demand for our products</p>"
        + "<p>We rely on a small number of contract manufacturers</p>"
        + "<p>Item 1B. Unresolved Staff Comments</p>" + "x" * 500 + "</body></html>")

    risks, why = extract_risks(junk)
    for r in risks:
        assert "MAY 31" not in r.upper(), r
        assert "BALANCE AT" not in r.upper(), r
        assert "MATURITY" not in r.upper(), r
        assert not r.upper().startswith("ITEM"), r
        assert sum(c.isdigit() for c in r) <= 3, r
        assert r != r.upper(), r
    assert any("consumer preferences" in r for r in risks), risks
    assert any("contract manufacturers" in r for r in risks), risks
    print("risk junk rejected ok")




def test_span_picks_real_section():
    """Item headings appear three times: contents, section, cross-reference.

    A real filing has all three, and only the middle one is the section. Taking
    the first gives a contents line; taking the last gives whatever tables
    follow a note. The parser must pick the properly-closed span between them.
    """
    from filing_text import _item_span, extract_risks, to_text

    doc = to_text(
        "<html><body>"
        # 1. table of contents
        "<p>Item 1A. Risk Factors .......... 12</p>"
        "<p>Item 1B. Unresolved Staff Comments .......... 20</p>"
        # 2. the real section
        "<p>Item 1A. Risk Factors</p>"
        "<p>A shift in consumer preferences could reduce demand for our products</p>"
        "<p>Weather patterns may affect store traffic in any given quarter</p>"
        + "<p>Explanatory text. </p>" * 60 +
        "<p>Item 1B. Unresolved Staff Comments</p><p>None.</p>"
        "<p>Item 8. Financial Statements</p>"
        # 3. a cross-reference deep in the notes, followed by tables
        + "<p>See Item 1A. Risk Factors for further discussion.</p>"
        + "".join(f"<p>Balance at May 31, 202{i} 1,2{i}4 $ 3,4{i}5</p>" for i in range(5)) * 40
        + "</body></html>")

    span = _item_span(doc, r"item\s*1a[\.\s]{0,4}risk\s*factors",
                      r"item\s*1b[\.\s]{0,4}unresolved|item\s*2[\.\s]{0,4}propert")
    assert span is not None
    assert "consumer preferences" in span, span[:120]
    assert "Balance at May 31" not in span, "picked the cross-reference, not the section"

    risks, why = extract_risks(doc)
    assert not why, why
    assert any("consumer preferences" in r for r in risks), risks
    assert any("Weather patterns" in r for r in risks), risks
    assert not any("Balance at" in r for r in risks), risks
    print("span selection ok")




def test_quarter_year_ago():
    """Quarters must compare against the same quarter a year earlier.

    A seasonal business read Q3-against-Q2 looks like it collapsed every
    autumn. Only the equivalent period is meaningful.
    """
    def q(y, qn, rev, eps):
        starts = {1: f"{y}-01-01", 2: f"{y}-04-01", 3: f"{y}-07-01", 4: f"{y}-10-01"}
        ends = {1: f"{y}-03-31", 2: f"{y}-06-30", 3: f"{y}-09-30", 4: f"{y}-12-31"}
        return (dur(starts[qn], ends[qn], rev, form="10-Q", filed=f"{y}-12-01"),
                dur(starts[qn], ends[qn], eps, form="10-Q", filed=f"{y}-12-01"))

    revs, epss = [dur("2025-01-01", "2025-12-31", 16_000)], [dur("2025-01-01", "2025-12-31", 3.20)]
    # last year's quarters, then this year's -- this year up on each
    for qn, (r, e) in enumerate([(3_800, 0.72), (3_900, 0.75), (4_000, 0.78), (4_300, 0.95)], 1):
        a, b = q(2025, qn, r, e)
        revs.append(a); epss.append(b)
    for qn, (r, e) in enumerate([(4_100, 0.80), (4_300, 0.86), (4_500, 0.90)], 1):
        a, b = q(2026, qn, r, e)
        revs.append(a); epss.append(b)

    eq = extract_equity(build("SEASONAL CO", {
        "Revenues": {"units": {"USD": revs}},
        "EarningsPerShareDiluted": {"units": {"USD/shares": epss}},
        "NetIncomeLoss": {"units": {"USD": [dur("2025-01-01", "2025-12-31", 1_600)]}},
    }))

    assert len(eq.quarters) == 3, [p.label for p in eq.quarters]
    q1 = eq.quarters[0]
    assert q1.get("revenue") == 4_100
    assert q1.year_ago.get("revenue") == 3_800, q1.year_ago
    assert round(q1.change("revenue"), 1) == 7.9, q1.change("revenue")
    assert q1.change("eps") is not None and q1.change("eps") > 0

    q3 = eq.quarters[2]
    assert q3.year_ago.get("revenue") == 4_000
    assert round(q3.change("revenue"), 1) == 12.5

    # No prior-year figure means no change, rather than a made-up one.
    bare = extract_equity(build("NEW CO", {
        "Revenues": {"units": {"USD": [
            dur("2025-01-01", "2025-12-31", 900),
            dur("2026-01-01", "2026-03-31", 300, form="10-Q", filed="2026-05-01")]}},
        "NetIncomeLoss": {"units": {"USD": [dur("2025-01-01", "2025-12-31", 90)]}},
    }))
    assert bare.quarters[0].change("revenue") is None
    print("quarter year-ago ok")




def test_mda_dedupes_segments():
    """Segment discussions repeat one sentence per region.

    Apple's filing says the same thing about Europe, Japan and Asia Pacific,
    changing only the place name. Quoting all of them fills the panel with one
    idea; the parser must keep one and move on to a different explanation.
    """
    from filing_text import extract_mda, to_text

    html = ("<html><body><p>Item 7. Management's Discussion and Analysis</p>"
            "<p>Total net sales increased 6% during 2025, primarily due to higher "
            "net sales of Services.</p>"
            "<table><tr><td>Europe</td></tr></table>"
            "<p>Europe net sales increased during 2025 compared to 2024 primarily "
            "due to higher net sales of Services, iPhone and Mac.</p>"
            "<table><tr><td>Japan</td></tr></table>"
            "<p>Japan net sales increased during 2025 compared to 2024 primarily "
            "due to higher net sales of iPhone, Services and iPad.</p>"
            "<table><tr><td>Rest of Asia Pacific</td></tr></table>"
            "<p>Rest of Asia Pacific net sales increased during 2025 compared to "
            "2024 primarily due to higher net sales of iPhone and Mac.</p>"
            "<p>Gross margin percentage increased during 2025 primarily due to a "
            "favourable shift in mix towards Services.</p>"
            + "<p>filler sentence for length. </p>" * 60
            + "<p>Item 7A. Quantitative and Qualitative Disclosures</p></body></html>")

    quotes, why = extract_mda(to_text(html))
    assert not why, why

    # The doubled label from the table cell must be gone.
    for q in quotes:
        assert not re.match(r"^(\w[\w ]*?) \1\b", q), q
        assert "Europe Europe" not in q and "Japan Japan" not in q

    # Only one of the three near-identical segment sentences survives.
    segmenty = [q for q in quotes if "net sales increased during 2025 compared" in q]
    assert len(segmenty) <= 1, segmenty

    # And the space it frees is used on a different explanation.
    assert any("Gross margin" in q for q in quotes), quotes
    print("mda segment dedupe ok")




def test_expectations():
    """The split between earned profit and expected profit."""
    from expectations import build, expectations, operating_leverage

    # A high price on modest earnings is mostly expectation.
    e = expectations(62.00, 2.16)
    assert e is not None
    assert round(e.justified) == 22 and round(e.expectation) == 40
    assert 60 < e.pct < 70 and e.heavy and not e.light

    # A low price on strong earnings is almost entirely earned.
    cheap = expectations(40.00, 6.00)
    assert cheap.pct == 0 and cheap.light

    # The justified figure can never exceed the price, or expectation goes
    # negative and the split stops meaning anything.
    assert expectations(15.00, 6.00).expectation == 0

    # A loss-maker has no "justified by earnings" figure at all.
    assert expectations(30.0, -1.2) is None
    assert expectations(30.0, 0) is None
    assert expectations(None, 2.0) is None
    assert expectations(30.0, None) is None

    # Operating leverage: profit swinging harder than sales.
    rev = [100, 110, 121, 133]
    ebit = [10, 13, 17, 22]                       # profit growing faster
    lev = operating_leverage(rev, ebit)
    assert lev is not None and lev > 1.5, lev

    # Flat years carry no information and must not divide by ~zero.
    assert operating_leverage([100, 100, 100], [10, 10, 10]) is None
    assert operating_leverage([], []) is None
    # A year that starts from a loss cannot give a meaningful percentage.
    assert operating_leverage([100, 110], [-5, 10]) is None

    rows = build(62.00, 2.16, rev, ebit, debt=9_300, cash=9_900,
                 shares=1_480, foreign_pct=57)
    names = [r.name for r in rows]
    assert "Price resting on expectations" in names
    assert "Sales earned abroad" in names
    # More cash than debt, so no debt-per-share row.
    assert "Debt behind each share" not in names
    for r in rows:
        assert r.what and r.why and len(r.why) > 30
    print("expectations ok")


def test_risk_diff():
    """Risk factor comparison must ignore rewording, not real change."""
    from filing_text import _norm_risk

    same = [
        ("Our business may be adversely affected by consumer discretionary spending",
         "Our business could be materially affected by consumer discretionary spending"),
        ("Excess inventory could require additional markdowns",
         "Excess inventory may require additional markdowns"),
    ]
    for a, b in same:
        assert _norm_risk(a) == _norm_risk(b), (a, b)

    different = [
        ("Excess inventory could require additional markdowns",
         "Increased spending on artificial intelligence infrastructure"),
        ("We depend on a limited number of manufacturing partners",
         "We face competition from established and emerging brands"),
    ]
    for a, b in different:
        assert _norm_risk(a) != _norm_risk(b), (a, b)

    # The key must not be empty for a real heading, or everything collapses
    # into one bucket and every risk looks unchanged.
    assert len(_norm_risk("Cybersecurity and data protection risks")) > 10
    print("risk diff ok")




def test_cache_expiry():
    """A cached filing index must not outlive the next filing.

    This was a real bug: company facts were cached on disk with no expiry, so
    a company that filed its second-quarter report kept showing only the
    first quarter until the cache file was deleted by hand.
    """
    import json as _json
    import pathlib, tempfile, time
    from sec_ratios import SecClient

    tmp = pathlib.Path(tempfile.mkdtemp())
    calls = {"n": 0}

    class Counting(SecClient):
        """Counts fetches so we can tell a cache hit from a refetch."""
        def __init__(self, **kw):
            super().__init__(**kw)

        def _fetch(self, url):
            calls["n"] += 1
            return {"fetched": calls["n"]}

    c = Counting(user_agent="t t@e.com", cache_dir=tmp)

    # Seed a cache file and backdate it well past the limit.
    f = tmp / "facts_0000000001.json"
    f.write_text(_json.dumps({"fetched": 0}))
    old = time.time() - (SecClient.FACTS_MAX_AGE + 60)
    os.utime(f, (old, old))

    # A fresh file inside the window is served from disk.
    fresh = tmp / "fresh.json"
    fresh.write_text(_json.dumps({"ok": True}))
    assert c._get_json("http://unused", "fresh.json",
                       max_age=SecClient.FACTS_MAX_AGE) == {"ok": True}

    # No max_age means the cache never expires -- correct for the ticker list,
    # which barely changes, and wrong for anything filing-dependent.
    assert c._get_json("http://unused", "facts_0000000001.json") == {"fetched": 0}

    assert SecClient.FACTS_MAX_AGE <= 24 * 60 * 60, \
        "facts must not be cached for more than a day"
    print("cache expiry ok")




def test_quarters_across_tags():
    """Quarters must be found even when a filer changes revenue tag mid-year.

    This was a real bug: the search stopped at the first revenue tag that
    matched anything, so a company that filed Q1 under one tag and Q2 under
    another showed only Q1 -- and the run-rate was built from a single
    quarter as though the others had not been filed.
    """
    def q(y, qn, val, tag_rows, form="10-Q"):
        starts = {1: f"{y}-01-01", 2: f"{y}-04-01", 3: f"{y}-07-01", 4: f"{y}-10-01"}
        ends = {1: f"{y}-03-31", 2: f"{y}-06-30", 3: f"{y}-09-30", 4: f"{y}-12-31"}
        tag_rows.append(dur(starts[qn], ends[qn], val, form=form, filed=f"{y}-12-01"))

    old_tag, new_tag = [], []
    # Prior year, for the year-ago comparison.
    for qn, v in enumerate([3_800, 3_900, 4_000, 4_300], 1):
        q(2025, qn, v, old_tag)
    # This year: Q1 under the old tag, Q2 and Q3 under a different one.
    q(2026, 1, 4_100, old_tag)
    q(2026, 2, 4_300, new_tag)
    q(2026, 3, 4_500, new_tag)

    eq = extract_equity(build("TAG SWITCHER", {
        "Revenues": {"units": {"USD": old_tag
                               + [dur("2025-01-01", "2025-12-31", 16_000)]}},
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": new_tag}},
        "NetIncomeLoss": {"units": {"USD": [dur("2025-01-01", "2025-12-31", 1_600)]}},
    }))

    labels = [p.fp for p in eq.quarters]
    assert labels == ["Q1", "Q2", "Q3"], labels
    assert [p.get("revenue") for p in eq.quarters] == [4_100, 4_300, 4_500]

    # The run-rate must use every filed quarter, not just the first tag's.
    ytd = sum(p.get("revenue") for p in eq.quarters)
    assert ytd == 12_900, ytd

    # And each quarter compares against its own equivalent a year earlier.
    assert eq.quarters[0].year_ago.get("revenue") == 3_800
    assert eq.quarters[2].year_ago.get("revenue") == 4_000


def test_quarter_numbering():
    """A missing first quarter must not renumber the ones that follow."""
    rows = [dur("2025-01-01", "2025-12-31", 16_000)]
    # Only Q2 and Q3 filed -- Q1 absent from the data entirely.
    rows.append(dur("2026-04-01", "2026-06-30", 4_300, form="10-Q", filed="2026-08-01"))
    rows.append(dur("2026-07-01", "2026-09-30", 4_500, form="10-Q", filed="2026-11-01"))
    # Their year-ago equivalents.
    rows.append(dur("2025-04-01", "2025-06-30", 3_900, form="10-Q", filed="2025-08-01"))
    rows.append(dur("2025-07-01", "2025-09-30", 4_000, form="10-Q", filed="2025-11-01"))

    eq = extract_equity(build("GAPPY CO", {
        "Revenues": {"units": {"USD": rows}},
        "NetIncomeLoss": {"units": {"USD": [dur("2025-01-01", "2025-12-31", 1_600)]}},
    }))

    labels = [p.fp for p in eq.quarters]
    assert labels == ["Q2", "Q3"], labels
    # Q2 must compare against last year's Q2, not last year's Q1.
    assert eq.quarters[0].year_ago.get("revenue") == 3_900, eq.quarters[0].year_ago
    print("quarter tags and numbering ok")




def test_quarters_from_ytd():
    """Quarters must be derived when a filer tags only year-to-date totals.

    This was the bug behind "1 of 4 quarters filed" for companies that had
    plainly filed more: the second quarter arrives as a 181-day cumulative
    span and the third as 273, so a filter looking for three-month periods
    found only the first quarter and reported the rest as not yet filed.
    """
    rows = [dur("2025-01-01", "2025-12-31", 16_000)]
    # Q1 tagged as a quarter; Q2 and Q3 only as running totals.
    rows.append(dur("2026-01-01", "2026-03-31", 4_100, form="10-Q", filed="2026-05-01"))
    rows.append(dur("2026-01-01", "2026-06-30", 8_400, form="10-Q", filed="2026-08-01"))
    rows.append(dur("2026-01-01", "2026-09-30", 12_900, form="10-Q", filed="2026-11-01"))

    eq = extract_equity(build("YTD ONLY", {
        "Revenues": {"units": {"USD": rows}},
        "NetIncomeLoss": {"units": {"USD": [dur("2025-01-01", "2025-12-31", 1_600)]}},
    }))

    assert [p.fp for p in eq.quarters] == ["Q1", "Q2", "Q3"], [p.fp for p in eq.quarters]
    got = [p.get("revenue") for p in eq.quarters]
    # 8,400 - 4,100 = 4,300 and 12,900 - 8,400 = 4,500.
    assert got == [4_100, 4_300, 4_500], got

    # A direct quarterly tag must win over anything derived.
    rows2 = list(rows)
    rows2.append(dur("2026-04-01", "2026-06-30", 4_275, form="10-Q", filed="2026-08-02"))
    eq2 = extract_equity(build("BOTH TAGGED", {
        "Revenues": {"units": {"USD": rows2}},
        "NetIncomeLoss": {"units": {"USD": [dur("2025-01-01", "2025-12-31", 1_600)]}},
    }))
    assert eq2.quarters[1].get("revenue") == 4_275, "a filed quarter beats a derived one"

    # A negative derivation is nonsense and must be dropped, not shown.
    rows3 = [dur("2025-01-01", "2025-12-31", 16_000),
             dur("2026-01-01", "2026-03-31", 5_000, form="10-Q", filed="2026-05-01"),
             dur("2026-01-01", "2026-06-30", 4_000, form="10-Q", filed="2026-08-01")]
    eq3 = extract_equity(build("SHRINKING", {
        "Revenues": {"units": {"USD": rows3}},
        "NetIncomeLoss": {"units": {"USD": [dur("2025-01-01", "2025-12-31", 1_600)]}},
    }))
    assert [p.fp for p in eq3.quarters] == ["Q1"], [p.fp for p in eq3.quarters]
    print("ytd quarters ok")




def test_never_more_than_four_quarters():
    """A fiscal year has four quarters, whatever the filing data looks like.

    Two things produced more: a full-year period being mistaken for a
    year-to-date total and differenced into an extra quarter, and an annual
    report old enough that two years of quarters fell after it.
    """
    rows = [
        dur("2025-01-01", "2025-12-31", 16_000),                 # the annual figure
        dur("2026-01-01", "2026-03-31", 4_100, form="10-Q", filed="2026-05-01"),
        dur("2026-01-01", "2026-06-30", 8_400, form="10-Q", filed="2026-08-01"),
        dur("2026-01-01", "2026-09-30", 12_900, form="10-Q", filed="2026-11-01"),
        # A full year tagged in a 10-K. This must not be read as cumulative.
        dur("2026-01-01", "2026-12-31", 17_500, form="10-K", filed="2027-02-01"),
    ]
    eq = extract_equity(build("FULL YEAR TRAP", {
        "Revenues": {"units": {"USD": rows}},
        "NetIncomeLoss": {"units": {"USD": [dur("2025-01-01", "2025-12-31", 1_600)]}},
    }))
    labels = [p.fp for p in eq.quarters]
    assert len(labels) <= 4, labels
    assert len(set(labels)) == len(labels), f"duplicate quarters: {labels}"
    for l in labels:
        assert l in {"Q1", "Q2", "Q3", "Q4"}, l

    # Two years of quarterly data after a stale annual report.
    many = [dur("2024-01-01", "2024-12-31", 15_000)]
    for y, vals in ((2025, [3_800, 3_900, 4_000, 4_300]),
                    (2026, [4_100, 4_300, 4_500, 4_800])):
        st_ = {1: f"{y}-01-01", 2: f"{y}-04-01", 3: f"{y}-07-01", 4: f"{y}-10-01"}
        en = {1: f"{y}-03-31", 2: f"{y}-06-30", 3: f"{y}-09-30", 4: f"{y}-12-31"}
        for i, v in enumerate(vals, 1):
            many.append(dur(st_[i], en[i], v, form="10-Q", filed=f"{y}-12-01"))

    eq2 = extract_equity(build("STALE ANNUAL", {
        "Revenues": {"units": {"USD": many}},
        "NetIncomeLoss": {"units": {"USD": [dur("2024-01-01", "2024-12-31", 1_500)]}},
    }))
    labels2 = [p.fp for p in eq2.quarters]
    assert len(labels2) <= 4, labels2
    assert len(set(labels2)) == len(labels2), f"duplicate quarters: {labels2}"
    # The four kept must be the most recent ones.
    assert eq2.quarters[-1].get("revenue") == 4_800, eq2.quarters[-1].get("revenue")
    print("quarter count bounded ok")


def main():
    test_clean()
    test_valuation()
    test_derivation()
    test_quarters()
    test_guards()
    test_scorecard()
    test_prices()
    test_history()
    test_filing_text()
    test_risk_junk_rejected()
    test_span_picks_real_section()
    test_quarter_year_ago()
    test_mda_dedupes_segments()
    test_cache_expiry()
    test_quarters_across_tags()
    test_quarter_numbering()
    test_quarters_from_ytd()
    test_never_more_than_four_quarters()
    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
