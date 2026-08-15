"""
The funds on the market strip.

These have no 10-K, so there are no ratios to compute and nothing to score.
What a reader needs instead is what the thing actually is, what makes it move,
and why it is worth watching at all -- which is written here rather than
derived, because none of it changes with the day's price.

Everything factual (what a fund holds, roughly how concentrated it is) is
described in general terms. Exact holdings live in N-PORT filings and would
need parsing; until that exists, saying "about a third" is honest and saying
"31.4%" would not be.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Fund:
    ticker: str
    name: str
    one_line: str
    what: str
    moves_up: list[str] = field(default_factory=list)
    moves_down: list[str] = field(default_factory=list)
    why: str = ""
    watch_out: str = ""


FUNDS: dict[str, Fund] = {
    "SPY": Fund(
        ticker="SPY",
        name="S&P 500 ETF",
        one_line="a fund holding all 500, in one share",
        what=(
            "A fund that owns shares in the 500 biggest companies listed in America — "
            "Apple, JPMorgan, Exxon, Walmart and so on. Buying one share makes you a "
            "part-owner of all of them at once, weighted by size, so the largest "
            "companies make up the largest share of your money."
        ),
        moves_up=[
            "Company profits across the economy come in better than expected",
            "Interest rates fall, which makes future profits worth more today and "
            "makes bonds a less attractive alternative",
            "The largest holdings rise — the biggest ten names alone are roughly a "
            "third of the fund, so they pull it disproportionately",
        ],
        moves_down=[
            "A recession looks likelier, because profits fall with the economy",
            "Interest rates rise, which does the reverse of the above",
            "A shock nobody priced in — a war, a bank failure, a pandemic",
        ],
        why=(
            "It is the default benchmark for the US stock market. When someone says "
            "\u201cthe market was up today\u201d, this is usually what they mean. It also sets the "
            "bar for any individual stock you buy: if a company does not beat this over "
            "years, you would have done better owning all 500 and not thinking about it."
        ),
        watch_out=(
            "\u201cDiversified\u201d does not mean evenly spread. A handful of technology companies "
            "make up an unusually large share of the index, so a bad quarter for them "
            "moves the whole thing more than the name suggests."
        ),
    ),
    "QQQ": Fund(
        ticker="QQQ",
        name="Nasdaq 100 ETF",
        one_line="a fund holding the 100 largest Nasdaq companies",
        what=(
            "A fund holding the 100 biggest companies on the Nasdaq exchange, excluding "
            "banks and insurers. In practice that makes it heavily weighted towards "
            "technology — chipmakers, software, online retail and the large platform "
            "companies."
        ),
        moves_up=[
            "Technology earnings beat expectations, or a new product cycle takes hold",
            "Interest rates fall, which matters more here than for the S&P because "
            "these companies are priced on profits expected years out",
            "Investors feel confident and move money towards growth",
        ],
        moves_down=[
            "Interest rates rise, making distant profits worth less today",
            "A large holding disappoints — concentration cuts both ways",
            "Regulation or competition threatens the big platform businesses",
        ],
        why=(
            "It is the shorthand for how technology is doing. Comparing it against the "
            "S&P on the same day tells you whether the market moved as a whole or "
            "whether one sector did the work."
        ),
        watch_out=(
            "It is far more concentrated than it sounds and swings harder in both "
            "directions. A 100-company fund that is mostly one sector is not the same "
            "kind of diversification as a 500-company one."
        ),
    ),
    "GLD": Fund(
        ticker="GLD",
        name="Gold ETF",
        one_line="a fund holding physical gold bars in a vault",
        what=(
            "A fund that holds actual gold bars, stored in a vault in London. Your share "
            "is a claim on a slice of that metal. There is no company here — no revenue, "
            "no profit, no dividend. Gold does not earn anything; it simply is."
        ),
        moves_up=[
            "Investors are nervous and want something that is not a company or a "
            "government promise",
            "Interest rates fall, because gold pays no interest and competes with "
            "savings — low rates make holding it cost less",
            "The dollar weakens, since gold is priced in dollars",
            "Inflation runs high, and people look for something that holds value",
        ],
        moves_down=[
            "Confidence returns and money moves back into shares",
            "Interest rates rise, making cash and bonds more attractive than an asset "
            "that pays nothing",
            "The dollar strengthens",
        ],
        why=(
            "Gold often rises on days shares fall, which makes it a useful thing to "
            "watch beside them. When both are falling together, something unusual is "
            "happening — usually rising interest rates hitting everything at once."
        ),
        watch_out=(
            "Because it produces nothing, gold has no earnings to grow and no dividend "
            "to collect. The only way it makes money is if someone later pays more for "
            "it than you did. That is a different proposition from owning a business, "
            "and worth being clear-eyed about."
        ),
    ),
}


def get(ticker: str) -> Fund | None:
    return FUNDS.get((ticker or "").upper())
