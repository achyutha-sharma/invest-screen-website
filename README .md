# Value Screen

Research a US-listed stock from what the company told the SEC.

**Live:** _(add your Streamlit URL here)_

## What it does

Every figure comes from a filing. Share price is the one exception and comes
from a market feed; without it the valuation rows say so and everything else
still works.

- **Three-year trend** — revenue, net income, EPS, margin, free cash flow and
  debt side by side, coloured by the direction you would rather see. For debt
  that means falling.
- **Quarterly progress** — each quarter against the same quarter a year
  earlier, which is the only honest comparison for a seasonal business.
- **Management's own words** — sentences from the MD&A that explain a movement,
  quoted verbatim rather than summarised.
- **Risk factors** — the company's own list, from Item 1A.
- **A scorecard out of five** — five things the filings can answer, each shown
  with the figure behind it.
- **Teach me** — four slides and a quiz built from the company's own numbers.

## What it refuses to do

- **No recommendations.** The scorecard rates the evidence already filed, not
  the future, and says so.
- **No invented explanations.** It shows what management said caused a result,
  never a guess at why a share price moved on a given day.
- **No meaningless ratios.** Funds have no revenue or margin, so they get an
  explanation page instead. A loss-making company gets no P/E rather than a
  negative one.

## Running it

```bash
pip install -r requirements.txt
export SEC_USER_AGENT="Your Name your@email.com"   # the SEC requires this
export FINNHUB_API_KEY="optional"                  # prices; omit and they hide
streamlit run app.py
```

On Streamlit Cloud both go in the app's secrets instead.

## Tests

```bash
python test_equity.py
```

Eleven groups, no network needed. They cover the awkward cases: filers that
switch XBRL tags between years, untagged figures rebuilt from other lines,
basic EPS standing in for diluted, quarters with no year-ago comparison, and a
price feed that is down.

## Files

| | |
|---|---|
| `app.py` | the Streamlit interface |
| `sec_equity.py` | per-share figures, quarters, ten-year history |
| `sec_ratios.py` | SEC fetching and XBRL tag resolution |
| `scorecard.py` | the five scored components |
| `filing_text.py` | MD&A and risk factors from filing HTML |
| `quiz.py` | questions generated per company |
| `funds.py` | explanations for index funds and gold |
| `prices.py` | the only non-SEC source |

## Not investment advice

Educational research only.
