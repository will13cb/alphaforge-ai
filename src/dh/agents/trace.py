"""Trace: one entry per hand-off between agents, with a plain-language description of what was passed and why.

This is what the app shows step by step and what the jury can inspect (also saved as JSON → S3).

    tr = Trace()
    tr.step("Profiler", "Portfolio", summary="risk level 2 ...", output=limits)
    print(tr.markdown())
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

ICON = {"pass": "✔", "warn": "⚠", "fail": "✘"}


class Trace:
    def __init__(self):
        self.steps: list[dict] = []

    def step(self, agent: str, to: str, summary: str, output=None, checks=None, sources=None) -> dict:
        e = dict(agent=agent, to=to, timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 summary=summary, output=output, checks=checks or [], sources=sources or [])
        self.steps.append(e)
        return e

    def markdown(self) -> str:
        lines = []
        for i, s in enumerate(self.steps, 1):
            lines.append(f"**{i}. {s['agent']} → {s['to']}**: {s['summary']}")
            lines += [f"   - {ICON[c['status']]} {c['rule']} {c['text']}: {c['detail']}" for c in s["checks"]]
        return "\n".join(lines)

    def to_json(self) -> str:
        return json.dumps(self.steps, ensure_ascii=False, indent=2, default=str)


def _caps_line(lim: dict) -> str:
    """One company's cap is per company (#24): show the range and the tightest ones."""
    caps = lim.get("company_caps")
    if not caps:
        return f"one company ≤ {lim['max_single']:.0%}"
    lo = sorted(caps.items(), key=lambda kv: kv[1])
    if lo[0][1] == lo[-1][1]:
        return f"one company ≤ {lo[0][1]:.1%} (same for all: the stock room binds)"
    return (f"one company ≤ {lo[0][1]:.1%} to {lo[-1][1]:.1%} depending on its worst drop "
            f"(e.g. {', '.join(f'{t} {c:.1%}' for t, c in lo[:2])})")


def describe_limits(lim: dict) -> str:
    """Profiler → Portfolio hand-off, in words."""
    if lim.get("missing"):
        return f"profile incomplete, asking the client for: {', '.join(lim['missing'])}. No proposal yet."
    s = (f"risk level {lim['risk_level']} ({lim['risk_name']}; tolerance {lim['risk_tolerance']}, capacity "
         f"{lim['risk_capacity']}), knowledge {lim['knowledge_score']}/5. Limits: max drawdown "
         f"{lim['max_drawdown']:.0%}, defensive ≥ {lim['min_defensive']:.0%}, crypto ≤ {lim['max_crypto']:.1%}, "
         + _caps_line(lim) + ".")
    if lim["flags"]:
        s += " Flags: " + "; ".join(lim["flags"]) + "."
    if lim.get("kyc"):
        s += " " + lim["kyc"]["message"][:1].upper() + lim["kyc"]["message"][1:] + "."
    return s


def describe_checks(who: str, checks: list[dict], verdict: str) -> str:
    n = {k: sum(c["status"] == k for c in checks) for k in ICON}
    fails = [c["rule"] for c in checks if c["status"] == "fail"]
    tail = {"pass": "approved", "warn": "approved with disclosures",
            "fail": f"sent back to {who} ({', '.join(fails)})"}[verdict]
    return f"{n['pass']} ✔, {n['warn']} ⚠, {n['fail']} ✘ → {tail}."
