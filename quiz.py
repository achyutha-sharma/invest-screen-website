"""
The quiz.

Questions are built from the figures already on the page, so a reader is
checking their understanding of a company they have just looked at rather than
recalling a definition in the abstract. Every question that needs a number is
skipped when that number is missing, which is why the set is generated per
company instead of being a fixed list.

The explanations matter more than the score. Each one says why the right answer
is right, and the wrong options are the mistakes people actually make -- share
price meaning expensive, revenue growth meaning profit, a high P/E meaning a
bad buy.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class Question:
    prompt: str
    options: list[str]
    correct: int
    why: str

    def shuffled(self, rng: random.Random) -> "Question":
        """Same question, options in a new order.

        Written with the right answer first for readability, which would make
        every answer A. Shuffling per round means a reader cannot pattern-match
        the position instead of the reasoning.
        """
        pairs = list(enumerate(self.options))
        rng.shuffle(pairs)
        return Question(
            prompt=self.prompt,
            options=[o for _, o in pairs],
            correct=next(i for i, (orig, _) in enumerate(pairs) if orig == self.correct),
            why=self.why,
        )


def build(name: str, eps=None, pe=None, margin=None, price=None, shares=None,
          fcf=None, net_income=None, dividend_yield=None,
          revenue_growth=None, income_growth=None) -> list[Question]:
    """Questions this company's filings can actually support.

    Each is phrased the way someone would actually wonder about it, rather than
    as a definition to recite. The wrong options are the specific mistakes
    people make, so getting one wrong teaches something.
    """
    qs: list[Question] = []

    if eps is not None:
        qs.append(Question(
            f"You own one share of {name}. It earned ${eps:,.2f} last year. "
            "Where did that money go?",
            [
                "It belongs to you, but the company decides whether to pay it out",
                f"It was paid into your account as ${eps:,.2f} cash",
                "It was added to the share price",
                "Nowhere — it is only an accounting figure",
            ],
            0,
            "Profit belongs to shareholders, but the company chooses what to do with it: "
            "pay a dividend, buy back shares, pay down debt, or reinvest. **EPS is what "
            "your share earned, not what you received.**",
        ))

    if pe:
        years = pe
        qs.append(Question(
            f"{name} costs ${price:,.2f} a share and earns ${eps:,.2f} a share a year. "
            f"That is a P/E of {pe:,.1f}. What is it telling you?"
            if price and eps else
            f"{name} trades at a P/E of {pe:,.1f}. What is it telling you?",
            [
                f"At this rate of profit, it takes about {years:,.0f} years to earn back "
                "what you paid",
                f"The share price will grow {years:,.0f}% a year",
                f"The company is {years:,.0f} times bigger than its rivals",
                f"You get ${years:,.0f} back every year",
            ],
            0,
            f"P/E is price divided by earnings per share. At {pe:,.1f}× you pay "
            f"${pe:,.0f} for each $1 of annual profit — so if profits never changed, it "
            f"would take about {pe:,.0f} years to earn your money back. Nobody expects "
            "profits to stay flat, which is exactly why the number varies so much.",
        ))

        qs.append(Question(
            "Two similar companies. One trades at 15× earnings, the other at 40×. "
            "Which is the better buy?",
            [
                "There is no way to tell without knowing what happens to their profits",
                "The 15× one — it is cheaper",
                "The 40× one — the market knows something",
                "Whichever pays a dividend",
            ],
            0,
            "A high multiple means investors expect growth; a low one often means they "
            "expect trouble. **The 40× company is the better buy if it grows into the "
            "price, and the worse one if it does not.** The ratio tells you what is "
            "being assumed, not whether the assumption is right.",
        ))

    if margin is not None:
        low = margin < 10
        qs.append(Question(
            f"For every $100 a customer spends at {name}, about ${margin:,.0f} ends up as "
            "profit. What does that tell you?",
            [
                f"${100 - margin:,.0f} went on making the product and running the company",
                f"The company wasted ${100 - margin:,.0f}",
                f"Shareholders received ${margin:,.0f}",
                "Nothing useful without the share price",
            ],
            0,
            "Margin shows how much of each sale survives every cost — materials, wages, "
            "marketing, interest and tax. "
            + ("A thin margin is not automatically bad: supermarkets run on a few percent "
               "and do fine on volume. **What matters is the direction.** A margin that is "
               "falling year after year means the company is spending more to earn the same."
               if low else
               "**What matters most is the direction.** A margin that is falling year "
               "after year means the company is spending more to earn the same."),
        ))

    if fcf is not None and net_income:
        conv = fcf / net_income if net_income else None
        if conv is not None:
            qs.append(Question(
                f"{name} reported profit, but the cash that actually arrived was different. "
                "How is that possible?",
                [
                    "Profit counts sales before the money is collected, and spreads costs "
                    "over years",
                    "One of the two figures must be wrong",
                    "The difference is always tax",
                    "It only happens at companies in trouble",
                ],
                0,
                "Profit involves judgement about *when* to count things — a sale on credit "
                "counts today even if the cash comes in months later. Cash flow only counts "
                f"money that moved. Here, each $1 of reported profit came with "
                f"${conv:,.2f} of real spare cash. **When the two drift apart for years, "
                "trust the cash.**",
            ))

    if price and shares:
        qs.append(Question(
            "Your friend says a $12 stock is cheaper than a $400 one. Are they right?",
            [
                "No — the price of one share says nothing about value",
                "Yes, obviously",
                "Yes, but only for small companies",
                "Only if both pay dividends",
            ],
            0,
            "A company decides how many shares to split itself into, and that alone sets "
            "the share price. Two identical businesses can trade at $12 and $400. "
            f"**What matters is the price against what the company earns.** {name}'s "
            f"entire business costs about ${price * shares / 1e9:,.1f} billion today.",
        ))

    qs.append(Question(
        "A company's sales grew 10% last year, but its profit fell. What most likely "
        "happened?",
        [
            "Its costs grew faster than its sales did",
            "It sold fewer products than the year before",
            "Its share price dropped",
            "It paid too much in dividends",
        ],
        0,
        "Sales tell you customers are still coming. They say nothing about what the "
        "company **keeps**. Growing revenue alongside falling profit usually means costs, "
        "discounts or interest rose faster than the business — which is why margin is "
        "worth watching next to growth.",
    ))

    if dividend_yield:
        qs.append(Question(
            f"{name} pays a dividend yielding {dividend_yield:,.2f}%. The share price then "
            "falls 20%. What happens to the cash you already received?",
            [
                "Nothing — it is yours to keep",
                "It is deducted from your account",
                "It converts back into shares",
                "The company can ask for it back",
            ],
            0,
            "Dividends are the one part of a return that a falling price cannot undo. "
            "That is why income investors care about them, and why a company cutting its "
            "dividend is treated as such bad news — it is the promise people relied on.",
        ))

    qs.append(Question(
        "A stock is up 40% over five years. What does that prove about the business?",
        [
            "Nothing by itself — the gain might be earnings, or just sentiment",
            "That its profits grew 40%",
            "That it is well run",
            "That it will keep rising",
        ],
        0,
        "A return has two engines: **the business earning more**, and **investors "
        "willing to pay more for the same earnings**. A stock can rise while profit per "
        "share falls, purely because the market re-rated it. That is a real return, but a "
        "fragile one — it can reverse without the company doing anything at all.",
    ))

    if pe and margin is not None:
        qs.append(Question(
            "A company's profits fall but its share price does not move. What "
            "happens to its P/E?",
            [
                "It rises, because the same price now buys less profit",
                "It falls, because the company is worth less",
                "Nothing — P/E only changes when the price does",
                "It becomes negative",
            ],
            0,
            "P/E is price divided by earnings. Shrink the bottom of a fraction and the "
            "result gets bigger. **A rising P/E is not always investors getting more "
            "optimistic** — sometimes it is just profits falling underneath a price that "
            "has not caught up yet.",
        ))

    if fcf is not None and net_income and fcf < net_income:
        qs.append(Question(
            f"{name} reported more profit than the cash it actually kept. Name one "
            "ordinary reason that happens.",
            [
                "It sold on credit, so the sale counts before the money arrives",
                "It is hiding losses",
                "It paid too much tax",
                "Its auditors made a mistake",
            ],
            0,
            "Selling on credit, building inventory, or spending heavily on equipment all "
            "make cash lag profit — none of them are wrongdoing. **What matters is "
            "whether the gap closes.** A company where cash trails profit every year for "
            "a decade is telling you something the profit line is not.",
        ))

    qs.append(Question(
        "Two companies earn the same profit. One has no debt, the other has a lot. "
        "Which is riskier for a shareholder?",
        [
            "The indebted one — lenders are paid before shareholders",
            "The debt-free one, because it is not growing",
            "They are identical if profits are identical",
            "Whichever has the lower share price",
        ],
        0,
        "Debt is a fixed claim that gets paid first, in good years and bad. In a bad "
        "year, interest still has to be paid and whatever is left over is what your "
        "share is worth. **Debt magnifies both directions** — it raises returns when "
        "things go well and wipes them out when they do not.",
    ))

    qs.append(Question(
        "A company buys back its own shares. What does that do to EPS?",
        [
            "It rises, because the same profit is split between fewer shares",
            "It falls, because the company spent cash",
            "Nothing — buybacks only affect the share price",
            "It doubles",
        ],
        0,
        "Fewer shares means each remaining one owns a bigger slice of the same profit. "
        "**This is why EPS can rise while total profit is flat or falling** — worth "
        "checking both, because a company can flatter its EPS without the business "
        "improving at all.",
    ))

    if margin is not None:
        qs.append(Question(
            "A supermarket has a 2% net margin and a software company has 25%. "
            "Which is the better business?",
            [
                "Cannot tell — they make money in completely different ways",
                "The software company, clearly",
                "The supermarket, because it sells more",
                "Whichever has the higher share price",
            ],
            0,
            "A supermarket keeps very little of each sale but sells enormous volume and "
            "turns its stock over constantly. Software keeps most of each sale but sells "
            "far less. **Margins are only comparable within an industry** — which is why "
            "this tool compares a company against its own past rather than a fixed "
            "threshold.",
        ))

    qs.append(Question(
        "Where does the money go when you buy a share on the stock exchange?",
        [
            "To another investor who is selling",
            "To the company",
            "To the government as tax",
            "It is split between the company and the seller",
        ],
        0,
        "The company only received money when it first issued those shares. Everything "
        "since is investors trading with each other. **Buying Nike shares does not fund "
        "Nike** — though a higher share price does make it cheaper for the company to "
        "raise money later.",
    ))

    if dividend_yield:
        qs.append(Question(
            "A company cuts its dividend. Why do investors usually react badly?",
            [
                "It suggests management no longer expects to afford it",
                "It is illegal to cut a dividend",
                "It always means the company is about to fail",
                "Because the share price is fixed to the dividend",
            ],
            0,
            "Companies work hard to avoid cutting, because doing so admits something has "
            "changed. **The cut itself is rarely the problem — it is what the cut "
            "implies** about the cash the company expects to have.",
        ))

    qs.append(Question(
        "Which of these is a fact rather than an opinion?",
        [
            "The cash that moved in and out of the bank last year",
            "The company's reported profit",
            "The value of its brand",
            "Its share price target",
        ],
        0,
        "Profit involves judgement about *when* to count a sale and how fast to write "
        "assets down. Cash either moved or it did not. **That is why free cash flow is "
        "the number to check when profit looks too good** — it has far less room for "
        "interpretation.",
    ))

    qs.append(Question(
        "What does a filing's risk factors section actually tell you?",
        [
            "What the company itself thinks could hurt it",
            "What is definitely about to go wrong",
            "What analysts predict",
            "Nothing — it is pure legal boilerplate",
        ],
        0,
        "It is the company's own list, written by its lawyers, so it names everything "
        "imaginable. **Listed does not mean happening.** What is worth noticing is a "
        "risk that is newly added, since something changed enough to write it down.",
    ))

    return qs


def new_seed() -> int:
    """A fresh seed for a new round of questions."""
    return random.randrange(1_000_000_000)


def pick(pool: list[Question], seed: int = 0, count: int = 5,
         exclude: set[str] | None = None) -> list[Question]:
    """Five questions, drawn at random and with their options reordered.

    The seed is held by the caller rather than generated here. Streamlit
    re-executes the whole script on every interaction, so drawing afresh each
    time would reshuffle the options underneath someone mid-answer. A new seed
    is minted only when the reader asks for another round.

    `exclude` holds the prompts already seen, so a second round draws from what
    is left before it starts repeating.
    """
    rng = random.Random(seed)
    seen = exclude or set()
    fresh = [q for q in pool if q.prompt not in seen]
    if len(fresh) < count:
        # Everything has been asked; start again from the whole pool rather
        # than showing fewer questions.
        fresh = list(pool)
    chosen = rng.sample(fresh, min(count, len(fresh)))
    return [q.shuffled(rng) for q in chosen]


def grade(score: int, total: int) -> tuple[str, str]:
    """A verdict and a line of encouragement, never a judgement of the person."""
    if total == 0:
        return "", ""
    pct = score / total
    if pct >= 0.8:
        return "You have got this", (
            "You can read the things most people skip past — what a ratio measures, and "
            "just as importantly what it does not.")
    if pct >= 0.5:
        return "Solid start", (
            "The definitions are landing. The ones to revisit are usually P/E and cash "
            "versus profit — they are where most of the confusion lives.")
    return "Worth another pass", (
        "These take a couple of goes. Switch back to Research and read the expanders "
        "under each number, then try again — they explain the same ideas against real "
        "figures.")
