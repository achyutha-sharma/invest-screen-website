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
    # Apparel and footwear. Peers are checked for still filing -- a company
    # taken private stops filing and can never resolve, so it would silently
    # shorten every comparison it appears in.
    "NKE": ["LULU", "UAA", "DECK"],
    "LULU": ["NKE", "DECK", "UAA"],
        "UAA": ["NKE", "LULU", "DECK"],
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
    "PYPL": ["V", "MA", "AXP"],
    # Airlines
    "DAL": ["UAL", "AAL", "LUV"],
    "UAL": ["DAL", "AAL", "LUV"],
    "AAL": ["DAL", "UAL", "LUV"],
    "LUV": ["DAL", "UAL", "AAL"],
    # Autos
    "F": ["GM", "TSLA", "STLA"],
    "GM": ["F", "TSLA", "STLA"],
    "TSLA": ["GM", "F", "LCID"],
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

    # Specialty and beauty retail. These share SIC 5990 with almost every
    # unclassified shop in America, so the code alone is useless here -- the
    # peer set has to be named.
    "ULTA": ["EL", "COTY", "BBWI"],
    "EL": ["ULTA", "COTY", "PG"],
    "COTY": ["EL", "ULTA", "PG"],
    "BBWI": ["ULTA", "EL", "GPS"],
    "GPS": ["ANF", "URBN", "AEO"],
    "ANF": ["GPS", "URBN", "AEO"],
    "URBN": ["ANF", "GPS", "AEO"],
    "AEO": ["ANF", "GPS", "URBN"],
    "ROST": ["TJX", "BURL", "TGT"],
    "TJX": ["ROST", "BURL", "TGT"],
    "BURL": ["ROST", "TJX", "TGT"],
    "DG": ["DLTR", "WMT", "TGT"],
    "DLTR": ["DG", "WMT", "TGT"],
    "BBY": ["TGT", "WMT", "AMZN"],
    "DECK": ["NKE", "LULU", "UAA"],
    "CROX": ["NKE", "DECK", "UAA"],
    "ONON": ["NKE", "DECK", "LULU"],

    # Restaurants and consumer brands.
    "DPZ": ["CMG", "YUM", "MCD"],
    "WEN": ["MCD", "YUM", "DPZ"],
    "QSR": ["MCD", "YUM", "WEN"],
    "MNST": ["KO", "PEP", "CELH"],
    "CELH": ["MNST", "KO", "PEP"],
    "KHC": ["GIS", "K", "PEP"],
    "GIS": ["KHC", "K", "PEP"],
    "K": ["GIS", "KHC", "PEP"],
    "CL": ["PG", "KMB", "CHD"],
    "KMB": ["PG", "CL", "CHD"],

    # Technology and software.
    "ADBE": ["CRM", "MSFT", "ORCL"],
    "NOW": ["CRM", "ADBE", "MSFT"],
    "SHOP": ["AMZN", "SQ", "PYPL"],
    "UBER": ["LYFT", "DASH", "ABNB"],
    "LYFT": ["UBER", "DASH", "ABNB"],
    "DASH": ["UBER", "ABNB", "LYFT"],
    "ABNB": ["UBER", "DASH", "MAR"],
    "QCOM": ["NVDA", "AMD", "AVGO"],
    "AVGO": ["NVDA", "QCOM", "AMD"],
    "MU": ["NVDA", "AMD", "INTC"],
    "TXN": ["AVGO", "QCOM", "INTC"],

    # Health care and pharmacy.
    "LLY": ["PFE", "MRK", "ABBV"],
    "ABBV": ["PFE", "MRK", "LLY"],
    "BMY": ["PFE", "MRK", "ABBV"],
    "AMGN": ["ABBV", "MRK", "LLY"],
    "MRNA": ["PFE", "BNTX", "MRK"],
    "CVS": ["WBA", "UNH", "CI"],
    "UNH": ["CVS", "CI", "ELV"],
    "HOOD": ["SCHW", "COIN", "IBKR"],
    "COIN": ["HOOD", "SCHW", "IBKR"],
    "SCHW": ["HOOD", "IBKR", "MS"],

    # Industrials and energy.
    "CAT": ["DE", "CMI", "HON"],
    "DE": ["CAT", "CMI", "AGCO"],
    "BA": ["LMT", "RTX", "GD"],
    "LMT": ["BA", "RTX", "GD"],
    "RTX": ["LMT", "BA", "GD"],
    "CVX": ["XOM", "COP", "OXY"],
    "COP": ["XOM", "CVX", "OXY"],
    "NEE": ["DUK", "SO", "AEP"],
    "DUK": ["NEE", "SO", "AEP"],

    # Metals, materials and industrials. Narrow SIC codes, but narrow is not
    # the same as covered -- these needed naming like everything else.
    "KALU": ["CENX", "AA", "ATI"],
    "AA": ["CENX", "KALU", "ATI"],
    "CENX": ["AA", "KALU", "ATI"],
    "ATI": ["CRS", "KALU", "AA"],
    "CRS": ["ATI", "KALU", "AA"],
    "X": ["NUE", "STLD", "CLF"],
    "NUE": ["STLD", "X", "CLF"],
    "STLD": ["NUE", "X", "CLF"],
    "CLF": ["X", "NUE", "STLD"],
    "FCX": ["SCCO", "TECK", "AA"],
    "SCCO": ["FCX", "TECK", "AA"],
    "NEM": ["GOLD", "AEM", "FCX"],
    "GOLD": ["NEM", "AEM", "FCX"],
    "DOW": ["LYB", "DD", "EMN"],
    "LYB": ["DOW", "DD", "EMN"],
    "DD": ["DOW", "LYB", "EMN"],
    "SHW": ["PPG", "RPM", "DD"],
    "PPG": ["SHW", "RPM", "DD"],
    "VMC": ["MLM", "SUM", "EXP"],
    "MLM": ["VMC", "SUM", "EXP"],

    # Machinery, transport and building.
    "CMI": ["CAT", "DE", "PCAR"],
    "PCAR": ["CMI", "CAT", "DE"],
    "EMR": ["HON", "ETN", "ROK"],
    "ETN": ["EMR", "HON", "ROK"],
    "HON": ["EMR", "ETN", "GE"],
    "GE": ["HON", "RTX", "EMR"],
    "UNP": ["CSX", "NSC", "CP"],
    "CSX": ["UNP", "NSC", "CP"],
    "NSC": ["UNP", "CSX", "CP"],
    "UPS": ["FDX", "XPO", "CHRW"],
    "FDX": ["UPS", "XPO", "CHRW"],
    "DHI": ["LEN", "PHM", "NVR"],
    "LEN": ["DHI", "PHM", "NVR"],
    "PHM": ["DHI", "LEN", "NVR"],

    # Medical devices, insurers and health services.
    "SYK": ["BSX", "ZBH", "MDT"],
    "BSX": ["SYK", "MDT", "ABT"],
    "MDT": ["SYK", "BSX", "ABT"],
    "ZBH": ["SYK", "BSX", "MDT"],
    "ABT": ["MDT", "BSX", "BDX"],
    "BDX": ["ABT", "MDT", "SYK"],
    "ISRG": ["SYK", "BSX", "MDT"],
    "EW": ["BSX", "MDT", "ABT"],
    "DXCM": ["PODD", "ISRG", "ABT"],
    "PODD": ["DXCM", "ISRG", "ABT"],
    "TMO": ["DHR", "A", "WAT"],
    "DHR": ["TMO", "A", "WAT"],
    "CI": ["UNH", "ELV", "CVS"],
    "ELV": ["UNH", "CI", "CVS"],
    "HUM": ["UNH", "ELV", "CI"],
    "HCA": ["THC", "UHS", "CYH"],
    "ZTS": ["IDXX", "ELAN", "MRK"],

    # Insurance and financials beyond the big banks.
    "PGR": ["ALL", "TRV", "CB"],
    "ALL": ["PGR", "TRV", "CB"],
    "TRV": ["ALL", "PGR", "CB"],
    "CB": ["TRV", "ALL", "AIG"],
    "AIG": ["CB", "MET", "PRU"],
    "MET": ["PRU", "AIG", "AFL"],
    "PRU": ["MET", "AIG", "AFL"],
    "AXP": ["V", "MA", "COF"],
    "COF": ["AXP", "DFS", "SYF"],
    "BLK": ["BX", "KKR", "TROW"],
    "BX": ["KKR", "APO", "BLK"],
    "KKR": ["BX", "APO", "CG"],
    "SPGI": ["MCO", "MSCI", "ICE"],
    "MCO": ["SPGI", "MSCI", "ICE"],
    "ICE": ["CME", "NDAQ", "SPGI"],
    "CME": ["ICE", "NDAQ", "CBOE"],

    # Media, travel and leisure.
    "CMCSA": ["CHTR", "DIS", "WBD"],
    "CHTR": ["CMCSA", "WBD", "DIS"],
    "WBD": ["DIS", "PARA", "NFLX"],
    "PARA": ["WBD", "DIS", "NFLX"],
    "MAR": ["HLT", "H", "IHG"],
    "HLT": ["MAR", "H", "IHG"],
    "BKNG": ["EXPE", "ABNB", "TRIP"],
    "EXPE": ["BKNG", "ABNB", "TRIP"],
    "RCL": ["CCL", "NCLH", "MAR"],
    "CCL": ["RCL", "NCLH", "MAR"],
    "NCLH": ["RCL", "CCL", "MAR"],
    "LVS": ["MGM", "WYNN", "CZR"],
    "MGM": ["LVS", "WYNN", "CZR"],
    "DKNG": ["FLUT", "MGM", "CZR"],

    # Property, utilities and telecoms.
    "AMT": ["CCI", "SBAC", "EQIX"],
    "CCI": ["AMT", "SBAC", "EQIX"],
    "EQIX": ["DLR", "AMT", "CCI"],
    "DLR": ["EQIX", "AMT", "CCI"],
    "PLD": ["EXR", "PSA", "AMT"],
    "PSA": ["EXR", "PLD", "CUBE"],
    "O": ["NNN", "SPG", "VICI"],
    "SPG": ["O", "KIM", "REG"],
    "SO": ["DUK", "NEE", "AEP"],
    "AEP": ["SO", "DUK", "NEE"],
    "D": ["SO", "DUK", "EXC"],
    "EXC": ["D", "SO", "AEP"],

    # Software and services not yet covered.
    "INTU": ["ADBE", "CRM", "NOW"],
    "WDAY": ["NOW", "CRM", "ADBE"],
    "SNOW": ["MDB", "DDOG", "NOW"],
    "DDOG": ["SNOW", "MDB", "NOW"],
    "MDB": ["SNOW", "DDOG", "ORCL"],
    "PANW": ["CRWD", "FTNT", "ZS"],
    "CRWD": ["PANW", "FTNT", "ZS"],
    "FTNT": ["PANW", "CRWD", "ZS"],
    "IBM": ["ACN", "ORCL", "MSFT"],
    "ACN": ["IBM", "INFY", "CTSH"],
    "TXT": ["GD", "LMT", "RTX"],
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
        return CURATED[tk], ("curated", "Common comparisons for this company.")

    if same_sic and sic and sic not in TOO_BROAD:
        peers = [c["ticker"] for c in same_sic if c["ticker"].upper() != tk][:3]
        if peers:
            return peers, ("sic", "Filers sharing this company's SEC industry code.")

    if sic in TOO_BROAD:
        return [], ("broad", "This company's SEC industry code covers businesses too "
                             "different to compare automatically.")
    return [], ("none", "No comparison set has been checked for this company yet.")
