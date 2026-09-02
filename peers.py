"""
Who to compare a company against.

Deciding who counts as a peer is a judgement, and the SEC does not publish a
"companies like this one" endpoint. Two sources are used, in order:

  1. The SEC's own industry classification. Every filer carries a SIC code, so
     two companies sharing one are in the same line of business by the
     government's own reckoning.
  2. A small hand-checked map for the largest and most-searched companies,
     because SIC codes are coarse -- Netflix and a cable operator share one,
     and nobody would call them peers.

Where neither applies the caller is told plainly, and the reader can type
tickers instead. A wrong peer set is worse than none: it makes a company look
cheap or expensive against businesses it has nothing in common with.
"""

from __future__ import annotations

# Hand-checked peer sets, keyed by ticker. Kept deliberately short: these are
# the comparisons a person would actually make, not everything in the sector.
CURATED: dict[str, list[str]] = {
    # Retail
    "HD": ["LOW", "TGT", "WMT"],
    "LOW": ["HD", "TGT", "WMT"],
    "TGT": ["WMT", "COST", "HD"],
    "WMT": ["TGT", "COST", "KR"],
    "COST": ["WMT", "TGT", "KR"],
    "KR": ["ACI", "WMT", "COST"],
    "ACI": ["KR", "WMT", "COST"],
    # Apparel and footwear
    "NKE": ["LULU", "SKX", "UAA"],
    "LULU": ["NKE", "UAA", "SKX"],
    "SKX": ["NKE", "UAA", "LULU"],
    "UAA": ["NKE", "SKX", "LULU"],
    # Restaurants
    "SBUX": ["MCD", "CMG", "YUM"],
    "MCD": ["SBUX", "YUM", "CMG"],
    "CMG": ["MCD", "SBUX", "YUM"],
    "YUM": ["MCD", "CMG", "SBUX"],
    # Media and streaming
    "NFLX": ["DIS", "WBD", "PARA"],
    "DIS": ["NFLX", "WBD", "PARA"],
    # Technology
    "AAPL": ["MSFT", "GOOGL", "DELL"],
    "MSFT": ["AAPL", "GOOGL", "ORCL"],
    "GOOGL": ["MSFT", "META", "AMZN"],
    "META": ["GOOGL", "SNAP", "PINS"],
    "AMZN": ["WMT", "GOOGL", "EBAY"],
    "ORCL": ["MSFT", "CRM", "SAP"],
    "CRM": ["ORCL", "MSFT", "NOW"],
    "NVDA": ["AMD", "INTC", "AVGO"],
    "AMD": ["NVDA", "INTC", "AVGO"],
    "INTC": ["AMD", "NVDA", "TXN"],
    # Banks
    "JPM": ["BAC", "C", "WFC"],
    "BAC": ["JPM", "C", "WFC"],
    "WFC": ["JPM", "BAC", "C"],
    "C": ["JPM", "BAC", "WFC"],
    "GS": ["MS", "JPM", "SCHW"],
    "MS": ["GS", "JPM", "SCHW"],
    # Payments
    "V": ["MA", "AXP", "PYPL"],
    "MA": ["V", "AXP", "PYPL"],
    "PYPL": ["V", "MA", "SQ"],
    # Airlines
    "DAL": ["UAL", "AAL", "LUV"],
    "UAL": ["DAL", "AAL", "LUV"],
    "AAL": ["DAL", "UAL", "LUV"],
    "LUV": ["DAL", "UAL", "AAL"],
    # Autos
    "F": ["GM", "TSLA", "STLA"],
    "GM": ["F", "TSLA", "STLA"],
    "TSLA": ["GM", "F", "RIVN"],
    # Beverages and staples
    "KO": ["PEP", "MNST", "KDP"],
    "PEP": ["KO", "MNST", "KDP"],
    "PG": ["CL", "KMB", "UL"],
    # Pharma
    "PFE": ["MRK", "JNJ", "BMY"],
    "MRK": ["PFE", "JNJ", "LLY"],
    "JNJ": ["PFE", "MRK", "ABBV"],
    # Telecom
    "T": ["VZ", "TMUS"],
    "VZ": ["T", "TMUS"],
    "TMUS": ["VZ", "T"],
}

# SIC codes too broad to make a useful peer set from. Grouping by these would
# put a streaming service beside a cable operator, or a fintech beside a bank.
TOO_BROAD = {"6199", "7372", "4813", "6770", "2834", "3674"}


def suggest(ticker: str, sic: str = "", same_sic: list[dict] | None = None) -> tuple[list[str], str]:
    """Peer tickers and a note on where they came from.

    Returns ([], reason) when no defensible set exists -- the caller then asks
    the reader to choose instead of guessing.
    """
    tk = (ticker or "").strip().upper()

    if tk in CURATED:
        return CURATED[tk], "Common comparisons for this company."

    if same_sic and sic and sic not in TOO_BROAD:
        peers = [c["ticker"] for c in same_sic if c["ticker"].upper() != tk][:3]
        if peers:
            return peers, "Filers sharing this company's SEC industry code."

    if sic in TOO_BROAD:
        return [], ("This company's industry code covers businesses too different to compare "
                    "automatically.")
    return [], "No peer set is available for this company."
