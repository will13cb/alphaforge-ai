"""Visual identity: four colours, one font stack, a few CSS rules. Every view uses these tokens, nothing else.

Neige (background), Gris saule (panels, separators), Gris antarctique (text, borders, navigation), Érable (primary
action, selection). Text contrast on Neige: Gris antarctique 6.4:1, Érable 5.2:1, error red 6.2:1, ink 12.6:1; white on Érable 5.5:1
(WCAG AA ≥ 4.5). Gris saule (2.2:1) is never used for text, only for borders and panels.
"""

NEIGE = "#F7F9FB"
SAULE = "#A3AE9F"
SAULE_LIGHT = "#E6EAE4"
ANTARCTIQUE = "#4E5D6C"
INK = "#26313B"
ERABLE = "#B5432A"
ERROR = "#B42318"

CSS = f"""
<style>
:root {{ --neige:{NEIGE}; --saule:{SAULE}; --saule-l:{SAULE_LIGHT}; --ant:{ANTARCTIQUE}; --ink:{INK};
         --erable:{ERABLE}; --err:{ERROR}; }}
.stApp {{ background: var(--neige); color: var(--ink); }}
/* Light, whatever the OS theme: without these, a dark-mode Mac gives white text on white and black input boxes
   (Streamlit follows the system theme; .streamlit/config.toml also sets base = "light"). */
:root, .stApp {{ color-scheme: light; }}
header[data-testid="stHeader"] {{ background: var(--neige); }}
.stApp p, .stApp li, .stApp label, .stApp span, .stApp div[data-testid="stMarkdownContainer"],
section[data-testid="stSidebar"] * {{ color: var(--ink); }}
.stApp .af-muted, .stApp .af-ex, section[data-testid="stSidebar"] .stCaption * {{ color: var(--ant); }}
.stApp input, .stApp textarea, .stApp div[data-baseweb="select"] > div, .stApp div[data-baseweb="input"],
.stApp div[data-baseweb="textarea"], .stApp div[data-baseweb="base-input"] {{
    background: #FFF !important; color: var(--ink) !important; border-color: var(--saule) !important; }}
.stApp input::placeholder, .stApp textarea::placeholder {{ color: #7A8794 !important; }}
.stApp div[role="radiogroup"] label div:first-child {{ background: #FFF; border-color: var(--ant); }}
.stApp div[data-testid="stExpander"] details {{ background: #FFF; }}
.stApp button[kind="primary"] *, .stApp button[kind="primary"] {{ color: #FFF !important; }}
.stApp .af-step.on {{ color: #FFF; }}
.block-container {{ max-width: 920px; padding-top: 4.5rem; padding-bottom: 6rem; }}
h1, h2, h3 {{ color: var(--ink); letter-spacing: -0.01em; }}
p, li, label {{ font-size: 1.02rem; line-height: 1.55; }}
section[data-testid="stSidebar"] {{ background: #FFFFFF; border-right: 1px solid var(--saule-l); }}
div[data-testid="stProgress"] > div > div > div > div {{ background: var(--erable); }}
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"] {{
    background: var(--erable); border-color: var(--erable); color: #FFF; }}
.stButton button[kind="primary"]:hover {{ background: #9A3822; border-color: #9A3822; }}
.stButton button[kind="secondary"] {{ border-color: var(--saule); color: var(--ant); background: #FFF; }}
.stButton button:focus-visible {{ outline: 3px solid var(--erable); outline-offset: 2px; }}
.af-q {{ font-weight: 600; margin: 1.1rem 0 0.15rem 0; color: var(--ink); }}
.af-badge {{ font-size: 0.72rem; font-weight: 500; padding: 1px 7px; border-radius: 9px; margin-left: 6px;
            vertical-align: middle; border: 1px solid var(--saule); color: var(--ant); background: #FFF; }}
.af-badge.req {{ border-color: var(--erable); color: var(--erable); }}
.af-ex {{ font-style: italic; color: var(--ant); font-size: 0.88rem; margin: -0.3rem 0 0.2rem 0; }}
.af-err {{ color: var(--err); font-size: 0.86rem; margin: -0.4rem 0 0.4rem 0; }}
.af-card {{ background: #FFF; border: 1px solid var(--saule-l); border-radius: 10px; padding: 1rem 1.2rem;
           margin: 0.4rem 0 0.8rem 0; }}
.af-card h4 {{ margin: 0 0 0.3rem 0; font-size: 1.05rem; }}
.af-muted {{ color: var(--ant); font-size: 0.9rem; }}
.af-metric {{ background: #FFF; border: 1px solid var(--saule-l); border-radius: 10px; padding: 0.7rem 0.9rem; }}
.af-metric .v {{ font-size: 1.5rem; font-weight: 650; color: var(--ink); }}
.af-metric .l {{ font-size: 0.85rem; color: var(--ant); }}
.af-note {{ border-left: 4px solid var(--saule); background: #FFF; padding: 0.6rem 0.9rem; border-radius: 4px;
           margin: 0.5rem 0; }}
.af-note.warn {{ border-left-color: #B7791F; }} .af-note.bad {{ border-left-color: var(--err); }}
.af-note.good {{ border-left-color: #3B7D4F; }}
.af-steps {{ display:flex; gap:6px; flex-wrap:wrap; margin: 0 0 0.6rem 0; }}
.af-step {{ font-size:0.8rem; padding:2px 9px; border-radius:10px; background: var(--saule-l); color: var(--ant); }}
.af-step.on {{ background: var(--erable); color:#FFF; }} .af-step.done {{ background:#FFF; border:1px solid var(--saule); }}
div[data-testid="stChatMessage"] {{ border-radius: 12px; padding: 0.6rem 0.9rem; margin-bottom: 0.4rem; }}
div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) {{
    background: var(--saule-l); margin-left: auto; max-width: 85%; width: fit-content; }}
div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarAssistant"]) {{
    background: #FFF; border: 1px solid var(--saule-l); margin-right: 6%; }}
.af-thinking {{ display:flex; align-items:center; gap:8px; color: var(--ant); font-size:0.95rem; }}
.af-thinking span.d {{ width:7px; height:7px; border-radius:50%; background: var(--erable); display:inline-block;
                       animation: af-b 1.2s infinite ease-in-out; }}
.af-thinking span.d:nth-child(2) {{ animation-delay: .15s; }} .af-thinking span.d:nth-child(3) {{ animation-delay: .3s; }}
@keyframes af-b {{ 0%, 80%, 100% {{ opacity:.25; transform: translateY(0); }} 40% {{ opacity:1; transform: translateY(-3px); }} }}
@media (prefers-reduced-motion: reduce) {{ .af-thinking span.d {{ animation: none; opacity: .8; }} }}
@media (max-width: 640px) {{ .block-container {{ padding: 1rem 0.8rem; }}
  div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) {{ max-width: 100%; }} }}
</style>
"""
