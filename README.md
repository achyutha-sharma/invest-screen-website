# Invest Screen

Research a US-listed stock using what the company told the SEC.

**Live:** (https://invest-screen-website.onrender.com/) or (https://invest-screen.streamlit.app/)

## What it shows

Every figure comes from a filing. Share price is the one exception and comes
from a market feed — without it those rows say so, and everything else works.

- Revenue, profit, EPS, margin, cash flow and debt over three years, coloured
  by the direction you would rather see
- Each quarter against the same quarter a year earlier
- What management said caused the results, quoted from the filing
- The company's own risk factors
- A score out of five, with the figure behind each part
- **Teach me** — four slides and a quiz built from the company's numbers

## What it will not do

- Recommend anything. The score rates what has been filed, not the future.
- Guess why a share price moved.
- Print a ratio that does not apply. A loss-making company gets no P/E, and
  funds get an explanation page rather than empty numbers.

## Running it

```bash
pip install -r requirements.txt
export SEC_USER_AGENT="Your Name your@email.com"   # required by the SEC
export FINNHUB_API_KEY="optional"                  # prices; omit and they hide
streamlit run app.py
```

On Streamlit Cloud both go in the app's secrets.

## Tests

```bash
python test_equity.py
```

Eleven groups, no network needed. They cover the awkward cases: filers that
change XBRL tags between years, figures rebuilt from other lines, quarters with
no year-ago comparison, and a price feed that is down.

## Files

| | |
|---|---|
| `app.py` | the interface |
| `sec_equity.py` | per-share figures, quarters, history |
| `sec_ratios.py` | SEC fetching and XBRL tag resolution |
| `scorecard.py` | the five scored parts |
| `filing_text.py` | management's discussion and risk factors |
| `quiz.py` | questions built per company |
| `funds.py` | index fund and gold explanations |
| `prices.py` | the only non-SEC source |

Educational only. Not investment advice.
