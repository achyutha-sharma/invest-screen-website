"""
Value Screen — research a stock from its SEC filings.

Every figure on this page comes from a filing. Share price is the one exception
and is optional: without a feed, the valuation rows say so and the other eight
sections carry on unchanged.

Run with: streamlit run app.py
"""

import html
import os

import streamlit as st

from scorecard import score
from sec_equity import extract_equity, value
from sec_ratios import SecClient

st.set_page_config(page_title="Value Screen", page_icon="📈", layout="centered")

E = html.escape
D = "&#36;"          # for markdown, where Streamlit reads bare $ as LaTeX
DH = "$"            # plain markdown only; HTML blocks must use D

# --------------------------------------------------------------------------
# Look
# --------------------------------------------------------------------------
# Deep violet ground, lifted surfaces, one lilac accent. Green and coral are
# reserved for direction -- nothing decorative is allowed to use them.

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap');
:root{
  --bg:#131029; --bg-2:#1A1636; --surf:#201B42; --surf-2:#282152;
  --line:#332B60; --line-2:#3D3470;
  --text:#EDEAF7; --text-2:#B3ACD1; --text-3:#7F779E;
  --acc:#A98BFF; --acc-2:#C7B2FF; --acc-dim:#6E5AB8;
  --up:#5FD69B; --up-bg:#16341F; --down:#FF7B8A; --down-bg:#3A1A25;
  --warn:#F0C46A; --warn-bg:#3A2E17;
  --c1:#A98BFF; --c2:#5FD69B; --c3:#F0C46A; --c4:#6FC6E8; --c5:#FF9BB0;
  --mono:'IBM Plex Mono',ui-monospace,Menlo,monospace;
}
.stApp{background:
  radial-gradient(1100px 620px at 12% -8%, #2A2159 0%, transparent 62%),
  radial-gradient(900px 520px at 96% 4%, #22284F 0%, transparent 58%), var(--bg);
  background-attachment:fixed}
html,body,[class*="css"],.stApp,p,span,div,label{
  font-family:'Archivo',system-ui,-apple-system,sans-serif; color:var(--text)}
.block-container{max-width:880px;padding-top:2.4rem;padding-bottom:4rem}
h1,h2,h3,h4{color:var(--text);letter-spacing:-.02em}

/* masthead */
.mast{display:flex;align-items:center;gap:.7rem;flex-wrap:wrap;
  border-bottom:1px solid var(--line);padding-bottom:.9rem;margin-bottom:1.4rem}
.logo{display:grid;place-items:center;width:32px;height:32px;border-radius:9px;
  background:linear-gradient(150deg,var(--acc),#7B5FE0);color:#15112B;font-weight:800;
  font-size:.76rem;box-shadow:0 4px 16px -4px rgba(169,139,255,.6)}
.mark{font-size:1.18rem;font-weight:700}
.mark span{color:var(--acc)}
.hero{font-size:2.05rem;font-weight:800;letter-spacing:-.035em;line-height:1.14;
  margin:0 0 .6rem;max-width:19ch}
.hero em{font-style:normal;background:linear-gradient(180deg,transparent 60%,rgba(169,139,255,.32) 60%)}
.sub{font-size:1rem;color:var(--text-2);max-width:54ch;margin:0 0 1.4rem}

/* company head */
.tk{font-family:var(--mono);font-size:.7rem;font-weight:700;letter-spacing:.06em;
  color:var(--acc);background:rgba(169,139,255,.13);border:1px solid var(--acc-dim);
  padding:.22rem .5rem;border-radius:4px}
h2.co{margin:.55rem 0 .3rem;font-size:1.8rem;font-weight:800}
.one{font-size:.96rem;color:var(--text-2);max-width:62ch;margin:0}

/* headline strip */
.five{display:grid;grid-template-columns:repeat(6,1fr);gap:1px;margin-top:1.3rem;
  background:var(--line);border:1px solid var(--line);border-radius:10px;overflow:hidden}
@media (max-width:900px){.five{grid-template-columns:repeat(3,1fr)}}
@media (max-width:520px){.five{grid-template-columns:repeat(2,1fr)}}
.fv{background:var(--surf);padding:.9rem .95rem}
.fv .k{display:block;font-size:.58rem;letter-spacing:.11em;text-transform:uppercase;
  color:var(--text-3);font-weight:700;margin-bottom:.3rem;line-height:1.3}
.fv .v{display:block;font-family:var(--mono);font-size:1.28rem;font-weight:700;
  letter-spacing:-.025em;color:#FFFFFF}
.fv .v.good{color:var(--up)} .fv .v.watch{color:var(--warn)} .fv .v.weak{color:var(--down)}
.fv .v.dim{color:var(--text-3);font-size:.9rem}
.fv .d{display:block;font-size:.7rem;color:var(--text-2);margin-top:.35rem;line-height:1.45}

/* section heads */
.sh{display:flex;align-items:baseline;gap:.7rem;margin:2rem 0 .75rem}
.sh .n{font-family:var(--mono);font-size:.62rem;font-weight:700;color:var(--acc);letter-spacing:.12em}
.sh h3{font-size:1rem;font-weight:700;margin:0}
.sh .note{margin-left:auto;font-size:.71rem;color:var(--text-3);font-family:var(--mono)}
.panel{background:var(--surf);border:1px solid var(--line);border-radius:10px;padding:1.1rem 1.15rem}

/* income flow */
.frow{display:flex;align-items:center;gap:.85rem;margin-bottom:.55rem}
.frow:last-child{margin-bottom:0}
.flab{font-size:.83rem;color:var(--text-2);flex:0 0 150px}
.flab b{color:var(--text);font-weight:600;display:block;font-size:.86rem}
.flab i{font-style:normal;font-size:.69rem;color:var(--text-3)}
.fbar{flex:1;height:24px;border-radius:5px;background:var(--line);overflow:hidden}
.fbar div{height:100%}
.famt{font-family:var(--mono);font-size:.86rem;font-weight:700;flex:0 0 82px;
  text-align:right;color:#FFFFFF}
@media (max-width:560px){.flab{flex:0 0 104px}.famt{flex:0 0 66px;font-size:.78rem}}

/* quarters */
.qrow{display:grid;grid-template-columns:repeat(4,1fr);gap:.55rem}
@media (max-width:600px){.qrow{grid-template-columns:repeat(2,1fr)}}
.qc{border:1px solid var(--line);border-radius:8px;padding:.7rem .75rem;background:var(--bg-2)}
.qc.pending{border-style:dashed;opacity:.55}
.qc .ql{font-family:var(--mono);font-size:.62rem;color:var(--text-3);font-weight:700;display:block}
.qc .qv{font-family:var(--mono);font-size:1.02rem;font-weight:700;display:block;
  margin-top:.3rem;color:#FFFFFF}
.qc .qv.up{color:var(--up)} .qc .qv.down{color:var(--down)}
.qc .qs{font-size:.67rem;color:var(--text-3);display:block;margin-top:.15rem}
.runrate{display:flex;gap:.7rem;margin-top:1rem;padding:.8rem .95rem;
  background:rgba(169,139,255,.08);border:1px solid var(--acc-dim);border-radius:8px;
  font-size:.88rem;color:var(--text-2)}
.runrate b{color:#FFFFFF}

/* chart */
.chart svg{display:block;width:100%;height:auto}
.ckey{display:flex;gap:1.1rem;font-family:var(--mono);font-size:.67rem;margin-bottom:.4rem}
.ckey span{display:flex;align-items:center;gap:.4rem;color:var(--text-2)}
.ln{width:15px;height:2.5px;border-radius:2px;display:inline-block}
.cfoot{font-size:.77rem;color:var(--text-3);margin:.6rem 0 0;max-width:72ch}

/* scorecard */
.stars{display:flex;align-items:center;gap:.9rem;flex-wrap:wrap;margin-bottom:.5rem}
.sdots{display:flex;gap:.35rem}
.sd{width:20px;height:20px;border-radius:50%;background:var(--line)}
.sd.on{background:var(--acc);box-shadow:0 0 14px -3px var(--acc)}
.sd.half{background:linear-gradient(90deg,var(--acc) 50%,var(--line) 50%)}
.sval{font-family:var(--mono);font-size:1.9rem;font-weight:700;color:#FFFFFF}
.sverd{font-size:1rem;font-weight:700;margin-left:auto}
.crow{display:flex;gap:.8rem;padding:.75rem 0;border-top:1px solid var(--line)}
.cpip{width:8px;height:8px;border-radius:50%;flex:0 0 8px;margin-top:.45rem}
.cpip.good{background:var(--up)} .cpip.mid{background:var(--warn)} .cpip.bad{background:var(--down)}
.cmain b{display:block;font-size:.87rem;font-weight:700;margin-bottom:.12rem;color:#FFFFFF}
.cmain span{font-size:.84rem;color:var(--text-2);line-height:1.55}
.cmain span b{display:inline;color:#FFFFFF}
.cscore{font-family:var(--mono);font-size:.79rem;font-weight:700;color:var(--text-3);margin-left:auto}
.sfoot{background:rgba(240,196,106,.08);border:1px solid #4E3E1E;border-radius:8px;
  padding:.8rem .95rem;margin-top:1rem;font-size:.85rem;color:var(--text-2);line-height:1.6}
.sfoot b{color:var(--warn)}
.skip{font-size:.79rem;color:var(--text-3);margin-top:.8rem}

/* notes */
.note-list p{position:relative;padding:.5rem 0 .5rem 1.25rem;margin:0;font-size:.85rem;
  color:var(--text-2);border-bottom:1px solid var(--line)}
.note-list p:last-child{border-bottom:0}
.note-list p::before{content:"";position:absolute;left:.3rem;top:1.05em;width:5px;height:5px;
  border-radius:50%;background:var(--text-3)}
.disc{font-size:.77rem;color:var(--text-3);margin-top:2rem;border-top:1px solid var(--line);
  padding-top:1rem;max-width:70ch}


/* mode toggle */
.modes{display:inline-flex;gap:.25rem;margin:1.2rem 0 .2rem;padding:.25rem;background:var(--surf);
  border:1px solid var(--line-2);border-radius:9px}
/* teach */
.gbar{display:flex;gap:.4rem;margin:1.3rem 0 1.2rem}
.gs{flex:1;height:5px;border-radius:3px;background:var(--line-2)}
.gs.done,.gs.now{background:var(--acc)}
.gnum{font-family:var(--mono);font-size:.63rem;font-weight:700;letter-spacing:.12em;color:var(--acc)}
.gtitle{font-size:1.5rem;font-weight:800;letter-spacing:-.03em;margin:.35rem 0 1rem;max-width:22ch}
.lead{font-size:1.06rem;color:var(--text);max-width:52ch;line-height:1.6;margin:0 0 1.1rem}
.lead b{font-weight:700;color:#FFFFFF}
.big{font-family:var(--mono);font-size:2.8rem;font-weight:700;letter-spacing:-.035em;
  line-height:1;display:block;margin:.1rem 0 .4rem;color:#FFFFFF}
.big.up{color:var(--up)} .big.down{color:var(--down)}
.bigsub{font-size:.94rem;color:var(--text-2);margin:0 0 1.2rem;max-width:50ch}
.bigsub b{color:#FFFFFF}
.split2{display:flex;height:32px;border-radius:7px;overflow:hidden;background:var(--line)}
.split2 div{height:100%}
.skey{display:flex;flex-wrap:wrap;gap:1rem;margin-top:.65rem}
.skey span{display:flex;align-items:center;gap:.4rem;font-size:.84rem;color:var(--text-2)}
.skey i{width:11px;height:11px;border-radius:3px;display:inline-block}
.skey b{font-family:var(--mono);font-weight:700;color:#FFFFFF}
.gloss{border:1px solid var(--line);border-radius:9px;overflow:hidden}
.gl{padding:.9rem 1rem;border-bottom:1px solid var(--line)}
.gl:last-child{border-bottom:0}
.gl .t{display:flex;align-items:baseline;gap:.7rem}
.gl .t b{font-size:.95rem;font-weight:700;color:#FFFFFF}
.gl .t i{font-style:normal;font-size:.78rem;color:var(--text-3)}
.gl .t span{margin-left:auto;font-family:var(--mono);font-size:1rem;font-weight:700;color:#FFFFFF}
.gl p{margin:.45rem 0 0;font-size:.85rem;color:var(--text-2);line-height:1.6;max-width:62ch}
.gl p b{color:#FFFFFF}
.finish{background:rgba(169,139,255,.08);border:1px solid var(--acc-dim);border-radius:9px;
  padding:1.15rem 1.25rem;margin-top:1.2rem}
.finish h4{margin:0 0 .5rem;font-size:1rem;color:#FFFFFF}
.finish p{margin:0;font-size:.9rem;color:var(--text-2);max-width:56ch}

/* streamlit widgets */
.stTextInput input{background:var(--surf) !important;color:var(--text) !important;
  border:1px solid var(--line-2) !important;border-radius:8px !important;
  font-size:1rem !important;padding:.8rem 1rem !important}
.stTextInput input:focus{border-color:var(--acc) !important;
  box-shadow:0 0 0 3px rgba(169,139,255,.18) !important}
.stTextInput label{color:var(--text-3) !important;font-size:.66rem !important;
  letter-spacing:.13em !important;text-transform:uppercase !important;font-weight:700 !important}
.stButton button{background:var(--surf);color:var(--text-2);border:1px solid var(--line-2);
  border-radius:20px;font-weight:600;font-size:.86rem;padding:.35rem .9rem}
.stButton button:hover{border-color:var(--acc);color:var(--acc)}
div[data-testid="stExpander"]{border-color:var(--line) !important;background:var(--surf)}
div[data-testid="stExpander"] summary{color:var(--text) !important}
.stSelectbox div[data-baseweb="select"]>div{background:var(--surf);border-color:var(--line-2)}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="mast"><span class="logo">VS</span>'
            '<span class="mark">Value<span>Screen</span></span></div>',
            unsafe_allow_html=True)

user_agent = os.environ.get("SEC_USER_AGENT")
if not user_agent:
    st.error("Set SEC_USER_AGENT to your name and email. The SEC turns away "
             "requests that do not identify the caller.")
    st.stop()

client = SecClient(user_agent=user_agent)


@st.cache_data(show_spinner=False)
def search(q: str):
    return client.search(q)


@st.cache_data(show_spinner=False)
def facts(cik: str):
    return client.company_facts(cik)


@st.cache_data(show_spinner=False)
def profile(cik: str):
    return client.company_profile(cik)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def money(v, decimals=1, html=True):
    """Human-scaled dollars: 46,300,000,000 -> $46.3bn.

    html=True emits the &#36; entity. Streamlit reads a pair of bare dollar
    signs as a LaTeX expression and eats every tag between them, so any figure
    going into an unsafe_allow_html block must use the entity.
    """
    if v is None:
        return "—"
    a = abs(v)
    sign = "−" if v < 0 else ""
    d = D if html else DH
    if a >= 1e9:
        return f"{sign}{d}{a / 1e9:.{decimals}f}bn"
    if a >= 1e6:
        return f"{sign}{d}{a / 1e6:.0f}m"
    return f"{sign}{d}{a:,.0f}"


def pct(v, dp=1):
    return "—" if v is None else f"{'+' if v >= 0 else '−'}{abs(v):.{dp}f}%"


def sh(n, title, note=""):
    st.markdown(
        f'<div class="sh"><span class="n">{n}</span><h3>{E(title)}</h3>'
        + (f'<span class="note">{E(note)}</span>' if note else "") + "</div>",
        unsafe_allow_html=True)


def ratio(a, b):
    return None if (a is None or not b) else a / b


# --------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------

if "cik" not in st.session_state:
    st.markdown('<h1 class="hero">Research a stock <em>properly</em>.</h1>'
                '<p class="sub">Straight from SEC filings. Professional terms, '
                "plainly defined.</p>", unsafe_allow_html=True)

query = st.text_input("Company name or ticker", placeholder="Nike, Starbucks, Netflix").strip()

if query:
    try:
        hits = search(query)
    except Exception as e:
        st.error(f"Could not reach the SEC: {e}")
        st.stop()
    if not hits:
        st.warning(f"Nothing matches “{query}”. Only US companies that file with "
                   "the SEC are covered — try a shorter name, or the ticker.")
        st.stop()
    chosen = hits[0] if len(hits) == 1 else st.selectbox(
        "Which company?", hits, format_func=lambda m: f"{m['name']} · {m['ticker']}")
    st.session_state["cik"] = chosen["cik"]
    st.session_state["ticker"] = chosen["ticker"]
    st.session_state["name"] = chosen["name"]

if "cik" not in st.session_state:
    st.caption("Try Nike, Starbucks or Netflix.")
    st.stop()

cik = st.session_state["cik"]
ticker = st.session_state["ticker"]

try:
    with st.spinner("Reading filings"):
        eq = extract_equity(facts(cik), cik=cik)
except ValueError as e:
    st.warning(str(e))
    st.stop()
except Exception as e:
    st.error(f"Could not load filings: {e}")
    st.stop()

prof = profile(cik)
latest = eq.latest
val = value(eq, price=None)          # no price feed wired yet
card = score(eq, val)


# --------------------------------------------------------------------------
# Teach mode
# --------------------------------------------------------------------------
# Six short slides on the company already on screen. Every figure is the same
# one the research view shows -- nothing is written twice, and nothing here is
# invented for the sake of a lesson.

def teach_slide(i, eq, latest, card):
    rev = latest.get("revenue"); ni = latest.get("net_income")
    eps = latest.get("eps"); dps = latest.get("dps")
    shares = latest.get("shares"); ebit = latest.get("ebit")
    ocf, capex = latest.get("ocf"), latest.get("capex")
    fcf = None if (ocf is None or capex is None) else ocf - capex
    margin = None if (ni is None or not rev) else 100 * ni / rev
    name = eq.entity.split(",")[0].title()

    if i == 0:
        st.markdown(f'<p class="lead">One share of {E(name)} is a <b>tiny piece</b> of the '
                    "company." + (f" The business is cut into <b>{shares:,.0f}</b> shares."
                                  if shares else "") + "</p>", unsafe_allow_html=True)
        if rev and ni is not None:
            st.markdown(f'<span class="big">{money(rev)}</span>'
                        f'<p class="bigsub">of sales last year, of which <b>{money(ni)}</b> '
                        "was profit. That profit is what your slice has a claim on.</p>",
                        unsafe_allow_html=True)
        with st.expander("Why the share price alone tells you nothing"):
            st.markdown(
                f"A {DH}10 share is not cheaper than a {DH}200 share.\n\n"
                f"Two companies, both worth {DH}100 million. One split itself into 10 million "
                f"shares ({DH}10 each), the other into 500,000 ({DH}200 each). **Identical "
                "businesses, identical value, wildly different share prices.**\n\n"
                "What matters is the price against what the company earns — the P/E, in slide 2.")

    elif i == 1:
        st.markdown('<p class="lead">Five terms cover most of a stock page. '
                    "<b>Formal name, then what it actually means.</b></p>",
                    unsafe_allow_html=True)
        terms = [
            ("EPS", "earnings per share",
             f"{D}{eps:,.2f}" if eps is not None else "—",
             "The profit that belongs to one share — total profit divided by the number of "
             "shares. <b>The engine under the price:</b> over long stretches a share price "
             "tends to follow it."),
            ("Revenue", "top line", money(rev),
             "Everything customers paid, before a single cost is taken out. Tells you whether "
             "people are still buying — <b>not</b> whether the company keeps any of it."),
            ("Net margin", "net profit margin",
             f"{margin:,.1f}%" if margin is not None else "—",
             f"How much of every {D}100 of sales survives as profit. <b>Falling margin means "
             "the company is spending more to earn the same.</b>"),
            ("Free cash flow", "cash after capital spending", money(fcf),
             "What is left after running the business and paying for new equipment. "
             "<b>Profit is an opinion. Cash is a fact.</b>"),
            ("Dividend per share", "cash paid to owners",
             f"{D}{dps:,.2f}" if dps else "none",
             "Cash handed to shareholders each year. <b>The only part of a return a falling "
             "price cannot take back</b> — once paid, it is yours."),
        ]
        st.markdown('<div class="gloss">' + "".join(
            f'<div class="gl"><div class="t"><b>{E(t)}</b><i>{E(g)}</i>'
            f"<span>{v}</span></div><p>{p}</p></div>" for t, g, v, p in terms)
            + "</div>", unsafe_allow_html=True)

    elif i == 2:
        if rev and ebit is not None:
            keep = 100 * ebit / rev
            st.markdown('<p class="lead">Of every dollar customers spend, this much survives '
                        "as <b>operating profit</b>.</p>", unsafe_allow_html=True)
            st.markdown(f'<span class="big">{D}{keep:.0f}</span>'
                        f'<p class="bigsub">out of every {D}100 of sales. The rest went on '
                        "making the product and running the company.</p>",
                        unsafe_allow_html=True)
        else:
            st.markdown('<p class="lead">This filing does not tag operating income, so the '
                        "cost breakdown is not available.</p>", unsafe_allow_html=True)
        with st.expander("Why margin matters more than size"):
            st.markdown(
                "A company selling twice as much is not twice as good if it keeps half as much "
                "of each sale.\n\n**Margin is the quality of the sales; revenue is only the "
                "quantity.** A rising revenue line with a falling margin usually means the "
                "company is buying growth with discounts.")

    elif i == 3:
        eps_hist = eq.series("eps")
        if len(eps_hist) >= 4:
            first, last_v = eps_hist[0][1], eps_hist[-1][1]
            n = len(eps_hist) - 1
            if first > 0 and last_v > 0:
                g = (last_v / first) ** (1 / n) - 1
                st.markdown('<p class="lead">Profit per share, over the whole period the '
                            "filings cover.</p>", unsafe_allow_html=True)
                st.markdown(
                    f'<span class="big {"up" if g >= 0 else "down"}">'
                    f'{"+" if g >= 0 else "−"}{abs(g) * 100:.1f}%</span>'
                    f'<p class="bigsub">a year on average, from <b>{D}{first:,.2f}</b> in '
                    f"{E(eps_hist[0][0])} to <b>{D}{last_v:,.2f}</b> in "
                    f"{E(eps_hist[-1][0])}.</p>", unsafe_allow_html=True)
        with st.expander("Why this is the number to watch"):
            st.markdown(
                "A share price is ultimately a claim on profit per share. Over a year the two "
                "can move in opposite directions; over a decade they rarely do.\n\n"
                "**A stock can rise while profit per share falls** — that happens when "
                "investors simply decide to pay more for the same earnings. It is a real "
                "return, but a fragile one, because it can reverse without the company doing "
                "anything.")

    elif i == 4:
        st.markdown('<p class="lead">The scorecard rates <b>what the filings show</b> — five '
                    "things a company has already reported.</p>", unsafe_allow_html=True)
        colour = {"good": "var(--up)", "mid": "var(--warn)", "bad": "var(--down)"}[card.tone]
        st.markdown(f'<span class="big" style="color:{colour}">{card.stars:.1f}<span '
                    f'style="font-size:1.2rem;color:var(--text-3)">/5</span></span>'
                    f'<p class="bigsub">{E(card.verdict)}. Section 08 shows each component and '
                    "why it scored what it did.</p>", unsafe_allow_html=True)
        with st.expander("What a score cannot tell you"):
            st.markdown(
                "**It is not a prediction and not advice.**\n\n"
                "A strong company bought at too high a price is still a poor investment, and a "
                "weak one can rise for years. The score measures evidence already filed — the "
                "future is not in the filings, and anyone claiming otherwise is guessing.")

    else:
        st.markdown('<p class="lead">Three things most people never learn.</p>',
                    unsafe_allow_html=True)
        st.markdown('<div class="finish"><h4>🎉 That is a company, read end to end.</h4>'
                    "<p><b>A rising stock is not a better business.</b> "
                    "<b>A great business can be a bad investment at the wrong price.</b> "
                    "<b>One number never tells the whole story.</b></p></div>",
                    unsafe_allow_html=True)
        with st.expander("Where to go from here"):
            st.markdown(
                "Switch to **Research** for the full picture on this company: where every "
                "dollar of revenue goes, how the current year is tracking, the ten-year "
                "history, and each component of the score.\n\n"
                "Then try a company you already know something about. The numbers make more "
                "sense when you can check them against what you expect.")


TEACH_TITLES = [
    "What am I buying?",
    "The words you will see",
    "What does it keep?",
    "Is it growing?",
    "What is the score?",
    "You have read a company",
]

# --------------------------------------------------------------------------
# Company head + headline strip
# --------------------------------------------------------------------------

st.markdown(f'<span class="tk">{E(ticker)}</span><h2 class="co">{E(eq.entity)}</h2>'
            f'<p class="one">{E(prof.get("industry") or "")}'
            f'{" · " if prof.get("industry") else ""}CIK {E(cik)} · '
            f'{E(latest.label)} · Form 10-K</p>', unsafe_allow_html=True)

mode = st.radio("View", ["Research", "Teach me"], horizontal=True,
                label_visibility="collapsed", key="mode")

eps = latest.get("eps")
dps = latest.get("dps")
rev = latest.get("revenue")
ni = latest.get("net_income")
margin = None if (ni is None or not rev) else 100 * ni / rev

if mode == "Teach me":
    step = st.session_state.get("step", 0)
    n = len(TEACH_TITLES)
    st.markdown('<div class="gbar">' + "".join(
        f'<div class="gs {"done" if j < step else "now" if j == step else ""}"></div>'
        for j in range(n)) + "</div>", unsafe_allow_html=True)
    st.markdown(f'<span class="gnum">Step {step + 1} of {n}</span>'
                f'<h3 class="gtitle">{E(TEACH_TITLES[step])}</h3>', unsafe_allow_html=True)

    teach_slide(step, eq, latest, card)

    back, fwd, _ = st.columns([1, 1, 3])
    if step > 0 and back.button("Back"):
        st.session_state["step"] = step - 1
        st.rerun()
    if step < n - 1 and fwd.button("Next"):
        st.session_state["step"] = step + 1
        st.rerun()

    st.markdown('<p class="disc">Every figure comes from filings made to the U.S. Securities '
                "and Exchange Commission. Educational only — not advice to buy or sell "
                "anything.</p>", unsafe_allow_html=True)
    if st.button("← Search another company"):
        for k in ("cik", "ticker", "name", "step"):
            st.session_state.pop(k, None)
        st.rerun()
    st.stop()

strip = [
    ("Score", f"{card.stars:.1f}/5", card.tone, "see section 08 for why"),
    ("Share price", "no feed", "dim", "not from filings — add a price source"),
    ("EPS", f"{D}{eps:,.2f}" if eps is not None else "—", "",
     "earnings per share — profit split per share"),
    ("P/E ratio", "needs price", "dim", "price-to-earnings"),
    ("Dividend per share", f"{D}{dps:,.2f}" if dps else "none", "",
     "cash declared per share, per year"),
    ("Net margin", f"{margin:,.2f}%" if margin is not None else "—",
     "good" if margin and margin > 15 else "watch" if margin and margin > 7 else "weak",
     "net profit margin — kept from every " + D + "100 of sales"),
]
st.markdown('<div class="five">' + "".join(
    f'<div class="fv"><span class="k">{E(k)}</span>'
    f'<span class="v {t}">{v}</span><span class="d">{d}</span></div>'
    for k, v, t, d in strip) + "</div>", unsafe_allow_html=True)

# --------------------------------------------------------------------------
# 01 the numbers
# --------------------------------------------------------------------------

sh("01", "The numbers", latest.label)
fcf = None
if latest.get("ocf") is not None and latest.get("capex") is not None:
    fcf = latest.get("ocf") - latest.get("capex")

rows = [
    ("EPS — earnings per share", f"{D}{eps:,.2f}" if eps is not None else "—",
     f"Last year's profit split across {latest.get('shares'):,.0f} shares."
     if latest.get("shares") else "Profit belonging to one share.",
     "Over long stretches a share price tends to follow this figure."),
    ("Revenue", money(rev, html=False), "Everything customers paid, before any cost.",
     "Tells you whether customers are still coming — not whether the company keeps any of it."),
    ("Net income", money(ni, html=False), "What was left after every cost.",
     "The bottom line. Compare its direction against revenue: profit growing slower than "
     "sales means costs are rising faster than the business."),
    ("Free cash flow", money(fcf, html=False),
     f"Cash after running the business and its capital spending."
     + (f" Against {money(ni, html=False)} of reported profit." if ni else ""),
     "Profit is an opinion. Cash is a fact."),
    ("Dividend per share", f"{D}{dps:,.2f}" if dps else "none declared",
     "Cash the company declared for each share." if dps
     else "This company pays no dividend — the cash is reinvested instead.",
     "The only part of a return a falling price cannot take back."),
]
for label, v, says, why in rows:
    with st.expander(f"{label}   ·   {v.replace('&#36;', '$')}"):
        st.markdown(f"{says}\n\n**Why it matters.** {why}")

# --------------------------------------------------------------------------
# 02 where the money goes
# --------------------------------------------------------------------------

gross = latest.get("gross_profit")
ebit = latest.get("ebit")
capex = latest.get("capex")
if rev and (gross is not None or ebit is not None):
    sh("02", "Where the money goes", latest.label)
    lines = [("Revenue", "total sales", rev, "var(--acc)")]
    if gross is not None:
        lines.append(("Cost of revenue", "making the product", -(rev - gross), "var(--c5)"))
        lines.append(("Gross profit", "what is left", gross, "var(--c3)"))
    if ebit is not None:
        if gross is not None:
            lines.append(("Operating costs", "running the business", -(gross - ebit), "var(--c5)"))
        lines.append(("Operating income", "EBIT — before interest and tax", ebit, "var(--up)"))
    if capex is not None:
        lines.append(("Capital spending", "new plant, kit, technology", -capex, "var(--c4)"))

    body = "".join(
        f'<div class="frow"><span class="flab"><b>{E(l)}</b><i>{E(g)}</i></span>'
        f'<span class="fbar"><div style="width:{max(abs(v) / rev * 100, 1.5):.1f}%;'
        f'background:{col}"></div></span>'
        f'<span class="famt">{money(v)}</span></div>'
        for l, g, v, col in lines)
    keep = f"{100 * ebit / rev:.0f}" if ebit is not None else None
    st.markdown(f'<div class="panel">{body}'
                + (f'<p class="cfoot">{D}{keep} of every {D}100 of sales survives to '
                   "operating income.</p>" if keep else "")
                + "</div>", unsafe_allow_html=True)

# --------------------------------------------------------------------------
# 03 this year so far
# --------------------------------------------------------------------------

if eq.quarters:
    sh("03", "This year so far", f"{len(eq.quarters)} of 4 quarters filed")
    ytd = sum(q.get("revenue") for q in eq.quarters if q.get("revenue"))
    run = ytd / len(eq.quarters) * 4
    last_year = rev
    cells = ""
    for i in range(4):
        if i < len(eq.quarters):
            q = eq.quarters[i]
            qeps = q.get("eps")
            cells += (f'<div class="qc"><span class="ql">{q.fp}</span>'
                      f'<span class="qv">{money(q.get("revenue"))}</span>'
                      f'<span class="qs">'
                      + (f'{D}{qeps:,.2f} per share' if qeps is not None else "EPS not filed")
                      + "</span></div>")
        else:
            cells += ('<div class="qc pending"><span class="ql">Q'
                      f'{i + 1}</span><span class="qv">—</span>'
                      '<span class="qs">not filed yet</span></div>')
    rr = ""
    if last_year:
        chg = 100 * (run / last_year - 1)
        rr = (f'<div class="runrate"><span>At this pace the year lands near '
              f'<b>{money(run)}</b> against <b>{money(last_year)}</b> last year — '
              f'<b>{pct(chg)}</b>. <span style="color:var(--text-3)">Arithmetic on the '
              "quarters filed, not a forecast.</span></span></div>")
    st.markdown(f'<div class="panel"><div class="qrow">{cells}</div>{rr}</div>',
                unsafe_allow_html=True)

# --------------------------------------------------------------------------
# 04 ten years
# --------------------------------------------------------------------------

eps_hist = eq.series("eps")
rev_hist = eq.series("revenue")
if len(eps_hist) >= 3 and len(rev_hist) >= 3:
    sh("04", "Ten years", "both starting at 100")
    W, H, L, R, T, B = 780, 200, 34, 10, 12, 24

    def idx(series):
        base = series[0][1]
        return [100 * v / base for _, v in series] if base else []

    ri, ei = idx(rev_hist), idx(eps_hist)
    allv = ri + ei
    lo, hi = min(allv + [100]), max(allv)
    pad = (hi - lo) * .08 or 10
    y0, y1 = lo - pad, hi + pad
    n = max(len(ri), len(ei)) - 1

    def X(i, count):
        return L + (i / max(count - 1, 1)) * (W - L - R)

    def Y(v):
        return T + (1 - (v - y0) / (y1 - y0)) * (H - T - B)

    def path(a):
        return " ".join(f"{'L' if i else 'M'}{X(i, len(a)):.1f},{Y(v):.1f}"
                        for i, v in enumerate(a))

    grid = ""
    for g in range(4):
        v = y0 + (y1 - y0) * g / 3
        y = Y(v)
        grid += (f'<line x1="{L}" y1="{y:.1f}" x2="{W - R}" y2="{y:.1f}" stroke="#332B60"/>'
                 f'<text x="{L - 6}" y="{y + 3.5:.1f}" text-anchor="end" '
                 'font-family="IBM Plex Mono,monospace" font-size="9" font-weight="600" '
                 f'fill="#7F779E">{v:.0f}</text>')
    labels = ""
    for i, (lab, _) in enumerate(eps_hist):
        if i % max(len(eps_hist) // 4, 1) == 0 or i == len(eps_hist) - 1:
            labels += (f'<text x="{X(i, len(eps_hist)):.1f}" y="{H - 7}" text-anchor="middle" '
                       'font-family="IBM Plex Mono,monospace" font-size="9" font-weight="600" '
                       f'fill="#7F779E">&#39;{E(lab[-2:])}</text>')

    st.markdown(f'''<div class="panel chart">
      <div class="ckey"><span><i class="ln" style="background:#A98BFF"></i>revenue</span>
      <span><i class="ln" style="background:#7F779E"></i>profit per share</span></div>
      <svg viewBox="0 0 {W} {H}" role="img" aria-label="Revenue and profit per share, indexed to 100">
        {grid}
        <path d="{path(ei)}" fill="none" stroke="#7F779E" stroke-width="1.9" stroke-dasharray="5 4"/>
        <path d="{path(ri)}" fill="none" stroke="#A98BFF" stroke-width="2.6"
          stroke-linejoin="round" stroke-linecap="round"/>
        {labels}
      </svg>
      <p class="cfoot">Both lines start at 100 so they can be compared. Where profit per share
        outpaces revenue the company is keeping more of what it sells; where it lags, costs or
        the share count are growing faster than the business.</p></div>''',
                unsafe_allow_html=True)

# --------------------------------------------------------------------------
# 08 the scorecard
# --------------------------------------------------------------------------

sh("08", "The scorecard", "what the filings answer")
dots = ""
for i in range(5):
    f = card.stars - i
    dots += f'<span class="sd {"on" if f >= 1 else "half" if f >= .5 else ""}"></span>'
colour = {"good": "var(--up)", "mid": "var(--warn)", "bad": "var(--down)"}[card.tone]
comp_rows = "".join(
    f'<div class="crow"><span class="cpip {c.tone}"></span>'
    f'<span class="cmain"><b>{E(c.name)}</b><span>{c.why}</span></span>'
    f'<span class="cscore">{c.score}/2</span></div>' for c in card.components)
skipped = ""
if card.unscored:
    skipped = ('<p class="skip">Not scored: '
               + "; ".join(E(u) for u in card.unscored) + "</p>")

st.markdown(f'''<div class="panel">
  <div class="stars"><span class="sval">{card.stars:.1f}</span>
    <span class="sdots">{dots}</span>
    <span class="sverd" style="color:{colour}">{E(card.verdict)}</span></div>
  {comp_rows}{skipped}
  <div class="sfoot"><b>What this is not.</b> It does not predict the share price and is not
    advice to buy or sell. A high score at the wrong price still loses money, and a low score
    can rise for years. It scores what the company has already reported — the future is not in
    the filings.</div></div>''', unsafe_allow_html=True)

# --------------------------------------------------------------------------
# Notes and footer
# --------------------------------------------------------------------------

if eq.notes:
    sh("09", "Worth knowing", "how these figures were built")
    st.markdown('<div class="panel note-list">'
                + "".join(f"<p>{E(n)}</p>" for n in eq.notes) + "</div>",
                unsafe_allow_html=True)

st.markdown('<p class="disc">Every figure comes from filings made to the U.S. Securities and '
            "Exchange Commission. Share price is not yet wired in, so valuation rows are "
            "unavailable. Educational research only — not advice to buy or sell anything.</p>",
            unsafe_allow_html=True)

if st.button("← Search another company"):
    for k in ("cik", "ticker", "name"):
        st.session_state.pop(k, None)
    st.rerun()
