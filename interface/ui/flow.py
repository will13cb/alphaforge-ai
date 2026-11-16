"""The pipeline as a small graph that fills in while it runs (live view) and after (Activity page).

Built only from the trace's recorded hand-offs (agent → to): a node is "done" once it has handed something on, the
node that just received a hand-off is "working" until it hands on in turn. Nothing here is estimated or simulated.
Inline SVG, coloured with the theme's tokens, so it follows light/dark mode."""
from __future__ import annotations

from html import escape

from dh.i18n import lang, tr

# Main row, in pipeline order (pipeline.py), and the Guardian below it, linked to the steps it checks.
NODES = [("Client", "your answers"), ("Profiler", "rules"), ("Market data", "deterministic"),
         ("Portfolio", "up to 3 strategies"), ("Critic", "Claude · Bedrock"), ("Explainer", "Claude · Bedrock"),
         ("Trace store", "Amazon S3")]
GUARDIAN = ("Guardian", "code-enforced rules")
GUARDS = ["Profiler", "Portfolio", "Explainer"]          # where pipeline.py calls the Guardian
ALIASES = {"Extractor": "Client", "Amazon S3": "Trace store", "local disk": "Trace store"}

W, NW = 1000, 122
ROW_Y, G_GAP = 22, 86                 # top of the main row; space between that row and the Guardian
T_SIZE, S_SIZE, PAD = 15, 11.5, 8     # title and subtitle font sizes; room kept on each side of a box
# French labels are longer than the English ones ("Données de marché", "règles imposées par le code") and ran out
# of their box: a title now wraps on two lines, a subtitle shrinks to fit, and the Guardian's box (alone on its
# row) grows to its text. A browser cannot be asked for a text's width here, so it is estimated per character.
_NARROW, _WIDE = set("iíìîïjlI.,:;'’!|·()[] "), set("mwMW@%")


def _width(text: str, size: float, bold: bool = False) -> float:
    """Estimated width of `text` in the graph's units (Inter and its fallbacks, a little on the safe side)."""
    em = sum(.30 if c in _NARROW else .40 if c in "ftr" else .90 if c in _WIDE else .70 if c.isupper() else .58
             for c in text)
    return em * size * (1.05 if bold else 1.0)


def _lines(title: str, room: float) -> list[str]:
    """The title on one line if it fits, else on the two most even lines."""
    words = title.split()
    if _width(title, T_SIZE, True) <= room or len(words) < 2:
        return [title]
    cuts = [(" ".join(words[:i]), " ".join(words[i:])) for i in range(1, len(words))]
    return list(min(cuts, key=lambda c: max(_width(c[0], T_SIZE, True), _width(c[1], T_SIZE, True))))


def _fit(text: str, size: float, room: float, bold: bool = False) -> float:
    """The font size, never above `size`, at which `text` fits in `room`."""
    w = _width(text, size, bold)
    return size if w <= room else round(max(8.0, size * room / w), 1)


def _labels() -> dict[str, tuple[list[str], str]]:
    """{node: (title lines, subtitle)} in the current language."""
    return {n: (_lines(tr(n), NW - 2 * PAD), tr(s)) for n, s in [*NODES, GUARDIAN]}


def _layout() -> tuple[dict, dict, int]:
    """({node: (x, y)}, {node: (width, height)}, total height). One height for every box, taller if a title wraps."""
    labels = _labels()
    nh = 76 if any(len(lines) > 1 for lines, _ in labels.values()) else 60
    gap = (W - 20 - len(NODES) * NW) / (len(NODES) - 1)
    pos = {name: (10 + i * (NW + gap), ROW_Y) for i, (name, _) in enumerate(NODES)}
    size = {name: (NW, nh) for name, _ in NODES}
    lines, sub = labels[GUARDIAN[0]]
    gw = max(*(_width(t, T_SIZE, True) for t in lines), _width(sub, S_SIZE)) + 2 * PAD
    gw = min(max(NW, round(gw)), W - 20)
    pos[GUARDIAN[0]] = (W / 2 - gw / 2, ROW_Y + nh + G_GAP)
    size[GUARDIAN[0]] = (gw, nh)
    return pos, size, ROW_Y + nh + G_GAP + nh + 22


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


def _edge(a: str, b: str, pos: dict, size: dict, used: set) -> str:
    on = (a, b) in used or (b, a) in used
    if b == GUARDIAN[0] or a == GUARDIAN[0]:
        n, g = (a if b == GUARDIAN[0] else b), GUARDIAN[0]
        x1, y1 = pos[n][0] + size[n][0] / 2, pos[n][1] + size[n][1]
        x2, y2 = pos[g][0] + size[g][0] / 2 + (GUARDS.index(n) - 1) * 34, pos[g][1]
        return (f'<path d="M{x1:.0f},{y1:.0f} C{x1:.0f},{y1 + 45:.0f} {x2:.0f},{y2 - 45:.0f} {x2:.0f},{y2:.0f}" '
                f'class="af-e {"on" if on else ""}" stroke-dasharray="5 5"/>')
    x1, y = pos[a][0] + size[a][0], pos[a][1] + size[a][1] / 2
    x2 = pos[b][0]
    return (f'<line x1="{x1:.0f}" y1="{y:.0f}" x2="{x2 - 4:.0f}" y2="{y:.0f}" class="af-e {"on" if on else ""}" '
            f'marker-end="url(#af-arrow{"-on" if on else ""})"/>')


def _text(x: float, y: float, cls: str, text: str, size: float, base: float) -> str:
    style = f' style="font-size:{size}px"' if size < base else ""
    return f'<text x="{x:.0f}" y="{y:.0f}" text-anchor="middle" class="{cls}"{style}>{escape(text)}</text>'


def _node(name: str, label: tuple[list[str], str], pos: dict, size: dict, runs: dict, working: str | None) -> str:
    (x, y), (w, h), (lines, sub) = pos[name], size[name], label
    cls = "work" if name == working else "done" if name in runs else "todo"
    n = runs.get(name, 0)
    badge = (f'<text x="{x + w - 10:.0f}" y="{y + 16:.0f}" class="af-badge" text-anchor="end">×{n}</text>'
             if n > 1 and name != "Client" else "")
    tick = (f'<path d="M{x + 10:.0f},{y + 14:.0f} l4,4 l8,-9" class="af-tick"/>' if cls == "done" else
            f'<circle cx="{x + 15:.0f}" cy="{y + 13:.0f}" r="4" class="af-dot"/>' if cls == "work" else "")
    room, cx, mid = w - 2 * PAD, x + w / 2, y + h / 2
    first = mid + 4 if len(lines) == 1 else mid - 6           # baseline of the title's first line
    texts = [_text(cx, first + 17 * i, "af-t", t, _fit(t, T_SIZE, room, True), T_SIZE) for i, t in enumerate(lines)]
    texts.append(_text(cx, first + 17 * (len(lines) - 1) + 17, "af-s", sub, _fit(sub, S_SIZE, room), S_SIZE))
    return (f'<g class="af-n {cls}"><rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h}" rx="12"/>{tick}{badge}'
            + "".join(texts) + "</g>")


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
    pos, size, height = _layout()
    labels = _labels()
    names = [n for n, _ in NODES]
    used |= {(a, b) for a, b in zip(names, names[1:]) if a in runs and b in runs}   # both ran: data went through
    edges = [_edge(a, b, pos, size, used) for a, b in zip(names, names[1:])]
    edges += [_edge(n, GUARDIAN[0], pos, size, used) for n in GUARDS]
    nodes = [_node(n, labels[n], pos, size, runs, working) for n in [*names, GUARDIAN[0]]]
    done = sum(1 for n in [*names, GUARDIAN[0]] if n in runs)
    label = ((f"Pipeline : {done} agents sur {len(names) + 1} terminés" + (f", {tr(working)} en cours" if working else ""))
             if lang() == "fr" else
             (f"Pipeline: {done} of {len(names) + 1} agents done" + (f", {working} working" if working else "")))
    arrows = "".join(
        f'<marker id="af-arrow{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        f'orient="auto"><path d="M0,0 L10,5 L0,10 z" style="fill: var({c})"/></marker>'
        for k, c in (("", "--line"), ("-on", "--good")))
    legend = caption if caption is not None else (
        (f"{tr(working)} : en cours…" if lang() == "fr" else f"{working} is working…") if working
        else tr("All steps recorded.") if finished else "")
    return (f'{CSS}<div class="af-flowgraph" role="img" aria-label="{escape(label)}">'
            f'<svg viewBox="0 0 {W} {height}" xmlns="http://www.w3.org/2000/svg"><defs>{arrows}</defs>'
            + "".join(edges) + "".join(nodes) + "</svg>"
            + (f'<div class="af-legend">{escape(tr(legend))}</div>' if legend else "") + "</div>")

