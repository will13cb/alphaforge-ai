"""Draw the AWS architecture map (aws/AWS_ARCHITECTURE*.svg), French and English, from one fixed layout.

    python scripts/build_aws_diagram.py

Hand-laid-out SVG rather than Mermaid: the automatic layout crossed every arrow. Plain SVG, no dependency; GitHub
shows it sharp at any zoom. Edit the labels below, re-run, commit the two SVGs."""
from __future__ import annotations

from html import escape
from pathlib import Path
import math
import re

ROOT = Path(__file__).resolve().parents[1]
W, H = 1440, 1100

C = dict(ink="#111827", mut="#4b5563", line="#9ca3af",
         aws="#ff9900", aws_bg="#fff7ed", aws_fill="#ffedd5", aws_stroke="#c2410c",
         s3_bg="#f0fdf4", s3_fill="#dcfce7", s3_stroke="#15803d",
         agent_fill="#dbeafe", agent_stroke="#1d4ed8", code_fill="#fef3c7", code_stroke="#b45309",
         host_bg="#f8fafc", host_stroke="#cbd5e1", plain="#f3f4f6", plain_stroke="#6b7280")

LABELS = {
    "fr": dict(
        title="AlphaForge AI · architecture AWS",
        subtitle="Les agents raisonnent sur Amazon Bedrock, le code décide, Amazon S3 garde la preuve.",
        client=["Client", "navigateur ou téléphone"],
        host="Streamlit Community Cloud · hébergement (hors AWS)",
        app=["Applications AlphaForge", "interface guidée · démo du jury", "orchestrateur pipeline.py"],
        agents=["4 agents Strands", "Extracteur · Critique", "Explicateur · Analyste"],
        code=["Code déterministe", "Profileur · Portefeuille · Gardien", "ou obligations à échéance (sans LLM)"],
        modes=["Mode réellement utilisé", "Bedrock en direct · cache · secours", "Texte FR/EN : faits vérifiés", "S3 indisponible : trace locale tentée"],
        tools="outils = fonctions du code",
        aws="AWS · clients us-east-1 par défaut · profil modèle global",
        bedrock=["Amazon Bedrock", "Claude Opus 5.5", "Converse / ConverseStream + outils"],
        reason="raisonnement + appels d'outils",
        s3="Amazon S3 · un compartiment",
        raw=["raw/", "données de marché, obligations"],
        traces=["traces/", "JSON : analyses et suivis"],
        voice=["voice/", "audio temporaire · nettoyage"],
        first="au besoin · catalogue distinct",
        every="trace · secours local si échec",
        transcribe=["Amazon Transcribe", "parole → texte · fr-CA, en-CA"],
        polly=["Amazon Polly", "texte → parole · voix neuronales"],
        speech="voix (facultative)",
        agentcore=["Bedrock AgentCore Runtime", "prévu, non déployé"],
        team="Poste de l'équipe",
        up=["make data-up", "données → S3 raw/"],
        warm=["make warm", "Bedrock → réponses dans cache/"],
        backup=["make backup", "S3 traces/ → dépôt"],
        repo=["Dépôt GitHub", "code · cache/ : Claude rejouable"],
        deploy="déploie",
        legend=[("aws", "service AWS"), ("s3", "Amazon S3"), ("agent", "agents Strands (Bedrock)"),
                ("code", "code déterministe : décide"), ("planned", "prévu, non déployé")],
    ),
    "en": dict(
        title="AlphaForge AI · AWS architecture",
        subtitle="Agents reason on Amazon Bedrock, code decides, Amazon S3 keeps the evidence.",
        client=["Client", "browser or phone"],
        host="Streamlit Community Cloud · hosting (outside AWS)",
        app=["AlphaForge apps", "guided interface · jury demo", "orchestrator pipeline.py"],
        agents=["4 Strands agents", "Extractor · Critic", "Explainer · Analyst"],
        code=["Deterministic code", "Profiler · Portfolio · Guardian", "or held-to-maturity path (no LLM)"],
        modes=["Actual execution mode", "Live Bedrock · cache · fallback", "French/English text: checked facts", "S3 unavailable: local trace attempted"],
        tools="tools = code functions",
        aws="AWS · us-east-1 clients by default · global model profile",
        bedrock=["Amazon Bedrock", "Claude Opus 5.5", "Converse / ConverseStream + tools"],
        reason="reasoning + tool calls",
        s3="Amazon S3 · one bucket",
        raw=["raw/", "market data, bonds"],
        traces=["traces/", "JSON: analyses and follow-ups"],
        voice=["voice/", "temporary audio · cleanup"],
        first="as needed · separate catalogue",
        every="trace · local fallback on failure",
        transcribe=["Amazon Transcribe", "speech → text · fr-CA, en-CA"],
        polly=["Amazon Polly", "text → speech · neural voices"],
        speech="voice (optional)",
        agentcore=["Bedrock AgentCore Runtime", "planned, not deployed"],
        team="Team workstation",
        up=["make data-up", "data → S3 raw/"],
        warm=["make warm", "Bedrock → answers in cache/"],
        backup=["make backup", "S3 traces/ → repo"],
        repo=["GitHub repo", "code · cache/: Claude replayable"],
        deploy="deploys",
        legend=[("aws", "AWS service"), ("s3", "Amazon S3"), ("agent", "Strands agents (Bedrock)"),
                ("code", "deterministic code: decides"), ("planned", "planned, not deployed")],
    ),
}

STYLE = {"aws": (C["aws_fill"], C["aws_stroke"], ""), "s3": (C["s3_fill"], C["s3_stroke"], ""),
         "agent": (C["agent_fill"], C["agent_stroke"], ""), "code": (C["code_fill"], C["code_stroke"], ""),
         "plain": (C["plain"], C["plain_stroke"], ""), "planned": ("#ffffff", C["line"], "6 5")}


def box(x, y, w, h, lines, kind, rx=10, size=16):
    fill, stroke, dash = STYLE[kind]
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" '
           f'stroke-width="1.8"{f" stroke-dasharray={chr(34)}{dash}{chr(34)}" if dash else ""}/>']
    n = len(lines)
    top = y + h / 2 - (n - 1) * 11 + 5
    for i, t in enumerate(lines):
        bold = i == 0
        out.append(f'<text x="{x + w / 2}" y="{top + i * 22:.0f}" text-anchor="middle" '
                   f'font-size="{size if bold else size - 2}" font-weight="{700 if bold else 400}" '
                   f'fill="{C["mut"] if kind == "planned" else (C["ink"] if bold else C["mut"])}">{escape(t)}</text>')
    return "".join(out)


def zone(x, y, w, h, label, bg, stroke, dash=""):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{bg}" stroke="{stroke}" stroke-width="1.5"'
            f'{f" stroke-dasharray={chr(34)}{dash}{chr(34)}" if dash else ""}/>'
            f'<text x="{x + 16}" y="{y + 26}" font-size="15" font-weight="700" fill="{C["mut"]}">{escape(label)}</text>')


def arrow(d, label=None, lx=0, ly=0, width=2.0, color=None, both=False, dash="", anchor="middle"):
    color = color or C["mut"]
    out = (f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}"'
           f'{f" stroke-dasharray={chr(34)}{dash}{chr(34)}" if dash else ""}/>')
    points = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", d)]
    ends = [(points[-2:], points[-4:-2])]
    if both:
        ends.append((points[:2], points[2:4]))
    for (tx, ty), (px, py) in ends:
        angle = math.atan2(ty-py, tx-px)
        bx, by = tx-10*math.cos(angle), ty-10*math.sin(angle)
        coords = f"{tx},{ty} {bx+4*math.sin(angle):.1f},{by-4*math.cos(angle):.1f} {bx-4*math.sin(angle):.1f},{by+4*math.cos(angle):.1f}"
        out += f'<polygon points="{coords}" fill="{color}"/>'
    if label:
        tw = len(label)*7 + 14
        left = lx if anchor == "start" else lx-tw/2
        out += f'<rect x="{left:.0f}" y="{ly-14}" width="{tw}" height="20" rx="3" fill="#ffffff"/>'
        out += (f'<text x="{lx}" y="{ly}" text-anchor="{anchor}" font-size="13.5" fill="{C["ink"]}">{escape(label)}</text>')
    return out


def cylinder(x, y, w, h, lines):
    fill, stroke = C["s3_fill"], C["s3_stroke"]
    e = 9
    out = (f'<path d="M{x},{y + e} v{h - 2 * e} a{w / 2},{e} 0 0,0 {w},0 v{-(h - 2 * e)}" fill="{fill}" stroke="{stroke}" stroke-width="1.8"/>'
           f'<ellipse cx="{x + w / 2}" cy="{y + e}" rx="{w / 2}" ry="{e}" fill="{fill}" stroke="{stroke}" stroke-width="1.8"/>')
    out += (f'<text x="{x + w / 2}" y="{y + h / 2 + 4}" text-anchor="middle" font-size="16" font-weight="700" '
            f'fill="{C["ink"]}" font-family="ui-monospace, Menlo, monospace">{escape(lines[0])}</text>'
            f'<text x="{x + w / 2}" y="{y + h / 2 + 26}" text-anchor="middle" font-size="14" fill="{C["mut"]}">'
            f'{escape(lines[1])}</text>')
    return out


def svg(lang: str) -> str:
    L = LABELS[lang]
    p = []
    p.append(f'<text x="40" y="44" font-size="24" font-weight="700" fill="{C["ink"]}">{escape(L["title"])}</text>')
    p.append(f'<text x="40" y="72" font-size="15.5" fill="{C["mut"]}">{escape(L["subtitle"])}</text>')

    # zones
    p.append(zone(220, 100, 420, 680, L["host"], C["host_bg"], C["host_stroke"]))
    p.append(zone(690, 100, 710, 680, L["aws"], C["aws_bg"], C["aws"]))
    p.append(zone(1040, 140, 340, 330, L["s3"], C["s3_bg"], C["s3_stroke"]))
    p.append(zone(220, 870, 1180, 150, L["team"], C["host_bg"], C["host_stroke"]))

    # client + hosted app
    p.append(box(14, 330, 196, 76, L["client"], "plain", rx=38))
    p.append(box(260, 150, 340, 96, L["app"], "plain"))
    p.append(box(260, 300, 340, 96, L["agents"], "agent"))
    p.append(box(260, 470, 340, 96, L["code"], "code"))
    p.append(box(260, 620, 340, 126, L["modes"], "plain", size=15))
    p.append(arrow("M430,566 L430,614"))
    p.append(arrow("M210,368 L254,368", both=True))
    p.append(arrow("M430,246 L430,294"))
    p.append(arrow("M300,246 C240,300 240,420 300,464"))
    p.append(arrow("M430,396 L430,464", L["tools"], 440, 436, anchor="start"))

    # AWS
    p.append(box(730, 290, 270, 116, L["bedrock"], "aws", size=17))
    p.append(arrow("M600,348 L724,348", width=4, color=C["agent_stroke"], both=True))
    p.append(f'<text x="662" y="334" text-anchor="middle" font-size="13.5" font-weight="600" fill="{C["agent_stroke"]}">'
             f'{escape(L["reason"].split(" + ")[0])}</text>')
    p.append(f'<text x="662" y="372" text-anchor="middle" font-size="13.5" font-weight="600" fill="{C["agent_stroke"]}">'
             f'+ {escape(L["reason"].split(" + ")[1])}</text>')
    p.append(cylinder(1080, 180, 260, 80, L["raw"]))
    p.append(cylinder(1080, 280, 260, 80, L["traces"]))
    p.append(cylinder(1080, 380, 260, 80, L["voice"]))
    p.append(arrow("M1080,214 L700,214 L700,186 L606,186", L["first"], 870, 206))
    p.append(arrow("M600,232 L1050,232 L1050,320 L1074,320", L["every"], 870, 254))
    p.append(box(730, 470, 270, 66, L["transcribe"], "aws"))
    p.append(box(730, 552, 270, 66, L["polly"], "aws"))
    p.append(arrow("M1000,503 L1040,503 L1040,430 L1074,430", both=True))
    p.append(arrow("M600,540 L660,540 L660,503 L724,503", L["speech"], 736, 460, anchor="start"))
    p.append(arrow("M660,540 L660,585 L724,585"))
    p.append(box(1060, 520, 300, 76, L["agentcore"], "planned"))

    # team
    p.append(box(250, 920, 230, 72, L["up"], "plain", size=15))
    p.append(box(510, 920, 270, 72, L["warm"], "plain", size=15))
    p.append(box(810, 920, 230, 72, L["backup"], "plain", size=15))
    p.append(box(1080, 920, 290, 72, L["repo"], "plain", size=15))
    p.append(arrow("M1040,956 L1074,956"))
    p.append(arrow("M1225,920 L1225,830 L630,830 L630,786", L["deploy"], 930, 823))

    # legend
    lx = 40
    for kind, text in L["legend"]:
        fill, stroke, dash = STYLE[kind]
        p.append(f'<rect x="{lx}" y="1048" width="18" height="14" rx="3" fill="{fill}" stroke="{stroke}" stroke-width="1.5"'
                 f'{f" stroke-dasharray={chr(34)}3 2{chr(34)}" if dash else ""}/>'
                 f'<text x="{lx + 24}" y="1060" font-size="13" fill="{C["mut"]}">{escape(text)}</text>')
        lx += 24 + 7.2 * len(text) + 22

    defs = (f'<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="11" markerHeight="11" markerUnits="userSpaceOnUse" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{C["mut"]}"/></marker>'
            f'<marker id="as" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="11" markerHeight="11" markerUnits="userSpaceOnUse" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{C["mut"]}"/></marker></defs>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
            f'font-family="DejaVu Sans" role="img" '
            f'aria-label="{escape(L["title"])}"><rect width="{W}" height="{H}" fill="#ffffff"/>{defs}'
            + "".join(p) + "</svg>\n")


def main() -> None:
    for lang, name in (("fr", "AWS_ARCHITECTURE.svg"), ("en", "AWS_ARCHITECTURE.en.svg")):
        (ROOT / "aws" / name).write_text(svg(lang), encoding="utf-8")
        print("wrote", f"aws/{name}")


if __name__ == "__main__":
    main()
