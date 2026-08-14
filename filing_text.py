"""
The parts of a filing that are prose, not XBRL.

Management's discussion, risk factors and the competition paragraph are written
in HTML, so they cannot be looked up by tag the way every other figure in this
tool can. They have to be fetched, sliced by item heading, and read.

Two rules keep this honest:

  1. Nothing is summarised or paraphrased. Sentences are quoted verbatim, so
     what appears on the page is what the company wrote.
  2. Where a section cannot be located, the caller is told plainly rather than
     shown a best guess. A wrong quote is worse than a missing one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{doc}"

# Management explains results in a small, predictable set of phrasings. These
# are the ones that carry a cause, which is exactly what a reader wants and the
# only part we are willing to surface.
CAUSE_PATTERNS = [
    r"primarily due to",
    r"primarily driven by",
    r"principally due to",
    r"was driven by",
    r"were driven by",
    r"driven primarily by",
    r"partially offset by",
    r"partly offset by",
    r"reflecting",
    r"as a result of",
    r"attributable to",
]
_CAUSE = re.compile("|".join(CAUSE_PATTERNS), re.I)

# A sentence worth quoting also names a movement, otherwise it is boilerplate.
_MOVEMENT = re.compile(
    r"\b(increase[sd]?|decrease[sd]?|grew|growth|decline[sd]?|rose|fell|improved|"
    r"expanded|contracted|higher|lower)\b", re.I)


@dataclass
class FilingText:
    """What could be pulled out of one filing's prose."""

    form: str = ""
    filed: str = ""
    url: str = ""
    mda: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    competitors: list[str] = field(default_factory=list)
    competition_note: str = ""
    problems: list[str] = field(default_factory=list)

    @property
    def anything(self) -> bool:
        return bool(self.mda or self.risks or self.competitors)


# --------------------------------------------------------------------------
# HTML to text
# --------------------------------------------------------------------------

_TAG = re.compile(r"<[^>]+>")
_SCRIPT = re.compile(r"<(script|style)\b.*?</\1>", re.I | re.S)
_ENTITY = {
    "&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
    "&#8217;": "'", "&#8216;": "'", "&#8220;": '"', "&#8221;": '"',
    "&#8212;": "—", "&#8211;": "–", "&#39;": "'", "&rsquo;": "'", "&ldquo;": '"',
    "&rdquo;": '"', "&mdash;": "—", "&ndash;": "–", "&#160;": " ",
}


def to_text(html: str) -> str:
    """Strip a filing's HTML down to readable prose."""
    s = _SCRIPT.sub(" ", html)
    # Block-level tags become paragraph breaks so sentences do not run together.
    s = re.sub(r"</(p|div|tr|table|h[1-6]|li)>", "\n", s, flags=re.I)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = _TAG.sub(" ", s)
    for k, v in _ENTITY.items():
        s = s.replace(k, v)
    s = re.sub(r"&#\d+;", " ", s)
    s = re.sub(r"[ \t\xa0]+", " ", s)
    s = re.sub(r"\n{2,}", "\n", s)
    return s


def _item_span(text: str, start_pat: str, end_pat: str) -> str | None:
    """Text between two item headings.

    Filings repeat item headings in the table of contents, so the *last*
    plausible start is taken -- the contents entry comes first, the real
    section later. A span under 400 characters is another contents hit and is
    rejected rather than returned as a section.
    """
    starts = [m.start() for m in re.finditer(start_pat, text, re.I)]
    if not starts:
        return None
    # Try each candidate from the last backwards: the table of contents match
    # comes first, the real section later, and any cross-reference later still.
    for s in reversed(starts):
        after = text[s:]
        # Search for the end *within* the text after this start. Looking at the
        # whole document would pair a late start with an early contents-page
        # end and produce an empty span.
        e = re.search(end_pat, after, re.I)
        span = after[: e.start()] if e and e.start() > 400 else after[:120_000]
        if len(span) > 400:
            return span
    return None


# --------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------


def extract_mda(text: str, limit: int = 4) -> tuple[list[str], str]:
    """Sentences where management explains a movement, in their own words."""
    span = _item_span(
        text,
        r"item\s*[27][\.\s]{0,4}(management|discussion)",
        r"item\s*(7a|3)[\.\s]{0,4}(quantitative|qualitative)",
    )
    if span is None:
        return [], "Management's discussion could not be located in this filing."

    # Drop the item heading. It ends at the first line break, and carries no
    # full stop -- which is why leaving it in fuses it onto the first sentence.
    if "\n" in span[:250]:
        first, rest = span.split("\n", 1)
        if re.search(r"item\s*[27]\b|management|discussion", first, re.I) and len(rest) > 400:
            span = rest

    out = []
    for raw in re.split(r"(?<=[.!?])\s+", span):
        s = " ".join(raw.split())
        # A section heading carries no full stop, so it fuses onto the
        # sentence after it. When a capitalised word follows a lowercase one
        # near the front, that is where the real sentence begins.
        if not (60 <= len(s) <= 320):
            continue
        if not (_CAUSE.search(s) and _MOVEMENT.search(s)):
            continue
        # Skip anything pointing elsewhere, and any leftover table wreckage.
        if re.search(r"\bsee (note|item|part)\b|\btable of contents\b", s, re.I):
            continue
        if sum(c.isdigit() for c in s) > len(s) * 0.30:
            continue
        out.append(s)
        if len(out) >= limit:
            break

    if not out:
        return [], ("Management's discussion was found, but no sentence in it explains a "
                    "movement in plain terms.")
    return out, ""


def extract_risks(text: str, limit: int = 6) -> tuple[list[str], str]:
    """Risk factor headings -- the bold one-liners, not the paragraphs beneath."""
    span = _item_span(
        text,
        r"item\s*1a[\.\s]{0,4}risk\s*factors",
        r"item\s*1b[\.\s]{0,4}unresolved|item\s*2[\.\s]{0,4}propert",
    )
    if span is None:
        return [], "The risk factors section could not be located in this filing."

    # A real Item 1A is closed by Item 1B or Item 2. _item_span cuts there, so
    # a span that ran to the length cap instead was never a section at all --
    # it is a cross-reference from the financial statements, and everything
    # "inside" it is whatever tables happened to follow.
    if len(span) >= 119_000:
        return [], ("The risk factors heading appears only as a cross-reference in this "
                    "filing, not as a readable section.")

    out, seen = [], set()
    for raw in span.split("\n"):
        s = " ".join(raw.split())
        if not (25 <= len(s) <= 200):
            continue
        # A heading is a complete short statement. Paragraph text that happens
        # to be wrapped ends mid-clause -- on a preposition, article or
        # conjunction -- which is the cleanest way to tell the two apart.
        if s.endswith(".") or s.count(".") > 1:
            continue
        if re.search(r"\b(and|or|the|a|an|of|to|in|for|with|that|which|as|at|by|from)$",
                     s, re.I):
            continue
        if not re.search(r"\b(may|could|might|risk|depend|fail|adverse|affect|if we|"
                         r"our abilit|we (are|do|rely|face))", s, re.I):
            continue
        # Financial-statement rows and headings survive the tests above, so
        # rule them out directly: real risk headings are prose, not figures,
        # and do not shout in capitals or name a balance-sheet date.
        if re.search(r"table of contents|^item\s|^\d|^\W", s, re.I):
            continue
        if sum(c.isdigit() for c in s) > 3:
            continue
        if s.upper() == s:
            continue
        if re.search(r"\b(20\d\d|balance at|maturity|as of \w+ \d)", s, re.I):
            continue
        # A heading is a claim with a verb, not a table label.
        if len(s.split()) < 5:
            continue
        key = s.lower()[:60]
        if key in seen:
            continue
        seen.add(key)
        out.append(s.rstrip(":;,"))
        if len(out) >= limit:
            break

    if not out:
        return [], "Risk factors were found, but no headings could be separated from the text."
    return out, ""


# Company names in a competition paragraph are capitalised runs, often with a
# suffix. Requiring one filters out sentence-initial words and section titles.
_NAME = re.compile(
    r"\b([A-Z][A-Za-z&.\-]*(?:\s+[A-Z][A-Za-z&.\-]*){0,3}"
    r"(?:\s+(?:Inc|Corp|Corporation|Company|Co|Ltd|LLC|plc|Group|Holdings|SE|AG|NV))\b\.?)")

_NOT_A_PEER = re.compile(
    r"^(the|our|we|this|these|item|part|united states|u\.s|company|annual report|"
    r"securities|exchange|commission|form|note|table)\b", re.I)


def extract_competitors(text: str, limit: int = 8) -> tuple[list[str], str, str]:
    """Competitors the company names itself, from the Item 1 competition text."""
    span = _item_span(
        text,
        r"item\s*1[\.\s]{0,4}business",
        r"item\s*1a[\.\s]{0,4}risk\s*factors",
    )
    if span is None:
        return [], "", "The business section could not be located in this filing."

    # The competition discussion is a subsection; find the paragraph around it.
    m = re.search(r"\bcompetit(?:ion|ors|ive)\b", span, re.I)
    if not m:
        return [], "", "This filing does not have a competition section we could find."
    window = span[max(0, m.start() - 500): m.start() + 4000]

    names, seen = [], set()
    for mm in _NAME.finditer(window):
        n = " ".join(mm.group(1).split()).rstrip(".")
        if _NOT_A_PEER.match(n) or len(n) < 4:
            continue
        key = n.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(n)
        if len(names) >= limit:
            break

    note = ""
    for raw in re.split(r"(?<=[.!?])\s+", window):
        s = " ".join(raw.split())
        if 60 <= len(s) <= 300 and re.search(r"\bcompet", s, re.I):
            note = re.sub(r"^(competition|competitors|competitive\s+\w+)\s+(?=[A-Z])", "",
                          s, flags=re.I)
            break

    if not names:
        return [], note, ("The filing discusses competition but does not name specific "
                          "companies in a form we could read.")
    return names, note, ""


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------


def latest_filings(client, cik: str, forms=("10-K", "10-Q", "8-K"), limit: int = 8):
    """Recent filings from the submissions index, newest first."""
    try:
        data = client._get_json(SUBMISSIONS.format(cik=cik), f"sub_{cik}.json")
    except Exception:
        return []
    recent = (data.get("filings") or {}).get("recent") or {}
    cols = ("form", "filingDate", "accessionNumber", "primaryDocument", "primaryDocDescription")
    if not all(c in recent for c in cols[:4]):
        return []

    out = []
    for i in range(len(recent["form"])):
        form = recent["form"][i]
        if forms and not any(form.startswith(f) for f in forms):
            continue
        acc = recent["accessionNumber"][i]
        out.append({
            "form": form,
            "filed": recent["filingDate"][i],
            "accession": acc,
            "doc": recent["primaryDocument"][i],
            "desc": (recent.get("primaryDocDescription") or [""] * (i + 1))[i],
            "url": ARCHIVE.format(cik_int=int(cik), acc_nodash=acc.replace("-", ""),
                                  doc=recent["primaryDocument"][i]),
        })
        if len(out) >= limit:
            break
    return out


def read_filing(client, cik: str, form_prefix: str = "10-K") -> FilingText:
    """Fetch the newest filing of a type and pull its prose sections.

    Never raises. A filing that cannot be fetched or parsed comes back with the
    reasons in `problems`, which the page shows instead of inventing content.
    """
    ft = FilingText()
    hits = [f for f in latest_filings(client, cik, forms=(form_prefix,), limit=1)]
    if not hits:
        ft.problems.append(f"No recent {form_prefix} was found for this filer.")
        return ft

    f = hits[0]
    ft.form, ft.filed, ft.url = f["form"], f["filed"], f["url"]

    try:
        import requests

        r = requests.get(f["url"], timeout=30, headers=client.headers)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        ft.problems.append(f"The filing document could not be downloaded ({e.__class__.__name__}).")
        return ft

    text = to_text(html)
    if len(text) < 5_000:
        ft.problems.append("The filing document was shorter than expected and may be a wrapper "
                           "rather than the report itself.")
        return ft

    ft.mda, why = extract_mda(text)
    if why:
        ft.problems.append(why)

    ft.risks, why = extract_risks(text)
    if why:
        ft.problems.append(why)

    ft.competitors, ft.competition_note, why = extract_competitors(text)
    if why:
        ft.problems.append(why)

    return ft
