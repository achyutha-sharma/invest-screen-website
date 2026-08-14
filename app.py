"""
Invest Screen — research a stock from its SEC filings.

Every figure on this page comes from a filing. Share price is the one exception
and is optional: without a feed, the valuation rows say so and the other eight
sections carry on unchanged.

Run with: streamlit run app.py
"""

import html
import os

import streamlit as st

from filing_text import latest_filings, read_filing
import funds as funds_data
from prices import PriceClient
from quiz import build as quiz_build, grade as quiz_grade, pick as quiz_pick
from scorecard import score
from sec_equity import extract_equity, pe_history, value
from sec_ratios import SecClient

st.set_page_config(page_title="Invest Screen", page_icon="📈", layout="centered")

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
.block-container{max-width:880px;padding-top:4.5rem;padding-bottom:4rem}
@media (max-width:640px){.block-container{padding-top:3.6rem}}

/* Streamlit chrome: the toolbar overlaps content and the rest is noise. */
header[data-testid="stHeader"]{background:transparent;height:0}
div[data-testid="stDecoration"]{display:none}
div[data-testid="stToolbar"]{right:.5rem}
#MainMenu{visibility:hidden}
footer{visibility:hidden}
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
  background:rgba(169,139,255,.13);border:1px solid var(--line);border-top:0;
  border-radius:0;color:var(--acc-2);font-size:.56rem;font-weight:700;
  letter-spacing:.04em;text-transform:lowercase;padding:.3rem .25rem;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
div[data-testid="stHorizontalBlock"]:has(button[kind]) .stButton button:hover{
  background:var(--acc);color:#15112B;border-color:var(--acc)}
div[data-testid="stHorizontalBlock"]{gap:1px !important}


.comp td:first-child{font-weight:700;font-size:.95rem}
.comp .mini{font-family:var(--mono);font-size:.72rem;font-weight:700;margin-left:.5rem}
.comp .mini.up{color:var(--up)} .comp .mini.down{color:var(--down)}
.comp tr.self td:first-child{color:var(--acc)}
.comp tbody tr:hover td{background:rgba(169,139,255,.05)}
.comp td{padding:.75rem .9rem}
.comp th{padding:.65rem .9rem}


/* quiz */
.qq{margin:1.3rem 0 .5rem}
.qq .qn{font-family:var(--mono);font-size:.62rem;font-weight:700;letter-spacing:.12em;
  color:var(--acc);text-transform:uppercase}
.qq p{margin:.3rem 0 0;font-size:1rem;color:var(--text);max-width:60ch;line-height:1.55}
.qa{border-radius:8px;padding:.85rem 1rem;margin:.5rem 0 .3rem;font-size:.88rem;
  line-height:1.62;max-width:66ch}
.qa.right{background:rgba(95,214,155,.09);border:1px solid #22502F;color:var(--text-2)}
.qa.right b{color:var(--up)}
.qa.wrong{background:rgba(240,196,106,.08);border:1px solid #4E3E1E;color:var(--text-2)}
.qa.wrong b{color:var(--warn)}
.qa b{font-weight:700}
.qscore{background:rgba(169,139,255,.08);border:1px solid var(--acc-dim);border-radius:10px;
  padding:1.2rem 1.3rem;margin-top:1.4rem}
.qscore .big{font-size:2.6rem}
.qscore .big.warn{color:var(--warn)}
.qscore .bigsub{margin:.3rem 0 0}
.qscore .bigsub b{color:#FFFFFF}


/* the link row is the bottom of each card, aligned to it exactly */
.nolink{height:100%;min-height:1.65rem;background:var(--surf);border:1px solid var(--line);
  border-top:0;border-radius:0 0 0 10px}
div[data-testid="stHorizontalBlock"]:has(button[kind]) .stButton button{
  height:1.65rem;min-height:1.65rem}
div[data-testid="stHorizontalBlock"]:has(button[kind])
  div[data-testid="stColumn"]:last-child .stButton button{border-radius:0 0 10px 0}


/* three-year table */
.years{width:100%;border-collapse:collapse}
.years th{font-size:.6rem;letter-spacing:.11em;text-transform:uppercase;color:var(--text-3);
  font-weight:700;padding:.55rem .7rem;text-align:right;border-bottom:1px solid var(--line)}
.years th:first-child{text-align:left}
.years td{padding:.65rem .7rem;text-align:right;font-family:var(--mono);font-size:.92rem;
  font-weight:700;color:#FFFFFF;border-bottom:1px solid var(--line)}
.years tr:last-child td{border-bottom:0}
.years td.mname{text-align:left;font-family:'Archivo',sans-serif;min-width:150px}
.years td.mname b{display:block;font-size:.88rem;color:#FFFFFF}
.years td.mname i{display:block;font-style:normal;font-size:.7rem;color:var(--text-3);
  font-weight:400;margin-top:.1rem}
.years td.tcol{min-width:74px}
.years tbody tr:hover td{background:rgba(169,139,255,.05)}
.trend{font-family:var(--mono);font-size:.8rem;font-weight:700}
.trend.up{color:var(--up)} .trend.down{color:var(--down)} .trend.flat{color:var(--text-3)}
.qc .qv.up{color:var(--up)} .qc .qv.down{color:var(--down)}
.qc .qs.up{color:var(--up)} .qc .qs.down{color:var(--down)}


.bullets p{position:relative;padding:.6rem 0 .6rem 1.35rem;margin:0;font-size:.93rem;
  color:var(--text-2);line-height:1.62;border-bottom:1px solid var(--line);max-width:64ch}
.bullets p:first-child{padding-top:0} 
.bullets p:last-child{border-bottom:0;padding-bottom:0}
.bullets p::before{content:"";position:absolute;left:.25rem;top:1.15em;width:6px;height:6px;
  border-radius:50%;background:var(--teach)}
.bullets p:first-child::before{top:.55em}
.bullets b{color:#FFFFFF;font-weight:700}


.gl p{margin:.5rem 0 0;font-size:.88rem;color:var(--text-2);line-height:1.65;max-width:64ch}
.gl p.eg{background:rgba(95,214,155,.07);border-left:2px solid var(--teach-dim);
  padding:.55rem .75rem;border-radius:0 5px 5px 0;margin-top:.7rem;color:var(--text-2)}
.gl p.eg b{color:var(--teach-2)}
.gl p.wm{color:var(--text-3);font-size:.85rem;border-top:1px solid var(--line);
  padding-top:.6rem;margin-top:.7rem}
.gl p.wm b{color:var(--text-2)}
.gl{padding:1.05rem 1.1rem}


.chart svg{display:block;width:100%;height:auto}
.ckey{display:flex;gap:1.1rem;font-family:var(--mono);font-size:.68rem;margin-bottom:.5rem}
.ckey span{display:flex;align-items:center;gap:.4rem;color:var(--text-2)}
.ln{width:15px;height:2.5px;border-radius:2px;display:inline-block}
h2.co .day{font-size:.7rem;vertical-align:middle}


.movers{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line);
  border:1px solid var(--line);border-radius:10px 10px 0 0;overflow:hidden}
@media (max-width:560px){.movers{grid-template-columns:1fr}}
.mv{background:var(--surf);padding:.85rem .95rem}
.mv .mt{display:block;font-family:var(--mono);font-size:.68rem;font-weight:700;
  letter-spacing:.06em;color:var(--acc)}
.mv .mp{display:block;font-family:var(--mono);font-size:1.2rem;font-weight:700;
  color:#FFFFFF;margin-top:.3rem}
.mv .mc{display:block;font-family:var(--mono);font-size:.78rem;font-weight:700;margin-top:.2rem}
.mv .mc.up{color:var(--up)} .mv .mc.down{color:var(--down)}


/* market strip: context, not companies -- flatter and quieter than the movers */
.mkt{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line);
  border:1px solid var(--line);border-radius:10px;overflow:hidden;margin-bottom:1.6rem}
@media (max-width:560px){.mkt{grid-template-columns:1fr}}
.mk{background:var(--bg-2);padding:.75rem .9rem}
.mk .ml{display:block;font-size:.82rem;font-weight:700;color:var(--text)}
.mk .mv2{display:block;font-family:var(--mono);font-size:1.05rem;font-weight:700;margin-top:.25rem}
.mk .mv2.up{color:var(--up)} .mk .mv2.down{color:var(--down)}
.mk .mw{display:block;font-size:.7rem;color:var(--text-3);margin-top:.2rem;line-height:1.4}


.fbody{font-size:.95rem;color:var(--text-2);line-height:1.7;margin:0;max-width:68ch}
.movegrid{display:grid;grid-template-columns:1fr 1fr;gap:1.4rem}
@media (max-width:640px){.movegrid{grid-template-columns:1fr;gap:1rem}}
.mhead{display:block;font-size:.62rem;letter-spacing:.12em;text-transform:uppercase;
  font-weight:700;margin-bottom:.5rem}
.mhead.up{color:var(--up)} .mhead.down{color:var(--down)}
.mcol p{position:relative;padding:.5rem 0 .5rem 1.1rem;margin:0;font-size:.88rem;
  color:var(--text-2);line-height:1.6;border-bottom:1px solid var(--line)}
.mcol p:last-child{border-bottom:0}
.mcol p::before{content:"";position:absolute;left:.2rem;top:1.05em;width:5px;height:5px;
  border-radius:50%;background:var(--text-3)}


/* search results: full-width rows */
.hitrow .stButton button{width:100%;text-align:left;justify-content:flex-start;
  background:var(--surf);border:1px solid var(--line);border-radius:7px;
  padding:.7rem .9rem;font-size:.92rem;font-weight:500;color:var(--text);
  min-height:2.7rem;margin-bottom:.35rem}
.hitrow .stButton button:hover{border-color:var(--acc);background:var(--surf-2);
  color:var(--acc-2)}
.hitrow .stButton button p{text-align:left !important;width:100%}


/* search results: each row is a full-width button dressed as a list item */
div[data-testid="stVerticalBlock"]:has(.hitrow) .stButton button{
  width:100%;text-align:left;justify-content:flex-start;background:var(--surf);
  border:1px solid var(--line);border-radius:7px;padding:.7rem .95rem;
  font-size:.92rem;font-weight:500;color:var(--text);min-height:2.7rem}
div[data-testid="stVerticalBlock"]:has(.hitrow) .stButton button:hover{
  border-color:var(--acc);background:var(--surf-2);color:var(--acc-2)}
div[data-testid="stVerticalBlock"]:has(.hitrow) .stButton button p{
  text-align:left !important;width:100%;font-family:var(--mono);font-size:.86rem}


/* the masthead is a button styled as a wordmark */
div[data-testid="stVerticalBlock"]:has(.masthome) > div:first-of-type + div .stButton button,
.masthome ~ div .stButton button{
  background:none !important;border:0 !important;padding:0 !important;
  font-family:'Archivo',sans-serif !important;font-size:1.18rem !important;
  font-weight:700 !important;color:var(--text) !important;letter-spacing:-.02em;
  width:auto !important;min-height:auto !important;height:auto !important;
  box-shadow:none !important}
.masthome ~ div .stButton button:hover{color:var(--acc) !important}
.masthome ~ div .stButton button p{font-size:1.18rem !important;font-weight:700 !important}
.mastline{border-bottom:1px solid var(--line);margin:.2rem 0 1.4rem}
div[data-testid="stColumn"]:has(.logo){flex:0 0 auto !important;width:auto !important;
  min-width:44px !important}
.masthome ~ div [data-testid="stColumn"] .stButton button{margin-top:.15rem}

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

st.markdown('<span class="masthome"></span>', unsafe_allow_html=True)
badge, word = st.columns([1, 9])
badge.markdown('<span class="logo">IS</span>', unsafe_allow_html=True)
if word.button("InvestScreen", key="home_logo"):
    go_home()
st.markdown('<div class="mastline"></div>', unsafe_allow_html=True)

def go_home():
    """Clear every page and selection, and return to the search screen."""
    for k in ("cik", "ticker", "name", "fund", "step", "searched",
              "quiz", "quiz_round", "mode", "peer_edit"):
        st.session_state.pop(k, None)
    for k in [k for k in st.session_state if k.startswith(("quiz_", "gl_", "hit_"))]:
        st.session_state.pop(k, None)
    st.rerun()


def home_button(key: str):
    """A home link at the top of a page. Placed before the content rather than
    after it, so it is reachable without scrolling to the bottom."""
    if st.button("← Home", key=key):
        go_home()


def secret(name: str, default: str = "") -> str:
    """Read a secret from either source.

    Streamlit Cloud supplies these through st.secrets; running locally they are
    environment variables. Checking both means the same file works in both
    places with nothing to remember.
    """
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.environ.get(name, default)


user_agent = secret("SEC_USER_AGENT")
if not user_agent:
    st.error("Set SEC_USER_AGENT to a name and email — the SEC turns away requests that "
             "do not identify the caller. Locally that is an environment variable; on "
             "Streamlit Cloud it goes in the app's secrets.")
    st.stop()

client = SecClient(user_agent=user_agent)
prices = PriceClient(api_key=secret("FINNHUB_API_KEY"))


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


_section_no = [0]


def sh(title, note=""):
    """Numbered section heading. Numbers are assigned as sections render, so a
    company missing one does not leave a gap in the sequence."""
    _section_no[0] += 1
    st.markdown(
        f'<div class="sh"><span class="n">{_section_no[0]:02d}</span><h3>{E(title)}</h3>'
        + (f'<span class="note">{E(note)}</span>' if note else "") + "</div>",
        unsafe_allow_html=True)


def ratio(a, b):
    return None if (a is None or not b) else a / b


# --------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------

if "cik" not in st.session_state:
    st.markdown('<h1 class="hero">Research a stock <em>properly</em>.</h1>'
                '<p class="sub">Straight from SEC filings.</p>', unsafe_allow_html=True)

query = st.text_input("Company name or ticker", placeholder="Search").strip()

# --------------------------------------------------------------------------
# Movers
# --------------------------------------------------------------------------
# Quotes for a small watchlist, ranked by today's move. Scanning the whole
# market would take thousands of calls a minute, so this is deliberately
# labelled as a watchlist rather than dressed up as "today's biggest movers".

# Ticker, label, and what it tracks. Funds, so no research page exists.
MARKET = [
    ("SPY", "S&P 500", "500 large US companies"),
    ("QQQ", "Nasdaq 100", "the largest non-financial tech names"),
    ("GLD", "Gold", "bullion held in a vault"),
]


if "cik" not in st.session_state and not query and prices.configured:
    mkt = []
    for tk, label, what in MARKET:
        try:
            qt = prices.quote(tk)
        except Exception:
            continue
        if qt.available and qt.day_change_pct is not None:
            mkt.append((tk, label, what, qt.day_change_pct))
    if mkt:
        st.markdown('<p class="picker">The market today</p>'
                    + '<div class="mkt">' + "".join(
                        f'<div class="mk"><span class="ml">{E(l)}</span>'
                        f'<span class="mv2 {"up" if p >= 0 else "down"}">'
                        f'{"▲" if p >= 0 else "▼"} {abs(p):.2f}%</span>'
                        f'<span class="mw">{E(w)}</span></div>'
                        for _, l, w, p in mkt) + "</div>", unsafe_allow_html=True)
        cols = st.columns(len(mkt))
        for col, (tk, label, _, _) in zip(cols, mkt):
            if col.button(f"what is {label}? →", key=f"fund_{tk}",
                          use_container_width=True):
                st.session_state["fund"] = tk
                for k in ("cik", "ticker", "name", "step"):
                    st.session_state.pop(k, None)
                st.rerun()
        st.caption("Funds tracking whole markets. They hold shares in hundreds of "
                   "companies rather than running a business, so there is no filing to "
                   "research — but they tell you whether a stock moved on its own news or "
                   "with everything else.")

# A query that has already been acted on must not re-trigger. Streamlit reruns
# the whole script on every interaction, and the search box keeps its text, so
# without this any click on an open page would bounce back to the results.
if query and query == st.session_state.get("searched"):
    query = ""

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
    # A list rather than a dropdown, and never auto-selected. The exact ticker
    # a reader wants is often not the first hit -- "delta" reaches an airline
    # and an apparel maker -- so showing the alternatives costs one click and
    # saves guessing the precise name.
    st.markdown(f'<p class="picker">{len(hits)} '
                f'{"match" if len(hits) == 1 else "matches"}</p>', unsafe_allow_html=True)
    # The whole row is the button. Streamlit cannot make an HTML block
    # clickable, so rather than pairing a div with a separate control, the
    # button itself carries the label and is styled to look like a row.
    box = st.container()
    box.markdown('<span class="hitrow"></span>', unsafe_allow_html=True)
    for h in hits:
        if box.button(f"{h['ticker']}  ·  {h['name'].title()}",
                      key=f"hit_{h['cik']}", use_container_width=True):
            st.session_state.pop("fund", None)
            for k in ("step", "quiz", "quiz_round"):
                st.session_state.pop(k, None)
            st.session_state["cik"] = h["cik"]
            st.session_state["ticker"] = h["ticker"]
            st.session_state["name"] = h["name"]
            st.session_state["searched"] = query
            st.rerun()
    st.stop()

# --------------------------------------------------------------------------
# Fund page
# --------------------------------------------------------------------------
# A fund has no filing to read, so this page is explanation rather than
# analysis: what the thing is, what moves it, and what to be wary of. Nothing
# here is computed, because nothing here changes with the price.

# Typing in the search box means leaving whatever page is open.
if query and st.session_state.get("fund"):
    st.session_state.pop("fund", None)
    st.session_state.pop("searched", None)

if st.session_state.get("fund"):
    fd = funds_data.get(st.session_state["fund"])
    if fd is None:
        st.session_state.pop("fund", None)
        st.rerun()

    fq = quote(fd.ticker)

    home_button("home_fund")

    day_badge = ""
    if fq.available and fq.day_change_pct is not None:
        tone = "good" if fq.day_change_pct >= 0 else "weak"
        day_badge = (f'<span class="day {tone}">'
                     f'{"▲" if fq.day_change_pct >= 0 else "▼"} '
                     f'{abs(fq.day_change_pct):.2f}% today</span>')

    st.markdown(f'<span class="tk">{E(fd.ticker)}</span>'
                f'<h2 class="co">{E(fd.name)}{day_badge}</h2>'
                f'<p class="one">{E(fd.one_line)}</p>', unsafe_allow_html=True)

    if fq.available:
        st.markdown('<div class="five" style="grid-template-columns:repeat(2,1fr)">'
                    f'<div class="fv"><span class="k">Price</span>'
                    f'<span class="v">{D}{fq.price:,.2f}</span>'
                    f'<span class="d">one share of the fund</span></div>'
                    f'<div class="fv"><span class="k">Today</span>'
                    f'<span class="v {"good" if (fq.day_change_pct or 0) >= 0 else "weak"}">'
                    + (f'{fq.day_change_pct:+,.2f}%' if fq.day_change_pct is not None else "—")
                    + f'</span><span class="d">as of {E(fq.as_of)}</span></div></div>',
                    unsafe_allow_html=True)

    sh("What this actually is")
    st.markdown(f'<div class="panel"><p class="fbody">{E(fd.what)}</p></div>',
                unsafe_allow_html=True)

    sh("What moves it")
    st.markdown('<div class="panel movegrid">'
                + '<div class="mcol"><span class="mhead up">Goes up when</span>'
                + "".join(f"<p>{E(x)}</p>" for x in fd.moves_up) + "</div>"
                + '<div class="mcol"><span class="mhead down">Goes down when</span>'
                + "".join(f"<p>{E(x)}</p>" for x in fd.moves_down) + "</div>"
                + "</div>", unsafe_allow_html=True)

    # Price history is not on every free plan, so the chart appears only when
    # the data does -- and its absence is not treated as an error.
    hist = prices.monthly(fd.ticker) if prices.configured else []
    if len(hist) >= 12:
        sh("How it has moved", f"{hist[0][0][:4]} to {hist[-1][0][:4]}")
        W, H, L, R, T, B = 780, 200, 44, 12, 14, 24
        vals = [v for _, v in hist]
        lo, hi = min(vals), max(vals)
        pad = (hi - lo) * 0.10 or 1
        y0, y1 = lo - pad, hi + pad

        def FX(i):
            return L + (i / max(len(vals) - 1, 1)) * (W - L - R)

        def FY(v):
            return T + (1 - (v - y0) / (y1 - y0)) * (H - T - B)

        grid = ""
        for g in range(4):
            v = y0 + (y1 - y0) * g / 3
            y = FY(v)
            grid += (f'<line x1="{L}" y1="{y:.1f}" x2="{W - R}" y2="{y:.1f}" stroke="#332B60"/>'
                     f'<text x="{L - 7}" y="{y + 3.5:.1f}" text-anchor="end" '
                     'font-family="IBM Plex Mono,monospace" font-size="9" font-weight="600" '
                     f'fill="#7F779E">{v:,.0f}</text>')
        step = max(len(vals) // 5, 1)
        xl = "".join(
            f'<text x="{FX(i):.1f}" y="{H - 7}" text-anchor="middle" '
            'font-family="IBM Plex Mono,monospace" font-size="9" font-weight="600" '
            f'fill="#7F779E">&#39;{hist[i][0][2:4]}</text>'
            for i in range(0, len(vals), step))
        line = " ".join(f"{'L' if i else 'M'}{FX(i):.1f},{FY(v):.1f}"
                        for i, v in enumerate(vals))
        rising = vals[-1] >= vals[0]
        colour = "#5FD69B" if rising else "#FF7B8A"
        st.markdown(f'''<div class="panel chart">
          <svg viewBox="0 0 {W} {H}" role="img"
               aria-label="{E(fd.name)} price since {E(hist[0][0][:4])}">
            {grid}
            <path d="{line}" fill="none" stroke="{colour}" stroke-width="2.4"
              stroke-linejoin="round" stroke-linecap="round"/>
            <circle cx="{FX(len(vals) - 1):.1f}" cy="{FY(vals[-1]):.1f}" r="3.6"
              fill="{colour}"/>
          </svg></div>''', unsafe_allow_html=True)
        st.caption("Month-end prices. A fund's chart is the whole story — there are no "
                   "earnings underneath it to compare against.")

    sh("Why it is worth watching")
    st.markdown(f'<div class="panel"><p class="fbody">{E(fd.why)}</p></div>',
                unsafe_allow_html=True)

    if fd.watch_out:
        st.markdown(f'<div class="sfoot"><b>Worth knowing.</b> {E(fd.watch_out)}</div>',
                    unsafe_allow_html=True)

    st.markdown('<p class="disc">Funds file holdings reports rather than financial '
                "statements, so there are no ratios here — a fund has no revenue or "
                "profit of its own. Prices come from a market feed. Educational only.</p>",
                unsafe_allow_html=True)
    st.stop()

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
    if "404" in str(e):
        st.warning(
            "**No financial statements are filed for this one.**\n\n"
            "Index funds and ETFs — S&P 500 trackers, sector funds — file holdings reports "
            "rather than 10-Ks. A fund has no revenue, no profit and no margin, because it "
            "does not run a business: it holds shares in hundreds of companies that do. "
            "Every ratio on this page would be meaningless.\n\n"
            "The same applies to trusts and some holding companies. Search an operating "
            "company instead.")
    else:
        st.error(f"Could not load filings: {e}")
    if st.button("← Search again"):
        for k in ("cik", "ticker", "name"):
            st.session_state.pop(k, None)
        st.rerun()
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


def shares_text(n):
    """Share count at a readable scale."""
    if n is None:
        return ""
    if n >= 1e9:
        return f"{n / 1e9:,.2f} billion"
    if n >= 1e6:
        return f"{n / 1e6:,.0f} million"
    return f"{n:,.0f}"


def teach_slide(i, eq, latest, card, val=None, quote_=None, px_hist=None):
    rev = latest.get("revenue"); ni = latest.get("net_income")
    eps = latest.get("eps"); dps = latest.get("dps")
    shares = latest.get("shares"); ebit = latest.get("ebit")
    gross = latest.get("gross_profit")
    ocf, capex = latest.get("ocf"), latest.get("capex")
    fcf = None if (ocf is None or capex is None) else ocf - capex
    ni = latest.get("net_income")
    margin = None if (ni is None or not rev) else 100 * ni / rev
    name = eq.entity.split(",")[0].title()

    # ---- 1. what a stock actually is ------------------------------------
    if i == 0:
        st.markdown('<p class="lead">A share is a <b>slice of a company</b> — not a bet, '
                    "not a token. Owning one makes you a part-owner of the business.</p>",
                    unsafe_allow_html=True)
        st.markdown(f'''<div class="panel bullets">
          <p><b>You own a piece of everything it has.</b> Its buildings, its brand, its
             cash — and its debts. {E(name)} is divided into
             <b>{shares_text(shares)}</b> shares.</p>
          <p><b>You have a claim on its profits.</b> Whatever the company earns belongs to
             shareholders. It decides whether to hand that out as a dividend or reinvest it.</p>
          <p><b>Your money does not go to the company.</b> Buying shares on an exchange
             means buying from another investor. The company only received money when it
             first sold those shares.</p>
          <p><b>The price moves without the company doing anything.</b> It is set by what
             buyers and sellers agree today, which is why a share can fall on a day the
             business had a perfectly good one.</p>
          <p><b>The company still notices.</b> A higher share price makes it cheaper to
             raise money and harder to be taken over, and most executives are paid partly
             in shares — so the price shapes what management does.</p>
        </div>''' if shares else '''<div class="panel bullets">
          <p><b>You own a piece of everything it has</b> — buildings, brand, cash, and debts.</p>
          <p><b>You have a claim on its profits</b>, which the company either pays out or
             reinvests.</p>
          <p><b>Your money does not go to the company</b> when you buy on an exchange. You
             are buying from another investor.</p>
          <p><b>The price moves without the company doing anything</b>, because it is set
             by what buyers and sellers agree today.</p>
        </div>''', unsafe_allow_html=True)

    # ---- 2. the words --------------------------------------------------
    elif i == 1:
        st.markdown('<p class="lead">Five terms cover most of a stock page. '
                    "<b>The formal name, what it means, and what it looks like here.</b></p>",
                    unsafe_allow_html=True)
        pe = val.pe if val else None
        dy = val.dividend_yield if val else None
        price = quote_.price if quote_ and quote_.available else None

        def eg(text):
            return f'<span class="eg">{text}</span>'

        terms = [
            ("EPS", "earnings per share",
             f"{D}{eps:,.2f}" if eps is not None else "—",
             "Take everything the company earned last year and divide it between every "
             "share that exists. That is EPS — <b>the profit belonging to one share</b>.",
             (f"{E(name)} earned {money(ni)} and has {shares_text(shares)} shares, "
              f"so each share earned <b>{D}{eps:,.2f}</b>."
              if eps is not None and ni and shares else
              "A company earning $100m with 50m shares has an EPS of $2.00."),
             "It is the number a share price tends to follow over long stretches. A rising "
             "price with falling EPS means investors are paying more for less — which can "
             "reverse quickly."),

            ("P/E ratio", "price-to-earnings",
             f"{pe:,.1f}×" if pe else "needs price",
             "How many dollars you pay for each dollar the share earns in a year. Price "
             "divided by EPS. <b>It is the market's expectations, priced.</b>",
             (f"At {D}{price:,.2f} a share against {D}{eps:,.2f} of earnings, you pay "
              f"<b>{D}{pe:,.0f} for every {D}1</b> of annual profit — about {pe:,.0f} years "
              "of profit to earn your money back, if nothing changed."
              if pe and price and eps else
              "A $60 share earning $3 trades at 20× — $20 paid per $1 of annual profit."),
             "High is not the same as expensive. A company at 40× may be the better buy if "
             "profits grow into the price; one at 10× may be cheap because investors expect "
             "trouble. <b>The ratio tells you what is assumed, not whether it is right.</b>"),

            ("Net margin", "net profit margin",
             f"{margin:,.1f}%" if margin is not None else "—",
             "Of every dollar customers spend, how much survives as profit after every "
             "cost — materials, wages, marketing, interest and tax.",
             (f"{E(name)} keeps about <b>{D}{margin:,.0f} of every {D}100</b> customers "
              f"spend."
              if margin is not None else
              "A supermarket keeps about $2 of every $100; a software company can keep $25."),
             "Thin is not automatically bad — supermarkets run on a few percent and do fine "
             "on volume. <b>The direction matters more than the level.</b> A margin falling "
             "year after year means the company is spending more to earn the same."),

            ("Free cash flow", "cash after capital spending",
             money(fcf),
             "The cash left after running the business <i>and</i> paying for the new "
             "equipment, stores or technology it needs to keep going.",
             (f"{E(name)} took in {money(ocf)} from operations and spent {money(capex)} on "
              f"capital, leaving <b>{money(fcf)}</b> against {money(ni)} of reported profit."
              if fcf is not None and ocf and capex and ni else
              "A company with $50m from operations spending $20m on equipment has $30m free."),
             "<b>Profit is an opinion. Cash is a fact.</b> Profit involves judgement about "
             "when to count a sale; cash either arrived or it did not. When the two drift "
             "apart for years, trust the cash."),

            ("Dividend yield", "cash paid to owners",
             f"{dy:,.2f}%" if dy else ("none" if not dps else "needs price"),
             "The cash a company hands its shareholders each year, as a percentage of what "
             "a share costs today.",
             (f"{E(name)} declares {D}{dps:,.2f} a share against a {D}{price:,.2f} price, "
              f"so every {D}100 invested pays about <b>{D}{dy:,.2f}</b> a year."
              if dy and dps and price else
              (f"{E(name)} pays no dividend — it reinvests the cash instead, which is normal "
               "for faster-growing companies." if not dps else
               "A $2 dividend on a $50 share is a 4% yield.")),
             "It is the one part of a return a falling price cannot take back. Once the cash "
             "is paid it is yours, which is why a company cutting its dividend is treated as "
             "such bad news."),
        ]

        st.markdown('<div class="gloss">' + "".join(
            f'<div class="gl"><div class="t"><b>{E(t)}</b><i>{E(g)}</i><span>{v}</span></div>'
            f"<p>{meaning}</p>"
            f'<p class="eg"><b>Here:</b> {example}</p>'
            f'<p class="wm">{why}</p></div>'
            for t, g, v, meaning, example, why in terms) + "</div>",
            unsafe_allow_html=True)

    # ---- 3. the score ---------------------------------------------------
    elif i == 2:
        st.markdown('<p class="lead">The scorecard rates <b>what the filings show</b> — five '
                    "things the company has already reported.</p>", unsafe_allow_html=True)
        colour = {"good": "var(--up)", "mid": "var(--warn)", "bad": "var(--down)"}[card.tone]
        st.markdown(f'<span class="big" style="color:{colour}">{card.stars:.1f}'
                    '<span style="font-size:1.2rem;color:var(--text-3)">/5</span></span>'
                    f'<p class="bigsub">{E(card.verdict)}. The scorecard below shows each component.</p>',
                    unsafe_allow_html=True)
        st.markdown('<div class="finish"><h4>🎉 That is a company, read end to end.</h4>'
                    "<p><b>A rising stock is not a better business.</b> "
                    "<b>A great business can be a bad investment at the wrong price.</b> "
                    "<b>One number never tells the whole story.</b></p></div>",
                    unsafe_allow_html=True)

    # ---- 4. the quiz ----------------------------------------------------
    else:
        st.markdown('<p class="lead">Five questions on what you have just read, '
                    "using <b>this company's own numbers</b>.</p>",
                    unsafe_allow_html=True)
        quiz_slide(eq, latest, val, quote_)



def quiz_slide(eq, latest, val, quote_):
    """The last teach slide: check the terms just covered, against this
    company's own numbers."""
    eps = latest.get("eps")
    ni = latest.get("net_income")
    rev = latest.get("revenue")
    margin = None if (ni is None or not rev) else 100 * ni / rev
    ocf, capex = latest.get("ocf"), latest.get("capex")
    fcf = None if (ocf is None or capex is None) else ocf - capex
    ni = latest.get("net_income")
    pe = val.pe if val else None
    dy = val.dividend_yield if val else None
    q = quote_

    qs = quiz_build(
        eq.entity.split(",")[0].title(),
        eps=eps, pe=pe, margin=margin,
        price=q.price if q.available else None,
        shares=latest.get("shares"),
        fcf=(None if latest.get("ocf") is None or latest.get("capex") is None
             else latest.get("ocf") - latest.get("capex")),
        net_income=ni, dividend_yield=dy,
        revenue_growth=None, income_growth=None,
    )

    rnd = st.session_state.get("quiz_round", 0)
    qs = quiz_pick(qs, rnd) if qs else []

    if qs:
        answers = st.session_state.setdefault("quiz", {})
        for n, question in enumerate(qs):
            key = f"q{rnd}_{n}"
            st.markdown(f'<div class="qq"><span class="qn">Question {n + 1}</span>'
                        f'<p>{E(question.prompt).replace("$", D)}</p></div>',
                        unsafe_allow_html=True)
            picked = st.radio(question.prompt, question.options, index=None,
                              key=f"quiz_{key}", label_visibility="collapsed")
            if picked is not None:
                chose = question.options.index(picked)
                answers[key] = chose == question.correct
                if chose == question.correct:
                    st.markdown('<div class="qa right"><b>Correct.</b> '
                                + question.why.replace("$", D) + "</div>",
                                unsafe_allow_html=True)
                else:
                    st.markdown(
                        '<div class="qa wrong"><b>Not quite.</b> The answer is “'
                        + E(question.options[question.correct]).replace("$", D)
                        + "”. " + question.why.replace("$", D) + "</div>",
                        unsafe_allow_html=True)

        done = [v for k, v in answers.items()
                if k in {f"q{rnd}_{i}" for i in range(len(qs))}]
        if len(done) == len(qs):
            got = sum(done)
            verdict, note = quiz_grade(got, len(qs))
            tone = "up" if got / len(qs) >= 0.8 else "warn" if got / len(qs) >= 0.5 else "down"
            st.markdown(f'<div class="qscore"><span class="big {tone}">{got}/{len(qs)}</span>'
                        f'<p class="bigsub"><b>{E(verdict)}.</b> {E(note)}</p></div>',
                        unsafe_allow_html=True)
            if st.button("Try five more", key="quiz_reset"):
                # Clearing the widget keys deselects the radios; bumping the
                # round draws a different five with the options reordered.
                for k in list(st.session_state):
                    if k.startswith("quiz_q"):
                        st.session_state.pop(k, None)
                st.session_state["quiz"] = {}
                st.session_state["quiz_round"] = rnd + 1
                st.rerun()
        else:
            st.caption(f"{len(done)} of {len(qs)} answered.")

TEACH_TITLES = [
    "What is a stock?",
    "The words you will see",
    "What is the score?",
    "Now it's your turn",
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


st.markdown(f'<span class="tk">{E(ticker)}</span><h2 class="co">{E(eq.entity)}{day}</h2>'
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
    home_button("home_teach")
    st.stop()

strip = [
    ("Score", f"{card.stars:.1f}/5", card.tone, "see the scorecard below", None),
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

if any(x[4] for x in strip):
    cols = st.columns(len(strip))
    for col, (k, _, _, _, g) in zip(cols, strip):
        if not g:
            col.markdown('<div class="nolink"></div>', unsafe_allow_html=True)
            continue
        if col.button("what is this? →", key=f"gl_{g}", use_container_width=True):
            # The radio owns st.session_state["mode"], so it cannot be written
            # here. Set a flag the radio's index reads on the next run.
            st.session_state["goto_teach"] = True
            st.session_state["step"] = 1
            st.rerun()

# --------------------------------------------------------------------------
# 01 the numbers
# --------------------------------------------------------------------------

sh("The numbers", "last three years")

def series3(key):
    """The three most recent filed values, oldest first."""
    got = eq.series(key)
    return got[-3:] if got else []


def fcf_series():
    out = []
    for p in eq.years:
        o, c = p.get("ocf"), p.get("capex")
        if o is not None and c is not None:
            out.append((p.label, o - c))
    return out[-3:]


def margin_series():
    out = []
    for p in eq.years:
        n, r = p.get("net_income"), p.get("revenue")
        if n is not None and r:
            out.append((p.label, 100 * n / r))
    return out[-3:]


LINES = [
    ("Revenue", series3("revenue"), money, "higher", "everything customers paid"),
    ("Net income", series3("net_income"), money, "higher", "what was left after every cost"),
    ("EPS", series3("eps"), lambda v: f"{D}{v:,.2f}", "higher", "profit belonging to one share"),
    ("Net margin", margin_series(), lambda v: f"{v:,.1f}%", "higher",
     "kept from every " + D + "100 of sales"),
    ("Free cash flow", fcf_series(), money, "higher", "cash after capital spending"),
    ("Dividend per share", series3("dps"), lambda v: f"{D}{v:,.2f}", "higher",
     "cash declared per share"),
    ("Total debt", series3("total_debt"), money, "lower", "everything borrowed"),
]

def arrow(vals, better):
    """Direction against the earliest of the three years shown."""
    if len(vals) < 2:
        return ""
    first, last_v = vals[0][1], vals[-1][1]
    if not first:
        return ""
    chg = 100 * (last_v / first - 1) if first > 0 else None
    if chg is None or abs(chg) < 0.5:
        return '<span class="trend flat">—</span>'
    good = (chg > 0) if better == "higher" else (chg < 0)
    return (f'<span class="trend {"up" if good else "down"}">'
            f'{"▲" if chg > 0 else "▼"}{abs(chg):,.0f}%</span>')

have = [x for x in LINES if x[1]]
if have:
    labels = [lab for lab, _ in max((x[1] for x in have), key=len)]
    span = len(labels) - 1
    head = ("<tr><th>Measure</th>" + "".join(f"<th>{E(l)}</th>" for l in labels)
            + f"<th>{span}-yr</th></tr>")
    body = ""
    for name, vals, fmt, better, hint in have:
        got = dict(vals)
        cells = ""
        for l in labels:
            v = got.get(l)
            cells += f"<td>{fmt(v) if v is not None else '—'}</td>"
        body += (f'<tr><td class="mname"><b>{E(name)}</b><i>{hint}</i></td>'
                 f'{cells}<td class="tcol">{arrow(vals, better)}</td></tr>')
    st.markdown(f'<div class="panel"><table class="years"><thead>{head}</thead>'
                f"<tbody>{body}</tbody></table></div>", unsafe_allow_html=True)
    st.caption(f"Green is the direction you would rather see — for debt that means falling. "
               f"The last column is the change from {E(labels[0])} to {E(labels[-1])}, "
               f"which is {span} year{'s' if span != 1 else ''} of growth.")

# --------------------------------------------------------------------------
# Trend chart
# --------------------------------------------------------------------------
# Revenue and profit per share, both indexed to 100 at the first year shown.
# Indexing is what makes them comparable: the point is not the level of either
# but whether they move together. Where EPS outpaces revenue the company is
# keeping more of each sale; where it lags, costs or the share count are
# growing faster than the business.

rev_hist = eq.series("revenue")
eps_hist = eq.series("eps")
if len(rev_hist) >= 3 and len(eps_hist) >= 3:
    sh("Trend", f"{rev_hist[0][0]} to {rev_hist[-1][0]}")
    W, H, L, R, T, B = 780, 210, 38, 12, 14, 26

    def indexed(series):
        base = series[0][1]
        return [100 * v / base for _, v in series] if base else []

    ri, ei = indexed(rev_hist), indexed(eps_hist)
    allv = [v for v in ri + ei if v is not None]
    lo, hi = min(allv + [100]), max(allv)
    pad = (hi - lo) * 0.10 or 10
    y0, y1 = lo - pad, hi + pad

    def X(i, n):
        return L + (i / max(n - 1, 1)) * (W - L - R)

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
                 f'<text x="{L - 7}" y="{y + 3.5:.1f}" text-anchor="end" '
                 'font-family="IBM Plex Mono,monospace" font-size="9" font-weight="600" '
                 f'fill="#7F779E">{v:.0f}</text>')

    labels = ""
    step = max(len(rev_hist) // 5, 1)
    for i, (lab, _) in enumerate(rev_hist):
        if i % step == 0 or i == len(rev_hist) - 1:
            labels += (f'<text x="{X(i, len(rev_hist)):.1f}" y="{H - 8}" text-anchor="middle" '
                       'font-family="IBM Plex Mono,monospace" font-size="9" font-weight="600" '
                       f"fill=\"#7F779E\">&#39;{E(lab[-2:])}</text>")

    dots = (f'<circle cx="{X(len(ri) - 1, len(ri)):.1f}" cy="{Y(ri[-1]):.1f}" r="3.6" '
            'fill="#A98BFF"/>'
            f'<circle cx="{X(len(ei) - 1, len(ei)):.1f}" cy="{Y(ei[-1]):.1f}" r="3.2" '
            'fill="#5FD69B"/>')

    st.markdown(f'''<div class="panel chart">
      <div class="ckey"><span><i class="ln" style="background:#A98BFF"></i>revenue</span>
        <span><i class="ln" style="background:#5FD69B"></i>profit per share</span></div>
      <svg viewBox="0 0 {W} {H}" role="img"
           aria-label="Revenue and profit per share since {E(rev_hist[0][0])}, both indexed to 100">
        {grid}
        <path d="{path(ei)}" fill="none" stroke="#5FD69B" stroke-width="2.2"
          stroke-linejoin="round" stroke-linecap="round"/>
        <path d="{path(ri)}" fill="none" stroke="#A98BFF" stroke-width="2.6"
          stroke-linejoin="round" stroke-linecap="round"/>
        {dots}{labels}
      </svg></div>''', unsafe_allow_html=True)
    st.caption("Both lines start at 100 so they can be compared. Where profit per share "
               "outpaces revenue the company is keeping more of what it sells; where it "
               "lags, costs or the share count are growing faster than the business.")

# --------------------------------------------------------------------------
# 03 this year so far
# --------------------------------------------------------------------------

if eq.quarters:
    sh("This year so far", f"{len(eq.quarters)} of 4 quarters filed")
    ytd = sum(qq.get("revenue") for qq in eq.quarters if qq.get("revenue"))
    run = ytd / len(eq.quarters) * 4
    last_year = rev
    cells = ""
    for i in range(4):
        if i < len(eq.quarters):
            qq = eq.quarters[i]
            chg = qq.change("revenue")
            tone = "" if chg is None else ("up" if chg >= 0 else "down")
            cells += (f'<div class="qc"><span class="ql">{qq.fp}</span>'
                      f'<span class="qv {tone}">{money(qq.get("revenue"))}</span>'
                      + (f'<span class="qs {tone}">'
                         f'{"▲" if chg >= 0 else "▼"}{abs(chg):,.1f}% on {qq.fp} last year'
                         "</span>" if chg is not None else
                         '<span class="qs">no year-ago figure filed</span>')
                      + "</div>")
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
# 05 what management said
# --------------------------------------------------------------------------
# Best-effort. Filings vary enormously in structure, so when a section cannot
# be read the block simply does not appear -- an empty box or a wrong quote
# would both be worse than silence.

ft = prose(cik)

if ft and ft.mda:
    sh("What management said", f"{ft.form} filed {ft.filed}")
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
    sh("What could go wrong", "the company's own list")
    st.markdown('<div class="panel risk">'
                + "".join(f'<div class="rr">{E(r)}</div>' for r in ft.risks)
                + "</div>", unsafe_allow_html=True)
    st.caption("From the filing's risk factors. Listed does not mean happening — filers "
               "list everything, partly for legal cover.")

# --------------------------------------------------------------------------
# 07 peers
# --------------------------------------------------------------------------
# Typed by the reader rather than parsed from the filing. Deciding who counts
# as a peer is a judgement, and a chosen set beats a guessed one.

# --------------------------------------------------------------------------
# 09 what would have to happen
# --------------------------------------------------------------------------
# Two sliders, because a return has two engines and either can undo the other.
# Explicitly not a forecast: the point is to show how much the answer moves
# when assumptions nobody knows are changed.

if eps and eps > 0:
    sh("What would have to happen", "move the sliders")
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
    st.caption("Not a prediction. Try 10% growth with the P/E at 15× — profits double and "
               "you still lose money.")

# --------------------------------------------------------------------------
# 10 filings
# --------------------------------------------------------------------------

fl = filings(cik)
if fl:
    sh("Recent filings", "newest first")
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

sh("The scorecard", "what the filings answer")
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
    sh("Worth knowing", "how these figures were built")
    st.markdown('<div class="panel note-list">'
                + "".join(f"<p>{E(n)}</p>" for n in eq.notes) + "</div>",
                unsafe_allow_html=True)

st.markdown('<p class="disc">Figures come from SEC filings. Share price and today\'s '
            "move come from a market feed. Educational research only — not advice.</p>",
            unsafe_allow_html=True)

home_button("home_bottom")
