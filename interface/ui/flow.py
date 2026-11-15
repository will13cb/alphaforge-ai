"""The pipeline as a small graph that fills in while it runs (live view) and after (Activity page).

Built only from the trace's recorded hand-offs (agent → to): a node is "done" once it has handed something on, the
node that just received a hand-off is "working" until it hands on in turn. Nothing here is estimated or simulated.
Inline SVG, coloured with the theme's tokens, so it follows light/dark mode."""
from __future__ import annotations

from html import escape

# Main row, in pipeline order (pipeline.py), and the Guardian below it, linked to the steps it checks.
NODES = [("Client", "your answers"), ("Profiler", "rules"), ("Market data", "deterministic"),
         ("Portfolio", "up to 3 strategies"), ("Critic", "Claude · Bedrock"), ("Explainer", "Claude · Bedrock"),
         ("Trace store", "Amazon S3")]
GUARDIAN = ("Guardian", "code-enforced rules")
GUARDS = ["Profiler", "Portfolio", "Explainer"]          # where pipeline.py calls the Guardian
ALIASES = {"Extractor": "Client", "Amazon S3": "Trace store", "local disk": "Trace store"}

W, H, NW, NH = 1000, 250, 122, 60
ROW_Y, G_Y = 22, 168


def _x(i: int) -> float:
    gap = (W - 20 - len(NODES) * NW) / (len(NODES) - 1)
    return 10 + i * (NW + gap)


def _pos() -> dict[str, tuple[float, float]]:
    p = {name: (_x(i), ROW_Y) for i, (name, _) in enumerate(NODES)}
    p[GUARDIAN[0]] = (W / 2 - NW / 2, G_Y)
    return p


def state(steps: list[dict], finished: bool = False) -> tuple[dict, set, str | None]:
    """({node: runs}, {(a, b) edges used}, working node). Only names in the graph count; others are ignored."""
    names = {n for n, _ in NODES} | {GUARDIAN[0]}
    runs: dict[str, int] = {"Client": 1}
    used, working = set(), None
    for s in steps:
        a, b = ALIASES.get(s.get("agent"), s.get("agent")), ALIASES.get(s.get("to"), s.get("to"))
        if a in names:
            runs[a] = runs.get(a, 0) + 1
        if a in names and b in names and a != b:
            used.add((a, b))
        working = b if b in names and b != "Client" else None
    if finished:
        working = None
    elif working is None and len(runs) == 1:
        working = "Profiler"                                   # nothing recorded yet: the Profiler starts
    return runs, used, working


def _edge(a: str, b: str, pos: dict, used: set) -> str:
    on = (a, b) in used or (b, a) in used
    if b == GUARDIAN[0] or a == GUARDIAN[0]:
        n = a if b == GUARDIAN[0] else b
        x1, y1 = pos[n][0] + NW / 2, pos[n][1] + NH
        x2, y2 = pos[GUARDIAN[0]][0] + NW / 2 + (GUARDS.index(n) - 1) * 34, pos[GUARDIAN[0]][1]
        return (f'<path d="M{x1:.0f},{y1:.0f} C{x1:.0f},{y1 + 45:.0f} {x2:.0f},{y2 - 45:.0f} {x2:.0f},{y2:.0f}" '
                f'class="af-e {"on" if on else ""}" stroke-dasharray="5 5"/>')
    x1, y = pos[a][0] + NW, pos[a][1] + NH / 2
    x2 = pos[b][0]
    return (f'<line x1="{x1:.0f}" y1="{y:.0f}" x2="{x2 - 4:.0f}" y2="{y:.0f}" class="af-e {"on" if on else ""}" '
            f'marker-end="url(#af-arrow{"-on" if on else ""})"/>')


def _node(name: str, sub: str, pos: dict, runs: dict, working: str | None) -> str:
    x, y = pos[name]
    cls = "work" if name == working else "done" if name in runs else "todo"
    n = runs.get(name, 0)
    badge = (f'<text x="{x + NW - 10:.0f}" y="{y + 16:.0f}" class="af-badge" text-anchor="end">×{n}</text>'
             if n > 1 and name != "Client" else "")
    tick = (f'<path d="M{x + 10:.0f},{y + 14:.0f} l4,4 l8,-9" class="af-tick"/>' if cls == "done" else
            f'<circle cx="{x + 15:.0f}" cy="{y + 13:.0f}" r="4" class="af-dot"/>' if cls == "work" else "")
    return (f'<g class="af-n {cls}"><rect x="{x:.0f}" y="{y:.0f}" width="{NW}" height="{NH}" rx="12"/>{tick}{badge}'
            f'<text x="{x + NW / 2:.0f}" y="{y + 34:.0f}" text-anchor="middle" class="af-t">{escape(name)}</text>'
            f'<text x="{x + NW / 2:.0f}" y="{y + 50:.0f}" text-anchor="middle" class="af-s">{escape(sub)}</text></g>')


CSS = """<style>
.af-flowgraph svg { width: 100%; height: auto; display: block; }
.af-flowgraph .af-n rect { fill: var(--panel); stroke: var(--line); stroke-width: 1.5; }
.af-flowgraph .af-n.done rect { stroke: var(--good); }
.af-flowgraph .af-n.work rect { stroke: var(--acc); stroke-width: 2.5; animation: af-pulse 1.2s ease-in-out infinite; }
.af-flowgraph .af-n.todo text { opacity: .45; }
.af-flowgraph .af-t { fill: var(--ink); font-size: 15px; font-weight: 600; font-family: inherit; }
.af-flowgraph .af-s { fill: var(--mut); font-size: 11.5px; font-family: inherit; }
.af-flowgraph .af-badge { fill: var(--mut); font-size: 11px; font-weight: 600; }
.af-flowgraph .af-tick { fill: none; stroke: var(--good); stroke-width: 2.5; stroke-linecap: round; stroke-linejoin: round; }
.af-flowgraph .af-dot { fill: var(--acc); animation: af-blink 1.2s ease-in-out infinite; }
.af-flowgraph .af-e { stroke: var(--line); stroke-width: 2; fill: none; }
.af-flowgraph .af-e.on { stroke: var(--good); }
.af-flowgraph .af-legend { font-size: .8rem; color: var(--mut); margin-top: .3rem; }
@media (max-width: 640px) { .af-flowgraph { overflow-x: auto; } .af-flowgraph svg { min-width: 680px; } }
@keyframes af-pulse { 50% { stroke-opacity: .35; } }
@keyframes af-blink { 50% { opacity: .2; } }
@media (prefers-reduced-motion: reduce) { .af-flowgraph .af-n.work rect, .af-flowgraph .af-dot { animation: none; } }
</style>"""


def svg(steps: list[dict], finished: bool = False, caption: str | None = None) -> str:
    """The graph for these recorded steps, as HTML for st.markdown(unsafe_allow_html=True)."""
    runs, used, working = state(steps, finished)
    pos = _pos()
    names = [n for n, _ in NODES]
    used |= {(a, b) for a, b in zip(names, names[1:]) if a in runs and b in runs}   # both ran: data went through
    edges = [_edge(a, b, pos, used) for a, b in zip(names, names[1:])]
    edges += [_edge(n, GUARDIAN[0], pos, used) for n in GUARDS]
    nodes = [_node(n, s, pos, runs, working) for n, s in [*NODES, GUARDIAN]]
    done = sum(1 for n in [*names, GUARDIAN[0]] if n in runs)
    label = (f"Pipeline: {done} of {len(names) + 1} agents done"
             + (f", {working} working" if working else ""))
    arrows = "".join(
        f'<marker id="af-arrow{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        f'orient="auto"><path d="M0,0 L10,5 L0,10 z" style="fill: var({c})"/></marker>'
        for k, c in (("", "--line"), ("-on", "--good")))
    legend = caption if caption is not None else (
        f"{working} is working…" if working else "All steps recorded." if finished else "")
    return (f'{CSS}<div class="af-flowgraph" role="img" aria-label="{escape(label)}">'
            f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg"><defs>{arrows}</defs>'
            + "".join(edges) + "".join(nodes) + "</svg>"
            + (f'<div class="af-legend">{escape(legend)}</div>' if legend else "") + "</div>")
