"""Visual identity: two modes, one set of tokens. Every view uses these tokens, nothing else.

light  Editorial: cream background, black ink, serif headings, black primary action (Wealthsimple direction).
dark   Trading desk: near-black background, violet primary action, green = passes, red = fails (Kraken direction).

The mode is chosen by the switch in the sidebar (session state `dark_mode`); `css(mode)` is injected at the top of
every run, so the switch applies at once. Text contrast (WCAG AA >= 4.5:1): light ink 17:1, muted 5.1:1, white on
ink 17:1; dark ink 16:1, muted 5.6:1, white on violet 4.8:1. No emoji anywhere in the interface.
"""

from __future__ import annotations

FONTS = ("@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700"
         "&family=Source+Serif+4:opsz,wght@8..60,400;8..60,500;8..60,600&display=swap');")
SANS = "Inter, -apple-system, 'Segoe UI', Roboto, sans-serif"
SERIF = "'Source Serif 4', Charter, 'Bitstream Charter', Georgia, serif"

PALETTES = {
    "light": dict(bg="#F6F4F0", panel="#FFFFFF", ink="#16161A", mut="#6B6862", line="#E4E0D8", soft="#EFEBE3",
                  field="#FFFFFF", acc="#16161A", accfg="#FFFFFF", acc_hover="#3A3A40", sel_bg="#EFEBE3",
                  sel_fg="#16161A", good="#1E6B45", warn="#8A5A12", bad="#A23B2A", c1="#16161A", c2="#B9B3A6",
                  c3="#E4E0D8", heading=SERIF, heading_weight="500", scheme="light"),
    "dark": dict(bg="#0E0D13", panel="#17161F", ink="#F2F1F7", mut="#9C99AD", line="#2A2836", soft="#201F2A",
                 field="#100F16", acc="#7B5CFA", accfg="#FFFFFF", acc_hover="#6A4BE8", sel_bg="#2A2147",
                 sel_fg="#C9BCFF", good="#4FC3A1", warn="#E0A84F", bad="#F0716A", c1="#7B5CFA", c2="#4FC3A1",
                 c3="#3A3848", heading=SANS, heading_weight="600", scheme="dark"),
}


def mode(state) -> str:
    """The display mode from the session state (the sidebar switch)."""
    return "dark" if state.get("dark_mode") else "light"


def palette(mode: str = "light") -> dict:
    return PALETTES.get(mode, PALETTES["light"])


def css(mode: str = "light", large: bool = False) -> str:
    p = palette(mode)
    tokens = "; ".join(f"--{k}:{v}" for k, v in p.items() if k not in ("heading", "heading_weight", "scheme"))
    base = f"""
<style>
{FONTS}
:root {{ {tokens}; }}
:root, .stApp {{ color-scheme: {p['scheme']}; }}
.stApp {{ background: var(--bg); color: var(--ink); font-family: {SANS}; }}
.stApp, .stApp p, .stApp li, .stApp label, .stApp span, .stApp td, .stApp th,
.stApp div[data-testid="stMarkdownContainer"], section[data-testid="stSidebar"] * {{ color: var(--ink); }}
.stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button p, .stApp td, .stApp th,
.stApp .af-card, .stApp .af-note {{ font-family: {SANS} !important; }}
header[data-testid="stHeader"] {{ background: var(--bg); }}
.stApp [data-testid="stExpander"] summary {{ background:var(--panel);color:var(--ink); }}
.stApp [data-testid="stExpander"] summary:hover {{ color:var(--acc); }}
.stApp [data-baseweb="select"] span {{ background:var(--field);color:var(--ink); }}

.block-container {{ max-width: 960px; padding-top: 4rem; padding-bottom: 6rem; }}

/* Type */
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h1 *, .stApp h2 *, .stApp h3 *, .stApp h4 * {{
    font-family: {p['heading']} !important; }}
h1, h2, h3, h4 {{ font-weight: {p['heading_weight']}; color: var(--ink);
    letter-spacing: -0.015em; }}
.stApp h1 {{ font-size: 2.6rem; line-height: 1.12; }}
.stApp h2 {{ font-size: 1.6rem; }} .stApp h3 {{ font-size: 1.25rem; }}
p, li, label {{ font-size: 1rem; line-height: 1.6; }}
.stApp .af-muted, .stApp .af-ex, .stApp div[data-testid="stCaptionContainer"] *,
section[data-testid="stSidebar"] div[data-testid="stCaptionContainer"] * {{ color: var(--mut); }}
.af-eyebrow {{ font-size: 0.75rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--mut);
    margin-bottom: 0.3rem; }}
hr {{ border-color: var(--line) !important; }}
.stApp a {{ color: var(--ink); text-decoration-color: var(--mut); }}

/* Sidebar */
section[data-testid="stSidebar"] {{ background: var(--panel); border-right: 1px solid var(--line); }}
.af-brand {{ display: flex; align-items: center; gap: 10px; font-weight: 600; font-size: 1.05rem;
    letter-spacing: -0.01em; margin: 0.2rem 0 1.2rem 0; }}
.af-brand .mark {{ width: 20px; height: 20px; border-radius: {'50%' if mode == 'light' else '6px'};
    background: var(--acc); display: inline-block; }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] {{ padding: 6px 12px; border-radius: 8px;
    margin-bottom: 2px; width: 100%; }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"] {{ background: var(--sel_bg); }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"] p {{ color: var(--sel_fg);
    font-weight: 500; }}
section[data-testid="stSidebar"] label[data-testid="stRadioOption"] > div > div:first-child {{ display: none; }}

/* Inputs */
.stApp input, .stApp textarea, .stApp div[data-baseweb="select"] > div, .stApp div[data-baseweb="input"],
.stApp div[data-baseweb="textarea"], .stApp div[data-baseweb="base-input"] {{
    background: var(--field) !important; color: var(--ink) !important; border-color: var(--line) !important;
    border-radius: 10px; }}
.stApp input::placeholder, .stApp textarea::placeholder {{ color: var(--mut) !important; opacity: 1; }}
.stApp div[data-baseweb="select"] svg {{ fill: var(--mut); }}
div[data-baseweb="popover"] ul, div[data-baseweb="popover"] li, div[data-baseweb="menu"] {{
    background: var(--panel) !important; color: var(--ink) !important; }}
div[data-baseweb="popover"] li:hover, div[data-baseweb="popover"] li[aria-selected="true"] {{
    background: var(--soft) !important; }}
/* Select boxes on Streamlit 1.5x and later (react-aria, no Base Web attributes): field, arrows and the option list. */
.stApp [data-testid="stSelectbox"] div[role="group"], .stApp [data-testid="stMultiSelect"] div[role="group"] {{
    background: var(--field) !important; color: var(--ink) !important; border-color: var(--line) !important; }}
.stApp [data-testid="stSelectbox"] div[role="group"] button svg,
.stApp [data-testid="stMultiSelect"] div[role="group"] > button svg {{ fill: var(--mut); color: var(--mut); }}
[data-testid$="VirtualDropdown"], [data-testid$="VirtualDropdown"] [role="listbox"] {{
    background: var(--panel) !important; color: var(--ink) !important; border-color: var(--line) !important; }}
[data-testid$="VirtualDropdown"] [role="option"] {{ color: var(--ink) !important; }}
[data-testid$="VirtualDropdown"] [role="option"][data-focused], [data-testid$="VirtualDropdown"] [role="option"][data-hovered],
[data-testid$="VirtualDropdown"] [role="option"][aria-selected="true"] {{ background: var(--soft) !important; }}
/* Chosen items of a multiselect. Streamlit 1.5x and later draws them as span[data-tag] (no Base Web tag any more):
   without the second selector they kept the primary colour as background under ink text, black on black. */
.stApp span[data-baseweb="tag"], .stApp [data-testid="stMultiSelect"] span[data-tag] {{
    background: var(--sel_bg) !important; }}
.stApp span[data-baseweb="tag"] *, .stApp [data-testid="stMultiSelect"] span[data-tag],
.stApp [data-testid="stMultiSelect"] span[data-tag] * {{ color: var(--sel_fg) !important; }}
.stApp label[data-testid="stRadioOption"] > div > div:first-child {{ background: var(--field) !important;
    border: 1px solid var(--mut) !important; }}
.stApp label[data-testid="stRadioOption"][data-selected="true"] > div > div:first-child {{
    background: var(--acc) !important; border-color: var(--acc) !important; }}
.stApp label[data-testid="stRadioOption"][data-selected="true"] > div > div:first-child > div {{
    background: var(--accfg) !important; }}
.stApp [data-testid="stTooltipIcon"] svg {{ stroke: var(--mut); }}

/* Switch (st.toggle): track, then thumb */
.stApp label:has(input[role="switch"]) > div:first-of-type {{ background: var(--line) !important; }}
.stApp label:has(input[role="switch"]:checked) > div:first-of-type {{ background: var(--acc) !important; }}
.stApp label:has(input[role="switch"]) > div:first-of-type > div {{ background: #FFFFFF !important;
    box-shadow: none !important; }}

/* Buttons */
.stButton button, .stFormSubmitButton button, .stDownloadButton button {{ border-radius: 999px;
    font-weight: 500; padding: 0.55rem 1.2rem; transition: background .15s ease, border-color .15s ease; }}
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"] {{
    background: var(--acc); border: 1px solid var(--acc); }}
.stApp button[kind="primary"], .stApp button[kind="primary"] * {{ color: var(--accfg) !important; }}
.stButton button[kind="primary"]:hover {{ background: var(--acc_hover); border-color: var(--acc_hover); }}
.stButton button[kind="secondary"], .stFormSubmitButton button[kind="secondary"] {{ background: transparent;
    border: 1px solid var(--line); color: var(--ink); }}
.stButton button[kind="secondary"]:hover {{ border-color: var(--ink); color: var(--ink); }}
.stApp button:focus-visible {{ outline: 2px solid var(--acc); outline-offset: 2px; }}

/* Tabs, expanders, tables, progress */
.stApp [data-testid="stTab"] p {{ color: var(--mut); font-weight: 500; }}
.stApp [data-testid="stTab"][aria-selected="true"] p {{ color: var(--ink); }}
.stApp [data-testid="stTab"] .react-aria-SelectionIndicator {{ background: var(--acc) !important; }}
.stApp [data-testid="stTabs"] [role="tablist"] {{ border-bottom: 1px solid var(--line); }}
.stApp div[data-testid="stExpander"] details {{ background: var(--panel); border: 1px solid var(--line);
    border-radius: 12px; }}
.stApp div[data-testid="stExpander"] summary:hover * {{ color: var(--ink); }}
.stApp div[data-testid="stExpander"] summary svg {{ fill: var(--mut); }}
.stApp table {{ background: var(--panel); border-color: var(--line); font-variant-numeric: tabular-nums; }}
.stApp table th, .stApp table td {{ border-color: var(--line) !important; background: var(--panel); }}
.stApp table th {{ color: var(--mut) !important; font-weight: 500; }}
.stApp [data-testid="stProgressBarTrack"] {{ background: var(--line) !important; }}
.stApp [data-testid="stProgressBarTrack"] > div {{ background: var(--acc) !important; }}
.stApp div[data-testid="stVegaLiteChart"], .stApp .vega-embed {{ background: transparent; }}

/* Interface components */
.af-q {{ font-weight: 600; margin: 1.2rem 0 0.2rem 0; color: var(--ink); }}
.af-badge {{ font-size: 0.72rem; font-weight: 500; padding: 2px 8px; border-radius: 999px; margin-left: 8px;
    vertical-align: middle; border: 1px solid var(--line); color: var(--mut); background: transparent; }}
.af-badge.req {{ border-color: var(--ink); color: var(--ink); }}
.af-ex {{ font-style: italic; color: var(--mut); font-size: 0.88rem; margin: -0.3rem 0 0.2rem 0; }}
.af-err {{ color: var(--bad); font-size: 0.86rem; margin: -0.4rem 0 0.4rem 0; }}
.af-card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 1.2rem 1.3rem;
    margin: 0.4rem 0 0.8rem 0; }}
.af-card h4 {{ margin: 0 0 0.35rem 0; font-size: 1.12rem; }}
.af-muted {{ color: var(--mut); font-size: 0.92rem; }}
.af-metric {{ background: {'transparent' if mode == 'light' else 'var(--panel)'};
    border: {'0' if mode == 'light' else '1px solid var(--line)'}; border-top: 1px solid var(--{'ink' if mode == 'light' else 'line'});
    border-radius: {'0' if mode == 'light' else '12px'}; padding: {'0.8rem 0 0 0' if mode == 'light' else '0.9rem 1rem'}; }}
.af-metric .v {{ font-family: {p['heading']}; font-size: 1.9rem; font-weight: {p['heading_weight']}; color: var(--ink);
    letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }}
.af-metric .l {{ font-size: 0.85rem; color: var(--mut); }}
.af-note {{ border: 1px solid var(--line); border-left: 3px solid var(--mut); background: var(--panel);
    padding: 0.7rem 1rem; border-radius: 10px; margin: 0.5rem 0; }}
.af-note.warn {{ border-left-color: var(--warn); }} .af-note.bad {{ border-left-color: var(--bad); }}
.af-note.good {{ border-left-color: var(--good); }}
.af-st {{ font-size: 0.72rem; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; padding: 1px 7px;
    border-radius: 999px; border: 1px solid currentColor; margin-right: 6px; white-space: nowrap; }}
.af-st.pass {{ color: var(--good) !important; }} .af-st.warn {{ color: var(--warn) !important; }}
.af-st.fail {{ color: var(--bad) !important; }}
.af-steps {{ display: flex; gap: 6px; flex-wrap: wrap; margin: 0 0 0.8rem 0; }}
.af-step {{ font-size: 0.8rem; padding: 3px 11px; border-radius: 999px; background: transparent;
    border: 1px solid var(--line); color: var(--mut); }}
.stApp .af-step.on {{ background: var(--acc); border-color: var(--acc); color: var(--accfg); }}
.stApp .af-step.done {{ border-color: var(--mut); color: var(--ink); }}

/* Chat */
div[data-testid="stChatMessage"] {{ border-radius: 14px; padding: 0.7rem 1rem; margin-bottom: 0.5rem;
    background: transparent; }}
div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) {{
    background: var(--soft); margin-left: auto; max-width: 85%; width: fit-content; }}
div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarAssistant"]) {{
    background: var(--panel); border: 1px solid var(--line); margin-right: 6%; }}
div[data-testid="stChatMessageAvatarUser"], div[data-testid="stChatMessageAvatarAssistant"] {{
    background: var(--acc) !important; }}
/* The avatar is an svg on older Streamlit and an icon-font span on newer ones: colour both, or the icon is drawn
   in ink on the accent square and disappears. */
div[data-testid="stChatMessageAvatarUser"] svg, div[data-testid="stChatMessageAvatarAssistant"] svg {{
    fill: var(--accfg); color: var(--accfg); }}
div[data-testid="stChatMessageAvatarUser"] span, div[data-testid="stChatMessageAvatarAssistant"] span {{
    color: var(--accfg) !important; fill: var(--accfg) !important; }}
div[data-testid="stBottom"], div[data-testid="stBottom"] > div {{ background: var(--bg) !important; }}
div[data-testid="stChatInput"] {{ background: var(--field) !important; border: 1px solid var(--line);
    border-radius: 14px; }}
div[data-testid="stChatInput"] textarea {{ color: var(--ink) !important; }}
.af-thinking {{ display: flex; align-items: center; gap: 8px; color: var(--mut); font-size: 0.95rem; }}
.af-thinking span.d {{ width: 7px; height: 7px; border-radius: 50%; background: var(--acc); display: inline-block;
    animation: af-b 1.2s infinite ease-in-out; }}
.af-thinking span.d:nth-child(2) {{ animation-delay: .15s; }} .af-thinking span.d:nth-child(3) {{ animation-delay: .3s; }}
@keyframes af-b {{ 0%, 80%, 100% {{ opacity: .25; transform: translateY(0); }} 40% {{ opacity: 1; transform: translateY(-3px); }} }}
@media (prefers-reduced-motion: reduce) {{ .af-thinking span.d {{ animation: none; opacity: .8; }} }}
/* Focus rings in the mode's accent (Streamlit's own primary colour comes from .streamlit/config.toml) */
.stApp div[data-baseweb="input"]:focus-within, .stApp div[data-baseweb="textarea"]:focus-within,
.stApp div[data-baseweb="select"] > div:focus-within {{ border-color: var(--acc) !important; }}
.stApp div[data-testid="stChatInput"] > div, .stApp div[data-testid="stChatInput"] div[data-baseweb] {{
    border-color: var(--line) !important; background: var(--field) !important; }}
.stApp div[data-testid="stChatInput"]:focus-within {{ border-color: var(--acc); }}
.stApp div[data-testid="stChatInput"] button {{ background: var(--acc) !important; border-radius: 10px; }}
.stApp div[data-testid="stChatInput"] button svg {{ fill: var(--accfg); color: var(--accfg); }}

/* Section tabs for phones (app.mobile_nav): hidden on wider screens */
.st-key-af_mnav {{ display: none; }}
.st-key-af_mnav [data-testid="stElementContainer"], .st-key-af_mnav [data-testid="stButtonGroup"] {{ width: 100% !important; }}
.st-key-af_mnav div[role="radiogroup"] {{ width: 100% !important; max-width: none !important; display: flex;
    flex-wrap: nowrap; }}
.st-key-af_mnav button {{ flex: 1 1 0 !important; min-width: 0; min-height: 40px; padding: 0 4px;
    background: var(--panel) !important; border-color: var(--line) !important; }}
.st-key-af_mnav button p {{ font-size: 0.85rem !important; color: var(--mut) !important; font-weight: 500; }}
.st-key-af_mnav button[aria-checked="true"] {{ background: var(--acc) !important; border-color: var(--acc) !important; }}
.st-key-af_mnav button[aria-checked="true"] p {{ color: var(--accfg) !important; }}

/* Phones (iPhone: 375-430 px wide) */
@media (max-width: 640px) {{
  .block-container {{ padding: 3.6rem 1rem calc(5rem + env(safe-area-inset-bottom)) 1rem; }}
  .stApp h1 {{ font-size: 1.9rem; line-height: 1.15; }} .stApp h2 {{ font-size: 1.35rem; }}
  .stApp h3 {{ font-size: 1.15rem; }}
  .st-key-af_mnav {{ display: block; width: 100% !important; margin-bottom: 0.4rem; }}
  /* 16 px in every field, or iOS Safari zooms the page on focus */
  .stApp input, .stApp textarea, .stApp div[data-baseweb="select"] * {{ font-size: 16px !important; }}
  /* Tap targets of at least 44 px */
  .stButton button, .stFormSubmitButton button, .stDownloadButton button {{ min-height: 46px; }}
  .stApp label[data-testid="stRadioOption"] {{ min-height: 40px; align-items: center; padding: 4px 0; }}
  .stApp div[data-testid="stExpander"] summary {{ min-height: 44px; }}
  /* Only the current step pill; "Step x of n" and the bar say the rest */
  .af-step:not(.on) {{ display: none; }}
  /* Metrics: three in a row, smaller figures */
  div[data-testid="stHorizontalBlock"]:has(.af-metric) {{ flex-wrap: nowrap; gap: 0.6rem; }}
  div[data-testid="stHorizontalBlock"]:has(.af-metric) > div {{ min-width: 0 !important; flex: 1 1 0 !important; }}
  .af-metric .v {{ font-size: 1.3rem; }} .af-metric .l {{ font-size: 0.75rem; line-height: 1.3; }}
  /* Review rows: title and Edit on one line */
  [class*="st-key-af_row"] div[data-testid="stHorizontalBlock"] {{ flex-wrap: nowrap; align-items: center; }}
  [class*="st-key-af_row"] div[data-testid="stColumn"] {{ min-width: 0 !important; }}
  [class*="st-key-af_row"] div[data-testid="stColumn"]:last-child {{ flex: 0 0 86px !important; }}
  [class*="st-key-af_row"] .stButton button {{ min-height: 38px; padding: 0.3rem 0.8rem; }}
  /* Step buttons: Continue first, the empty spacer dropped */
  [class*="st-key-af_nav"] div[data-testid="stColumn"]:nth-child(2) {{ order: -1; }}
  [class*="st-key-af_nav"] div[data-testid="stColumn"]:nth-child(3) {{ display: none; }}
  .af-card {{ padding: 1rem 1.05rem; }}
  .stApp table {{ display: block; overflow-x: auto; }}
  div[data-testid="stChatMessage"] {{ padding: 0.6rem 0.75rem; }}
  div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) {{ max-width: 100%; }}
  div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarAssistant"]) {{ margin-right: 0; }}
  div[data-testid="stBottom"] > div {{ padding-bottom: env(safe-area-inset-bottom); }}
}}
/* Recorded activity uses the same accessible palette as the rest of the app. */
.af-event {{ border: 1px solid var(--line); background: var(--panel); border-radius: 10px; padding: 1rem; margin: .6rem 0; overflow-wrap: anywhere; }}
.af-event-head {{ font-weight: 600; display: flex; flex-wrap: wrap; gap: .5rem; justify-content: space-between; }}
.af-event-time {{ color: var(--mut); font-size: .8rem; }}
.af-flow {{ display: flex; flex-wrap: wrap; gap: .5rem; }}
.af-flow span {{ border: 1px solid var(--line); border-radius: 6px; padding: .35rem .6rem; }}
</style>
"""
    return base + ("""<style>
html { font-size:19px; }
.stApp p,.stApp li,.stApp label,.stApp input,.stApp textarea,.stApp button p {
    font-size:1.08rem!important; line-height:1.65!important;
}
/* Recorded activity uses the same accessible palette as the rest of the app. */
.af-event {{ border: 1px solid var(--line); background: var(--panel); border-radius: 10px; padding: 1rem; margin: .6rem 0; overflow-wrap: anywhere; }}
.af-event-head {{ font-weight: 600; display: flex; flex-wrap: wrap; gap: .5rem; justify-content: space-between; }}
.af-event-time {{ color: var(--mut); font-size: .8rem; }}
.af-flow {{ display: flex; flex-wrap: wrap; gap: .5rem; }}
.af-flow span {{ border: 1px solid var(--line); border-radius: 6px; padding: .35rem .6rem; }}
</style>""" if large else "")


CSS = css("light")  # kept for callers that import the constant


def style_chart(chart, mode: str = "light"):
    """The engine's Altair charts, recoloured for the mode: transparent background, axis/legend text in the mode's
    colours, and the marks drawn in plain black/white/grey swapped for the mode's ink (black is invisible on the
    dark background). Data and encodings are not touched. Returns the original chart if anything fails."""
    import altair as alt

    p = palette(mode)
    swap = {"black": p["ink"], "#000": p["ink"], "#000000": p["ink"], "gray": p["mut"], "grey": p["mut"],
            "#64748b": p["mut"], "#475569": p["mut"], "#94a3b8": p["c3" if mode == "light" else "mut"],
            "#2563eb": p["c1"], "#b91c1c": p["bad"]}

    def walk(x):
        if isinstance(x, dict):
            return {k: (swap.get(v.lower(), v) if k in ("color", "fill", "stroke") and isinstance(v, str)
                        else walk(v)) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        return x

    try:
        from dh import i18n
        spec = i18n.chart_spec(walk(chart.to_dict()))
        cfg = spec.setdefault("config", {})
        cfg["background"] = "transparent"
        cfg["font"] = SANS
        cfg["view"] = {**cfg.get("view", {}), "stroke": None}
        ax = dict(labelColor=p["mut"], titleColor=p["mut"], gridColor=p["line"], domainColor=p["line"],
                  tickColor=p["line"], labelFontSize=11, titleFontSize=11, titleFontWeight=500)
        cfg["axis"] = {**cfg.get("axis", {}), **ax}
        cfg["legend"] = {**cfg.get("legend", {}), "labelColor": p["ink"], "titleColor": p["mut"]}
        cfg["title"] = {**cfg.get("title", {}), "color": p["ink"]}
        cfg["text"] = {**cfg.get("text", {}), "color": p["ink"]}
        cfg["range"] = {**cfg.get("range", {}), "category": [p["c1"], p["c2"], p["warn"], p["bad"], p["mut"]]}
        kind = next((c for k, c in (("layer", alt.LayerChart), ("hconcat", alt.HConcatChart),
                                    ("vconcat", alt.VConcatChart), ("concat", alt.ConcatChart),
                                    ("facet", alt.FacetChart), ("repeat", alt.RepeatChart)) if k in spec), alt.Chart)
        return kind.from_dict(spec, validate=False)
    except Exception:  # noqa: BLE001 — a chart keeps its engine colours rather than breaking the page
        return chart



def apply_theme() -> str:
    """Use the current accessible theme in the jury app as well as the guided app."""
    import streamlit as st
    with st.sidebar:
        st.toggle("Dark mode", key="dark_mode")
    current = mode(st.session_state)
    st.markdown(css(current, st.session_state.get("large_text", False)), unsafe_allow_html=True)
    return current

