"""Static visual mockups for the guided interface (no engine, illustrative numbers only).
Run: python interface/mockups/build.py && node interface/mockups/shoot.js  -> *.html and *.png."""
import math
from pathlib import Path

OUT = Path(__file__).parent

def drawdown_path(depth, seed, w=760, h=220):
    pts, n = [], 120
    for i in range(n):
        t = i / (n - 1)
        base = -depth * math.sin(min(t / 0.45, 1) * math.pi / 2) * (1 - max(0, t - 0.55) * 1.6)
        wob = 0.12 * depth * math.sin(i * 0.9 + seed) * math.sin(i * 0.23 + seed)
        v = min(0, base + wob)
        pts.append(f"{i / (n - 1) * w:.1f},{-v / 30 * h:.1f}")
    return " ".join(pts)

def chart():
    a, b = drawdown_path(26.5, 1), drawdown_path(9.5, 3)
    lim = 15 / 30 * 220
    return f"""<svg viewBox="0 0 760 240" class="chart" preserveAspectRatio="none">
  <line x1="0" y1="0" x2="760" y2="0" class="axis"/>
  <line x1="0" y1="{lim:.0f}" x2="760" y2="{lim:.0f}" class="limit"/>
  <text x="4" y="{lim - 6:.0f}" class="lbl">Your limit, -15%</text>
  <polyline points="{a}" class="s1"/><polyline points="{b}" class="s2"/>
  <text x="0" y="236" class="lbl">2021</text><text x="380" y="236" class="lbl" text-anchor="middle">2023</text>
  <text x="760" y="236" class="lbl" text-anchor="end">2026</text></svg>
  <div class="legend"><span><i class="k1"></i>25% Tesla, as asked</span><span><i class="k2"></i>3.1% Tesla, within your limits</span></div>"""

STRATS = [
    ("Core", "Most growth your limits allow", 15, 75, 10, "$28,000", "7.0%", "Broadest mix of companies and countries", "Largest swings of the three"),
    ("Income", "Ten points less growth", 5, 85, 10, "$22,400", "5.6%", "Steadier, bond interest does most of the work", "Less room to grow over 4 years"),
    ("Defensive", "Twenty points less growth", 0, 82, 18, "$17,600", "4.4%", "Smallest drop in the 2021-2026 data", "May trail inflation"),
]

def strategies():
    cards = []
    for i, (n, sub, s, b, c, d, dp, pro, con) in enumerate(STRATS):
        s = [15, 8, 3][i]; b = 100 - s - c
        cards.append(f"""<div class="card strat{' first' if i == 0 else ''}">
  <div class="row"><div><div class="sname">{n}</div><div class="muted">{sub}</div></div>
  {'<span class="tag">Closest to your request</span>' if i == 0 else ''}</div>
  <div class="bar"><span style="width:{s}%" class="b1"></span><span style="width:{b}%" class="b2"></span><span style="width:{c}%" class="b3"></span></div>
  <div class="split"><span><i class="k1"></i>Stocks {s}%</span><span><i class="k2"></i>Bonds {b}%</span><span><i class="k3"></i>Cash {c}%</span></div>
  <div class="stat"><div class="muted">Worst drop, 2021-2026</div><div class="num">{d}</div><div class="muted">{dp} of $400,000</div></div>
  <ul class="pc"><li><b>For</b> {pro}</li><li><b>Against</b> {con}</li></ul>
  <div class="status ok">17 of 17 checks passed</div></div>""")
    return "".join(cards)

KPIS = [("Loss you can accept", "$60,000", "15% of $400,000, your answer"),
        ("Growth assets allowed", "15%", "Set by your 4-year horizon"),
        ("Kept safe for withdrawals", "$48,000", "12 months of expenses"),
        ("Rules checked", "17", "Modelled on NI 31-103 suitability")]

def results():
    k = "".join(f'<div class="card kpi"><div class="muted">{a}</div><div class="num">{b}</div><div class="muted sm">{c}</div></div>' for a, b, c in KPIS)
    return f"""
<div class="eyebrow">Your results</div>
<h1>Robert, here is what fits within your limits</h1>
<p class="lead">59 years old &middot; $400,000 &middot; 4-year horizon &middot; Simulation for learning, not financial advice</p>
<div class="kpis">{k}</div>
<div class="sechead"><h2>Three simulated strategies</h2><span class="muted">Same rules, three levels of growth</span></div>
<div class="strats">{strategies()}</div>
<div class="sechead"><h2>Your request: 25% in Tesla</h2><span class="muted">Shown side by side, every check re-run</span></div>
<div class="card compare">
  <table><thead><tr><th></th><th>As asked</th><th>Within your limits</th></tr></thead><tbody>
  <tr><td>Tesla share</td><td>25%</td><td>3.1%</td></tr>
  <tr><td>Worst drop, 2021-2026</td><td class="bad">$106,000</td><td class="good">$38,000</td></tr>
  <tr><td>Your loss limit</td><td>$60,000</td><td>$60,000</td></tr>
  <tr><td>Checks not met</td><td class="bad">9 of 17</td><td class="good">0 of 17</td></tr></tbody></table>
  <div class="why"><div class="muted">Why 3.1%</div>A single company may use at most a quarter of your $60,000 loss limit at its own worst
  2021-2026 drop. Tesla fell 73% at its worst, so 3.1% is the most that stays inside that rule. <span class="src">Rule C1 &middot; Source: daily prices 2021-2026</span></div>
</div>
<div class="sechead"><h2>Worst drop over time</h2><span class="muted">Loss from the previous high, 2021-2026</span></div>
<div class="card">{chart()}</div>"""

def welcome():
    return """
<div class="hero">
  <div class="eyebrow">AlphaForge AI &middot; Simulation</div>
  <h1 class="big">Invest within limits<br>you can explain.</h1>
  <p class="lead">Answer a few questions. We work out how much risk you can carry, propose up to three simulated
  strategies that respect it, and show the rule, the number and the source behind every answer.</p>
</div>
<div class="choices">
  <div class="card choice sel"><div class="sname">In your own words</div><div class="muted">Describe your situation. A number is kept only if you wrote it.</div>
    <div class="ta">I'm 59 and retiring in about 4 years. I have $400,000 saved and 12 months of expenses set aside. I can't lose more than 15%. I'd like 25% in Tesla.</div>
    <div class="btn primary">Continue</div></div>
  <div class="card choice"><div class="sname">Step by step</div><div class="muted">About 5 minutes, one topic at a time, with help on each question.</div>
    <div class="steps"><div><span>1</span>Your situation</div><div><span>2</span>Goals and horizon</div><div><span>3</span>Comfort with losses</div><div><span>4</span>Preferences</div></div>
    <div class="btn">Start the questions</div><div class="btn ghost">Try an example client</div></div>
</div>
<div class="notice">This is a simulation for learning. It is not financial advice and makes no transaction.</div>"""

BASE = """*{box-sizing:border-box;margin:0;padding:0}body{background:var(--bg);color:var(--ink);font:15px/1.5 Inter,sans-serif;-webkit-font-smoothing:antialiased}
.muted{color:var(--mut)}.sm{font-size:12.5px}.eyebrow{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);margin-bottom:10px}
h1{font-size:34px;line-height:1.15;letter-spacing:-.02em;font-weight:600}h1.big{font-size:56px}h2{font-size:19px;font-weight:600;letter-spacing:-.01em}
.lead{color:var(--mut);font-size:16px;margin-top:10px;max-width:640px}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--r);padding:20px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:28px}.kpi .num{font-size:28px;margin:6px 0 2px}
.num{font-weight:600;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.sechead{display:flex;justify-content:space-between;align-items:baseline;margin:38px 0 14px}
.strats{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.row{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
.sname{font-size:17px;font-weight:600}.tag{font-size:11.5px;padding:3px 9px;border-radius:999px;background:var(--tagbg);color:var(--tagfg);white-space:nowrap}
.bar{display:flex;height:8px;border-radius:4px;overflow:hidden;margin:18px 0 10px;gap:2px}.b1{background:var(--c1)}.b2{background:var(--c2)}.b3{background:var(--c3)}
.split,.legend{display:flex;gap:14px;font-size:12.5px;color:var(--mut)}i{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:6px}
i.k1{background:var(--c1)}i.k2{background:var(--c2)}i.k3{background:var(--c3)}
.stat{margin:18px 0;padding:14px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}.stat .num{font-size:24px}
.pc{list-style:none;font-size:13.5px;display:grid;gap:6px}.pc li{display:grid;grid-template-columns:62px 1fr}.pc b{font-weight:600}.strat .row{flex-direction:column-reverse;gap:10px;min-height:76px;justify-content:flex-end}
.status{margin-top:14px;font-size:12.5px;font-weight:500}.ok{color:var(--good)}
.compare{display:grid;grid-template-columns:1.3fr 1fr;gap:28px}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th{text-align:left;font-size:12px;font-weight:500;color:var(--mut);padding:0 0 10px}td{padding:11px 0;border-top:1px solid var(--line)}td:not(:first-child),th:not(:first-child){text-align:right}
td.bad{color:var(--bad);font-weight:600}td.good{color:var(--good);font-weight:600}.why{font-size:14px;line-height:1.6}.why .muted{margin-bottom:6px}
.src{display:block;margin-top:10px;font-size:12px;color:var(--mut)}
.chart{width:100%;height:240px;overflow:visible}.chart polyline{fill:none;stroke-width:2}.s1{stroke:var(--c1)}.s2{stroke:var(--c2)}
.axis{stroke:var(--line)}.limit{stroke:var(--bad);stroke-dasharray:4 4}.lbl{fill:var(--mut);font-size:11px}.legend{margin-top:14px}
.hero{padding:30px 0 34px}.choices{display:grid;grid-template-columns:1.25fr 1fr;gap:16px}.choice{padding:26px;display:flex;flex-direction:column;gap:12px}
.choice.sel{border-color:var(--ink)}.ta{border:1px solid var(--line);border-radius:calc(var(--r) - 4px);padding:14px;font-size:14px;color:var(--ink);background:var(--field);min-height:110px}
.btn{text-align:center;padding:12px;border-radius:var(--br);border:1px solid var(--line);font-weight:500;font-size:14px}.btn.primary{background:var(--acc);color:var(--accfg);border-color:var(--acc)}.btn.ghost{border-color:transparent;color:var(--mut)}
.steps{display:grid;gap:8px;font-size:14px;margin:4px 0 6px}.steps span{display:inline-grid;place-items:center;width:22px;height:22px;border-radius:50%;border:1px solid var(--line);font-size:11px;margin-right:10px}
.notice{margin-top:18px;font-size:13px;color:var(--mut);padding:12px 16px;border-radius:var(--r);background:var(--note)}
.top{display:flex;align-items:center;justify-content:space-between;padding:18px 40px;border-bottom:1px solid var(--line)}
.logo{display:flex;align-items:center;gap:10px;font-weight:600;letter-spacing:-.01em}.mark{width:22px;height:22px;border-radius:6px;background:var(--acc)}
.nav{display:flex;gap:26px;font-size:14px;color:var(--mut)}.nav .on{color:var(--ink);font-weight:500}"""

THEMES = {
 "a-editorial": dict(label="A. Editorial light (Wealthsimple direction)", css="""
:root{--bg:#F6F4F0;--card:#FFF;--ink:#16161A;--mut:#6B6862;--line:#E4E0D8;--acc:#16161A;--accfg:#FFF;--r:14px;--br:999px;
--c1:#16161A;--c2:#B9B3A6;--c3:#E4E0D8;--good:#1E6B45;--bad:#A23B2A;--tagbg:#EFEBE3;--tagfg:#16161A;--field:#FBFAF7;--note:#EFEBE3}
h1,h2,.sname{font-family:'Bitstream Charter',Georgia,serif;font-weight:500}h1{font-size:40px}h1.big{font-size:64px}
.wrap{max-width:1040px;margin:0 auto;padding:44px 40px 70px}.top{border:0;padding:24px 40px}.mark{border-radius:50%}
.card{box-shadow:0 1px 2px rgba(20,20,20,.04)}.kpi{background:transparent;border:0;border-top:1px solid var(--ink);border-radius:0;padding:14px 0 0;box-shadow:none}
.kpi .num{font-family:'Bitstream Charter',Georgia,serif;font-weight:500;font-size:34px}""", layout="top"),
 "b-dark": dict(label="B. Dark trading desk (Kraken direction)", css="""
:root{--bg:#0E0D13;--card:#17161F;--ink:#F2F1F7;--mut:#8D8A9E;--line:#2A2836;--acc:#7B5CFA;--accfg:#FFF;--r:12px;--br:10px;
--c1:#7B5CFA;--c2:#4FC3A1;--c3:#3A3848;--good:#4FC3A1;--bad:#F0716A;--tagbg:#2A2147;--tagfg:#C9BCFF;--field:#100F16;--note:#17161F}
.wrap{max-width:1240px;margin:0 auto;padding:36px 40px 70px}.top{background:#121118}
.choice.sel{border-color:var(--acc)}.strat.first{border-color:#3D3366}.kpi .num{font-size:30px}""", layout="top"),
 "c-console": dict(label="C. Light console with sidebar (Kraken Pro direction)", css="""
:root{--bg:#F4F5F8;--card:#FFF;--ink:#14151A;--mut:#666A79;--line:#E3E5EB;--acc:#5B3FD9;--accfg:#FFF;--r:10px;--br:8px;
--c1:#5B3FD9;--c2:#9AA3B5;--c3:#DADDE5;--good:#18794E;--bad:#C2362B;--tagbg:#EEEAFD;--tagfg:#4A30C2;--field:#FAFBFC;--note:#EEF0F4}
.shell{display:grid;grid-template-columns:248px 1fr;min-height:100vh}.side{background:#FFF;border-right:1px solid var(--line);padding:22px 18px}
.side .logo{margin:0 6px 30px}.side a{display:block;padding:9px 12px;border-radius:8px;font-size:14px;color:var(--mut);margin-bottom:2px}
.side a.on{background:var(--tagbg);color:var(--tagfg);font-weight:500}.side .who{margin-top:36px;padding:14px;border:1px solid var(--line);border-radius:10px;font-size:13px}
.side .who div{display:flex;justify-content:space-between;padding:4px 0}.wrap{padding:30px 40px 70px;max-width:1240px}
h1{font-size:28px}h1.big{font-size:44px}.kpi .num{font-size:26px}""", layout="side"),
}

SIDE_NAV = ["Welcome", "Your profile", "Your results", "Assistant"]

def page(theme, screen):
    t = THEMES[theme]
    body = results() if screen == "results" else welcome()
    on = "Your results" if screen == "results" else "Welcome"
    if t["layout"] == "side":
        links = "".join(f'<a class="{"on" if n == on else ""}">{n}</a>' for n in SIDE_NAV)
        who = ('<div class="who"><div class="muted">Profile</div><div><span>Age</span><b>59</b></div><div><span>Invested</span><b>$400,000</b></div>'
               '<div><span>Horizon</span><b>4 years</b></div><div><span>Loss limit</span><b>15%</b></div></div>') if screen == "results" else ""
        html = f'<div class="shell"><aside class="side"><div class="logo"><span class="mark"></span>AlphaForge</div>{links}{who}</aside><main class="wrap">{body}</main></div>'
    else:
        nav = "".join(f'<span class="{"on" if n == on else ""}">{n}</span>' for n in SIDE_NAV)
        html = f'<div class="top"><div class="logo"><span class="mark"></span>AlphaForge</div><div class="nav">{nav}</div></div><div class="wrap">{body}</div>'
    return f'<!doctype html><html><head><meta charset="utf-8"><title>{t["label"]}</title><style>{BASE}{t["css"]}</style></head><body>{html}</body></html>'

if __name__ == "__main__":
    for th in THEMES:
        for sc in ("welcome", "results"):
            (OUT / f"{th}-{sc}.html").write_text(page(th, sc))
    print("HTML written; screenshots: node interface/mockups/shoot.js")
