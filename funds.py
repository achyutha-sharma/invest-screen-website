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
    # Long-run average, not a recent one. A three-year figure would need a
    # price history the free feed does not supply, and would go stale the
    # moment it was written. The multi-decade average is stable, and it is
    # the number worth knowing: it sets the bar any investment is measured
    # against.
    long_run: str = ""
    long_run_note: str = ""
    # The single most important number for a fund, and the one thing N-PORT
    # does not contain -- it lives in the prospectus. Written by hand and
    # checked against the provider, with the date so a stale figure is
    # visible rather than silently wrong.
    cost: str = ""
    cost_note: str = ""
    checked: str = ""


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
        long_run="about 10% a year",
        long_run_note=(
            "Averaged over decades, before inflation and with dividends reinvested. "
            "<b>No individual year looks like the average</b> — the index has fallen more "
            "than 30% in a year and risen more than 30% in another. The average is what "
            "you get for sitting through both."
        ),
        cost="about 0.09% a year",
        cost_note=(
            "<b>About {D}9 a year on every {D}10,000 invested.</b> VOO holds the same "
            "500 companies for roughly a third of that. SPY is older and trades more "
            "heavily, which matters to traders; for holding, the cheaper fund keeps more "
            "of the return."
        ),
        checked="September 2026",
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
        cost="0.20% a year",
        cost_note=(
            "<b>{D}20 a year on every {D}10,000 invested</b> — around six times what a "
            "broad index fund charges, for a narrower and more concentrated set of "
            "companies."
        ),
        checked="September 2026",
        long_run="higher than the S&P, with bigger falls",
        long_run_note=(
            "Technology has outgrown the wider market over the last few decades, so this "
            "has returned more than the S&P 500 over that stretch. It has also fallen "
            "much harder when sentiment turned — it lost roughly 80% after the dot-com "
            "peak in 2000 and took fifteen years to recover. <b>A higher average is not "
            "free; it is paid for in the size of the drops.</b>"
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
        cost="0.40% a year",
        cost_note=(
            "<b>{D}40 a year on every {D}10,000 invested.</b> Storing and insuring metal "
            "costs money, and because gold produces no income there is nothing to offset "
            "the fee — it comes straight out of the holding."
        ),
        checked="September 2026",
        long_run="roughly keeps pace with inflation",
        long_run_note=(
            "Over very long stretches gold has held its purchasing power rather than "
            "grown it — an ounce buys roughly what it always did. It has had long "
            "stretches of going nowhere, including two decades after its 1980 peak. "
            "<b>It is held for what it does when other things fall, not for growth.</b>"
        ),
    ),

    "VOO": Fund(
        ticker="VOO",
        name="Vanguard S&P 500 ETF",
        one_line="the same 500 companies as SPY, at a third of the cost",
        what=(
            "A fund holding the 500 biggest companies listed in America, weighted by "
            "size. It tracks the same index as SPY and holds the same businesses; the "
            "difference between them is what they charge."
        ),
        moves_up=[
            "Company profits across the economy come in better than expected",
            "Interest rates fall, making future profits worth more today",
            "The largest holdings rise — the biggest ten names are roughly a third of "
            "the fund",
        ],
        moves_down=[
            "A recession looks likelier, because profits fall with the economy",
            "Interest rates rise, which does the reverse",
            "A shock nobody priced in",
        ],
        why=(
            "It is the most common way to own the US stock market. Comparing an "
            "individual company against it answers the question that matters: would you "
            "have done better owning all 500 and not thinking about it?"
        ),
        watch_out=(
            "\u201cDiversified\u201d does not mean evenly spread. A handful of technology "
            "companies make up an unusually large share of the index, so a bad quarter "
            "for them moves the whole fund more than the name suggests."
        ),
        long_run="about 10% a year",
        long_run_note=(
            "Averaged over decades, before inflation and with dividends reinvested. "
            "<b>No individual year looks like the average</b> — the index has fallen more "
            "than 30% in a year and risen more than 30% in another."
        ),
        cost="0.03% a year",
        cost_note=(
            "<b>{D}3 a year on every {D}10,000 invested.</b> SPY tracks the same index "
            "and charges about 0.09% — three times as much for the same holdings. On a "
            "long horizon that difference compounds into real money, which is why cost "
            "is the first thing to check on any fund."
        ),
        checked="September 2026",
    ),

    "VTI": Fund(
        ticker="VTI",
        name="Vanguard Total Stock Market ETF",
        one_line="almost every public company in America, in one holding",
        what=(
            "A fund holding roughly 3,600 US companies — the S&P 500 plus the mid-sized "
            "and small ones it leaves out. Weighted by size, so the largest companies "
            "still dominate: the small end is a few percent of the money despite being "
            "most of the names."
        ),
        moves_up=[
            "The same things that move the S&P 500, since large companies are most of "
            "the fund",
            "Smaller companies do well, which tends to happen when rates fall and credit "
            "is easy",
        ],
        moves_down=[
            "A recession looks likelier — smaller companies usually fall further than "
            "large ones",
            "Interest rates rise, which hits smaller and more indebted companies hardest",
        ],
        why=(
            "It is the simplest single answer to \u201cown the US market\u201d. In practice it "
            "moves almost identically to an S&P 500 fund, because the extra 3,000 "
            "companies are a small share of the money."
        ),
        watch_out=(
            "Owning 3,600 companies sounds far more diversified than owning 500, but the "
            "weighting means the two behave nearly the same. <b>The extra names add very "
            "little, either way.</b>"
        ),
        long_run="close to the S&P 500",
        long_run_note=(
            "Over long stretches this and an S&P 500 fund have returned within a fraction "
            "of a percent of each other, for the reason above. Choosing between them "
            "matters far less than most comparisons suggest."
        ),
        cost="0.03% a year",
        cost_note="<b>{D}3 a year on every {D}10,000 invested.</b>",
        checked="September 2026",
    ),

    "VXUS": Fund(
        ticker="VXUS",
        name="Vanguard Total International Stock ETF",
        one_line="companies outside the United States",
        what=(
            "A fund holding roughly 8,000 companies across 40-odd countries — developed "
            "markets such as Japan, the UK and Germany, and emerging ones including "
            "China, India and Brazil. It holds no US companies at all, which is the "
            "point: it is the piece a US-only portfolio is missing."
        ),
        moves_up=[
            "Economies outside the US grow faster than expected",
            "The dollar weakens, because foreign earnings convert back into more dollars",
            "Investors rotate away from US stocks after a long run of US outperformance",
        ],
        moves_down=[
            "The dollar strengthens, shrinking foreign returns before anything else "
            "happens",
            "A crisis in a large holding country",
            "Global growth slows — emerging markets usually fall hardest",
        ],
        why=(
            "The US is a large share of the world's stock market but not all of it. "
            "Holding this alongside a US fund is how most long-term portfolios avoid "
            "betting everything on one country."
        ),
        watch_out=(
            "It has badly trailed US stocks for well over a decade, which makes it "
            "tempting to skip. <b>That is exactly the reasoning that leads people to own "
            "only whatever has done best recently</b> — and the periods when "
            "international leads tend to arrive without warning."
        ),
        long_run="lower than US stocks over the last fifteen years",
        long_run_note=(
            "Over that stretch, US stocks have returned roughly twice as much a year. "
            "Over much longer periods the two have taken turns. <b>Which one leads next "
            "is not something anyone can tell you.</b>"
        ),
        cost="about 0.05% a year",
        cost_note=(
            "<b>Around {D}5 a year on every {D}10,000 invested.</b> Higher than a US "
            "index fund because trading in 40 countries costs more, but still a fraction "
            "of what an actively managed international fund charges."
        ),
        checked="September 2026",
    ),

    "BND": Fund(
        ticker="BND",
        name="Vanguard Total Bond Market ETF",
        one_line="thousands of US bonds — lending, not owning",
        what=(
            "A fund holding roughly 10,000 US investment-grade bonds: government debt, "
            "mortgage-backed securities and bonds issued by large companies. Buying a "
            "bond means lending money for a fixed return, rather than owning a share of "
            "a business. It pays interest monthly."
        ),
        moves_up=[
            "Interest rates fall — existing bonds paying higher rates become more "
            "valuable",
            "Investors move to safety during a stock market fall",
        ],
        moves_down=[
            "Interest rates rise, because new bonds pay more than the ones already held",
            "Inflation runs high, eroding the value of a fixed payment",
        ],
        why=(
            "It is what most portfolios hold alongside stocks to steady them. Bonds "
            "usually rise when stocks fall, though 2022 was a reminder that usually is "
            "not always."
        ),
        watch_out=(
            "<b>A bond fund is not a savings account.</b> It fell roughly 13% in 2022 "
            "when rates rose sharply — the worst year for bonds in decades. Safer than "
            "stocks does not mean it cannot lose money."
        ),
        long_run="roughly 4 to 5% a year",
        long_run_note=(
            "Bond returns track the interest rate at the time you buy, more than "
            "anything else. <b>The yield today is a reasonable guide to the return from "
            "here</b>, which is not true of stocks."
        ),
        cost="0.03% a year",
        cost_note="<b>{D}3 a year on every {D}10,000 invested.</b>",
        checked="September 2026",
    ),

    "NLR": Fund(
        ticker="NLR",
        name="VanEck Uranium and Nuclear ETF",
        one_line="uranium miners and the companies that run nuclear plants",
        what=(
            "A fund holding companies across the nuclear chain: miners that dig uranium "
            "out of the ground, utilities that operate reactors, and the industrial "
            "firms that build and service them. Roughly half energy, a quarter "
            "utilities, the rest industrial — so it is two quite different businesses "
            "in one holding."
        ),
        moves_up=[
            "Governments commit to new reactors, or extend the life of existing ones",
            "Electricity demand rises faster than supply — data centres are the current "
            "reason",
            "The uranium price rises, which flows straight to the miners",
        ],
        moves_down=[
            "A nuclear accident anywhere in the world, which historically reprices the "
            "whole sector regardless of where it happened",
            "Reactor projects are delayed or cancelled — they run to decades, not years",
            "The uranium price falls, or new supply arrives",
        ],
        why=(
            "It is the most direct way to hold the nuclear story in one line. The two "
            "halves behave differently: utilities are steady and regulated, miners swing "
            "with a commodity price."
        ),
        watch_out=(
            "This is a **concentrated sector bet**, not a diversified holding. It has "
            "fallen sharply in years when the wider market rose, and a single political "
            "decision in one country can move it. The fee is also six to fifteen times "
            "what a broad index fund charges."
        ),
        long_run="highly variable, with long flat stretches",
        long_run_note=(
            "Nuclear went nearly nowhere for the decade after Fukushima in 2011, then "
            "rose sharply as power demand and policy turned. <b>A theme can be correct "
            "and still take fifteen years to pay</b>, which is the risk in any sector "
            "fund built on one idea."
        ),
        cost="0.52% a year",
        cost_note=(
            "<b>{D}52 a year on every {D}10,000 invested</b> — roughly seventeen times "
            "what a broad index fund charges. Sector and theme funds cost more because "
            "they are smaller and trade more; the fee is the price of the narrower bet."
        ),
        checked="September 2026",
    ),

    "XLF": Fund(
        ticker="XLF",
        name="Financial Select Sector SPDR",
        one_line="the banks, insurers and payment companies in the S&P 500",
        what=(
            "A fund holding the financial companies within the S&P 500 — large banks, "
            "insurers, asset managers, exchanges and payment networks. It is weighted by "
            "size, so the biggest banks dominate. It holds no companies outside the "
            "index, so smaller regional banks are largely absent."
        ),
        moves_up=[
            "Interest rates rise, because banks earn more on the gap between what they "
            "lend at and what they pay depositors",
            "The economy looks strong, so fewer loans go bad",
            "Regulation loosens, or capital requirements fall",
        ],
        moves_down=[
            "A recession looks likelier — banks lose money when borrowers default",
            "Interest rates fall sharply, compressing lending margins",
            "A credit event: one bank failing tends to drag the whole sector, whether or "
            "not the others are exposed",
        ],
        why=(
            "Financials are the sector most directly tied to interest rates and the "
            "credit cycle, so it often moves before the rest of the market does. Watching "
            "it alongside the S&P shows whether a move is broad or rate-driven."
        ),
        watch_out=(
            "Banks are leveraged by design — they operate on a thin layer of equity "
            "beneath a large balance sheet. <b>That magnifies both directions</b>, and it "
            "is why financials fall harder than most sectors in a crisis. 2008 and the "
            "2023 regional bank failures are the reference points."
        ),
        long_run="broadly in line with the S&P, with deeper falls",
        long_run_note=(
            "Over long stretches financials have returned roughly what the index has, "
            "but with worse drawdowns. The sector took more than a decade to recover its "
            "2007 peak. <b>Similar average, much rougher path.</b>"
        ),
        cost="0.08% a year",
        cost_note=(
            "<b>{D}8 a year on every {D}10,000 invested.</b> Cheap for a sector fund — "
            "the Select Sector SPDRs are index funds carved out of the S&P 500 rather "
            "than actively chosen, which keeps the fee close to a broad index fund."
        ),
        checked="September 2026",
    ),
}


def get(ticker: str) -> Fund | None:
    return FUNDS.get((ticker or "").upper())
