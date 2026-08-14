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

from filing_text import latest_filings, read_filing
from peers import suggest
from prices import PriceClient
from scorecard import score
from sec_equity import extract_equity, pe_history, value
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
  --teach:#4FC98C; --teach-2:#7FE0B0; --teach-dim:#2E7A55;
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


/* quotes, risks, peers, filings */
.quote p{margin:0 0 .6rem;font-size:.92rem;color:var(--text-2);line-height:1.68}
.quote p:last-of-type{margin-bottom:0}
.quote .src{display:block;font-family:var(--mono);font-size:.68rem;color:var(--text-3);
  margin-top:.8rem;font-weight:600}
.risk .rr{padding:.7rem 0;border-bottom:1px solid var(--line);font-size:.9rem;color:var(--text-2)}
.risk .rr:first-child{padding-top:0} .risk .rr:last-child{border-bottom:0;padding-bottom:0}
.comp{width:100%;border-collapse:collapse}
.comp th{font-size:.6rem;letter-spacing:.12em;text-transform:uppercase;color:var(--text-3);
  font-weight:700;padding:.55rem .7rem;text-align:right;border-bottom:1px solid var(--line)}
.comp th:first-child{text-align:left}
.comp td{padding:.6rem .7rem;text-align:right;font-family:var(--mono);font-size:.9rem;
  font-weight:700;color:#FFFFFF;border-bottom:1px solid var(--line)}
.comp tr:last-child td{border-bottom:0}
.comp td:first-child{text-align:left;font-family:'Archivo',sans-serif}
.comp tr.self td{background:rgba(169,139,255,.09)}
.comp tr.self td:first-child{color:var(--acc)}
.feed{list-style:none;margin:0;padding:0}
.feed li{display:flex;gap:.8rem;padding:.7rem 0;border-bottom:1px solid var(--line);
  align-items:baseline}
.feed li:first-child{padding-top:0} .feed li:last-child{border-bottom:0;padding-bottom:0}
.ftype{font-family:var(--mono);font-size:.61rem;font-weight:700;padding:.22rem .42rem;
  border-radius:4px;flex:0 0 auto}
.ftype.q{background:rgba(111,198,232,.15);color:#6FC6E8}
.ftype.k{background:rgba(169,139,255,.15);color:var(--acc)}
.ftype.e{background:rgba(95,214,155,.13);color:var(--up)}
.ftype.o{background:rgba(240,196,106,.13);color:var(--warn)}
.fmain{flex:1;min-width:0;font-size:.89rem}
.fmain a{color:var(--text-2);text-decoration:none}
.fmain a:hover{color:var(--acc);text-decoration:underline}
.fwhen{font-family:var(--mono);font-size:.7rem;color:var(--text-3);flex:0 0 auto}
.day{display:inline-flex;align-items:center;gap:.3rem;font-family:var(--mono);font-size:.72rem;
  font-weight:700;padding:.22rem .5rem;border-radius:5px;margin-left:.5rem}
.day.good{background:var(--up-bg);color:var(--up);border:1px solid #22502F}
.day.weak{background:var(--down-bg);color:var(--down);border:1px solid #562733}
.fv .learn{display:block;font-size:.63rem;font-weight:700;color:var(--acc);margin-top:.4rem}
.stSlider label{color:var(--text-2) !important;font-size:.85rem !important;font-weight:600 !important}


.picker{font-size:.66rem;letter-spacing:.13em;text-transform:uppercase;color:var(--text-3);
  font-weight:700;margin:1.4rem 0 .6rem}
.trio{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin-top:2.2rem;
  padding-top:1.5rem;border-top:1px solid var(--line)}
@media (max-width:640px){.trio{grid-template-columns:1fr;gap:1.1rem}}
.tr b{display:block;font-size:.9rem;margin-bottom:.2rem;color:#FFFFFF}
.tr span{font-size:.83rem;color:var(--text-2);line-height:1.5}


/* ---- mode toggle: a segmented control, not radio circles ---------------- */
div[role="radiogroup"]{gap:.25rem !important;padding:.25rem;background:var(--surf);
  border:1px solid var(--line-2);border-radius:9px;display:inline-flex !important;
  margin:1.1rem 0 .2rem}
div[role="radiogroup"] > label{margin:0 !important;padding:.45rem 1.05rem !important;
  border-radius:6px;cursor:pointer;transition:all .15s;background:transparent}
div[role="radiogroup"] > label:hover{background:var(--surf-2)}
/* hide the circle itself */
div[role="radiogroup"] > label > div:first-child{display:none !important}
div[role="radiogroup"] > label p{font-size:.87rem !important;font-weight:600 !important;
  color:var(--text-3) !important;margin:0 !important}
div[role="radiogroup"] > label:has(input:checked){background:var(--teach)}
div[role="radiogroup"] > label:has(input:checked) p{color:#0F1F17 !important;font-weight:700 !important}

/* ---- teach mode is green; research stays violet ------------------------ */
.teach .gbar .gs.done, .teach .gbar .gs.now{background:var(--teach)}
.teach .gnum{color:var(--teach)}
.teach .lead b{color:var(--teach-2)}
.teach .big{color:var(--teach-2)}
.teach .big.up{color:var(--up)} .teach .big.down{color:var(--down)}
.teach .gl .t b{color:#FFFFFF}
.teach .gl .t span{color:var(--teach-2)}
.teach .picker{color:var(--teach)}
.teach .finish{background:rgba(95,214,155,.09);border-color:var(--teach-dim)}
.teach .finish h4{color:var(--teach-2)}
.teach div[data-testid="stExpander"]{border-color:var(--teach-dim) !important}
.teach div[data-testid="stExpander"] summary:hover{color:var(--teach-2) !important}
.teach .stSlider [data-baseweb="slider"] [role="slider"]{background:var(--teach) !important;
  box-shadow:0 2px 10px -2px rgba(95,214,155,.8) !important}
.teach .stSlider [data-baseweb="slider"] div[data-testid="stSliderTickBar"]{color:var(--text-3)}
.teach .btn-next button{background:var(--teach) !important;border-color:var(--teach) !important;
  color:#0F1F17 !important}


/* the glossary links read as the bottom row of the strip, not as controls */
.five{border-bottom-left-radius:0;border-bottom-right-radius:0;border-bottom:0}
div[data-testid="stHorizontalBlock"]:has(button[kind]) .stButton button{
  background:var(--surf);border:1px solid var(--line);border-top:0;border-radius:0;
  color:var(--acc);font-size:.62rem;font-weight:700;padding:.45rem .3rem;
  letter-spacing:.01em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
div[data-testid="stHorizontalBlock"]:has(button[kind]) .stButton button:hover{
  background:var(--surf-2);color:var(--acc-2)}
div[data-testid="stHorizontalBlock"]{gap:1px !important}

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
prices = PriceClient(api_key=os.environ.get("FINNHUB_API_KEY", ""))


@st.cache_data(show_spinner=False)
def search(q: str):
    return client.search(q)


@st.cache_data(show_spinner=False)
def facts(cik: str):
    return client.company_facts(cik)


@st.cache_data(show_spinner=False)
def profile(cik: str):
    return client.company_profile(cik)


@st.cache_data(show_spinner=False, ttl=600)
def quote(ticker: str):
    return prices.quote(ticker)


@st.cache_data(show_spinner=False, ttl=86_400)
def fiscal_prices(ticker: str, ends: tuple):
    return prices.at_fiscal_ends(ticker, list(ends))


@st.cache_data(show_spinner=False, ttl=86_400)
def filings(cik: str):
    return latest_filings(client, cik, limit=8)


@st.cache_data(show_spinner=False, ttl=86_400)
def prose(cik: str):
    """Filing text is best-effort: when a section cannot be read, the page
    simply does not show it rather than showing something wrong."""
    try:
        return read_filing(client, cik)
    except Exception:
        return None


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

POPULAR = [("NKE", "Nike"), ("SBUX", "Starbucks"), ("NFLX", "Netflix"),
           ("AAPL", "Apple"), ("HD", "Home Depot"), ("KO", "Coca-Cola")]

if "cik" not in st.session_state:
    st.markdown('<h1 class="hero">Research a stock <em>properly</em>.</h1>'
                '<p class="sub">Straight from SEC filings. Professional terms, plainly '
                "defined, and never a recommendation.</p>", unsafe_allow_html=True)

query = st.text_input("Company name or ticker", placeholder="Nike, Starbucks, Netflix").strip()

if "cik" not in st.session_state and not query:
    st.markdown('<p class="picker">Or start with one of these</p>', unsafe_allow_html=True)
    for row in (POPULAR[:3], POPULAR[3:]):
        for col, (tk, nm) in zip(st.columns(3), row):
            if col.button(nm, key=f"pop_{tk}", use_container_width=True):
                hits = search(tk)
                if hits:
                    st.session_state["cik"] = hits[0]["cik"]
                    st.session_state["ticker"] = hits[0]["ticker"]
                    st.session_state["name"] = hits[0]["name"]
                    st.rerun()

    st.markdown('''<div class="trio">
      <div class="tr"><b>Filed, not estimated</b>
        <span>Every figure comes from a filing made to the SEC.</span></div>
      <div class="tr"><b>Flags what does not apply</b>
        <span>Some ratios are meaningless for some filers. We say so instead of
        printing them.</span></div>
      <div class="tr"><b>No recommendations</b>
        <span>What happened, and what the price assumes. You decide.</span></div>
    </div>''', unsafe_allow_html=True)

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

q = quote(ticker)
ends = tuple((p.label, p.end.isoformat()) for p in eq.years)
hist_px = fiscal_prices(ticker, ends) if q.available else {}
pe_hist = [v for _, v in pe_history(eq, hist_px)]

val = value(eq, price=q.price if q.available else None,
            day_change_pct=q.day_change_pct)
card = score(eq, val, pe_history=pe_hist or None)


# --------------------------------------------------------------------------
# Teach mode
# --------------------------------------------------------------------------
# Six short slides on the company already on screen. Every figure is the same
# one the research view shows -- nothing is written twice, and nothing here is
# invented for the sake of a lesson.

def teach_slide(i, eq, latest, card, val=None, quote_=None, px_hist=None):
    rev = latest.get("revenue"); ni = latest.get("net_income")
    eps = latest.get("eps"); dps = latest.get("dps")
    shares = latest.get("shares"); ebit = latest.get("ebit")
    gross = latest.get("gross_profit")
    ocf, capex = latest.get("ocf"), latest.get("capex")
    fcf = None if (ocf is None or capex is None) else ocf - capex
    margin = None if (ni is None or not rev) else 100 * ni / rev
    name = eq.entity.split(",")[0].title()

    # ---- 1. what am I buying -------------------------------------------
    if i == 0:
        st.markdown(f'<p class="lead">One share is a <b>tiny piece</b> of the company.'
                    + (f" There are <b>{shares / 1e9:,.2f} billion</b> of them."
                       if shares and shares > 1e8 else
                       f" There are <b>{shares:,.0f}</b> of them." if shares else "")
                    + "</p>", unsafe_allow_html=True)

        # Segment revenue is not in company facts -- only consolidated totals
        # are -- so this shows where each $100 of sales goes rather than which
        # product it came from. Same filing, and it is the more useful half.
        if rev and (gross is not None or ebit is not None):
            parts = []
            if gross is not None:
                parts.append(("Making the product", rev - gross, "var(--c5)"))
                if ebit is not None:
                    parts.append(("Running the company", gross - ebit, "var(--c3)"))
            if ebit is not None:
                parts.append(("Operating profit", ebit, "var(--up)"))
            st.markdown('<p class="picker">Where every ' + D + '100 of sales goes</p>'
                        + '<div class="split2">' + "".join(
                            f'<div style="width:{max(100 * abs(v) / rev, 1.5):.1f}%;'
                            f'background:{c}"></div>' for _, v, c in parts) + "</div>"
                        + '<div class="skey">' + "".join(
                            f'<span><i style="background:{c}"></i>{E(l)} '
                            f'<b>{D}{100 * v / rev:,.0f}</b></span>' for l, v, c in parts)
                        + "</div>", unsafe_allow_html=True)

        cap = val.market_cap if val and val.market_cap else None
        with st.expander(f"Market cap  ·  {money(cap, html=False) if cap else 'needs price'}"):
            st.markdown(
                "Share price × number of shares — what the whole company costs at today's "
                "price.\n\n**This is what tells you how big something is, not the share "
                "price.** A \\$500 share can be better value than a \\$5 one; it depends "
                "how many shares exist and how much the company earns.")

    # ---- 2. the words --------------------------------------------------
    elif i == 1:
        st.markdown('<p class="lead">Five terms cover most of a stock page. '
                    "<b>Formal name, then what it actually means.</b></p>",
                    unsafe_allow_html=True)
        pe = val.pe if val else None
        dy = val.dividend_yield if val else None
        terms = [
            ("EPS", "earnings per share", f"{D}{eps:,.2f}" if eps is not None else "—",
             "The profit that belongs to one share — total profit divided by the number of "
             "shares. <b>The engine under the price:</b> over long stretches a share price "
             "tends to follow it."),
            ("P/E ratio", "price-to-earnings", f"{pe:,.1f}×" if pe else "needs price",
             "How many dollars you pay for each dollar the share earns in a year. <b>High "
             "usually means investors expect growth</b> — it only turns out expensive if that "
             "growth never arrives."),
            ("Net margin", "net profit margin", f"{margin:,.1f}%" if margin is not None else "—",
             f"How much of every {D}100 of sales survives as profit. <b>Falling margin means "
             "the company is spending more to earn the same.</b>"),
            ("Free cash flow", "cash after capital spending", money(fcf),
             "What is left after running the business and paying for new equipment. "
             "<b>Profit is an opinion. Cash is a fact.</b>"),
            ("Dividend yield", "cash paid to owners", f"{dy:,.2f}%" if dy else
             ("none" if not dps else "needs price"),
             "Cash handed to shareholders each year as a percentage of the price. <b>The only "
             "part of a return a falling price cannot take back.</b>"),
        ]
        st.markdown('<div class="gloss">' + "".join(
            f'<div class="gl"><div class="t"><b>{E(t)}</b><i>{E(g)}</i>'
            f"<span>{v}</span></div><p>{p}</p></div>" for t, g, v, p in terms)
            + "</div>", unsafe_allow_html=True)

    # ---- 3. is it getting better ---------------------------------------
    elif i == 2:
        rev_g = ni_g = None
        rs, ns = eq.series("revenue"), eq.series("net_income")
        if len(rs) >= 2 and rs[-2][1]:
            rev_g = 100 * (rs[-1][1] / rs[-2][1] - 1)
        if len(ns) >= 2 and ns[-2][1] and ns[-2][1] > 0:
            ni_g = 100 * (ns[-1][1] / ns[-2][1] - 1)

        bits = []
        if rev_g is not None:
            bits.append(f"Revenue <b>{'+' if rev_g >= 0 else '−'}{abs(rev_g):.1f}%</b>")
        if ni_g is not None:
            bits.append(f"net income <b>{'+' if ni_g >= 0 else '−'}{abs(ni_g):.1f}%</b>")
        st.markdown('<p class="lead">' + (", ".join(bits) + " on last year."
                    if bits else "Not enough filed history to compare years.") + "</p>",
                    unsafe_allow_html=True)

        with st.expander(f"Net margin  ·  {f'{margin:,.2f}%' if margin is not None else '—'}"):
            st.markdown(
                f"Of every \\$100 customers spend, about \\${margin:.0f} becomes profit."
                if margin is not None else "Revenue or profit was not tagged in this filing."
                + "\n\nMargin is the *quality* of sales; revenue is only the quantity. "
                "A rising revenue line with a falling margin usually means growth is being "
                "bought with discounts.")
        with st.expander(f"Free cash flow  ·  {money(fcf, html=False)}"):
            st.markdown(
                (f"Reported profit was {money(ni, html=False)}. Real spare cash was "
                 f"**{money(fcf, html=False)}**.\n\n" if ni and fcf is not None else "")
                + "**Profit is an opinion. Cash is a fact.** Profit involves judgement about "
                "when to count things. Cash either arrived or it did not.")

    # ---- 4. is it expensive --------------------------------------------
    elif i == 3:
        pe = val.pe if val else None
        if pe:
            st.markdown('<p class="lead">The <b>P/E ratio</b> — what you pay for every '
                        + D + "1 of yearly profit.</p>", unsafe_allow_html=True)
            st.markdown(f'<span class="big">{pe:,.1f}×</span>', unsafe_allow_html=True)
        else:
            st.markdown('<p class="lead">A P/E needs a share price, and one is not available '
                        "here. Everything else on this page still comes from the filing.</p>",
                        unsafe_allow_html=True)
        with st.expander("Why the share price alone means nothing"):
            st.markdown(
                "A \\$10 share is not cheaper than a \\$200 share.\n\n"
                "Two companies, both worth \\$100 million. One split itself into 10 million "
                "shares (\\$10 each), the other into 500,000 (\\$200 each). **Identical "
                "businesses, identical value, wildly different share prices.**\n\n"
                "What matters is the price against what the company earns.")

    # ---- 5. what would you have made -----------------------------------
    elif i == 4:
        if px_hist and len(px_hist) >= 2 and eps:
            first_lab, p0 = px_hist[0]
            p1 = quote_.price if quote_ and quote_.available else px_hist[-1][1]
            e_series = eq.series("eps")
            e0 = next((v for lab, v in e_series if lab == first_lab), None)

            amt = st.slider("Amount invested", 100, 10_000, 1_000, 100, format="$%d")
            if e0 and e0 > 0 and p0 > 0:
                price_end = amt * (p1 / p0)
                from_earnings = amt * (eps / e0) - amt
                from_multiple = price_end - amt - from_earnings
                divs = 0.0
                dseries = dict(eq.series("dps"))
                for lab, px in px_hist:
                    d = dseries.get(lab)
                    if d and px:
                        divs += amt * (d / px)
                total = price_end + divs

                st.markdown(
                    f'<span class="big {"up" if total >= amt else "down"}">'
                    f'{D}{total:,.0f}</span>'
                    f'<p class="bigsub">a {"gain" if total >= amt else "loss"} of '
                    f'<b>{D}{abs(total - amt):,.0f}</b> over '
                    f"{len(px_hist) - 1} years.</p>", unsafe_allow_html=True)

                segs = [("business earnings", "var(--c2)", from_earnings),
                        ("investors paying more", "var(--c1)", from_multiple),
                        ("dividends", "var(--c3)", divs)]
                segs = [x for x in segs if abs(x[2]) > amt * 0.005]
                scale = sum(abs(x[2]) for x in segs) or 1
                st.markdown('<div class="split2">' + "".join(
                    f'<div style="width:{100 * abs(v) / scale:.1f}%;'
                    + ("background:repeating-linear-gradient(45deg,#FF7B8A,#FF7B8A 5px,"
                       "#E06070 5px,#E06070 10px)" if v < 0 else f"background:{c}")
                    + '"></div>' for _, c, v in segs) + "</div>"
                    + '<div class="skey">' + "".join(
                        f'<span><i style="'
                        + ("background:repeating-linear-gradient(45deg,#FF7B8A,#FF7B8A 4px,"
                           "#E06070 4px,#E06070 8px)" if v < 0 else f"background:{c}")
                        + f'"></i>{E(l)} <b>{"−" if v < 0 else "+"}{D}{abs(v):,.0f}</b></span>'
                        for l, c, v in segs) + "</div>", unsafe_allow_html=True)

                with st.expander("Where that came from"):
                    st.markdown(
                        "A return has three parts, and they are not the same thing.\n\n"
                        "**The business earning more** is durable. **Investors paying more** "
                        "can reverse overnight — nothing about the company changed. "
                        "**Dividends** are already yours.")
        else:
            st.markdown('<p class="lead">This needs ten years of share prices, which are not '
                        "available for this company. Everything else on the page comes from "
                        "filings and still works.</p>", unsafe_allow_html=True)

    # ---- 6. the score ---------------------------------------------------
    else:
        st.markdown('<p class="lead">The scorecard rates <b>what the filings show</b> — five '
                    "things the company has already reported.</p>", unsafe_allow_html=True)
        colour = {"good": "var(--up)", "mid": "var(--warn)", "bad": "var(--down)"}[card.tone]
        st.markdown(f'<span class="big" style="color:{colour}">{card.stars:.1f}'
                    '<span style="font-size:1.2rem;color:var(--text-3)">/5</span></span>'
                    f'<p class="bigsub">{E(card.verdict)}. Section 08 shows each component.</p>',
                    unsafe_allow_html=True)
        st.markdown('<div class="finish"><h4>🎉 That is a company, read end to end.</h4>'
                    "<p><b>A rising stock is not a better business.</b> "
                    "<b>A great business can be a bad investment at the wrong price.</b> "
                    "<b>One number never tells the whole story.</b></p></div>",
                    unsafe_allow_html=True)


TEACH_TITLES = [
    "What am I buying?",
    "The words you will see",
    "Is it getting better?",
    "Is it expensive?",
    "What would you have made?",
    "What is the score?",
]

# --------------------------------------------------------------------------
# Company head + headline strip
# --------------------------------------------------------------------------

eps = latest.get("eps")
dps = latest.get("dps")
rev = latest.get("revenue")
ni = latest.get("net_income")
margin = None if (ni is None or not rev) else 100 * ni / rev

pe = val.pe
dy = val.dividend_yield

day = ""
if q.available and q.day_change_pct is not None:
    arrow = "▲" if q.day_change_pct >= 0 else "▼"
    tone = "good" if q.day_change_pct >= 0 else "weak"
    day = (f'<span class="day {tone}">{arrow} {abs(q.day_change_pct):.2f}% today</span>')


st.markdown(f'<span class="tk">{E(ticker)}</span>{day}<h2 class="co">{E(eq.entity)}</h2>'
            f'<p class="one">{E(prof.get("industry") or "")}'
            f'{" · " if prof.get("industry") else ""}CIK {E(cik)} · '
            f'{E(latest.label)} · Form 10-K</p>', unsafe_allow_html=True)

_views = ["Research", "Teach me"]
_want = 1 if st.session_state.pop("goto_teach", False) else None
if _want is not None:
    st.session_state.pop("mode", None)
mode = st.radio("View", _views, index=_want if _want is not None else 0,
                horizontal=True, label_visibility="collapsed", key="mode")

if mode == "Teach me":
    # Scope the green palette to this view only; research stays violet.
    st.markdown('<div class="teach"></div>'
                "<style>section.main{--scope:teach}</style>", unsafe_allow_html=True)
    st.markdown("""<style>
      div[role="radiogroup"] ~ div .gs.done, div[role="radiogroup"] ~ div .gs.now,
      .gs.done, .gs.now{background:var(--teach) !important}
      .gnum{color:var(--teach) !important}
      .lead b{color:var(--teach-2) !important}
      .finish{background:rgba(95,214,155,.09) !important;
        border-color:var(--teach-dim) !important}
      .finish h4{color:var(--teach-2) !important}
      .gl .t span{color:var(--teach-2) !important}
      .picker{color:var(--teach) !important}
      div[data-testid="stExpander"]{border-color:var(--teach-dim) !important}
      [data-baseweb="slider"] [role="slider"]{background:var(--teach) !important;
        box-shadow:0 2px 10px -2px rgba(95,214,155,.75) !important}
      [data-baseweb="slider"] div[data-testid="stSliderThumbValue"]{color:var(--teach) !important}
      .stButton button{border-color:var(--teach-dim) !important}
      .stButton button:hover{border-color:var(--teach) !important;color:var(--teach) !important}
    </style>""", unsafe_allow_html=True)
    step = st.session_state.get("step", 0)
    n = len(TEACH_TITLES)
    st.markdown('<div class="gbar">' + "".join(
        f'<div class="gs {"done" if j < step else "now" if j == step else ""}"></div>'
        for j in range(n)) + "</div>", unsafe_allow_html=True)
    st.markdown(f'<span class="gnum">Step {step + 1} of {n}</span>'
                f'<h3 class="gtitle">{E(TEACH_TITLES[step])}</h3>', unsafe_allow_html=True)

    teach_slide(step, eq, latest, card, val=val, quote_=q,
                px_hist=[(lab, hist_px[lab]) for lab in
                         [p.label for p in eq.years] if lab in hist_px])

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
    ("Score", f"{card.stars:.1f}/5", card.tone, "see section 08 for why", None),
    ("Share price", f"{D}{q.price:,.2f}" if q.available else "no feed",
     "" if q.available else "dim",
     f"as of {q.as_of}" if q.as_of else (q.problem or "price unavailable"), "price"),
    ("EPS", f"{D}{eps:,.2f}" if eps is not None else "—", "",
     "earnings per share — profit split per share", "eps"),
    ("P/E ratio", f"{pe:,.2f}×" if pe else ("n/m" if q.available else "needs price"),
     "" if pe else "dim",
     "price-to-earnings" + ("" if pe else " — a loss means no P/E" if q.available else ""),
     "pe"),
    ("Dividend yield", f"{dy:,.2f}%" if dy else ("none" if dps is None or not dps else "needs price"),
     "good" if dy and dy > 2 else "" if dy else "dim",
     "cash paid to you per " + D + "100 held", "div"),
    ("Net margin", f"{margin:,.2f}%" if margin is not None else "—",
     "good" if margin and margin > 15 else "watch" if margin and margin > 7 else "weak",
     "net profit margin — kept from every " + D + "100 of sales", "margin"),
]
st.markdown('<div class="five">' + "".join(
    f'<div class="fv"><span class="k">{E(k)}</span>'
    f'<span class="v {t}">{v}</span><span class="d">{d}</span>'
    + "</div>" for k, v, t, d, g in strip) + "</div>", unsafe_allow_html=True)

glossable = [x for x in strip if x[4]]
if glossable:
    cols = st.columns(len(glossable))
    for col, (k, _, _, _, g) in zip(cols, glossable):
        if col.button("what does this mean? →", key=f"gl_{g}", use_container_width=True):
            # The radio owns st.session_state["mode"], so it cannot be written
            # here. Set a flag the radio's index reads on the next run.
            st.session_state["goto_teach"] = True
            st.session_state["step"] = 1
            st.rerun()

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
    ytd = sum(qq.get("revenue") for qq in eq.quarters if qq.get("revenue"))
    run = ytd / len(eq.quarters) * 4
    last_year = rev
    cells = ""
    for i in range(4):
        if i < len(eq.quarters):
            qq = eq.quarters[i]
            qeps = qq.get("eps")
            cells += (f'<div class="qc"><span class="ql">{qq.fp}</span>'
                      f'<span class="qv">{money(qq.get("revenue"))}</span>'
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
# 05 what management said
# --------------------------------------------------------------------------
# Best-effort. Filings vary enormously in structure, so when a section cannot
# be read the block simply does not appear -- an empty box or a wrong quote
# would both be worse than silence.

ft = prose(cik)

if ft and ft.mda:
    sh("05", "What management said", f"{ft.form} filed {ft.filed}")
    st.markdown('<div class="panel quote">'
                + "".join(f"<p>“{E(x)}”</p>" for x in ft.mda)
                + '<span class="src">Quoted verbatim from the filing — not summarised</span>'
                + "</div>", unsafe_allow_html=True)
    with st.expander("Why the share price move is not explained here"):
        st.markdown(
            "The filing says what was reported and what management blamed for it. It cannot "
            "say why the price moved on a given day — that is news, rumour, rates and the "
            "whole market's mood at once.\n\n**A confident-sounding reason is worse than no "
            "reason**, so this tool does not guess one.")

if ft and ft.risks:
    sh("06", "What could go wrong", "the company's own list")
    st.markdown('<div class="panel risk">'
                + "".join(f'<div class="rr">{E(r)}</div>' for r in ft.risks)
                + "</div>", unsafe_allow_html=True)
    st.caption("Taken from the filing's risk factors. A company listing a risk does not mean "
               "it is happening — filers list everything they can think of, partly for legal "
               "protection.")

# --------------------------------------------------------------------------
# 07 peers
# --------------------------------------------------------------------------
# Typed by the reader rather than parsed from the filing. Deciding who counts
# as a peer is a judgement, and a chosen set beats a guessed one.

sh("07", "Compare with peers", "tap a company to open it")

suggested, why_peers = suggest(ticker, sic=str(prof.get("sic") or ""))
chosen = st.session_state.get("peer_edit", "")
peer_list = [p.strip().upper() for p in chosen.split(",") if p.strip()][:4] if chosen else suggested

rows, missed = [], []
for tk in peer_list:
    hits = search(tk)
    if not hits or hits[0]["cik"] == cik:
        missed.append(tk)
        continue
    try:
        h = hits[0]
        peq = extract_equity(facts(h["cik"]), cik=h["cik"])
        pq = quote(h["ticker"])
        pv = value(peq, price=pq.price if pq.available else None)
        pl = peq.latest
        pm = (None if pl.get("net_income") is None or not pl.get("revenue")
              else 100 * pl["net_income"] / pl["revenue"])
        rows.append({"cik": h["cik"], "ticker": h["ticker"],
                     "name": peq.entity.split(",")[0].title(),
                     "pe": pv.pe, "margin": pm, "dy": pv.dividend_yield,
                     "day": pq.day_change_pct})
    except Exception:
        missed.append(tk)

if rows:
    def cell(v, suffix="", dp=2):
        return "—" if v is None else f"{v:,.{dp}f}{suffix}"

    def daycell(v):
        if v is None:
            return "—"
        return (f'<span style="color:var(--{"up" if v >= 0 else "down"})">'
                f'{"▲" if v >= 0 else "▼"} {abs(v):.2f}%</span>')

    head = ("<tr><th>Company</th><th>P/E</th><th>Net margin</th>"
            "<th>Div. yield</th><th>Today</th></tr>")
    body = (f'<tr class="self"><td>{E(eq.entity.split(",")[0].title())}</td>'
            f"<td>{cell(pe, '×')}</td><td>{cell(margin, '%')}</td>"
            f"<td>{cell(dy, '%')}</td><td>{daycell(q.day_change_pct)}</td></tr>")
    for r in rows:
        body += (f'<tr><td>{E(r["name"])}</td><td>{cell(r["pe"], "×")}</td>'
                 f'<td>{cell(r["margin"], "%")}</td><td>{cell(r["dy"], "%")}</td>'
                 f'<td>{daycell(r["day"])}</td></tr>')
    st.markdown(f'<div class="panel"><table class="comp"><thead>{head}</thead>'
                f"<tbody>{body}</tbody></table></div>", unsafe_allow_html=True)

    # Tapping a peer opens it, which is the whole point of showing the table.
    cols = st.columns(min(len(rows), 4))
    for col, r in zip(cols, rows):
        if col.button(f"Open {r['ticker']}", key=f"peer_{r['ticker']}",
                      use_container_width=True):
            st.session_state["cik"] = r["cik"]
            st.session_state["ticker"] = r["ticker"]
            st.session_state["name"] = r["name"]
            for k in ("peer_edit", "step"):
                st.session_state.pop(k, None)
            st.rerun()
    st.caption(why_peers + " Comparing against similar businesses is more honest than a fixed "
               "threshold, because what counts as a normal multiple differs completely between "
               "industries.")
elif why_peers and not peer_list:
    st.caption(why_peers)

with st.expander("Choose different companies"):
    st.text_input("Tickers, comma separated", key="peer_edit", placeholder="LOW, TGT, WMT")
    if missed:
        st.caption("Could not use: " + ", ".join(missed))

# --------------------------------------------------------------------------
# 09 what would have to happen
# --------------------------------------------------------------------------
# Two sliders, because a return has two engines and either can undo the other.
# Explicitly not a forecast: the point is to show how much the answer moves
# when assumptions nobody knows are changed.

if eps and eps > 0:
    sh("09", "What would have to happen", "move the sliders")
    start_pe = float(round(pe)) if pe else 20.0
    c1, c2 = st.columns(2)
    g = c1.slider("EPS growth a year", -10.0, 25.0, 5.0, 0.5, format="%.1f%%")
    m = c2.slider("P/E ratio", 5.0, 70.0, min(max(start_pe, 5.0), 70.0), 1.0, format="%.0f×")

    eps5 = eps * (1 + g / 100) ** 5
    price5 = eps5 * m
    divs = (dps or 0) * 5
    base = q.price if q.available else (eps * start_pe)
    ret = ((price5 + divs) / base) ** (1 / 5) - 1 if base > 0 else None

    if ret is not None:
        tone = "up" if ret >= 0 else "down"
        st.markdown(
            f'<div class="panel"><span class="big {tone}">{ret * 100:,.1f}%</span>'
            f'<p class="bigsub">a year for five years. <b>{D}1,000</b> would become '
            f'<b>{D}{1000 * (1 + ret) ** 5:,.0f}</b>, with EPS at '
            f'<b>{D}{eps5:,.2f}</b> and the share at <b>{D}{price5:,.0f}</b>.</p>'
            + ("" if q.available else
               '<p class="cfoot">No live price, so this starts from the current EPS at '
               f"{start_pe:.0f}× rather than the market price.</p>")
            + "</div>", unsafe_allow_html=True)
    st.caption("Not a prediction. Set growth to 10% then drag the P/E down to 15× — profits "
               "double and you still lose money, because what people will pay fell.")

# --------------------------------------------------------------------------
# 10 filings
# --------------------------------------------------------------------------

fl = filings(cik)
if fl:
    sh("10", "Recent filings", "newest first")
    kinds = {"10-K": ("k", "Annual report"), "10-Q": ("q", "Quarterly report"),
             "8-K": ("e", "Current report")}
    items = ""
    for f in fl:
        cls, what = kinds.get(f["form"][:4], ("o", "Filing"))
        desc = f.get("desc") or what
        items += (f'<li><span class="ftype {cls}">{E(f["form"])}</span>'
                  f'<span class="fmain"><a href="{E(f["url"])}" target="_blank" '
                  f'rel="noopener">{E(desc)}</a></span>'
                  f'<span class="fwhen">{E(f["filed"])}</span></li>')
    st.markdown(f'<div class="panel"><ul class="feed">{items}</ul></div>',
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
