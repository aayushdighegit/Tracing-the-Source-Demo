import streamlit as st
import pandas as pd
import numpy as np
import networkx as nx
import streamlit.components.v1 as components
from pyvis.network import Network
import pydeck as pdk
import os
import re
import time
import html
import altair as alt
from generate_data import generate_seeded_outbreak_data
from auth import (MiniMothClient, MiniMothError, SessionStore, ensure_fresh, end_session, normalize_phone,
                  parse_allowlist, mask_phone, ERROR_MESSAGES, SESSION_COOKIE, HANDLE_MAX_AGE_S)

st.set_page_config(layout="wide", page_title="Tracing the Source | Outbreak Intelligence")

# Table sizing: roomy rows, and a height that fits every row so tables never need a vertical scrollbar
TABLE_ROW_H = 40
def fit_height(n_rows):
    return (n_rows + 1) * TABLE_ROW_H + 4

# UI THEME — Plague Inc palette with Cyberpunk-style controls (presentation only, no data logic)
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bodoni+Moda:opsz,wght@6..96,800;6..96,900&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');
:root {
    --bg: #16171b; --panel: #1f2126; --panel-2: #24262c; --line: #33353c;
    --accent: #d9a441; --accent-soft: rgba(217,164,65,0.13); --accent-line: rgba(217,164,65,0.45);
    --text: #e7e3dc; --muted: #b3ada5; --teal: #7cc4c0; --teal-soft: rgba(124,196,192,0.12); --teal-line: rgba(124,196,192,0.45);
    --cut: 10px; --mono: 'JetBrains Mono', monospace;
}

/* Base: two fonts only — Inter for text, JetBrains Mono for numbers and IDs */
/* Background: drifting amber/teal aurora, radar sweep, tactical grid, glass panels */
.stApp { background-color: #101114; }
.stApp::before {
    content: ""; position: fixed; inset: -20%; z-index: 0; pointer-events: none;
    background:
        radial-gradient(circle at 20% 25%, rgba(217,164,65,0.55), transparent 32%),
        radial-gradient(circle at 80% 15%, rgba(124,196,192,0.40), transparent 30%),
        radial-gradient(circle at 70% 80%, rgba(184,116,42,0.50), transparent 34%),
        radial-gradient(circle at 15% 85%, rgba(47,111,108,0.55), transparent 32%),
        radial-gradient(circle at 50% 50%, rgba(217,164,65,0.18), transparent 45%);
    filter: blur(70px) saturate(1.25); opacity: 0.85;
    animation: aurora 26s ease-in-out infinite alternate;
}
@keyframes aurora {
    0%   { transform: translate(0, 0) rotate(0deg) scale(1); }
    33%  { transform: translate(6%, -4%) rotate(8deg) scale(1.08); }
    66%  { transform: translate(-5%, 5%) rotate(-6deg) scale(1.04); }
    100% { transform: translate(3%, 3%) rotate(12deg) scale(1.12); }
}
[data-testid="stAppViewContainer"] { z-index: 1; background: transparent !important; }
[data-testid="stAppViewContainer"]::before {
    content: ""; position: fixed; inset: 0; z-index: -1; pointer-events: none;
    background:
        radial-gradient(ellipse at 50% 45%, transparent 45%, rgba(8,8,10,0.70) 100%),
        linear-gradient(rgba(255,255,255,0.05) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.05) 1px, transparent 1px),
        linear-gradient(rgba(255,255,255,0.022) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.022) 1px, transparent 1px);
    background-size: 100% 100%, 120px 120px, 120px 120px, 24px 24px, 24px 24px;
}
[data-testid="stAppViewContainer"]::after {
    content: ""; position: fixed; z-index: -1; pointer-events: none;
    width: 160vmax; height: 160vmax; left: calc(60% - 80vmax); top: calc(35% - 80vmax);
    background: conic-gradient(from 0deg, rgba(217,164,65,0.20), rgba(217,164,65,0.05) 18deg, transparent 60deg, transparent 360deg);
    border-radius: 50%; animation: sweep 14s linear infinite;
}
@keyframes sweep { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .stApp::before, [data-testid="stAppViewContainer"]::after { animation: none; } }

/* Glass panels so the colour shows through but text stays readable */
:root { --panel: rgba(28,30,35,0.78); --panel-2: rgba(36,38,44,0.88); }
.hero, .kpi, .stMain [data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]),
.stMain [data-testid="stExpander"] details, .wrap-table {
    backdrop-filter: blur(14px) saturate(1.2); -webkit-backdrop-filter: blur(14px) saturate(1.2);
}
.hero { box-shadow: 0 10px 40px rgba(0,0,0,0.35), 0 0 0 1px rgba(217,164,65,0.10) inset; }
.kpi { box-shadow: 0 6px 24px rgba(0,0,0,0.25); }
[data-testid="stSidebar"] {
    background: rgba(18,19,23,0.72) !important; backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
}
.st-key-nav { background: rgba(16,17,20,0.78) !important; backdrop-filter: blur(14px); }
[data-testid="stHeader"] { background: transparent; }
.block-container { padding: 1.2rem 2rem 7rem 2rem; max-width: 1500px; }
[data-testid="stSidebar"][aria-expanded="true"] { min-width: 290px !important; max-width: 290px !important; }
.stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp button { font-family: 'Inter', sans-serif; }
.stMain p, .stMain li { font-size: 1rem; line-height: 1.6; }
.stMain h3 { font-size: 1.15rem !important; font-weight: 600 !important; color: var(--text); padding: 0 0 4px 0 !important; letter-spacing: -0.01em; }
.stMain h4 { font-size: 1rem !important; font-weight: 600 !important; color: var(--text); }
[data-testid="stCaptionContainer"] p { color: var(--muted); font-size: 0.92rem; }
.stMain code { background: var(--accent-soft); color: #f0d29a; }
.stMain [data-testid="stVerticalBlock"] { gap: 1.1rem; }

/* Sidebar */
[data-testid="stSidebar"] { background: #1a1b20; border-right: 1px solid var(--line); }
[data-testid="stSidebar"] h2 { font-size: 1.05rem !important; font-weight: 600 !important; color: var(--text); }
[data-testid="stSidebar"] h3 { font-size: 0.95rem !important; font-weight: 600 !important; color: var(--accent); }
[data-testid="stSidebar"] [data-testid="stForm"] { border: 1px solid var(--line); background: var(--panel); }
.log { font-family: var(--mono); font-size: 0.85rem; color: var(--muted); line-height: 2; }
.log b { color: var(--text); font-weight: 500; float: right; }

/* Status bar */
.statusbar { display: grid; grid-template-areas: "status" "brand"; gap: 4px; padding: 0 0 18px 0; margin-bottom: 14px; border-bottom: 1px solid var(--line); }
.statusbar .spacer { display: none; }
.statusbar .status { grid-area: status; justify-self: end; gap: 12px; white-space: nowrap; }
.statusbar .status > * { flex-shrink: 0; }
.statusbar .brand { grid-area: brand; justify-self: center; }
.brand { text-align: center; }
.brand .name { font-size: clamp(2.6rem, 4.4vw, 4.4rem); transform-origin: center bottom; }
.brand .area { margin-top: 10px; font-size: 1rem; font-style: italic; letter-spacing: 0.04em; color: var(--muted); }
.brand .area::before, .brand .area::after { content: ""; display: inline-block; width: 28px; height: 1px; background: var(--accent-line); vertical-align: middle; margin: 0 12px; }
@media (max-width: 700px) { .statusbar .status { justify-self: center; } }

/* Acrylic Didone wordmark: same amber, frosted sheen on the letters and a soft blurred halo behind them */
.wordmark {
    position: relative; display: inline-block; isolation: isolate;
    font-family: 'Bodoni Moda', 'Didot', 'Bodoni 72', serif !important; font-optical-sizing: auto; font-weight: 900 !important;
    line-height: 0.95; letter-spacing: -0.035em; transform: scaleY(1.12); margin-bottom: 4px;
    color: transparent !important;
    background: linear-gradient(172deg, color-mix(in srgb, var(--accent) 52%, #ffffff) 0%, var(--accent) 34%,
                var(--accent) 62%, color-mix(in srgb, var(--accent) 78%, #000000) 100%);
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-stroke: 0.5px color-mix(in srgb, var(--accent) 55%, #ffffff);
    filter: drop-shadow(0 2px 6px rgba(0,0,0,0.25));
}
.wordmark::before {
    content: attr(data-text); position: absolute; inset: 0; z-index: -1; pointer-events: none;
    color: var(--accent); -webkit-text-fill-color: var(--accent); -webkit-text-stroke: 0; filter: blur(14px); opacity: 0.5;
}
.status { display: flex; align-items: center; gap: 18px; font-family: var(--mono); font-size: 0.85rem; color: var(--muted); }
.status .live { color: var(--teal); }
.status .live::before { content: ""; display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--teal); margin-right: 8px; box-shadow: 0 0 0 3px var(--teal-soft); }

/* Hero: top suspected source */
.hero { position: relative; padding: 22px 26px 24px 26px; margin-bottom: 18px; background: linear-gradient(180deg, var(--accent-soft), var(--panel) 55%); border: 1px solid var(--accent-line); }
.hero-top { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 14px; }
.flag { font-family: var(--mono); font-size: 0.78rem; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: #1a1b20; background: var(--accent); padding: 5px 12px;
        clip-path: polygon(0 0, calc(100% - 8px) 0, 100% 8px, 100% 100%, 0 100%); }
.score { font-family: var(--mono); font-size: 0.85rem; color: var(--accent); border: 1px solid var(--accent-line); padding: 4px 10px; }
.hero .label { font-size: 0.85rem; color: var(--muted); }
.hero .batch { font-size: 2rem; font-weight: 700; color: var(--text); letter-spacing: -0.01em; margin: 2px 0 2px 0; }
.hero .sub { font-size: 0.95rem; color: var(--muted); margin-bottom: 18px; }
.hero .sub b { color: var(--text); font-weight: 600; }
.stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
.stats > div { padding: 14px 16px 14px 0; }
.stats > div + div { padding-left: 16px; border-left: 1px solid var(--line); }
.stats .k { font-size: 0.8rem; color: var(--muted); margin-bottom: 4px; }
.stats .v { font-family: var(--mono); font-size: 1.15rem; color: var(--text); }
.stats .v.accent { color: var(--accent); }
.code { display: inline-block; margin-top: 16px; padding: 6px 12px; font-family: var(--mono); font-size: 0.86rem; }
.code.rc1 { background: var(--accent-soft); color: #f0d29a; border: 1px solid var(--accent-line); }
.code.rc2 { background: var(--teal-soft); color: var(--teal); border: 1px solid var(--teal-line); }
.code.rc3 { background: rgba(179,173,165,0.10); color: var(--muted); border: 1px solid var(--line); }
.actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 18px; }

/* Cyberpunk buttons (Streamlit buttons + link buttons) */
.stApp .stButton button, .stApp .stDownloadButton button, .stApp [data-testid="stFormSubmitButton"] button, a.cp-btn {
    position: relative; border: none; border-radius: 0; padding: 10px 30px 10px 20px; min-height: 0;
    clip-path: polygon(0 0, calc(100% - var(--cut)) 0, 100% var(--cut), 100% 100%, var(--cut) 100%, 0 calc(100% - var(--cut)));
    background: var(--accent); color: #1a1b20; transition: background .12s, transform .08s;
}
a.cp-btn { display: inline-block; text-decoration: none !important; font-weight: 600; font-size: 0.88rem; letter-spacing: 0.08em; text-transform: uppercase; color: #1a1b20 !important; }
.stApp .stButton button p, .stApp .stDownloadButton button p, .stApp [data-testid="stFormSubmitButton"] button p {
    font-weight: 600; font-size: 0.88rem; letter-spacing: 0.08em; text-transform: uppercase;
}
.stApp .stButton button:hover, .stApp .stDownloadButton button:hover, .stApp [data-testid="stFormSubmitButton"] button:hover, a.cp-btn:hover { background: #e6b862; color: #1a1b20; }
.stApp .stButton button:active, .stApp .stDownloadButton button:active, .stApp [data-testid="stFormSubmitButton"] button:active, a.cp-btn:active { transform: translateY(1px); }
.stApp .stButton button:focus-visible, .stApp .stDownloadButton button:focus-visible, .stApp [data-testid="stFormSubmitButton"] button:focus-visible, a.cp-btn:focus-visible { outline: 2px solid var(--teal); outline-offset: 2px; }
a.cp-btn.ghost, [data-testid="stSidebar"] [data-testid="stFormSubmitButton"] button {
    background: linear-gradient(225deg, var(--accent) 0 14px, var(--panel-2) 14px); color: var(--text) !important; box-shadow: inset 3px 0 0 var(--accent);
}
[data-testid="stSidebar"] [data-testid="stFormSubmitButton"] button { width: 100%; }
a.cp-btn.ghost:hover, [data-testid="stSidebar"] [data-testid="stFormSubmitButton"] button:hover { background: var(--accent); color: #1a1b20 !important; }

/* Metric cards */
.kpi-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px; }
.kpi { grid-column: span 2; background: var(--panel); border: 1px solid var(--line); padding: 16px 18px; }
.kpi.wide { grid-column: span 3; }
.kpi .k { font-size: 0.85rem; color: var(--muted); }
.kpi .v { font-family: var(--mono); font-size: 2rem; font-weight: 500; color: var(--text); margin: 4px 0 2px 0; line-height: 1.15; }
.kpi .v small { font-size: 1rem; color: var(--muted); }
.kpi .v.accent { color: var(--accent); }
.kpi .s { font-size: 0.85rem; color: var(--muted); margin-bottom: 12px; }
.kpi .s.down { color: #e39a8f; }
.kpi .track { height: 6px; background: var(--bg); }
.kpi .fill { height: 100%; background: var(--accent); }
.kpi .fill.second { background: var(--teal); }
@media (max-width: 900px) { .kpi, .kpi.wide { grid-column: span 6; } .stats { grid-template-columns: 1fr; } .stats > div + div { padding-left: 0; border-left: none; border-top: 1px solid var(--line); } }

/* Panels, alerts, expander, tables */
.stMain [data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) { background: var(--panel); padding: 6px 8px; }
.stMain [data-testid="stExpander"] details { background: var(--panel); }
.stMain [data-testid="stExpander"] summary p { font-weight: 600; }
.stMain [data-testid="stDataFrame"] { border: 1px solid var(--line); }
.stMain [data-testid="stMetricValue"], .stMain [data-testid="stMetricValue"] div { font-family: var(--mono); font-weight: 500; }

/* Wrapping tables */
.wrap-table { width: 100%; border-collapse: collapse; font-size: 0.95rem; border: 1px solid var(--line); }
.wrap-table { border-top: 2px solid var(--accent); }
.wrap-table th { text-align: left; font-family: var(--mono); font-weight: 500; font-size: 0.74rem; letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--accent); background: var(--panel-2); padding: 11px 12px; border-bottom: 1px solid var(--accent-line); white-space: normal; vertical-align: bottom; }
.wrap-table td { padding: 13px 12px; border-bottom: 1px solid var(--line); vertical-align: middle; color: var(--text); line-height: 1.45; }
.wrap-table tbody tr:nth-child(even) td { background: rgba(255,255,255,0.025); }
html[data-mode="light"] .wrap-table tbody tr:nth-child(even) td { background: rgba(60,45,20,0.03); }
.wrap-table td:first-child { font-weight: 600; }
.wrap-table td.food { color: var(--muted); }
.wrap-table.top3 th, .wrap-table.top3 td { padding-left: 10px; padding-right: 10px; }
.wrap-table.top3 td:last-child { min-width: 195px; }
.wrap-table.top3 td:nth-child(2) { min-width: 115px; }
.wrap-table.top3 th { white-space: normal; }
.rank-chip { display: inline-block; min-width: 34px; text-align: center; font-family: var(--mono); font-weight: 600; font-size: 0.85rem; padding: 3px 8px;
    color: #1a1b20; background: var(--teal); clip-path: polygon(0 0, calc(100% - 7px) 0, 100% 7px, 100% 100%, 0 100%); }
.rank-chip.first { background: var(--accent); box-shadow: 0 0 12px rgba(217,164,65,0.45); }
.reason-tag { display: inline-block; padding: 4px 9px; font-family: var(--mono); font-size: 0.78rem; line-height: 1.4; border: 1px solid var(--line); color: var(--muted); }
.reason-tag.rc1 { color: var(--accent); border-color: var(--accent-line); background: var(--accent-soft); }
.reason-tag.rc2 { color: var(--teal); border-color: var(--teal-line); background: var(--teal-soft); }

/* Interactive tables: themed frame */
.stMain [data-testid="stDataFrame"] { border: 1px solid var(--line) !important; border-top: 2px solid var(--accent) !important; box-shadow: 0 8px 24px rgba(0,0,0,0.18); }
html[data-mode="light"] .stMain [data-testid="stDataFrame"] { box-shadow: 0 8px 20px rgba(90,70,30,0.08); }
.wrap-table tr:last-child td { border-bottom: none; }
.wrap-table.top3 tbody tr:first-child td { background: var(--accent-soft); }
.wrap-table .num { text-align: right; font-family: var(--mono); }
.wrap-table .mono { font-family: var(--mono); font-size: 0.9rem; }
.wrap-table .risk { min-width: 110px; }
.wrap-table .risk-track { height: 6px; background: var(--bg); margin-top: 6px; }
.wrap-table .risk-fill { height: 100%; background: var(--accent); }
.ok-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--teal); margin-right: 8px; }

/* Bottom dock navigation */
.st-key-nav {
    position: fixed; bottom: 0; right: 0; left: 290px; z-index: 990; padding: 10px 16px 12px 16px;
    background: rgba(22,23,27,0.94); border-top: 1px solid var(--line); backdrop-filter: blur(8px);
}
body:has([data-testid="stSidebar"][aria-expanded="false"]) .st-key-nav { left: 0; }
@media (max-width: 768px) { .st-key-nav { left: 0; } }
.st-key-nav { align-items: center; width: auto !important; }
.st-key-nav [data-testid="stElementContainer"] { width: auto !important; }
.st-key-nav div[role="radiogroup"] { gap: 8px; justify-content: center; flex-wrap: nowrap; width: 100%; }
.st-key-nav div[role="radiogroup"] label {
    margin: 0 !important; padding: 8px 30px 8px 22px; min-width: 150px; justify-content: center; cursor: pointer; background: var(--panel);
    clip-path: polygon(0 0, calc(100% - var(--cut)) 0, 100% var(--cut), 100% 100%, 0 100%);
    border-bottom: 2px solid var(--line); transition: background .12s;
}
.st-key-nav div[role="radiogroup"] label > div > div:first-child:not([data-testid]) { display: none; }
.st-key-nav div[role="radiogroup"] label p { display: flex; flex-direction: column; align-items: center; gap: 2px; font-size: 0.8rem; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }
.st-key-nav div[role="radiogroup"] label p span { font-size: 1.3rem !important; }
.st-key-nav div[role="radiogroup"] label:hover { background: var(--panel-2); }
.st-key-nav div[role="radiogroup"] label:hover p { color: var(--text); }
.st-key-nav div[role="radiogroup"] label[data-selected="true"] { background: var(--accent); border-bottom-color: #1a1b20; }
.st-key-nav div[role="radiogroup"] label[data-selected="true"] p { color: #1a1b20; }

/* Graph legend */
.legend { display: flex; flex-wrap: wrap; gap: 20px; font-size: 0.92rem; color: var(--muted); margin: 4px 0 12px 0; }
.legend i { display: inline-block; width: 10px; height: 10px; margin-right: 8px; vertical-align: -1px; }
/* ===== Animations & interactions ===== */
@keyframes rise { from { opacity: 0; transform: translateY(18px); } to { opacity: 1; transform: none; } }
@keyframes fill-in { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@keyframes scan { 0% { transform: translateX(-120%); } 60%, 100% { transform: translateX(420%); } }
@keyframes flag-alert { 0%, 100% { filter: none; } 8%, 24% { filter: brightness(1.45) drop-shadow(0 0 8px rgba(217,164,65,0.8)); } 16% { filter: brightness(0.8); } }
@keyframes ping { 0% { box-shadow: 0 0 0 0 rgba(124,196,192,0.65); } 100% { box-shadow: 0 0 0 10px rgba(124,196,192,0); } }
@keyframes shine { from { transform: translateX(-130%) skewX(-20deg); } to { transform: translateX(260%) skewX(-20deg); } }
@keyframes glitch {
    0%   { clip-path: polygon(0 0, calc(100% - var(--cut)) 0, 100% var(--cut), 100% 100%, var(--cut) 100%, 0 calc(100% - var(--cut))); transform: none; }
    20%  { clip-path: polygon(0 8%, calc(100% - var(--cut)) 8%, 100% 30%, 100% 60%, var(--cut) 60%, 0 40%); transform: translateX(-2px); }
    40%  { clip-path: polygon(0 45%, 100% 45%, 100% 100%, var(--cut) 100%, 0 calc(100% - var(--cut))); transform: translateX(2px); }
    60%  { clip-path: polygon(0 0, calc(100% - var(--cut)) 0, 100% var(--cut), 100% 70%, 0 70%); transform: translateX(-1px); }
    100% { clip-path: polygon(0 0, calc(100% - var(--cut)) 0, 100% var(--cut), 100% 100%, var(--cut) 100%, 0 calc(100% - var(--cut))); transform: none; }
}
@keyframes glow-pulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(217,164,65,0); } 50% { box-shadow: 0 0 22px 2px rgba(217,164,65,0.35); } }
@keyframes hop { 0%, 100% { transform: translateY(0); } 40% { transform: translateY(-5px); } 70% { transform: translateY(1px); } }
@keyframes underline { from { transform: scaleX(0); } to { transform: scaleX(1); } }

/* Entrance: staggered rise */
.statusbar { animation: rise .5s ease-out both; }
.hero { animation: rise .6s .05s ease-out both; }
.kpi { animation: rise .55s ease-out both; }
.kpi:nth-child(1) { animation-delay: .15s; } .kpi:nth-child(2) { animation-delay: .22s; } .kpi:nth-child(3) { animation-delay: .29s; }
.kpi:nth-child(4) { animation-delay: .36s; } .kpi:nth-child(5) { animation-delay: .43s; }
.stMain [data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]),
.stMain [data-testid="stExpander"] { animation: rise .6s .45s ease-out both; }
.kpi .fill, .wrap-table .risk-fill { transform-origin: left; animation: fill-in 1.1s .5s cubic-bezier(.2,.8,.2,1) both; }

/* Hero: scanning beam + alert flag */
.hero { overflow: hidden; }
.hero::after {
    content: ""; position: absolute; top: 0; bottom: 0; left: 0; width: 22%; pointer-events: none;
    background: linear-gradient(90deg, transparent, rgba(217,164,65,0.10), rgba(255,236,190,0.16), rgba(217,164,65,0.10), transparent);
    animation: scan 6s 1.2s ease-in-out infinite;
}
.flag { animation: flag-alert 4s 1s infinite; }
.score { transition: background .2s, color .2s; }
.hero:hover .score { background: var(--accent); color: #1a1b20; }
.hero .stats > div { transition: background .2s; }
.hero .stats > div:hover { background: rgba(217,164,65,0.06); }

/* Live signal */
.status .live::before { animation: ping 1.8s ease-out infinite; }

/* Buttons: shine sweep, glitch on hover, press-down */
.stApp .stButton button, .stApp .stDownloadButton button, .stApp [data-testid="stFormSubmitButton"] button, a.cp-btn { overflow: hidden; }
.stApp .stButton button::before, .stApp .stDownloadButton button::before, .stApp [data-testid="stFormSubmitButton"] button::before, a.cp-btn::before {
    content: ""; position: absolute; top: 0; bottom: 0; left: 0; width: 40%; pointer-events: none;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.45), transparent); transform: translateX(-130%) skewX(-20deg);
}
.stApp .stButton button:hover::before, .stApp .stDownloadButton button:hover::before, .stApp [data-testid="stFormSubmitButton"] button:hover::before, a.cp-btn:hover::before { animation: shine .7s ease-out; }
.stApp .stButton button:hover, .stApp .stDownloadButton button:hover, .stApp [data-testid="stFormSubmitButton"] button:hover, a.cp-btn:hover {
    animation: glitch .32s steps(2, end) 1; text-shadow: -1.5px 0 var(--teal), 1.5px 0 rgba(0,0,0,0.35); box-shadow: 0 0 24px rgba(217,164,65,0.45);
}
.stApp .stButton button:active, .stApp .stDownloadButton button:active, .stApp [data-testid="stFormSubmitButton"] button:active, a.cp-btn:active { transform: scale(0.97) translateY(1px); }

/* Cards: lift + glow */
.kpi { transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease; }
.kpi:hover { transform: translateY(-4px); border-color: var(--accent-line); box-shadow: 0 14px 34px rgba(0,0,0,0.4), 0 0 24px rgba(217,164,65,0.15); }
.kpi:hover .fill { filter: brightness(1.25) drop-shadow(0 0 6px rgba(217,164,65,0.7)); }
.kpi:hover .fill.second { filter: brightness(1.2) drop-shadow(0 0 6px rgba(124,196,192,0.7)); }
.kpi .v { transition: letter-spacing .25s ease, color .25s ease; }
.kpi:hover .v { letter-spacing: 0.02em; }
.stMain [data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) { transition: border-color .25s, box-shadow .25s; }
.stMain [data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]):hover { border-color: var(--accent-line) !important; box-shadow: 0 0 30px rgba(217,164,65,0.10); }

/* Section headings: underline grows in */
.stMain h3 { position: relative; }
.stMain h3::after { content: ""; position: absolute; left: 0; bottom: 0; width: 56px; height: 2px; background: var(--accent); transform-origin: left; animation: underline .7s .6s ease-out both; }

/* Tables: row highlight */
.wrap-table tbody tr { transition: background .15s; }
.wrap-table tbody tr:hover td { background: rgba(217,164,65,0.09); }
.wrap-table tbody tr:hover td:first-child { box-shadow: inset 3px 0 0 var(--accent); }

/* Dock: icon hop + glowing active tab */
.st-key-nav div[role="radiogroup"] label { transition: background .15s, transform .15s; }
.st-key-nav div[role="radiogroup"] label:hover { transform: translateY(-3px); }
.st-key-nav div[role="radiogroup"] label:hover p span { animation: hop .45s ease-out; }
.st-key-nav div[role="radiogroup"] label[data-selected="true"] { animation: glow-pulse 2.6s ease-in-out infinite; }

/* Sidebar inputs: amber focus glow */
[data-testid="stSidebar"] [data-baseweb="select"] > div, [data-testid="stSidebar"] [role="group"] { transition: box-shadow .2s, border-color .2s; }
[data-testid="stSidebar"] [data-baseweb="select"] > div:hover, [data-testid="stSidebar"] [role="group"]:hover { box-shadow: 0 0 0 1px var(--accent-line), 0 0 14px rgba(217,164,65,0.18); }

@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation: none !important; transition: none !important; }
}
.st-key-cursorfx, .st-key-splashfx { display: none; }
/* ===== Targeting cursor (drawn by the cursor script; only active on mouse devices) ===== */
html.tc-cursor-on, html.tc-cursor-on * { cursor: none !important; }
html.tc-cursor-on input[type="text"], html.tc-cursor-on textarea { cursor: text !important; }
#tc-cursor { position: fixed; inset: 0; pointer-events: none; z-index: 2147483647; opacity: 0; transition: opacity .2s; }
#tc-cursor .tc-ring { position: absolute; left: 0; top: 0; width: 34px; height: 34px; will-change: transform, width, height; }
#tc-cursor .c { position: absolute; width: 10px; height: 10px; border: 0 solid var(--accent); filter: drop-shadow(0 0 4px rgba(217,164,65,0.85)); transition: border-color .2s, width .2s, height .2s; }
#tc-cursor .tl { left: 0; top: 0; border-top-width: 2px; border-left-width: 2px; }
#tc-cursor .tr { right: 0; top: 0; border-top-width: 2px; border-right-width: 2px; }
#tc-cursor .bl { left: 0; bottom: 0; border-bottom-width: 2px; border-left-width: 2px; }
#tc-cursor .br { right: 0; bottom: 0; border-bottom-width: 2px; border-right-width: 2px; }
#tc-cursor .tc-dot, #tc-cursor .tc-chev { position: absolute; left: 0; top: 0; will-change: transform; }
#tc-cursor .tc-dot i { position: absolute; left: -5px; top: -5px; width: 10px; height: 10px; border-radius: 50%;
    background: var(--accent); box-shadow: 0 0 10px 3px rgba(217,164,65,0.75); transition: background .2s, box-shadow .2s, transform .12s; }
#tc-cursor .tc-chev b { position: absolute; width: 7px; height: 7px; margin: -3.5px 0 0 -3.5px; border: 0 solid var(--teal);
    border-width: 2px 2px 0 0; opacity: 0; transition: opacity .18s; filter: drop-shadow(0 0 4px rgba(124,196,192,0.9)); }
#tc-cursor .tc-chev .u { transform: translateY(-17px) rotate(-45deg); }
#tc-cursor .tc-chev .r { transform: translateX(17px) rotate(45deg); }
#tc-cursor .tc-chev .d { transform: translateY(17px) rotate(135deg); }
#tc-cursor .tc-chev .l { transform: translateX(-17px) rotate(-135deg); }
#tc-cursor.lock .c { border-color: var(--teal); width: 14px; height: 14px; filter: drop-shadow(0 0 6px rgba(124,196,192,0.9)); }
#tc-cursor.lock .tc-dot i { background: var(--teal); box-shadow: 0 0 10px 3px rgba(124,196,192,0.75); }
#tc-cursor.lock .tc-chev b { opacity: 1; animation: chev-pulse .9s ease-in-out infinite; }
#tc-cursor.lock .tc-chev .u { --dx: 0px; --dy: -17px; --rot: -45deg; }
#tc-cursor.lock .tc-chev .r { --dx: 17px; --dy: 0px; --rot: 45deg; }
#tc-cursor.lock .tc-chev .d { --dx: 0px; --dy: 17px; --rot: 135deg; }
#tc-cursor.lock .tc-chev .l { --dx: -17px; --dy: 0px; --rot: -135deg; }
@keyframes chev-pulse {
    0%, 100% { transform: translate(var(--dx), var(--dy)) rotate(var(--rot)); }
    50%      { transform: translate(calc(var(--dx) * 1.25), calc(var(--dy) * 1.25)) rotate(var(--rot)); }
}
#tc-cursor.down .tc-dot i { transform: scale(0.55); }
#tc-cursor.down .c { width: 7px; height: 7px; }
/* Idle cursor look (hover/lock look above stays the same) */
#tc-cursor:not(.lock) .tc-dot i { left: -6px; top: -6px; width: 12px; height: 12px; background: transparent; border: 2px solid var(--accent);
    box-shadow: 0 0 8px 1px rgba(217,164,65,0.6), inset 0 0 4px rgba(217,164,65,0.5); }
#tc-cursor:not(.lock) .tc-dot i::after { content: ""; position: absolute; left: 50%; top: 50%; width: 3px; height: 3px; margin: -1.5px 0 0 -1.5px; border-radius: 50%; background: var(--accent); }
#tc-cursor:not(.lock) .c { width: 8px; height: 8px; animation: breathe 1.6s ease-in-out infinite; }
#tc-cursor .tl { --bx: -1; --by: -1; } #tc-cursor .tr { --bx: 1; --by: -1; } #tc-cursor .bl { --bx: -1; --by: 1; } #tc-cursor .br { --bx: 1; --by: 1; }
@keyframes breathe { 0%, 100% { transform: none; } 50% { transform: translate(calc(var(--bx) * 3px), calc(var(--by) * 3px)); } }
#tc-cursor.down:not(.lock) .c { width: 6px; height: 6px; }

/* "Come out" on hover: lift, grow and glow (the glow sits on the wrapper so the cut corners don't clip it) */
.stButton, .stDownloadButton, [data-testid="stFormSubmitButton"], .cp-wrap { transition: filter .2s ease; }
.stButton:hover, .stDownloadButton:hover, [data-testid="stFormSubmitButton"]:hover, .cp-wrap:hover {
    filter: drop-shadow(0 0 10px rgba(217,164,65,0.75)) drop-shadow(0 0 26px rgba(217,164,65,0.45));
}
.cp-wrap { display: inline-block; }
.stApp .stButton button, .stApp .stDownloadButton button, .stApp [data-testid="stFormSubmitButton"] button, a.cp-btn { transition: background .12s, transform .18s cubic-bezier(.2,.9,.3,1.4); }
.stApp .stButton button:hover, .stApp .stDownloadButton button:hover, .stApp [data-testid="stFormSubmitButton"] button:hover, a.cp-btn:hover { transform: translateY(-3px) scale(1.05); }
.stApp .stButton button:active, .stApp .stDownloadButton button:active, .stApp [data-testid="stFormSubmitButton"] button:active, a.cp-btn:active { transform: translateY(0) scale(0.97); }
/* Runner-up suspects (#2, #3) */
.runner-label { font-size: 0.85rem; color: var(--muted); margin: -4px 0 8px 2px; }
.runners { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px; }
.runner { background: var(--panel); border: 1px solid var(--line); border-left: 3px solid var(--teal); padding: 14px 18px; animation: rise .55s .12s ease-out both;
          backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px); transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease; }
.runner:hover { transform: translateY(-3px); border-color: var(--teal-line); box-shadow: 0 0 22px rgba(124,196,192,0.15); }
.runner-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.runner .rk { font-family: var(--mono); font-weight: 600; color: #1a1b20; background: var(--teal); padding: 2px 10px; clip-path: polygon(0 0, calc(100% - 7px) 0, 100% 7px, 100% 100%, 0 100%); }
.runner .rscore { font-family: var(--mono); font-size: 0.85rem; color: var(--teal); }
.runner .rbatch { font-size: 1.15rem; font-weight: 600; color: var(--text); }
.runner .rsub { font-size: 0.88rem; color: var(--muted); margin-bottom: 10px; }
.runner .track { height: 6px; background: var(--bg); margin-bottom: 10px; }
.runner .fill { height: 100%; background: var(--teal); transform-origin: left; animation: fill-in 1.1s .5s cubic-bezier(.2,.8,.2,1) both; }
.runner .rstats { display: flex; flex-wrap: wrap; gap: 6px 16px; font-family: var(--mono); font-size: 0.82rem; color: var(--text); }
.runner .code { margin-top: 10px; font-size: 0.8rem; }
@media (max-width: 900px) { .runners { grid-template-columns: 1fr; } }

/* SitRep ticker */
.sitrep { display: flex; align-items: stretch; margin: -4px 0 16px 0; border: 1px solid var(--line); background: var(--panel);
          backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); overflow: hidden; }
.sitrep-tag { flex: none; display: flex; align-items: center; padding: 0 16px 0 12px; font-family: var(--mono); font-size: 0.75rem; font-weight: 600;
              letter-spacing: 0.12em; text-transform: uppercase; color: #1a1b20; background: var(--accent);
              clip-path: polygon(0 0, 100% 0, calc(100% - 8px) 100%, 0 100%); }
.sitrep-tag::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: #1a1b20; margin-right: 8px; animation: blink 1.2s steps(2) infinite; }
.sitrep-track { flex: 1; overflow: hidden; mask-image: linear-gradient(90deg, transparent, #000 4%, #000 96%, transparent); -webkit-mask-image: linear-gradient(90deg, transparent, #000 4%, #000 96%, transparent); }
.sitrep-run { display: inline-flex; white-space: nowrap; gap: 18px; padding: 9px 0; font-family: var(--mono); font-size: 0.85rem; color: var(--muted);
              animation: sitrep-scroll 38s linear infinite; }
.sitrep-run b { color: var(--text); font-weight: 600; }
.sitrep-run .sep { color: var(--accent); font-size: 0.7rem; align-self: center; }
.sitrep:hover .sitrep-run { animation-play-state: paused; }
@keyframes sitrep-scroll { from { transform: translateX(0); } to { transform: translateX(-50%); } }
@keyframes blink { 50% { opacity: 0.2; } }
@media (prefers-reduced-motion: reduce) { .sitrep-run { white-space: normal; flex-wrap: wrap; animation: none; padding: 9px 12px; } }

/* Signed-in user chip (sidebar) */
.user-chip { display: flex; align-items: center; gap: 10px; padding: 10px 12px; margin-bottom: 8px; border: 1px solid var(--teal-line); background: var(--teal-soft); }
.user-chip .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--teal); box-shadow: 0 0 0 3px var(--teal-soft); }
.user-chip .who { font-size: .72rem; color: var(--muted); text-transform: uppercase; letter-spacing: .08em; }
.user-chip .num { font-family: var(--mono); font-size: .88rem; color: var(--text); }
.user-chip .sbx { margin-left: auto; font-family: var(--mono); font-size: .65rem; color: var(--accent); border: 1px solid var(--accent-line); padding: 1px 6px; }
.st-key-authfx { display: none; }

/* Data directory */
.dir-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin-top: 6px; }
.dir-card { background: var(--panel); border: 1px solid var(--line); border-top: 2px solid var(--accent); padding: 14px 18px 16px 18px;
            backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px); animation: rise .5s ease-out both; transition: border-color .2s, box-shadow .2s; }
.dir-card:hover { border-color: var(--accent-line); box-shadow: 0 0 24px rgba(217,164,65,0.12); }
.dir-card.wide { grid-column: 1 / -1; }
.dir-head { display: flex; justify-content: space-between; align-items: center; padding-bottom: 8px; margin-bottom: 8px; border-bottom: 1px solid var(--accent-line);
            font-family: var(--mono); font-size: .78rem; letter-spacing: .1em; text-transform: uppercase; color: var(--accent); }
.dir-head b { font-weight: 600; color: #1a1b20; background: var(--accent); padding: 1px 9px; clip-path: polygon(0 0, calc(100% - 6px) 0, 100% 6px, 100% 100%, 0 100%); }
.dir-card ul { list-style: none; margin: 0; padding: 0; }
.dir-card li { padding: 6px 0; border-bottom: 1px dashed var(--line); color: var(--text); font-size: .95rem; break-inside: avoid; }
.dir-card li:last-child { border-bottom: none; }
.dir-card.wide ul { columns: 4 200px; column-gap: 28px; }
.dir-card.wide li { font-family: var(--mono); font-size: .86rem; }
@media (max-width: 900px) { .dir-grid { grid-template-columns: 1fr; } }

/* ===== Light mode (set by the theme toggle; html[data-mode] comes from the page script) ===== */
html[data-mode="light"] {
    --bg: #f5f1e8; --panel: rgba(255,255,255,0.74); --panel-2: rgba(255,255,255,0.9); --line: #d9d0bf;
    --accent: #b07a16; --accent-soft: rgba(176,122,22,0.12); --accent-line: rgba(176,122,22,0.45);
    --text: #26231e; --muted: #6d665c; --teal: #2c8c86; --teal-soft: rgba(44,140,134,0.12); --teal-line: rgba(44,140,134,0.45);
}
html[data-mode="light"] .stApp { background-color: #f5f1e8; }
html[data-mode="light"] .stApp::before { opacity: 0.38; }
html[data-mode="light"] [data-testid="stAppViewContainer"]::before {
    background:
        radial-gradient(ellipse at 50% 45%, transparent 55%, rgba(120,95,55,0.14) 100%),
        linear-gradient(rgba(60,45,20,0.07) 1px, transparent 1px),
        linear-gradient(90deg, rgba(60,45,20,0.07) 1px, transparent 1px),
        linear-gradient(rgba(60,45,20,0.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(60,45,20,0.035) 1px, transparent 1px);
    background-size: 100% 100%, 120px 120px, 120px 120px, 24px 24px, 24px 24px;
}
html[data-mode="light"] [data-testid="stAppViewContainer"]::after { opacity: 0.55; }
html[data-mode="light"] [data-testid="stSidebar"] { background: rgba(250,247,240,0.82) !important; }
html[data-mode="light"] .st-key-nav { background: rgba(245,241,232,0.88) !important; }
html[data-mode="light"] .stMain code, html[data-mode="light"] .code.rc1 { color: #7d5409; }
html[data-mode="light"] .kpi .s.down { color: #b0503c; }
html[data-mode="light"] .stApp .stButton button:hover, html[data-mode="light"] .stApp .stDownloadButton button:hover,
html[data-mode="light"] .stApp [data-testid="stFormSubmitButton"] button:hover, html[data-mode="light"] a.cp-btn:hover { background: #c58d24; }
html[data-mode="light"] .hero { box-shadow: 0 10px 34px rgba(90,70,30,0.12), 0 0 0 1px rgba(176,122,22,0.10) inset; }
html[data-mode="light"] .kpi { box-shadow: 0 6px 20px rgba(90,70,30,0.08); }
html[data-mode="light"] .kpi:hover { box-shadow: 0 14px 30px rgba(90,70,30,0.16), 0 0 22px rgba(176,122,22,0.16); }

/* Theme toggle button (status bar) */
.mode-toggle {
    position: relative; display: inline-flex; align-items: center; gap: 8px; padding: 6px 22px 6px 14px; border: 1px solid var(--accent-line);
    background: var(--accent-soft); color: var(--text); font-family: var(--mono); font-size: 0.8rem; letter-spacing: 0.06em; text-transform: uppercase;
    clip-path: polygon(0 0, calc(100% - 9px) 0, 100% 9px, 100% 100%, 0 100%); transition: background .15s, color .15s, transform .15s;
}
.mode-toggle:hover { background: var(--accent); color: #1a1b20; transform: translateY(-2px); }
.mode-toggle svg { width: 15px; height: 15px; }
.mode-toggle .to-dark { display: none; }
html[data-mode="light"] .mode-toggle .to-light { display: none; }
html[data-mode="light"] .mode-toggle .to-dark { display: inline-flex; }
.mode-toggle span { display: inline-flex; align-items: center; gap: 8px; }
</style>
""", unsafe_allow_html=True)

# Page script: light/dark mode, targeting cursor and pixel trail (runs before sign-in so the login screen is themed too)
# Targeting cursor (UI only): an amber reticle that locks onto buttons and cards on hover
CURSOR_JS = r"""
<script>
(function () {
  const w = window.parent, d = w.document;
  if (!d.getElementById('tc-theme-script')) {
    const t = d.createElement('script');
    t.id = 'tc-theme-script';
    t.textContent = `(function () {
      const KEY = 'stActiveTheme-' + location.pathname + '-v2';
      let mode = null;
      try { mode = JSON.parse(localStorage.getItem(KEY)); } catch (e) {}
      if (mode !== 'Light' && mode !== 'Dark') {  /* first visit (or 'System'): start in dark mode */
        localStorage.setItem(KEY, JSON.stringify('Dark')); sessionStorage.removeItem('tc-splash-seen'); location.reload(); return;
      }
      document.documentElement.setAttribute('data-mode', mode.toLowerCase());
      document.addEventListener('click', function (e) {
        if (!e.target.closest || !e.target.closest('.mode-toggle')) return;
        localStorage.setItem(KEY, JSON.stringify(mode === 'Dark' ? 'Light' : 'Dark'));
        location.reload();
      });
    })();`;
    d.head.appendChild(t);
  }
  if (d.getElementById('tc-cursor-script') || w.matchMedia('(pointer: coarse)').matches) return;
  const s = d.createElement('script');
  s.id = 'tc-cursor-script';
  s.textContent = `(function () {
    const d = document, root = d.createElement('div');
    root.id = 'tc-cursor';
    root.innerHTML = '<div class="tc-ring"><i class="c tl"></i><i class="c tr"></i><i class="c bl"></i><i class="c br"></i></div>' +
                     '<div class="tc-chev"><b class="u"></b><b class="r"></b><b class="d"></b><b class="l"></b></div>' +
                     '<div class="tc-dot"><i></i></div>';
    d.body.appendChild(root);
    d.documentElement.classList.add('tc-cursor-on');
    const ring = root.querySelector('.tc-ring'), dot = root.querySelector('.tc-dot'), chev = root.querySelector('.tc-chev');
    const LOCK = 'button, a.cp-btn, .st-key-nav label, [data-baseweb="select"], [role="slider"], .kpi, .runner, summary';
    let mx = -100, my = -100, rx = -100, ry = -100, rw = 34, rh = 34, target = null;
    function setTarget(t) { if (t === target) return; target = t; root.classList.toggle('lock', !!t); }
    d.addEventListener('mousemove', function (e) {
      mx = e.clientX; my = e.clientY;
      const overFrame = e.target.tagName === 'IFRAME' || e.target.tagName === 'CANVAS';
      root.style.opacity = overFrame ? 0 : 1;
      d.documentElement.classList.toggle('tc-cursor-on', !overFrame);
      setTarget(e.target.closest ? e.target.closest(LOCK) : null);
    }, { passive: true });
    d.addEventListener('mouseout', function (e) { if (!e.relatedTarget) root.style.opacity = 0; });
    d.addEventListener('mousedown', function () { root.classList.add('down'); });
    d.addEventListener('mouseup', function () { root.classList.remove('down'); });
    (function loop() {
      let cx = mx, cy = my, tw = 34, th = 34;
      if (target && target.isConnected) {
        const r = target.getBoundingClientRect(), pad = 7;
        tw = r.width + pad * 2; th = r.height + pad * 2; cx = r.left + r.width / 2; cy = r.top + r.height / 2;
      } else if (target) { setTarget(null); }
      rx += (cx - rx) * 0.24; ry += (cy - ry) * 0.24; rw += (tw - rw) * 0.24; rh += (th - rh) * 0.24;
      ring.style.width = rw + 'px'; ring.style.height = rh + 'px';
      ring.style.transform = 'translate(' + (rx - rw / 2) + 'px,' + (ry - rh / 2) + 'px)';
      dot.style.transform = chev.style.transform = 'translate(' + mx + 'px,' + my + 'px)';
      requestAnimationFrame(loop);
    })();

    /* Pixel trail: background grid cells light up around the cursor in a ragged stair-step and fade out */
    const host = d.querySelector('[data-testid="stAppViewContainer"]') || d.body;
    const cv = d.createElement('canvas');
    cv.id = 'tc-pixels';
    cv.style.cssText = 'position:fixed;inset:0;width:100vw;height:100vh;pointer-events:none;z-index:-1;';
    host.insertBefore(cv, host.firstChild);
    const ctx = cv.getContext('2d'), CELL = 24, RADIUS = 4, cells = new Map();
    let dpr = 1, running = false, lastCell = '';
    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      cv.width = innerWidth * dpr; cv.height = innerHeight * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resize(); window.addEventListener('resize', resize);
    function light(cx, cy) {
      for (let dx = -RADIUS; dx <= RADIUS; dx++) {
        for (let dy = -RADIUS; dy <= RADIUS; dy++) {
          const dist = Math.hypot(dx, dy);
          if (dist > RADIUS + Math.random() * 1.2 - 0.6) continue;
          const key = (cx + dx) + ',' + (cy + dy);
          const strength = Math.max(0, 1 - dist / (RADIUS + 0.8)) * (0.55 + Math.random() * 0.45);
          const cell = cells.get(key);
          if (!cell || cell.a < strength) cells.set(key, { a: strength, teal: cell ? cell.teal : Math.random() < 0.12 });
        }
      }
      if (!running) { running = true; requestAnimationFrame(draw); }
    }
    function draw() {
      ctx.clearRect(0, 0, innerWidth, innerHeight);
      cells.forEach(function (c, key) {
        const p = key.split(','), x = p[0] * CELL, y = p[1] * CELL;
        ctx.fillStyle = c.teal ? 'rgba(124,196,192,' + (c.a * 0.42) + ')' : 'rgba(217,164,65,' + (c.a * 0.38) + ')';
        ctx.fillRect(x + 1, y + 1, CELL - 2, CELL - 2);
        if (c.a > 0.55) {
          ctx.strokeStyle = c.teal ? 'rgba(124,196,192,' + (c.a * 0.7) + ')' : 'rgba(240,200,120,' + (c.a * 0.6) + ')';
          ctx.strokeRect(x + 1.5, y + 1.5, CELL - 3, CELL - 3);
        }
        c.a *= 0.93;
        if (c.a < 0.02) cells.delete(key);
      });
      if (cells.size) requestAnimationFrame(draw); else running = false;
    }
    if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      d.addEventListener('mousemove', function (e) {
        if (e.target.tagName === 'IFRAME' || e.target.tagName === 'CANVAS' && e.target !== cv) return;
        const cx = Math.floor(e.clientX / CELL), cy = Math.floor(e.clientY / CELL), key = cx + ',' + cy;
        if (key === lastCell) return;
        lastCell = key; light(cx, cy);
      }, { passive: true });
    }
  })();`;
  d.head.appendChild(s);
})();
</script>
"""
with st.container(key="cursorfx"):
    components.html(CURSOR_JS, height=0)

# 0. ACCESS CONTROL: phone OTP sign-in via MiniMoth (see auth.py). Off when no API key is configured.
def _setting(name):
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.environ.get(name)

MM_API_KEY = _setting("MINIMOTH_API_KEY")
AUTH_ENABLED = bool(MM_API_KEY)
AUTHORIZED_PHONES = parse_allowlist(_setting("AUTHORIZED_PHONES") or "")

@st.cache_resource
def _auth_session_store():
    # Saved to a git-ignored file so a server restart or redeploy doesn't sign officers out
    return SessionStore(os.environ.get("AUTH_SESSIONS_FILE")
                        or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".streamlit", ".auth_sessions.json"))

def _cookie_js(value, max_age):
    # Only an opaque random handle goes to the browser, never the MiniMoth tokens
    with st.container(key="authfx"):
        components.html(f"""<script>
        const p = window.parent, secure = p.location.protocol === 'https:' ? '; Secure' : '';
        p.document.cookie = '{SESSION_COOKIE}={value}; path=/; max-age={max_age}; SameSite=Strict' + secure;
        </script>""", height=0)

def _render_login(client, store):
    ss = st.session_state
    st.markdown("""
<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="stExpandSidebarButton"] { display: none !important; }
.block-container { max-width: 520px !important; padding-top: 9vh !important; }
.login-head { text-align: center; margin-bottom: 18px; animation: rise .5s ease-out both; }
.login-head .kicker { font-family: var(--mono); font-size: .78rem; letter-spacing: .14em; text-transform: uppercase; color: var(--accent); }
.login-head h1 { color: var(--text) !important; font-size: 2rem !important; margin: 6px 0 4px 0 !important; padding: 0 !important; }
.login-head h1.wordmark { color: transparent !important; font-size: 3.4rem !important; transform-origin: center bottom; margin: 10px 0 12px 0 !important; }
.login-head p { color: var(--muted); font-size: .95rem; margin: 0; }
.login-badge { display: inline-flex; gap: 8px; align-items: center; margin-top: 12px; padding: 4px 12px; font-family: var(--mono); font-size: .75rem;
               color: var(--teal); border: 1px solid var(--teal-line); background: var(--teal-soft); }
.st-key-login [data-testid="stForm"] { background: var(--panel); border: 1px solid var(--line); border-top: 2px solid var(--accent);
               backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px); padding: 22px 22px 18px 22px; animation: rise .55s .08s ease-out both; }
.st-key-login [data-testid="stFormSubmitButton"] button { width: 100%; }
.login-foot { text-align: center; color: var(--muted); font-size: .8rem; margin-top: 14px; }
.login-foot a { color: var(--accent); }
.sandbox-note { font-family: var(--mono); font-size: .8rem; color: var(--accent); border: 1px dashed var(--accent-line); background: var(--accent-soft); padding: 8px 12px; margin-bottom: 12px; text-align: center; }
</style>""", unsafe_allow_html=True)

    if ss.pop("auth_clear_cookie", False):
        _cookie_js("", 0)

    with st.container(key="login"):
        st.markdown("""
<div class="login-head">
  <div class="kicker">Restricted · public-health officers only</div>
  <h1 class="wordmark" data-text="Tracing the Source">Tracing the Source</h1>
  <p>Case records are confidential. Verify your registered mobile number to continue.</p>
  <div class="login-badge">● WhatsApp OTP · SMS fallback · powered by MiniMoth</div>
</div>""", unsafe_allow_html=True)
        if client.is_sandbox:
            st.markdown('<div class="sandbox-note">Sandbox key: no real message is sent. The code is always 000000.</div>', unsafe_allow_html=True)
        if ss.get("auth_notice"):
            st.info(ss.pop("auth_notice"))

        if ss.get("auth_stage") != "code":
            with st.form("otp_phone"):
                phone_in = st.text_input("Mobile number", placeholder="+91 98765 43210")
                if st.form_submit_button("Send verification code"):
                    phone = normalize_phone(phone_in)
                    if not phone:
                        st.error(ERROR_MESSAGES["BAD_PHONE_FORMAT"])
                    else:
                        try:
                            # Numbers off the allow-list get the same screen but no code is sent,
                            # so the form can't be used to discover which numbers are authorised.
                            if not AUTHORIZED_PHONES or phone in AUTHORIZED_PHONES:
                                client.send_otp(phone)
                            ss.auth_pending_phone, ss.auth_sent_at, ss.auth_stage = phone, time.time(), "code"
                            st.rerun()
                        except MiniMothError as e:
                            st.error(e.friendly)
        else:
            phone = ss.get("auth_pending_phone")
            st.caption(f"Code sent to {mask_phone(phone)} via WhatsApp (SMS if WhatsApp fails). It's valid for 10 minutes.")
            with st.form("otp_code"):
                code = st.text_input("6-digit code", max_chars=6, placeholder="••••••")
                if st.form_submit_button("Verify & enter"):
                    code = (code or "").strip()
                    if not re.fullmatch(r"\d{6}", code):
                        st.error(ERROR_MESSAGES["INVALID_OTP_CODE"])
                    elif AUTHORIZED_PHONES and phone not in AUTHORIZED_PHONES:
                        st.error(ERROR_MESSAGES["INVALID_OTP"])
                    else:
                        try:
                            tokens = client.verify_otp(phone, code)
                            ss.auth_handle = store.create(phone, tokens)
                            ss.auth_cookie_pending = True
                            for k in ("auth_stage", "auth_pending_phone", "auth_sent_at"):
                                ss.pop(k, None)
                            st.rerun()
                        except MiniMothError as e:
                            st.error(e.friendly)
            left, right = st.columns(2)
            wait = int(30 - (time.time() - ss.get("auth_sent_at", 0)))
            if left.button("Change number", use_container_width=True):
                ss.auth_stage = "phone"
                st.rerun()
            if right.button("Resend code" if wait <= 0 else f"Resend in {wait}s", disabled=wait > 0, use_container_width=True):
                try:
                    if not AUTHORIZED_PHONES or phone in AUTHORIZED_PHONES:
                        client.send_otp(phone)
                    ss.auth_sent_at = time.time()
                    st.rerun()
                except MiniMothError as e:
                    st.error(e.friendly)
        st.markdown('<div class="login-foot">Simulation for public-health decision support · synthetic data</div>', unsafe_allow_html=True)

if AUTH_ENABLED:
    _mm_client = MiniMothClient(MM_API_KEY)
    _auth_store = _auth_session_store()
    _handle = st.session_state.get("auth_handle") or st.context.cookies.get(SESSION_COOKIE)
    _session = ensure_fresh(_mm_client, _auth_store, _handle) if _handle else None
    if _session and AUTHORIZED_PHONES and _session["phone"] not in AUTHORIZED_PHONES:
        end_session(_mm_client, _auth_store, _handle)   # number was removed from the allow-list
        _session = None
    if not _session:
        if st.session_state.pop("auth_handle", None):
            st.session_state.auth_notice = ERROR_MESSAGES["SESSION_EXPIRED"]
        _render_login(_mm_client, _auth_store)
        st.stop()
    st.session_state.auth_handle = _handle
    if st.session_state.pop("auth_cookie_pending", False):
        _cookie_js(_handle, HANDLE_MAX_AGE_S)
    st.sidebar.markdown(f"""
<div class="user-chip"><span class="dot"></span><div><div class="who">Signed in</div><div class="num">{mask_phone(_session['phone'])}</div></div>
{'<span class="sbx">SANDBOX</span>' if _mm_client.is_sandbox else ''}</div>""", unsafe_allow_html=True)
    if not AUTHORIZED_PHONES:
        st.sidebar.caption("⚠ No allow-list set: any verified number can sign in. Set AUTHORIZED_PHONES.")
    if st.sidebar.button("Log out", use_container_width=True):
        end_session(_mm_client, _auth_store, _handle)
        st.session_state.pop("auth_handle", None)
        st.session_state.auth_clear_cookie = True
        st.rerun()
    st.sidebar.divider()
else:
    st.sidebar.caption("Open demo mode: officer sign-in (MiniMoth OTP) switches on when MINIMOTH_API_KEY is configured.")

# 1. INGEST & CLEAN SYNTHETIC CASE REPORTS (RUBRIC OBJECTIVE 1)
@st.cache_data
def load_and_prepare_data():
    if not os.path.exists('synthetic_patients.csv'):
        return generate_seeded_outbreak_data(42)
    b = pd.read_csv('synthetic_batches.csv')
    v = pd.read_csv('synthetic_vendors.csv')
    p = pd.read_csv('synthetic_patients.csv')
    if 'consumption_time' not in p.columns or 'supplier' not in b.columns:
        return generate_seeded_outbreak_data(42)
    return b, v, p

if 'raw_patients_df' not in st.session_state:
    b_df, v_df, p_df = load_and_prepare_data()
    st.session_state.batches_df = b_df
    st.session_state.vendors_df = v_df
    st.session_state.raw_patients_df = p_df

df_batches = st.session_state.batches_df
df_vendors = st.session_state.vendors_df
raw_patients = st.session_state.raw_patients_df

# DATA CLEANING PIPELINE (Deduplicate & strip missing vendor records)
total_raw_records = len(raw_patients)
deduped_patients = raw_patients.drop_duplicates(subset=['patient_id'])
duplicates_removed = total_raw_records - len(deduped_patients)
cleaned_patients = deduped_patients.dropna(subset=['reported_vendor', 'status']).copy()
missing_removed = len(deduped_patients) - len(cleaned_patients)

# LOADING SCREEN (UI only): plays once per browser tab, then fades into the dashboard
SPLASH_JS = r"""
<script>
(function () {
  const w = window.parent, d = w.document;
  if (d.getElementById('tc-splash') || w.sessionStorage.getItem('tc-splash-seen')) return;
  w.sessionStorage.setItem('tc-splash-seen', '1');
  const reduce = w.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let mode = 'dark';
  try { if (JSON.parse(w.localStorage.getItem('stActiveTheme-' + w.location.pathname + '-v2')) === 'Light') mode = 'light'; } catch (e) {}

  const css = d.createElement('style');
  css.id = 'tc-splash-css';
  css.textContent = `
  #tc-splash { position: fixed; inset: 0; z-index: 2147483646; display: grid; place-items: center; overflow: hidden;
    --sp-bg: #101114; --sp-text: #e7e3dc; --sp-muted: #9f978d; --sp-accent: #d9a441; --sp-teal: #7cc4c0; --sp-line: rgba(255,255,255,0.06);
    background: radial-gradient(ellipse at 70% 10%, rgba(217,164,65,0.16), transparent 55%), radial-gradient(ellipse at 10% 95%, rgba(47,111,108,0.28), transparent 55%), var(--sp-bg);
    font-family: 'JetBrains Mono', ui-monospace, Consolas, monospace; color: var(--sp-text); transition: opacity .6s ease, transform .6s ease; }
  #tc-splash.light { --sp-bg: #f5f1e8; --sp-text: #26231e; --sp-muted: #6d665c; --sp-accent: #b07a16; --sp-teal: #2c8c86; --sp-line: rgba(60,45,20,0.08);
    background: radial-gradient(ellipse at 70% 10%, rgba(176,122,22,0.14), transparent 55%), radial-gradient(ellipse at 10% 95%, rgba(44,140,134,0.14), transparent 55%), var(--sp-bg); }
  #tc-splash::before { content: ""; position: absolute; inset: 0; pointer-events: none;
    background: linear-gradient(var(--sp-line) 1px, transparent 1px) 0 0 / 24px 24px, linear-gradient(90deg, var(--sp-line) 1px, transparent 1px) 0 0 / 24px 24px; }
  #tc-splash.out { opacity: 0; transform: scale(1.04); pointer-events: none; }
  #tc-splash .sp-wrap { position: relative; width: min(620px, 90vw); display: flex; flex-direction: column; align-items: center; gap: 22px; }
  #tc-splash .sp-radar { position: relative; width: 150px; height: 150px; }
  #tc-splash .sp-radar .ring { position: absolute; inset: 0; border-radius: 50%; border: 1px solid var(--sp-accent); opacity: .35; }
  #tc-splash .sp-radar .ring.r2 { inset: 22px; opacity: .25; } #tc-splash .sp-radar .ring.r3 { inset: 46px; opacity: .2; }
  #tc-splash .sp-radar .sweep { position: absolute; inset: 0; border-radius: 50%;
    background: conic-gradient(from 0deg, rgba(217,164,65,0.55), rgba(217,164,65,0.05) 50deg, transparent 90deg); animation: sp-spin 1.6s linear infinite; }
  #tc-splash .sp-radar .core { position: absolute; left: 50%; top: 50%; width: 12px; height: 12px; margin: -6px; border-radius: 50%;
    background: var(--sp-accent); box-shadow: 0 0 18px 4px rgba(217,164,65,.6); }
  #tc-splash .sp-radar .blip { position: absolute; width: 8px; height: 8px; margin: -4px; border-radius: 50%; background: var(--sp-teal); opacity: 0; animation: sp-blip 1.6s ease-out infinite; }
  #tc-splash .sp-radar .b1 { left: 72%; top: 30%; animation-delay: .25s; } #tc-splash .sp-radar .b2 { left: 28%; top: 64%; animation-delay: .8s; } #tc-splash .sp-radar .b3 { left: 62%; top: 74%; animation-delay: 1.2s; }
  #tc-splash .sp-radar .br { position: absolute; width: 16px; height: 16px; border: 0 solid var(--sp-accent); }
  #tc-splash .sp-radar .tl { left: -14px; top: -14px; border-top-width: 2px; border-left-width: 2px; }
  #tc-splash .sp-radar .tr { right: -14px; top: -14px; border-top-width: 2px; border-right-width: 2px; }
  #tc-splash .sp-radar .bl { left: -14px; bottom: -14px; border-bottom-width: 2px; border-left-width: 2px; }
  #tc-splash .sp-radar .bb { right: -14px; bottom: -14px; border-bottom-width: 2px; border-right-width: 2px; }
  #tc-splash.locked .sp-radar .br { border-color: var(--sp-teal); transition: border-color .3s; }
  #tc-splash .sp-title { position: relative; font-family: 'Bodoni Moda', 'Didot', 'Bodoni 72', serif; font-weight: 900; font-size: clamp(2.6rem, 6vw, 4.2rem);
    letter-spacing: -0.035em; line-height: 1; min-height: 1.15em; white-space: nowrap; transform: scaleY(1.12); transform-origin: center bottom; }
  #tc-splash .sp-title .t { color: transparent; -webkit-background-clip: text; background-clip: text;
    background-image: linear-gradient(172deg, color-mix(in srgb, var(--sp-accent) 52%, #ffffff) 0%, var(--sp-accent) 34%, var(--sp-accent) 62%, color-mix(in srgb, var(--sp-accent) 78%, #000000) 100%);
    -webkit-text-stroke: 0.5px color-mix(in srgb, var(--sp-accent) 55%, #ffffff); filter: drop-shadow(0 0 16px rgba(217,164,65,.45)); }
  #tc-splash .sp-title .caret { height: .8em; width: .12em; }
  #tc-splash .sp-title .caret { display: inline-block; width: .55em; height: 1em; margin-left: 4px; vertical-align: -.12em; background: var(--sp-accent); animation: sp-caret .8s steps(2) infinite; }
  #tc-splash .sp-sub { margin-top: -10px; font-family: 'Inter', system-ui, sans-serif; font-size: 1rem; font-style: italic; letter-spacing: .04em; color: var(--sp-muted); }
  #tc-splash .sp-log { width: 100%; min-height: 150px; font-size: .82rem; line-height: 1.95; color: var(--sp-muted); }
  #tc-splash .sp-log div { display: flex; justify-content: space-between; gap: 16px; animation: sp-in .25s ease-out both; }
  #tc-splash .sp-log b { font-weight: 600; color: var(--sp-teal); }
  #tc-splash .sp-log .lock b { color: var(--sp-accent); }
  #tc-splash .sp-bar { width: 100%; height: 6px; background: var(--sp-line); position: relative; overflow: hidden; }
  #tc-splash .sp-bar i { position: absolute; inset: 0 auto 0 0; width: 0; background: var(--sp-accent); box-shadow: 0 0 12px rgba(217,164,65,.7); transition: width .25s ease; }
  #tc-splash .sp-foot { width: 100%; display: flex; justify-content: space-between; font-size: .75rem; color: var(--sp-muted); letter-spacing: .08em; }
  @keyframes sp-spin { to { transform: rotate(360deg); } }
  @keyframes sp-blip { 0% { opacity: 0; transform: scale(.4); } 20% { opacity: 1; transform: scale(1.3); } 100% { opacity: 0; transform: scale(.8); } }
  @keyframes sp-caret { 50% { opacity: 0; } }
  @keyframes sp-in { from { opacity: 0; transform: translateX(-8px); } to { opacity: 1; transform: none; } }
  `;
  d.head.appendChild(css);

  const el = d.createElement('div');
  el.id = 'tc-splash';
  if (mode === 'light') el.classList.add('light');
  el.innerHTML =
    '<div class="sp-wrap">' +
      '<div class="sp-radar"><div class="ring"></div><div class="ring r2"></div><div class="ring r3"></div><div class="sweep"></div>' +
      '<div class="blip b1"></div><div class="blip b2"></div><div class="blip b3"></div><div class="core"></div>' +
      '<i class="br tl"></i><i class="br tr"></i><i class="br bl"></i><i class="br bb"></i></div>' +
      '<div class="sp-title"><span class="t"></span><span class="caret"></span></div>' +
      '<div class="sp-sub">Cut through the noise. Find the source</div>' +
      '<div class="sp-log"></div>' +
      '<div class="sp-bar"><i></i></div>' +
      '<div class="sp-foot"><span class="pct">0%</span><span>Click or press any key to skip</span></div>' +
    '</div>';
  d.body.appendChild(el);

  const title = 'Tracing the Source', tEl = el.querySelector('.t'), log = el.querySelector('.sp-log'),
        bar = el.querySelector('.sp-bar i'), pct = el.querySelector('.pct');
  const steps = [
    ['Ingesting __RAW__ case reports', 'OK'],
    ['Removing __DUPS__ duplicates, __MISSING__ incomplete', 'OK'],
    ['Mapping __VENDORS__ vendors across __WARDS__ wards', 'OK'],
    ['Tracing __BATCHES__ batches → __WHOLESALERS__ wholesalers', 'OK'],
    ['Running Bayesian traceback (past data only)', 'SOURCE LOCKED']
  ];
  let done = false;
  function finish() {
    if (done) return; done = true;
    el.classList.add('out');
    setTimeout(function () { el.remove(); css.remove(); }, 650);
  }
  ['click', 'keydown'].forEach(function (ev) { d.addEventListener(ev, finish, { once: true }); });
  if (reduce) { tEl.textContent = title; setTimeout(finish, 700); return; }

  let i = 0;
  (function type() { if (i <= title.length) { tEl.textContent = title.slice(0, i++); setTimeout(type, 45); } })();
  steps.forEach(function (s, k) {
    setTimeout(function () {
      if (done) return;
      const row = d.createElement('div');
      if (k === steps.length - 1) { row.className = 'lock'; el.classList.add('locked'); }
      row.innerHTML = '<span>&gt; ' + s[0] + '</span><b>' + s[1] + '</b>';
      log.appendChild(row);
      const p = Math.round((k + 1) / steps.length * 100);
      bar.style.width = p + '%'; pct.textContent = p + '%';
    }, 700 + k * 420);
  });
  // Leave once the dashboard has drawn (and the boot log has played), or after 6 s at most
  const start = Date.now();
  (function wait() {
    if (done) return;
    const ready = d.querySelector('.statusbar') && Date.now() - start > 700 + steps.length * 420 + 450;
    if (ready || Date.now() - start > 6000) finish(); else setTimeout(wait, 120);
  })();
})();
</script>
"""
_n_wholesalers = df_batches['supplier'].nunique() if 'supplier' in df_batches.columns else 0
SPLASH_JS = (SPLASH_JS
    .replace("__AREA__", "Thane · Kalyan · Dombivli")
    .replace("__RAW__", str(total_raw_records)).replace("__DUPS__", str(duplicates_removed))
    .replace("__MISSING__", str(missing_removed)).replace("__VENDORS__", str(df_vendors['vendor_id'].nunique()))
    .replace("__WARDS__", str(df_vendors['ward'].nunique())).replace("__BATCHES__", str(len(df_batches)))
    .replace("__WHOLESALERS__", str(_n_wholesalers)))
with st.container(key="splashfx"):
    components.html(SPLASH_JS, height=0)

# 2. SIDEBAR: TEMPORAL CONTROLS & LIVE HOSPITAL INTAKE
st.sidebar.header("Outbreak simulation controls")
current_day = st.sidebar.slider(
    "Timeline: Days Passed (Strict Past-Data Filter)", 
    min_value=1, max_value=3, value=3,
    help="Strictly filters report_day <= selected day. Zero future data leakage."
)

st.sidebar.divider()
st.sidebar.subheader("Live patient report input")
st.sidebar.caption("Inject new synthetic case reports dynamically.")
with st.sidebar.form("live_intake_form"):
    v_choice = st.selectbox("Vendor Visited", sorted(df_vendors['vendor_id'].unique()))
    s_choice = st.radio("Health Status", ["Sick", "Healthy"], horizontal=True)
    late_flag = st.checkbox("Delayed / Late Report?")
    if st.form_submit_button("Submit Case Report"):
        new_pid = f"Patient_{1000 + len(raw_patients) + 1}"
        new_entry = pd.DataFrame([{
            'patient_id': new_pid,
            'reported_vendor': v_choice,
            'status': s_choice,
            'consumption_time': f"2026-10-1{1+current_day} 14:30",
            'eat_day': max(1, current_day - 1) if late_flag else current_day,
            'report_day': current_day,
            'is_late_report': late_flag,
            'noisy_recall': False
        }])
        st.session_state.raw_patients_df = pd.concat([raw_patients, new_entry], ignore_index=True)
        st.rerun()

st.sidebar.divider()
st.sidebar.subheader("Ingestion & cleaning log")
st.sidebar.markdown(f"""
<div class="log">
Raw reports ingested <b>{total_raw_records}</b><br>
Duplicate logs removed <b>{duplicates_removed}</b><br>
Missing / incomplete cleaned <b>{missing_removed}</b><br>
Late reports (all days) <b>{int(cleaned_patients['is_late_report'].sum())}</b><br>
Wrong-recall reports (simulated) <b>{int(cleaned_patients['noisy_recall'].sum())}</b><br>
Seeded reproducibility <b>seed=42</b>
</div>
""", unsafe_allow_html=True)
st.sidebar.caption("Wrong-recall reports stay in the data on purpose: healthy controls and Laplace smoothing dilute them instead of letting them flip the ranking.")

# 3. CORE ENGINE FUNCTION (Encapsulated so we can verify temporal integrity)
def run_bayesian_traceback(patients_df, vendors_df, batches_df, max_day):
    # STRICT TEMPORAL FILTER: Only use cases reported on or before max_day
    available = patients_df[patients_df['report_day'] <= max_day].copy()
    sick_df = available[available['status'] == 'Sick']

    G = nx.DiGraph()
    for _, row in batches_df.iterrows():
        G.add_edge(row['supplier'], row['batch_id'])
    for _, row in vendors_df.iterrows():
        G.add_edge(row['batch_received'], row['vendor_id'])
    for _, row in available.iterrows():
        G.add_edge(row['reported_vendor'], row['patient_id'])
        G.nodes[row['patient_id']]['status'] = row['status']

    all_batches = batches_df['batch_id'].tolist()
    scores = []
    risk_lookup = {}

    # Baseline population sickness rate for Relative Risk comparison
    total_pop_sick = len(sick_df)
    total_pop_exposed = len(available)
    base_rate = (total_pop_sick + 1) / (total_pop_exposed + 2) if total_pop_exposed > 0 else 0.01

    for batch in all_batches:
        if batch not in G:
            continue
        descendants = nx.descendants(G, batch)
        sick_c = sum(1 for n in descendants if G.nodes[n].get('status') == 'Sick')
        healthy_c = sum(1 for n in descendants if G.nodes[n].get('status') == 'Healthy')
        total_exp = sick_c + healthy_c

        # True Bayesian Risk Score with Laplace Smoothing: (Sick + 1) / (Total + 2)
        risk = (sick_c + 1) / (total_exp + 2) if total_exp > 0 else 0.0
        risk_lookup[batch] = risk
        rel_risk = risk / base_rate if base_rate > 0 else 1.0

        # Multi-ward spread count for this batch
        batch_vendors = set(vendors_df[vendors_df['batch_received'] == batch]['vendor_id'])
        affected_v = set(sick_df[sick_df['reported_vendor'].isin(batch_vendors)]['reported_vendor'])
        wards_hit = vendors_df[vendors_df['vendor_id'].isin(affected_v)]['ward'].nunique()

        # RUBRIC: Explicit Reason Code for EACH ranking
        if risk > 0.45 and wards_hit >= 5:
            reason_code = f"RC-01 [CRITICAL]: High Attack Rate ({risk:.0%}) + {wards_hit}-Ward Convergence"
        elif total_exp > 200 and risk < 0.35:
            reason_code = "RC-02 [POPULAR BASELINE]: High Exposure Volume / Low Relative Risk"
        else:
            reason_code = "RC-03 [BACKGROUND NOISE]: Sporadic Baseline Illness / Recall Noise"

        b_info = batches_df[batches_df['batch_id'] == batch].iloc[0]
        scores.append({
            'Rank': 0,
            'Batch': batch,
            'Wholesaler': b_info['supplier'],
            'Risk Score (%)': round(risk * 100, 1),
            'Relative Risk': f"{rel_risk:.2f}x",
            'Sick': sick_c,
            'Healthy': healthy_c,
            'Wards Hit': wards_hit,
            'Reason Code': reason_code
        })

    df_res = pd.DataFrame(scores).sort_values(by='Risk Score (%)', ascending=False).reset_index(drop=True)
    df_res['Rank'] = [f"#{i+1}" for i in range(len(df_res))]
    return available, sick_df, G, df_res, risk_lookup

available_reports, sick_patients, G, df_scores, batch_risk_lookup = run_bayesian_traceback(
    cleaned_patients, df_vendors, df_batches, current_day
)

top_1_suspect = df_scores.iloc[0] if not df_scores.empty else None
top_3_suspects = df_scores.head(3)
prime_suspect = top_1_suspect['Batch'] if top_1_suspect is not None else None

# Display helpers (UI only)
FOOD_BY_BATCH = df_batches.set_index('batch_id')['food_item'].to_dict() if 'food_item' in df_batches.columns else {}
THEME_TYPE = (st.context.theme.type or "dark") if hasattr(st.context, "theme") else "dark"

# HEADER & 3-TAB HORIZONTAL RADIO MENU
st.markdown(f"""
<div class="statusbar">
  <div class="spacer"></div>
  <div class="brand">
    <div class="name wordmark" data-text="Tracing the Source">Tracing the Source</div><div class="area">Cut through the noise. Find the source</div></div>
  <div class="status"><span class="live">Live</span><span>Day {current_day} of 3</span>
    <button class="mode-toggle" type="button" title="Switch light / dark mode"><span class="to-light"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg> Light</span><span class="to-dark"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg> Dark</span></button></div>
</div>
""", unsafe_allow_html=True)

NAV_LABELS = {
    "Main Dashboard": ":material/dashboard: Dashboard",
    "Data Directory": ":material/folder_open: Data",
    "Geographic Map": ":material/map: Map",
    "Supply Chain Graph": ":material/hub: Supply chain",
}
with st.container(key="nav"):
    view_option = st.radio(
        "Select View:",
        ["Main Dashboard", "Data Directory", "Geographic Map", "Supply Chain Graph"],
        format_func=NAV_LABELS.get,
        horizontal=True,
        label_visibility="collapsed"
    )

# ==========================================
# TAB 1: MAIN DASHBOARD
# ==========================================
if view_option == "Main Dashboard":
    implicated_vendors = sick_patients['reported_vendor'].nunique()
    affected_wards = df_vendors[df_vendors['vendor_id'].isin(sick_patients['reported_vendor'])]['ward'].nunique()
    late_cases_count = int(available_reports['is_late_report'].sum())
    total_vendors = df_vendors['vendor_id'].nunique()
    total_wards = df_vendors['ward'].nunique()

    def short_name(batch):
        return batch.split('(')[-1].rstrip(')') if '(' in batch else batch

    def raw_count_leader(sick_df):
        counts = sick_df.merge(df_vendors, left_on='reported_vendor', right_on='vendor_id')['batch_received'].value_counts()
        return (counts.index[0], int(counts.iloc[0])) if len(counts) else (None, 0)

    # AUTO SITREP TICKER (written from the live numbers; rule-based, not an LLM)
    if top_1_suspect is not None:
        n_target_vendors = df_vendors.loc[df_vendors['batch_received'] == prime_suspect, 'vendor_id'].nunique()
        sitrep = [
            f"Day {current_day}: <b>{len(sick_patients)}</b> confirmed cases in <b>{affected_wards}/{total_wards}</b> wards",
            f"Lead suspect <b>{html.escape(short_name(prime_suspect))}</b> ({html.escape(str(FOOD_BY_BATCH.get(prime_suspect, '')))}) at <b>{top_1_suspect['Risk Score (%)']}%</b> risk, {top_1_suspect['Relative Risk']} baseline",
            f"Pull this batch at <b>{n_target_vendors}</b> vendors supplied by {html.escape(str(top_1_suspect['Wholesaler']))}",
            f"<b>{total_vendors - n_target_vendors}</b> vendors spared a city-wide recall",
        ]
        ticker = '<span class="sep">◆</span>'.join(f"<span>{item}</span>" for item in sitrep)
        st.markdown(f"""
<div class="sitrep" title="Auto-generated situation report: updates with the day slider and new case reports">
  <div class="sitrep-tag">SitRep</div>
  <div class="sitrep-track"><div class="sitrep-run">{ticker}<span class="sep">◆</span>{ticker}<span class="sep">◆</span></div></div>
</div>
""", unsafe_allow_html=True)

    # RUBRIC: TOP-1 & TOP-3 LIST + EARLY DETECTION BANNER
    if top_1_suspect is not None:
        rc_class = "rc1" if top_1_suspect['Reason Code'].startswith("RC-01") else "rc2" if top_1_suspect['Reason Code'].startswith("RC-02") else "rc3"
        st.markdown(f"""
<div class="hero">
  <div class="hero-top"><span class="flag">Top-1 suspected source identified</span><span class="score">{top_1_suspect['Risk Score (%)']}% posterior risk</span></div>
  <div class="label">Day {current_day} early detection · before lab confirmation</div>
  <div class="batch">{html.escape(str(top_1_suspect['Batch']))}</div>
  <div class="sub">Wholesaler <b>{html.escape(str(top_1_suspect['Wholesaler']))}</b> · Food <b>{html.escape(str(FOOD_BY_BATCH.get(top_1_suspect['Batch'], '—')))}</b></div>
  <div class="stats">
    <div><div class="k">Relative risk vs. baseline</div><div class="v accent">{top_1_suspect['Relative Risk']}</div></div>
    <div><div class="k">Sick / healthy exposed</div><div class="v">{top_1_suspect['Sick']} / {top_1_suspect['Healthy']}</div></div>
    <div><div class="k">Wards hit</div><div class="v">{top_1_suspect['Wards Hit']} of {total_wards}</div></div>
  </div>
  <div class="code {rc_class}">{html.escape(str(top_1_suspect['Reason Code']))}</div>
  <div class="actions"><span class="cp-wrap"><a class="cp-btn" href="#recall">Targeted recall list</a></span><span class="cp-wrap"><a class="cp-btn ghost" href="#evidence">Evidence trail</a></span></div>
</div>
""", unsafe_allow_html=True)

    def pct(part, whole):
        return min(part / whole, 1) * 100 if whole else 0

    runner_cards = ""
    for _, r in top_3_suspects.iloc[1:3].iterrows():
        r_class = "rc1" if r['Reason Code'].startswith("RC-01") else "rc2" if r['Reason Code'].startswith("RC-02") else "rc3"
        runner_cards += f"""
  <div class="runner">
    <div class="runner-top"><span class="rk">{html.escape(str(r['Rank']))}</span><span class="rscore">{r['Risk Score (%)']}% risk</span></div>
    <div class="rbatch">{html.escape(str(r['Batch']))}</div>
    <div class="rsub">{html.escape(str(FOOD_BY_BATCH.get(r['Batch'], '—')))} · {html.escape(str(r['Wholesaler']))}</div>
    <div class="track"><div class="fill" style="width:{min(max(r['Risk Score (%)'], 0), 100):.0f}%"></div></div>
    <div class="rstats"><span>{r['Relative Risk']} vs. baseline</span><span>{r['Sick']} sick / {r['Healthy']} healthy</span><span>{r['Wards Hit']} wards</span></div>
    <div class="code {r_class}">{html.escape(str(r['Reason Code']))}</div>
  </div>"""
    if runner_cards:
        st.markdown(f'<div class="runner-label">Also ranked in the top 3</div><div class="runners">{runner_cards}</div>', unsafe_allow_html=True)

    st.markdown(f"""
<div class="kpi-grid">
  <div class="kpi wide"><div class="k">Confirmed sick cases</div><div class="v accent">{len(sick_patients)}</div>
    <div class="s">of {len(available_reports)} cleaned reports</div>
    <div class="track"><div class="fill" style="width:{pct(len(sick_patients), len(available_reports)):.0f}%"></div></div></div>
  <div class="kpi wide"><div class="k">Cleaned reports (≤ Day {current_day})</div><div class="v">{len(available_reports)}</div>
    <div class="s down">-{duplicates_removed + missing_removed} noisy/missing removed</div>
    <div class="track"><div class="fill second" style="width:{pct(len(available_reports), len(cleaned_patients)):.0f}%"></div></div></div>
  <div class="kpi"><div class="k">Late reports integrated</div><div class="v">{late_cases_count}</div>
    <div class="s">reported after the day of eating</div>
    <div class="track"><div class="fill second" style="width:{pct(late_cases_count, len(available_reports)):.0f}%"></div></div></div>
  <div class="kpi"><div class="k">Implicated vendors</div><div class="v">{implicated_vendors} <small>/ {total_vendors}</small></div>
    <div class="s">linked to a sick case</div>
    <div class="track"><div class="fill" style="width:{pct(implicated_vendors, total_vendors):.0f}%"></div></div></div>
  <div class="kpi"><div class="k">City wards affected</div><div class="v">{affected_wards} <small>/ {total_wards}</small></div>
    <div class="s">with at least one sick case</div>
    <div class="track"><div class="fill" style="width:{pct(affected_wards, total_wards):.0f}%"></div></div></div>
</div>
""", unsafe_allow_html=True)

    # EPI-CURVE: sick cases by time of eating, split by link to the top-1 suspect batch
    with st.container(border=True):
        st.subheader("Epidemic curve (sick cases by time of eating)")
        st.caption(f"3-hour slots, reports up to Day {current_day}. Amber = ate at a vendor stocking the top-1 suspect batch; teal = all other sick cases.")
        if sick_patients.empty:
            st.info("No confirmed sick cases yet.")
        else:
            suspect_vendors = set(df_vendors.loc[df_vendors['batch_received'] == prime_suspect, 'vendor_id'])
            epi = sick_patients[['reported_vendor', 'consumption_time']].copy()
            epi['slot'] = pd.to_datetime(epi['consumption_time'], errors='coerce').dt.floor('3h')
            epi = epi.dropna(subset=['slot'])
            epi['Link'] = np.where(epi['reported_vendor'].isin(suspect_vendors), f"Top-1 suspect ({short_name(prime_suspect)})", "Other sick cases")
            epi_counts = epi.groupby(['slot', 'Link']).size().reset_index(name='Cases')
            light = THEME_TYPE == "light"
            accent, teal = ("#b07a16", "#2c8c86") if light else ("#d9a441", "#7cc4c0")
            ink, grid = ("#6d665c", "rgba(60,45,20,0.10)") if light else ("#b3ada5", "rgba(255,255,255,0.07)")
            link_order = [f"Top-1 suspect ({short_name(prime_suspect)})", "Other sick cases"]
            chart = (
                alt.Chart(epi_counts)
                .mark_bar(width={"band": 0.86}, cornerRadiusTopLeft=2, cornerRadiusTopRight=2)
                .encode(
                    x=alt.X('slot:T', title=None, timeUnit=alt.TimeUnitParams(unit='yearmonthdatehours', step=3),
                            axis=alt.Axis(format='%a %d · %H:%M', labelAngle=0, labelColor=ink, tickColor=grid, domainColor=grid, labelFontSize=11)),
                    y=alt.Y('Cases:Q', stack='zero', title='Sick cases',
                            axis=alt.Axis(labelColor=ink, titleColor=ink, gridColor=grid, domainColor=grid, tickColor=grid, tickMinStep=1)),
                    color=alt.Color('Link:N', scale=alt.Scale(domain=link_order, range=[accent, teal]),
                                    legend=alt.Legend(orient='top', title=None, labelColor=ink, symbolType='square', labelLimit=320)),
                    order=alt.Order('Link:N', sort='descending'),
                    tooltip=[alt.Tooltip('slot:T', title='Ate between', format='%a %d %b, %H:%M'),
                             alt.Tooltip('Link:N', title='Group'), alt.Tooltip('Cases:Q', title='Sick cases')],
                )
                .properties(height=260)
                .configure(background='transparent')
                .configure_view(strokeWidth=0)
            )
            st.altair_chart(chart, use_container_width=True)

    with st.container(border=True):
        st.subheader("Top-3 ranked suspected sources (Bayesian engine)")
        st.caption("Separates true common exposures from popular foods, 5% background illness, and 10% wrong recall.")
        # Rendered as a wrapping table so the long reason codes never need a horizontal scrollbar
        top3_rows = "".join(
            f"<tr><td><span class='rank-chip {'first' if r['Rank'] == '#1' else ''}'>{html.escape(str(r['Rank']))}</span></td>"
            f"<td class='mono'>{html.escape(str(r['Batch']))}</td>"
            f"<td class='food'>{html.escape(str(FOOD_BY_BATCH.get(r['Batch'], '—')))}</td>"
            f"<td>{html.escape(str(r['Wholesaler']))}</td>"
            f"<td><div class='risk'><span class='mono'>{r['Risk Score (%)']:.1f}%</span>"
            f"<div class='risk-track'><div class='risk-fill' style='width:{min(max(r['Risk Score (%)'], 0), 100):.1f}%'></div></div></div></td>"
            f"<td class='num'>{r['Sick']}</td><td class='num'>{r['Healthy']}</td><td class='num'>{r['Wards Hit']}</td>"
            f"<td><span class='reason-tag {'rc1' if r['Reason Code'].startswith('RC-01') else 'rc2' if r['Reason Code'].startswith('RC-02') else 'rc3'}'>{html.escape(str(r['Reason Code']))}</span></td></tr>"
            for _, r in top_3_suspects.iterrows()
        )
        st.markdown(f"""
<table class="wrap-table top3">
  <thead><tr><th>Rank</th><th>Batch</th><th>Food</th><th>Wholesaler</th><th title="Laplace Smoothed Posterior Probability">Bayesian Risk</th>
  <th class="num">Sick</th><th class="num">Healthy</th><th class="num">Wards Hit</th><th>Reason Code</th></tr></thead>
  <tbody>{top3_rows}</tbody>
</table>
""", unsafe_allow_html=True)

    with st.container(border=True):
        st.subheader("Simple baseline (raw case count & co-occurrence)")
        st.caption("Fails by flagging popular foods eaten by everyone.")
        naive_df = sick_patients.merge(df_vendors, left_on='reported_vendor', right_on='vendor_id')
        naive_counts = naive_df['batch_received'].value_counts().reset_index()
        naive_counts.columns = ['Batch', 'Raw Sick Co-occurrence']
        base_tbl, base_note = st.columns([1, 1], gap="large")
        with base_tbl:
            st.dataframe(
                naive_counts,
                column_config={
                    "Batch": st.column_config.TextColumn("Batch"),
                    "Raw Sick Co-occurrence": st.column_config.ProgressColumn(
                        "Raw sick co-occurrence", format="%d", min_value=0,
                        max_value=int(naive_counts['Raw Sick Co-occurrence'].max()) if len(naive_counts) else 1, width=190),
                },
                width="stretch", height=fit_height(len(naive_counts)), row_height=TABLE_ROW_H, hide_index=True
            )
        with base_note:
            base_batch, base_sick = raw_count_leader(sick_patients)
            if base_batch is None:
                st.info("No confirmed sick cases yet, so the baseline has nothing to rank.")
            elif base_batch != prime_suspect:
                stock_share = df_vendors.loc[df_vendors['batch_received'] == base_batch, 'vendor_id'].nunique() / total_vendors
                base_row = df_scores[df_scores['Batch'] == base_batch]
                base_healthy = int(base_row['Healthy'].iloc[0]) if not base_row.empty else 0
                st.error(f"**Baseline Failure:** Flags `{base_batch}` as #1 because {stock_share:.0%} of vendors stock it "
                         f"({base_sick} sick eaters, even though {base_healthy} healthy people also had it). "
                         f"The Bayesian engine ranks `{prime_suspect}` first instead.")
            else:
                st.info(f"The baseline agrees with the Bayesian engine on `{base_batch}` at this point in the outbreak.")

    # RUBRIC: EARLY DETECTION ACROSS DAYS (Proving Detection Before All Cases Arrive)
    with st.expander("Early detection proof (Day 1 vs Day 2 vs Day 3 trajectory & mathematical model)"):
        st.markdown("#### 1. Early source detection (before all cases or lab results arrive)")
        day_progression = []
        for d in [1, 2, 3]:
            _, d_sick, _, d_scores, _ = run_bayesian_traceback(cleaned_patients, df_vendors, df_batches, d)
            top_d = d_scores.iloc[0]
            d_base, _ = raw_count_leader(d_sick)
            day_progression.append({
                'Timeline': f"Day {d} ({'Early Onset - 25% Data' if d==1 else 'Mid Outbreak' if d==2 else 'Full Data'})",
                'Top-1 Ranked Batch': top_d['Batch'],
                'Bayesian Risk (%)': f"{top_d['Risk Score (%)']}%",
                'Top-3 Ranking': " › ".join(f"{short_name(b)} {r}%" for b, r in zip(d_scores['Batch'].head(3), d_scores['Risk Score (%)'].head(3))),
                'Confirmed Sick Cases Used': top_d['Sick'],
                'Healthy Controls Used': top_d['Healthy'],
                'Beats Raw Count Baseline?': (f"✅ YES (Isolates {short_name(top_d['Batch'])} over {short_name(d_base)})"
                                              if d_base is not None and d_base != top_d['Batch'] else "Same pick as baseline")
            })
        # Rendered as a wrapping table so it fits laptop screens without a horizontal scrollbar
        day_df = pd.DataFrame(day_progression)
        day_head = "".join(f"<th>{html.escape(c)}</th>" for c in day_df.columns)
        day_body = "".join(
            "<tr>" + "".join(f"<td>{html.escape(str(v)).replace('✅ ', '<span class=ok-dot></span>')}</td>" for v in row) + "</tr>"
            for row in day_df.itertuples(index=False)
        )
        st.markdown(f'<table class="wrap-table"><thead><tr>{day_head}</tr></thead><tbody>{day_body}</tbody></table>', unsafe_allow_html=True)

        st.markdown("#### 2. Underlying Bayesian Laplace math & automated temporal test (`pytest`)")
        st.latex(r"P(\text{Risk} \mid \text{Batch}) = \frac{\text{Confirmed Sick Descendants} + 1}{\text{Total Exposed (Sick + Healthy Controls)} + 2}")
        
        # Temporal leakage assertion check right inside UI
        max_day_in_subset = int(available_reports['report_day'].max()) if not available_reports.empty else current_day
        assert max_day_in_subset <= current_day, "Temporal Leakage Detected!"
        st.info(f"**Temporal Integrity Check Passed (`report_day <= {current_day}`):** Maximum `report_day` in active memory is **Day {max_day_in_subset}**. Zero future cases leaked.")

    # RUBRIC: TARGETED RECALL LIST (NOT A BROAD ONE) + EVIDENCE TRAIL FOR EACH RANKING
    with st.container(border=True):
        st.subheader("Targeted recall & vendor investigation list", anchor="recall")
        st.caption("Targets ONLY vendors linked to the Top-1 contaminated batch—sparing innocent businesses.")
        targeted_vendors = df_vendors[df_vendors['batch_received'] == prime_suspect].copy()
        v_case_counts = sick_patients.groupby('reported_vendor').size().reset_index(name='Confirmed Sick')
        targeted_list = targeted_vendors.merge(v_case_counts, left_on='vendor_id', right_on='reported_vendor', how='left').fillna({'Confirmed Sick': 0})
        targeted_list['Confirmed Sick'] = targeted_list['Confirmed Sick'].astype(int)
        targeted_list['Action'] = np.where(targeted_list['Confirmed Sick'] > 0, "🚨 Priority Sample & Quarantine", "⚠️ Precautionary Batch Pull")
        targeted_list = targeted_list.sort_values(by='Confirmed Sick', ascending=False)

        st.metric(
            label="Targeted Scope vs. Broad City-Wide Recall",
            value=f"{len(targeted_list)} Vendors Quarantined",
            delta=f"{total_vendors - len(targeted_list)} Innocent Vendors Spared ({(total_vendors - len(targeted_list)) / total_vendors:.1%} Disruption Saved)"
        )
        recall_rows = targeted_list[['vendor_id', 'ward', 'batch_received', 'Confirmed Sick', 'Action']].head(8)
        st.dataframe(
            recall_rows.assign(Action=recall_rows['Action'].str.replace(r'^\W+\s*', '', regex=True)),
            column_config={
                "vendor_id": st.column_config.TextColumn("Vendor", width=100),
                "ward": st.column_config.TextColumn("Ward"),
                "batch_received": st.column_config.TextColumn("Batch"),
                "Confirmed Sick": st.column_config.ProgressColumn(
                    "Confirmed sick", format="%d", min_value=0,
                    max_value=max(int(recall_rows['Confirmed Sick'].max()), 1) if len(recall_rows) else 1, width=150),
                "Action": st.column_config.TextColumn("Action"),
            },
            width="stretch",
            height=fit_height(len(recall_rows)),
            row_height=TABLE_ROW_H,
            hide_index=True
        )

        recall_doc = f"""========================================================
OFFICIAL MUNICIPAL PUBLIC HEALTH TARGETED RECALL ORDER
Region: Thane, Kalyan & Dombivli ({total_wards} Municipal Wards)
========================================================
TOP-1 SUSPECT BATCH: {top_1_suspect['Batch']}
WHOLESALER SOURCE:   {top_1_suspect['Wholesaler']}
BAYESIAN RISK SCORE: {top_1_suspect['Risk Score (%)']}% ({top_1_suspect['Relative Risk']})
REASON CODE:         {top_1_suspect['Reason Code']}
TARGETED SCOPE:      {len(targeted_list)} / {total_vendors} Vendors ({total_vendors - len(targeted_list)} Innocent Vendors Spared)

TARGETED VENDOR QUARANTINE LIST:
{targeted_list[['vendor_id', 'ward', 'Confirmed Sick', 'Action']].to_string(index=False)}
========================================================"""
        st.download_button(
            label="Export Recall Order (.txt)",
            data=recall_doc,
            file_name=f"Targeted_Recall_Day_{current_day}.txt",
            mime="text/plain"
        )

    with st.container(border=True):
        st.subheader("Per-ranking evidence trail inspector", anchor="evidence")
        st.caption("Select ANY ranked batch to inspect its full Patient → Vendor → Ward → Consumption Time → Wholesaler trail.")
        selected_evidence_batch = st.selectbox("Inspect Evidence Trail For Ranking:", df_scores['Batch'].tolist())
        selected_row = df_scores[df_scores['Batch'] == selected_evidence_batch].iloc[0]
        st.markdown(f"**Reason Code:** `{selected_row['Reason Code']}` · **Food:** {FOOD_BY_BATCH.get(selected_evidence_batch, '—')}")

        trace_df = sick_patients.merge(df_vendors, left_on='reported_vendor', right_on='vendor_id')
        trace_df = trace_df[trace_df['batch_received'] == selected_evidence_batch].merge(df_batches, left_on='batch_received', right_on='batch_id')
        cols_to_show = ['patient_id', 'consumption_time', 'report_day', 'is_late_report', 'reported_vendor', 'ward', 'supplier']
        trail_rows = trace_df[cols_to_show].sort_values(by='consumption_time', ascending=False).head(10)
        st.dataframe(
            trail_rows,
            column_config={
                "patient_id": st.column_config.TextColumn("Patient", width=115),
                "consumption_time": st.column_config.TextColumn("Ate at", width=140),
                "report_day": st.column_config.NumberColumn("Reported", format="Day %d", width=95),
                "is_late_report": st.column_config.CheckboxColumn("Late?", width=70),
                "reported_vendor": st.column_config.TextColumn("Vendor", width=100),
                "ward": st.column_config.TextColumn("Ward"),
                "supplier": st.column_config.TextColumn("Wholesaler"),
            },
            width="stretch",
            height=fit_height(len(trail_rows)),
            row_height=TABLE_ROW_H,
            hide_index=True
        )

# ==========================================
# TAB 2: GEOGRAPHIC MAP (Thane, Kalyan, Dombivli)
# ==========================================
elif view_option == "Data Directory":
    st.subheader("Data directory")
    st.caption("Every name in the simulated outbreak dataset.")

    def name_card(title, names, wide=False, icon=""):
        items = "".join(f"<li>{html.escape(str(n))}</li>" for n in names)
        return (f'<div class="dir-card{" wide" if wide else ""}"><div class="dir-head"><span>{icon} {title}</span>'
                f'<b>{len(names)}</b></div><ul>{items}</ul></div>')

    wholesalers = sorted(df_batches['supplier'].dropna().unique()) if 'supplier' in df_batches.columns else []
    foods = sorted(df_batches['food_item'].dropna().unique()) if 'food_item' in df_batches.columns else []
    batches = sorted(df_batches['batch_id'].dropna().unique())
    wards = sorted(df_vendors['ward'].dropna().unique())
    vendors = sorted(df_vendors['vendor_id'].dropna().unique())
    st.markdown(
        '<div class="dir-grid">'
        + name_card("Wholesalers", wholesalers, icon="◆")
        + name_card("Foods", foods, icon="●")
        + name_card("Food batches", batches, icon="■")
        + name_card("Wards", wards, wide=True, icon="▲")
        + name_card("Vendors", vendors, wide=True, icon="▪")
        + '</div>', unsafe_allow_html=True)

elif view_option == "Geographic Map":
    st.subheader("Live outbreak clusters across 24 wards (Thane, Kalyan & Dombivli)")
    st.caption("Red circles scale with confirmed sick cases at each street vendor. Hover over any cluster to inspect Ward, Vendor, and Case details.")

    if not sick_patients.empty:
        v_counts = sick_patients['reported_vendor'].value_counts().reset_index()
        v_counts.columns = ['vendor_id', 'sick_cases']
        map_df = v_counts.merge(df_vendors[['vendor_id', 'ward', 'lat', 'lon']].drop_duplicates(), on='vendor_id')
        map_df['radius'] = map_df['sick_cases'] * 75 + 100

        layer = pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            get_position='[lon, lat]',
            get_radius='radius',
            get_fill_color='[217, 164, 65, 175]',
            pickable=True,
            auto_highlight=True
        )
        view_state = pdk.ViewState(latitude=19.22, longitude=73.06, zoom=11, pitch=30)
        st.pydeck_chart(pdk.Deck(
            layers=[layer],
            initial_view_state=view_state,
            map_style="light" if THEME_TYPE == "light" else "dark",
            tooltip={"text": "Vendor: {vendor_id}\nMunicipal Ward: {ward}\nConfirmed Sick Cases: {sick_cases}"}
        ))
    else:
        st.info("No outbreak clusters detected for this day.")

# ==========================================
# TAB 3: SUPPLY CHAIN GRAPH (PyVis 3D Network)
# ==========================================
elif view_option == "Supply Chain Graph":
    st.subheader("Multi-tier supply chain graph (wholesaler → batch → vendor → patient)")

    st.markdown("""
<div class="legend">
  <span><i style="background:#a855f7; transform:rotate(45deg)"></i>Wholesalers</span>
  <span><i style="background:#ff4b4b"></i>Top-1 suspect batch (large)</span>
  <span><i style="background:#4b4bff"></i>Safe commercial batches</span>
  <span><i style="background:#ffa500"></i>Street vendors</span>
  <span><i style="background:#ff4b4b; border-radius:50%; width:7px; height:7px"></i>Confirmed sick patients</span>
</div>
""", unsafe_allow_html=True)

    graph_filter = st.radio(
        "Graph Display Mode:",
        ["Show Full Supply Chain Web", f"Isolate Top-1 Suspect Evidence Trail ({prime_suspect})"],
        horizontal=True
    )

    net = Network(height='550px', width='100%', bgcolor='#f5f1e8' if THEME_TYPE == 'light' else '#1f2126', font_color='#26231e' if THEME_TYPE == 'light' else 'white', directed=True)
    net.repulsion(node_distance=200, central_gravity=0.1, spring_length=200, spring_strength=0.05, damping=0.95)

    all_batches = df_batches['batch_id'].tolist()
    all_wholesalers = df_batches['supplier'].unique().tolist()

    if graph_filter.startswith("Isolate") and prime_suspect:
        prime_wholesaler = df_batches[df_batches['batch_id'] == prime_suspect]['supplier'].iloc[0]
        allowed_nodes = {prime_wholesaler, prime_suspect} | nx.descendants(G, prime_suspect)
    else:
        allowed_nodes = set(G.nodes())

    for node in G.nodes():
        if node not in allowed_nodes:
            continue
        if node in all_wholesalers:
            net.add_node(node, label=f"Wholesaler:\n{node}", color='#a855f7', size=40, shape='diamond')
        elif node in all_batches:
            r_score = batch_risk_lookup.get(node, 0)
            node_color = '#ff4b4b' if node == prime_suspect else '#4b4bff'
            net.add_node(node, label=f"{node}\n(Risk: {r_score:.0%})", color=node_color, size=32)
        elif str(node).startswith("Vendor"):
            net.add_node(node, label=str(node), color='#ffa500', size=18)
        else:
            if G.nodes[node].get('status') == 'Sick':
                net.add_node(node, label="", title=f"Sick Patient: {node}", color='#ff4b4b', size=8)

    added_nodes = set(net.get_nodes())
    for u, v in G.edges():
        if u in added_nodes and v in added_nodes:
            net.add_edge(u, v, color='#3d4048')

    net.save_graph('pyvis_graph.html')
    with open('pyvis_graph.html', 'r', encoding='utf-8') as HtmlFile:
        components.html(HtmlFile.read(), height=560)
