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

from dataclasses import dataclass


@dataclass
class Question:
    prompt: str
    options: list[str]
    correct: int
    why: str


def build(name: str, eps=None, pe=None, margin=None, price=None, shares=None,
          fcf=None, net_income=None, dividend_yield=None,
          revenue_growth=None, income_growth=None) -> list[Question]:
    """Questions this company's filings can actually support."""
    qs: list[Question] = []

    if eps is not None:
        qs.append(Question(
            f"{name} reported EPS of ${eps:,.2f}. What does that mean?",
            [
                f"Each share earned ${eps:,.2f} of profit last year",
                f"Each share is worth ${eps:,.2f}",
                f"The company paid ${eps:,.2f} to each shareholder",
                f"The share price rose ${eps:,.2f}",
            ],
            0,
            "EPS is profit divided by the number of shares — what one share *earned*, "
            "not what it costs and not what was paid out. Over long stretches a share "
            "price tends to follow this figure, which is why it is worth watching.",
        ))

    if pe:
        qs.append(Question(
            f"{name} trades at a P/E of {pe:,.1f}×. What are you paying?",
            [
                f"${pe:,.0f} for every $1 the share earns in a year",
                f"${pe:,.0f} for one share",
                f"{pe:,.0f}% more than the company is worth",
                f"${pe:,.0f} of dividends a year",
            ],
            0,
            "P/E is price divided by earnings per share. At "
            f"{pe:,.1f}× you are paying ${pe:,.0f} for each $1 of annual profit — so if "
            f"nothing changed it would take about {pe:,.0f} years of profit to earn your "
            "money back.",
        ))

        qs.append(Question(
            "A company has a much higher P/E than its competitors. What does that tell you?",
            [
                "Investors expect its profits to grow faster",
                "It is definitely overpriced",
                "It is a safer investment",
                "It pays a bigger dividend",
            ],
            0,
            "A high P/E usually means investors expect growth — they are paying now for "
            "profits that have not arrived. **It only turns out to be expensive if that "
            "growth never comes.** A low P/E can equally mean investors expect trouble "
            "rather than signalling a bargain.",
        ))

    if margin is not None:
        qs.append(Question(
            f"{name}'s net margin is {margin:,.1f}%. Out of every $100 customers spend, "
            "how much becomes profit?",
            [
                f"About ${margin:,.0f}",
                f"About ${min(margin * 4, 99):,.0f}",
                "All of it, minus tax",
                "It depends on the share price",
            ],
            0,
            f"Net margin is profit divided by revenue. At {margin:,.1f}% the company keeps "
            f"about ${margin:,.0f} of every $100 spent by customers. A **falling** margin "
            "means it is spending more to earn the same, which usually shows up in the "
            "share price later.",
        ))

    if fcf is not None and net_income:
        conv = fcf / net_income if net_income else None
        if conv is not None:
            qs.append(Question(
                "Reported profit and free cash flow disagree for a company. Which would "
                "you trust more?",
                [
                    "Free cash flow — cash either arrived or it did not",
                    "Profit — it is the official figure",
                    "Whichever is higher",
                    "They always match, so one is a mistake",
                ],
                0,
                "**Profit is an opinion. Cash is a fact.** Profit involves judgement about "
                "when to count revenue and costs. Cash either landed in the bank or it did "
                f"not. Here, every $1 of reported profit came with ${conv:,.2f} of real "
                "spare cash.",
            ))

    if price and shares:
        qs.append(Question(
            "Company A's shares cost $10 and Company B's cost $200. Which is cheaper?",
            [
                "There is no way to tell from the share price",
                "Company A, clearly",
                "Company B, because expensive shares are better quality",
                "Whichever has more shares",
            ],
            0,
            "**Share price on its own tells you nothing.** Two identical businesses can "
            "have wildly different share prices depending only on how many shares they "
            "split themselves into. What matters is the price against what the company "
            f"earns — {name}'s whole business costs about "
            f"${price * shares / 1e9:,.1f} billion at today's price.",
        ))

    if revenue_growth is not None and income_growth is not None:
        faster = "profit" if income_growth > revenue_growth else "sales"
        qs.append(Question(
            "A company's sales grow 10% but its profit falls. What is the most likely "
            "explanation?",
            [
                "Its costs grew faster than its sales",
                "It sold fewer products",
                "The share price fell",
                "It paid a larger dividend",
            ],
            0,
            "Sales tell you whether customers are still coming; they say nothing about "
            "what the company **keeps**. Growing revenue with shrinking profit usually "
            "means costs, discounts or interest are rising faster than the business. "
            f"At {name}, {faster} grew faster last year.",
        ))

    if dividend_yield:
        qs.append(Question(
            f"{name} has a dividend yield of {dividend_yield:,.2f}%. What does that mean?",
            [
                f"Every $100 of stock pays about ${dividend_yield:,.2f} a year in cash",
                f"The dividend grew {dividend_yield:,.2f}% last year",
                f"The share price will rise {dividend_yield:,.2f}%",
                f"{dividend_yield:,.2f}% of profit is paid out",
            ],
            0,
            "Dividend yield is the dividend per share divided by the share price. It is "
            "**the only part of a return a falling price cannot take back** — once the "
            "cash is paid, it is yours.",
        ))

    qs.append(Question(
        "A stock rose 40% over five years. What does that prove about the business?",
        [
            "Nothing on its own — the gain could be earnings or sentiment",
            "That profits grew 40%",
            "That it is a good company",
            "That the dividend was raised",
        ],
        0,
        "A return has two engines: **the business earning more**, and **investors paying "
        "more for the same earnings**. A stock can rise while profit per share falls, if "
        "the market simply decides to pay a higher multiple. That is a real return, but a "
        "fragile one — it can reverse without the company doing anything.",
    ))

    return qs


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
