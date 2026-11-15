"""Analyst (app follow-ups): a Strands agent on Amazon Bedrock that answers the client's follow-up questions.

"What if I put 10% in NVDA?", "what if my horizon were 8 years?", "why so few stocks?". It decides which
deterministic tools to call, and every number in its answer must come from a tool result it cites. Same discipline
as the Critic (decision #14 "agents investigate and argue, code enforces"):

    1. tools     Joud's market tools (#15, incl. required_return), the Critic's views on the run, and two what-ifs
                 that RE-RUN THE REAL PIPELINE (Profiler → Portfolio → checks C-F → Guardian): `what_if_position`,
                 `what_if_profile`. Nothing is computed by the model.
    2. backed?   every number in the answer must appear in a tool result it cites (critic._backed); else the answer
                 is replaced by the deterministic one, and the trace says why
    3. wording   no buy/sell advice, no forecast; the simulation disclaimer is added by code
    4. budget    at most MAX_CALLS tool calls

Modes, like the Critic and the Explainer (#23): `bedrock` (committed demo cache → local cache → Strands agent) and
`mock` (default, tests, offline): a deterministic analyst that reads the question with simple patterns, calls the
same tools and writes the answer from their results.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone

from ..data import ROOT, period, period_label
from ..personas import DISCLAIMER

DISCLAIMER_FR = "Simulation seulement, pour un profil fictif. Pas un conseil financier ; aucune transaction réelle."
from . import critic, market
from .rules import UNIVERSE

PROMPT_VERSION = "analyst-v3"
DEMO_CACHE = ROOT / "cache" / "analyst"     # committed: the demo replays offline
LOCAL_CACHE = ROOT / ".cache" / "analyst"   # gitignored
MAX_CALLS = 5
PROFILE_FIELDS = ("horizon_years", "max_loss_pct", "target_amount", "monthly_contribution", "capital",
                  "withdrawal_share_3y")
SYSTEM_PROMPT = f"""You are the Analyst in an investment-analysis SIMULATION (no real money, no advice). A fictional
client already got up to three strategies; you receive FACTS (their limits and strategies, as JSON) and their
follow-up QUESTION. Answer it by CHECKING with the tools, at most {MAX_CALLS} calls:
- what_if_position(ticker, weight, also, profile_changes): re-runs the pipeline with that position (and other
  positions / profile changes asked in the same question), shows "as asked" vs "fits your limits".
- what_if_profile(field, value, also): re-runs the pipeline with profile fields changed ({", ".join(PROFILE_FIELDS)}).
- results_overview (the client's own results), the market tools, required_return, look_through, strategy_checks,
  limit_reason.
- You may see CONVERSATION SO FAR: use it to understand follow-ups ("and with 5%?"), but every number in your
  answer must come from a tool result you obtained for THIS answer.
- Explaining a concept (volatility, a bond, ...) needs no tool: plain words, no numbers.
Rules:
- Every tool result has a call_id (t1, t2, ...). Cite the call_ids your answer relies on.
- Quote numbers ONLY as they appear in the results you cite (you may round 0.912 to 0.91 or 0.132 to 13.2%).
  An answer with a number no cited result contains is replaced by code.
- At most 5 short sentences, plain language, IN THE CLIENT'S LANGUAGE (French or English). Give the numbers; the
  client decides. Never "buy"/"sell", never a forecast. If a tool returns an error (e.g. an asset we have no data
  for), say so plainly.
- A number written next to an asset or a strategy must come from THAT asset's or strategy's result; counts ("9
  rules") and years must be in the results too. Code checks all of this.
Answer with JSON only: {{"answer": "<text>", "evidence": ["t1", ...]}}
"""


# ---- tools ---------------------------------------------------------------------------------------------

def _compact_version(v: dict | None) -> dict | None:
    if not v:
        return None
    return {k: v.get(k) for k in ("real_weight", "max_drawdown", "drawdown_cad", "loss_limit", "loss_limit_cad",
                                  "growth", "verdict", "request_at")} | {"fails": [f["id"] for f in v.get("fails", [])]}


def make_tools(res: dict, profile: dict, rets=None, holdings=None) -> list:
    """The Critic's tools (market tools + views on the run) and two what-ifs that re-run the real pipeline."""
    from . import pipeline

    def rerun(p: dict) -> dict:
        return pipeline.run(p, rets=rets, holdings=holdings, critic=False)

    def what_if_position(ticker: str, weight: float, also: dict | None = None,
                         profile_changes: dict | None = None) -> dict:
        """Re-run the pipeline as if the client asked for this position, and compare "as asked" with "fits your limits".

        Args:
            ticker: a ticker, e.g. "NVDA" (list_assets gives what we have data for).
            weight: fraction of the portfolio, e.g. 0.10 for 10%.
            also: other positions asked at the same time, {ticker: weight}, e.g. {"TSLA": 0.05}.
            profile_changes: profile fields changed at the same time, e.g. {"horizon_years": 8}.

        Returns:
            why (the Profiler's reason), as_asked and fits: real weight through ETFs, worst drop in % and in $,
            the client's loss limit in % and $, verdict and the failing checks; or not_assessable.
        """
        req = {str(ticker).upper().strip(): weight, **{str(k).upper().strip(): v for k, v in (also or {}).items()}}
        if any(not isinstance(w, (int, float)) or not 0 < w <= 1 for w in req.values()) or sum(req.values()) > 1:
            return {"error": "weights must be fractions between 0 and 1 (e.g. 0.10 for 10%), together at most 1"}
        changes = dict(profile_changes or {})
        bad = [k for k in changes if k not in PROFILE_FIELDS]
        if bad:
            return {"error": f"profile_changes fields must be among {', '.join(PROFILE_FIELDS)}"}
        r = rerun({**profile, **changes, "requested_positions": {t: float(w) for t, w in req.items()}})
        c = r.get("request_comparison") or {}
        if not c:
            return {"error": "no comparison: the profile is incomplete or no strategy was kept"}
        return market._round({"request": c["request"], "profile_changes": changes, "why": c.get("why", {}),
                              "not_assessable": c.get("not_assessable", []),
                              "as_asked": _compact_version(c.get("as_asked")), "fits": _compact_version(c.get("fits"))})

    def what_if_profile(field: str, value: float, also: dict | None = None) -> dict:
        """Re-run the pipeline with profile fields changed, and show what moves.

        Args:
            field: one of horizon_years, max_loss_pct (0-100), target_amount, monthly_contribution, capital,
                withdrawal_share_3y (0-1).
            value: the new value.
            also: other fields changed at the same time, e.g. {"max_loss_pct": 20}.

        Returns:
            before and after: loss limit, defensive floor, horizon growth cap, and each strategy's growth share,
            worst drop and chance of ending below what was put in (risk-only view).
        """
        changes = {field: value, **(also or {})}
        if any(k not in PROFILE_FIELDS for k in changes):
            return {"error": f"fields must be among {', '.join(PROFILE_FIELDS)}"}
        if any(not isinstance(v, (int, float)) or v < 0 for v in changes.values()):
            return {"error": "values must be non-negative numbers"}

        def view(r):
            lim = r["limits"]
            if lim.get("missing"):
                return {"missing": lim["missing"]}
            return {"loss_limit": lim.get("loss_limit"), "defensive_floor": lim.get("min_defensive"),
                    "horizon_growth_cap": lim.get("horizon_max_growth"),
                    "strategies": [{"key": s["key"], "growth": s["split"]["growth"],
                                    "max_drawdown": s["stats"].get("max_drawdown"),
                                    "prob_loss": s["stats"].get("prob_loss")} for s in r.get("strategies", [])]}

        before = view(res) if res.get("strategies") is not None else view(rerun(profile))
        return market._round({"field": field, "old": profile.get(field), "new": value,
                              "changes": {k: {"old": profile.get(k), "new": v} for k, v in changes.items()},
                              "before": before, "after": view(rerun({**profile, **changes}))})

    def results_overview() -> dict:
        """The client's own results from this run: their limits and each proposed strategy.

        Returns:
            loss_limit (and in $), defensive_floor, horizon_growth_cap, and per strategy: key, name, growth share,
            worst drop, return in 2022, chance of ending below what was put in (risk-only view), warnings.
        """
        lim = res["limits"]
        return market._round({
            "loss_limit": lim.get("loss_limit"), "loss_limit_cad": lim.get("loss_limit_cad"),
            "defensive_floor": lim.get("min_defensive"), "horizon_growth_cap": lim.get("horizon_max_growth"),
            "strategies": [{"key": s["key"], "name": s["name"], "growth": s["split"]["growth"],
                            "max_drawdown": s["stats"].get("max_drawdown"), "return_2022": s["stats"].get("return_2022"),
                            "prob_loss": s["stats"].get("prob_loss"),
                            "warnings": [c["check"] for c in s.get("checks", []) if c["status"] == "warn"]}
                           for s in res.get("strategies") or []]})

    return critic.make_tools(res.get("strategies") or [], res["limits"], holdings or {}) + [results_overview, what_if_position,
                                                                                          what_if_profile]


# ---- reading the question: assets, amounts, language ------------------------------------------------------

# Company and fund names a client actually types → tickers (the 31 starter assets). Universe names from the CSVs are
# added at run time when available. Ambiguous short words ("or", "cn") are left out on purpose.
ALIASES = {
    "apple": "AAPL", "microsoft": "MSFT", "nvidia": "NVDA", "google": "GOOGL", "alphabet": "GOOGL",
    "amazon": "AMZN", "tesla": "TSLA", "jpmorgan": "JPM", "jp morgan": "JPM", "johnson & johnson": "JNJ",
    "johnson and johnson": "JNJ", "procter & gamble": "PG", "procter and gamble": "PG", "exxon": "XOM",
    "exxonmobil": "XOM", "exxon mobil": "XOM", "royal bank": "RY.TO", "banque royale": "RY.TO", "rbc": "RY.TO",
    "td bank": "TD.TO", "banque td": "TD.TO", "toronto-dominion": "TD.TO", "manulife": "MFC.TO", "manuvie": "MFC.TO",
    "enbridge": "ENB.TO", "canadian natural": "CNQ.TO", "cn rail": "CNR.TO", "canadian national": "CNR.TO",
    "canadien national": "CNR.TO", "fortis": "FTS.TO", "couche-tard": "ATD.TO", "couche tard": "ATD.TO",
    "shopify": "SHOP.TO", "constellation software": "CSU.TO", "bitcoin": "BTC-USD", "btc": "BTC-USD",
    "ethereum": "ETH-USD", "ether": "ETH-USD", "eth": "ETH-USD", "s&p 500": "SPY", "s&p500": "SPY",
    "nasdaq": "QQQ", "tsx 60": "XIU.TO", "tsx": "XIU.TO", "gold": "GLD", "l'or": "GLD", "l’or": "GLD",
    "canadian bonds": "XBB.TO", "obligations canadiennes": "XBB.TO", "us bonds": "AGG", "treasuries": "TLT",
}
_STOP = {"ETF", "ESG", "CAD", "USD", "OK", "AI", "IA", "TFSA", "RRSP", "CELI", "REER", "PDF", "FAQ"}
_FR = re.compile(r"\b(et si|je|j'|j’|mon|ma|mes|vous|votre|pourquoi|quel(le)?s?|dans|avec|ans|mettais|mets|aurais|"
                 r"combien|est-ce|faut|rendement|objectif|actions|acheter|vendre|devrais|devriez|dois|peux|une|des|les|du)\b|"
                 r"[éèêàùç]", re.I)
_ADVICE = re.compile(r"\b(should i|shall i|do you recommend|is it a good (time|idea)|buy|sell|dois-je|devrais-je|"
                     r"devriez|faut-il|est-ce que je (dois|devrais)|acheter|vendre|recommandez)\b", re.I)
_PCT = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
_YEARS = re.compile(r"(\d+(?:[.,]\d+)?)[\s-]*(?:years?|ans?|yrs?)\b", re.I)
_LOSS = re.compile(r"(?:lose|loss|losing|perdre|perte|baisse de)\D{0,25}?(\d+(?:[.,]\d+)?)\s*%", re.I)
_AMOUNT = re.compile(r"(\d{1,3}(?:[   ,]\d{3})+|\d+(?:[.,]\d+)?)\s*(k|K|M)?\s*\$")
_MONTHLY = re.compile(r"par mois|/\s*mois|per month|a month|/\s*month|monthly|mensuel", re.I)
_CAPITAL = re.compile(r"\b(capital|j'ai|j’ai|i have|invest(ir|ed)?|placer|placé|start with)\b", re.I)
_TARGET = re.compile(r"\b(target|objectif|cible|reach|atteindre|goal|to have|pour avoir|obtenir|arriver à)\b", re.I)
_REQ_RETURN = re.compile(r"(rendement|return).{0,40}(n[ée]cessaire|requis|need|besoin|faut|required)|"
                         r"(need|besoin|faut|required).{0,40}(rendement|return)|quel rendement|what return", re.I)
_FACTS = re.compile(r"risk|risqu|volatil|tell me about|parle[- ]moi|comment .{0,20}(fait|comport)|how did|"
                    r"performance|perform|historique|history", re.I)
_CORR = re.compile(r"corr[ée]l|correlat|m[êe]me pari|same bet|move together|bougent ensemble|redondan|overlap", re.I)
_STRESS = re.compile(r"2022|krach|crash|crise|crisis|sell-off|chute", re.I)
_WHY = re.compile(r"\b(why|pourquoi)\b", re.I)


def _num(x: str) -> float:
    return float(re.sub(r"[   ]", "", str(x)).replace(",", "."))


def _amount(m: re.Match) -> float:
    raw, unit = m.group(1), m.group(2)
    digits = re.sub(r"[   ,]", "", raw) if re.search(r"[   ,]\d{3}\b", raw) else raw.replace(",", ".")
    return float(digits) * {"k": 1e3, "K": 1e3, "M": 1e6}.get(unit or "", 1)


def aliases() -> dict[str, str]:
    """ALIASES + the official names of the 31 assets when the starter CSVs are there."""
    out = dict(ALIASES)
    meta = market._meta()
    if meta is not None:
        for t, name in meta["name"].dropna().items():
            out.setdefault(str(name).lower(), t)
    return out


def find_assets(q: str) -> list[tuple[int, str]]:
    """(position, ticker) for every asset named in the question: tickers (any case for 3+ letters), company or
    fund names, and unknown UPPERCASE symbols (e.g. XSP) so the tools can say "no data"."""
    found: dict[int, str] = {}
    for name, t in sorted(aliases().items(), key=lambda kv: -len(kv[0])):
        for m in re.finditer(r"(?<![\w&])" + re.escape(name) + r"(?![\w&])", q, re.I):
            if not any(abs(m.start() - p) < len(name) for p in found):
                found[m.start()] = t
    known = {t.upper(): t for t in UNIVERSE}
    for m in re.finditer(r"[A-Za-z][A-Za-z.\-]{1,9}", q):
        w = m.group(0).rstrip(".")
        u = w.upper()
        if any(abs(m.start() - p) < 3 for p in found):
            continue
        t = known.get(u) or known.get(u + ".TO")
        if t and (w.isupper() or len(w) >= 3) and w.lower() not in {"and", "the", "for", "pour", "sur", "avec"}:
            found[m.start()] = t
        elif w.isupper() and 2 <= len(w) <= 6 and u not in _STOP and not t:
            found[m.start()] = u
    return sorted(found.items())


def parse(question: str, profile: dict) -> dict:
    """What the question asks, read with simple patterns (the Bedrock agent reads anything; this is the fallback)."""
    q = question or ""
    lang = "fr" if _FR.search(q) else "en"
    loss = _LOSS.search(q)
    assets = find_assets(q)
    pcts = [(m.start(), _num(m.group(1)) / 100) for m in _PCT.finditer(q) if not (loss and loss.start() <= m.start() <= loss.end())]
    positions: dict[str, float] = {}
    free = list(pcts)
    for pos, t in assets:  # each asset takes the nearest percentage still free
        if not free:
            break
        i = min(range(len(free)), key=lambda k: abs(free[k][0] - pos))
        if abs(free[i][0] - pos) <= 40:
            positions[t] = free.pop(i)[1]
    changes: dict[str, float] = {}
    if loss:
        changes["max_loss_pct"] = _num(loss.group(1))
    y = _YEARS.search(q)
    if y:
        changes["horizon_years"] = _num(y.group(1))
    amounts = list(_AMOUNT.finditer(q))
    target = None
    for m in amounts:
        around = q[max(0, m.start() - 40): m.end() + 25]
        v = _amount(m)
        if _MONTHLY.search(q[m.end(): m.end() + 25]):
            changes["monthly_contribution"] = v
        elif _CAPITAL.search(q[max(0, m.start() - 40): m.start()]) and not _TARGET.search(q[max(0, m.start() - 25): m.start()]):
            changes["capital"] = v
        elif _TARGET.search(around) or _REQ_RETURN.search(q):
            target = v
    intents = []
    if positions:
        intents.append("position")
    elif changes or target and not _REQ_RETURN.search(q):
        intents.append("profile")
    if _REQ_RETURN.search(q):
        intents.append("required_return")
    if target and "profile" in intents:
        changes["target_amount"] = target
    if _CORR.search(q) and len({t for _, t in assets}) >= 2 and not positions:
        intents.append("correlation")
    elif _FACTS.search(q) and assets and not positions:
        intents.append("facts")
    if _ADVICE.search(q) and not positions and "facts" not in intents and "correlation" not in intents:
        intents.append("advice")
    if _STRESS.search(q) and not positions and not assets:
        intents.append("stress")
    if _WHY.search(q) and not intents:
        intents.append("why")
    return {"lang": lang, "positions": positions, "changes": changes, "target": target, "intents": intents,
            "assets": [t for _, t in assets]}


# ---- writing the answer (English or French) ---------------------------------------------------------------

def _p(x: float, lang: str, nd: int = 1) -> str:
    s = f"{x * 100:.{nd}f}"
    return (s.replace(".", ",") + " %") if lang == "fr" else s + "%"


def _m(x: float, lang: str) -> str:
    s = f"{x:,.0f}"
    return (s.replace(",", " ") + " $") if lang == "fr" else s + " $"


def _req(r: dict, lang: str) -> str:
    sep = " et " if lang == "fr" else " and "
    nd = lambda w: 0 if abs(w * 100 - round(w * 100)) < 1e-6 else 1  # noqa: E731
    return sep.join(f"{_p(w, lang, nd(w))} {'dans' if lang == 'fr' else 'in'} {t}" for t, w in r.items())


READINGS_FR = {
    "out of reach": "hors de portée : même 100 % par année ne suffirait pas",
    "reached without": "atteint sans rendement : ce qui est investi couvre déjà la cible",
    "cash-like": "le cash a suffi sur les 12 derniers mois ; pas besoin de risque en actions pour ça",
    "needs more": "il faut plus que ce que le cash a rapporté : l'écart doit venir d'actifs plus risqués, avec leurs baisses",
}


def _part_position(r: dict, lang: str) -> str:
    fr = lang == "fr"
    if "error" in r:
        return (f"Je n'ai pas pu vérifier : {r['error']}." if fr else f"I could not check that: {r['error']}.")
    if r.get("not_assessable"):
        na = ", ".join(r["not_assessable"])
        return (f"Nous n'avons pas de données pour {na} parmi les actifs analysés, donc je ne peux pas l'évaluer."
                if fr else f"We have no data for {na} in the assets analysed, so I can't assess it.")
    a, f = r.get("as_asked") or {}, r.get("fits")
    ch = r.get("profile_changes") or {}
    cond = ""
    if "horizon_years" in ch:
        cond = (f" avec un horizon de {ch['horizon_years']:g} ans" if fr else f" with a {ch['horizon_years']:g}-year horizon")
    out = [(f"Avec {_req(r['request'], lang)} comme demandé{cond}, la pire baisse {period_label()} aurait été de "
            f"{_p(a['max_drawdown'], lang)}" if fr else
            f"With {_req(r['request'], lang)} as asked{cond}, the worst {period_label()} drop would have been "
            f"{_p(a['max_drawdown'], lang)}")
           + ((f", soit environ {_m(a['drawdown_cad'], lang)} pour une limite de {_m(a['loss_limit_cad'], lang)}" if fr
               else f", about {_m(a['drawdown_cad'], lang)} against your {_m(a['loss_limit_cad'], lang)} limit")
              if a.get("drawdown_cad") else "") + "."]
    n = len(a.get("fails", []))
    out.append((f"{n} règle(s) ne passeraient pas ({', '.join(a['fails'])})." if fr else
                f"{n} rule(s) would fail ({', '.join(a['fails'])}).") if n else
               ("Aucune règle ne serait enfreinte." if fr else "No rule would fail."))
    if f:
        held = _req(f["request_at"], lang)
        out.append(f"La version qui respecte vos limites contient {held}, avec une pire baisse de "
                   f"{_p(f['max_drawdown'], lang)}." if fr else
                   f"The version that fits your limits holds {held}, with a worst drop of {_p(f['max_drawdown'], lang)}.")
    else:
        for t, why in (r.get("why") or {}).items():
            out.append(f"Pas de version possible pour {t} : {why}." if fr else f"No version fits for {t}: {why}.")
    out.append("Le choix vous appartient." if fr else "The choice stays yours.")
    return " ".join(out)


def _part_profile(r: dict, lang: str, display: dict | None = None) -> str:
    fr = lang == "fr"
    if "error" in r:
        return (f"Je n'ai pas pu vérifier : {r['error']}." if fr else f"I could not check that: {r['error']}.")
    b, a = r["before"], r["after"]
    if "missing" in a:
        return ("Avec ce changement, le profil est incomplet : le conseiller poserait d'abord la question." if fr
                else "With that change the profile is incomplete; the advisor would ask first.")
    names = {"horizon_years": ("horizon", "horizon"), "max_loss_pct": ("perte acceptée", "accepted loss"),
             "target_amount": ("cible", "target"), "monthly_contribution": ("versement mensuel", "monthly contribution"),
             "capital": ("capital", "capital"), "withdrawal_share_3y": ("retraits sur 3 ans", "withdrawals within 3 years")}
    def val(k, v):
        if k == "horizon_years":
            return f"{v:g} {'ans' if fr else 'years'}"
        if k == "max_loss_pct":
            return _p(v / 100, lang, 0)
        if k == "withdrawal_share_3y":
            return _p(v, lang, 0)
        return _m(v, lang)
    art = {"horizon_years": "un", "max_loss_pct": "une", "target_amount": "une", "monthly_contribution": "un",
           "capital": "un", "withdrawal_share_3y": "des"}
    what = ", ".join((f"{art[k]} {names[k][0]} de {val(k, c['new'])}" if fr else
                      f"{'an' if k == 'max_loss_pct' else 'a'} {names[k][1]} of {val(k, c['new'])}")
                     for k, c in r.get("changes", {}).items())
    gb = {s["key"]: s for s in b.get("strategies", [])}
    label = lambda k: (display or {}).get(k, k)  # noqa: E731
    lines = [f"{label(s['key'])} : {_p(gb[s['key']]['growth'], lang, 0)} → {_p(s['growth'], lang, 0)} en actions" if fr else
             f"{label(s['key'])}: {_p(gb[s['key']]['growth'], lang, 0)} → {_p(s['growth'], lang, 0)} in stocks"
             for s in a["strategies"] if s["key"] in gb]
    text = (f"Avec {what}, votre limite de perte serait de {_p(a['loss_limit'], lang, 0)} (aujourd'hui "
            f"{_p(b['loss_limit'], lang, 0)}) et votre plancher défensif de {_p(a['defensive_floor'], lang, 0)} "
            f"(aujourd'hui {_p(b['defensive_floor'], lang, 0)})." if fr else
            f"With {what}, your loss limit would be {_p(a['loss_limit'], lang, 0)} (now {_p(b['loss_limit'], lang, 0)}) "
            f"and your defensive floor {_p(a['defensive_floor'], lang, 0)} (now {_p(b['defensive_floor'], lang, 0)}).")
    text += " " + ("; ".join(lines) + "." if lines else ("Les stratégies changeraient." if fr else "The strategies would change."))
    if "max_loss_pct" in r.get("changes", {}) and a["loss_limit"] == b["loss_limit"]:
        text += (" Votre limite de perte ne bouge pas : c'est la plus petite entre ce que vous acceptez et ce que votre "
                 "situation (horizon, épargne, revenus) permet, et c'est votre situation qui la plafonne." if fr else
                 " Your loss limit does not move: it is the smaller of what you accept and what your situation "
                 "(horizon, savings, income) allows, and your situation is what caps it.")
    if a["defensive_floor"] == b["defensive_floor"] and set(r.get("changes", {})) == {"max_loss_pct"}:
        text += (" La part en actions vient de votre horizon, pas de la perte que vous acceptez." if fr else
                 " The share in stocks is set by your horizon, not by the loss you accept.")
    return text


def _part_required(r: dict, lang: str) -> str:
    fr = lang == "fr"
    if "error" in r:
        return (f"Je n'ai pas pu le calculer : {r['error']}." if fr else f"I could not compute it: {r['error']}.")
    req = r.get("required")
    head = (f"Pour atteindre {_m(r['target_amount'], lang)} en {r['horizon_years']:g} ans (pour {_m(r['total_invested'], lang)} "
            f"investis), il faut " if fr else
            f"To reach {_m(r['target_amount'], lang)} in {r['horizon_years']:g} years ({_m(r['total_invested'], lang)} put in), "
            f"you need ")
    head += ("plus que ce qui est réaliste" if fr else "more than is realistic") if req is None else (
        f"environ {_p(req, lang)} par année" if fr else f"about {_p(req, lang)} a year")
    cash = ""
    if "cash_last_12m" in r:
        rate = r.get("boc_overnight")  # only when the macro file is loaded: leave it out otherwise (was a KeyError)
        cash = (f" ; le cash a rapporté {_p(r['cash_last_12m'], lang)} sur 12 mois"
                + (f" (taux directeur {_p(rate, lang, 2)})" if rate is not None else "") if fr else
                f"; cash paid {_p(r['cash_last_12m'], lang)} over 12 months"
                + (f" (policy rate {_p(rate, lang, 2)})" if rate is not None else ""))
    reading = r.get("reading", "")
    if fr:
        reading = next((v for k, v in READINGS_FR.items() if reading.startswith(k)), reading)
    return f"{head}{cash}. {reading[:1].upper() + reading[1:]}."


def _part_facts(r: dict, lang: str) -> str:
    fr = lang == "fr"
    if "error" in r:
        return (f"Je n'ai pas de données : {r['error'].split('.')[0]}." if fr else f"No data: {r['error'].split('.')[0]}.")
    out = []
    for a in r.get("assets", []):
        out.append(f"{a['ticker']} : pire baisse {period_label()} de {_p(a['max_drawdown'], lang)}, volatilité de "
                   f"{_p(a['ann_vol'], lang)} par année, {_p(a['return_2022'], lang)} en 2022" if fr else
                   f"{a['ticker']}: worst {period_label()} drop {_p(a['max_drawdown'], lang)}, volatility {_p(a['ann_vol'], lang)} "
                   f"a year, {_p(a['return_2022'], lang)} in 2022")
    tail = " Ce sont des faits passés, pas une prévision." if fr else " These are past facts, not a forecast."
    return "; ".join(out) + "." + tail


def _part_corr(r: dict, lang: str) -> str:
    fr = lang == "fr"
    if "error" in r:
        return (f"Je n'ai pas pu le vérifier : {r['error'].split('.')[0]}." if fr else f"I could not check: {r['error'].split('.')[0]}.")
    pairs = "; ".join(f"{p['a']}/{p['b']} {p['correlation']:.2f}".replace(".", "," if fr else ".") for p in r["pairs"])
    return (f"Corrélations des rendements quotidiens {period_label()} : {pairs}. Au-dessus d'environ 0,8, c'est en bonne partie "
            f"le même pari." if fr else
            f"Daily return correlations {period_label()}: {pairs}. Above about 0.8, it is largely the same bet.")


def _part_stress(r: dict, name: str, lang: str) -> str:
    fr = lang == "fr"
    if "error" in r:
        return (f"Je n'ai pas pu le vérifier : {r['error']}." if fr else f"I could not check: {r['error']}.")
    return (f"Pendant la baisse de 2022 (du {r['start']} au {r['end']}), « {name} » aurait fait {_p(r['cumulative_return'], lang)}, "
            f"avec un creux de {_p(r['deepest_drop'], lang)}." if fr else
            f"In the 2022 sell-off ({r['start']} to {r['end']}), '{name}' would have returned {_p(r['cumulative_return'], lang)}, "
            f"with a deepest drop of {_p(r['deepest_drop'], lang)}.")


def _part_why(r: dict, lang: str) -> str:
    fr = lang == "fr"
    names = {"loss_limit": ("limite de perte", "loss limit"), "defensive_floor": ("plancher défensif", "defensive floor"),
             "crypto": ("plafond crypto", "crypto cap"), "risk_level": ("niveau de risque", "risk level")}
    n = names.get(r.get("name"), (f"plafond pour {r.get('name')}", f"cap for {r.get('name')}"))[0 if fr else 1]
    v = r.get("value")
    vs = (str(v) if r.get("name") == "risk_level" else _p(v, lang, 0 if r.get("name") in names else 1)) \
        if isinstance(v, (int, float)) else "?"
    reasons = "; ".join(r.get("reasons", [])) or ("aucune raison écrite trouvée" if fr else "no written reason found")
    return (f"Votre {n} est de {vs}, parce que : {reasons}." if fr else f"Your {n} is {vs} because: {reasons}.")


HELP = {
    "en": ("I can check a position (\"what if I put part of my money in Tesla?\", with a percentage), several at once, "
           "a change to your profile (horizon in years, the loss you accept in %, a target or a monthly amount in $), "
           "the return your goal needs, an asset's past risk, whether two assets are the same bet, how your strategy "
           "did in the 2022 sell-off, or why a limit has its value."),
    "fr": ("Je peux vérifier une position (« et si je mettais une partie de mon argent dans Tesla ? », avec un "
           "pourcentage), plusieurs à la fois, un changement de profil (horizon en années, perte acceptée en %, cible "
           "ou versement mensuel en $), le rendement que votre objectif demande, le risque passé d'un actif, si deux "
           "actifs sont le même pari, le comportement de votre stratégie pendant la baisse de 2022, ou pourquoi une "
           "limite a sa valeur."),
}


# ---- conversation: concepts, the client's own results, follow-ups --------------------------------------------

# Written definitions (ours, no numbers): the offline analyst explains a concept from here, never from memory.
GLOSSARY = {
    "volatility": ("volatility|volatilité|volatile",
                   "Volatility measures how much an investment's value moves up and down from day to day. Higher "
                   "volatility means bigger swings in both directions, so the value you see at a given moment can be "
                   "far from where it was a few weeks before. It is one measure of risk among others, not the whole story."),
    "worst drop": ("worst drop|drawdown|max drawdown|pire baisse|baisse maximale",
                   "The worst drop (also called maximum drawdown) is the largest fall from a peak to a low point over a "
                   "period. It answers: if you had bought at the worst moment, how much would you have been down before "
                   "it recovered? We compare it with the loss you said you could live with."),
    "diversification": ("diversif",
                        "Diversification means spreading money across investments that don't all move together, so one "
                        "bad surprise doesn't sink everything. Owning many companies in one fund, plus bonds, is more "
                        "diversified than owning a few similar companies."),
    "etf": ("\\betf|index fund|fonds indiciel|fnb",
            "An index fund (ETF) is one investment that holds many companies or bonds at once, following a list such as "
            "the largest Canadian companies. It is a simple way to be diversified with low fees."),
    "bond": ("\\bbond|obligation",
             "A bond is a loan you make to a government or a company: it pays interest and gives the money back at a "
             "set date. Bonds usually move less than stocks, which is why they make up the safer, defensive part."),
    "stock": ("\\bstock|\\bshare\\b|\\baction\\b|equit",
              "A stock (or share) is a small piece of ownership in a company. Its value follows the company's prospects "
              "and the market's mood, so it can rise a lot over time but also fall sharply."),
    "dividend": ("dividend|dividende",
                 "A dividend is part of a company's profit paid out to its shareholders, usually every few months. It "
                 "is not guaranteed: a company can lower or stop it."),
    "correlation": ("correlat|corrélat",
                    "Correlation says whether two investments tend to move together. Close to one, they move almost in "
                    "step (largely the same bet); close to zero, their moves are unrelated, which helps diversification."),
    "loss limit": ("loss limit|limite de perte",
                   "Your loss limit is the largest drop we let your portfolio show in our tests. It is the smaller of the "
                   "drop you said you could accept and what your situation (horizon, savings, income) can carry."),
    "defensive": ("defensive|défensi",
                  "The defensive part is the money kept in steadier investments (short-term bonds, Canadian and U.S. "
                  "bonds, gold) so it is there when you need it and cushions the falls of the growth part."),
    "horizon": ("horizon",
                "Your horizon is how long until you need the money. The longer it is, the more time there is to wait "
                "for markets to recover after a fall, so the larger the share in stocks can be."),
    "cvar": ("cvar|expected shortfall|tail",
             "Conditional value at risk (CVaR) is the average loss on the worst days. It describes how bad a bad day "
             "usually is, not just how often bad days happen."),
    "crypto": ("crypto|bitcoin|ether",
               "Crypto-assets such as Bitcoin are digital tokens whose price can swing far more than stocks; in our data "
               "they had the deepest falls. We include them only if you ask and your limits allow it."),
    "gic": ("\\bgic|\\bcpg|guaranteed investment",
            "A GIC (guaranteed investment certificate) is a deposit that pays a fixed interest for a set time, with the "
            "capital guaranteed. It doesn't move with markets."),
    "through the etfs": ("look[- ]?through|through the etf|via les fnb|via les etf",
                         "Counting through the ETFs means opening each fund to see the companies inside. Owning a "
                         "company directly and again inside a fund can add up to more than it looks."),
    "simulation": ("simulation|advice|conseil|real money",
                   "This is a simulation: it shows how strategies would have behaved with past data and explains the "
                   "rules applied. It is not personal financial advice, and nothing is bought or sold."),
}
_CONCEPT_Q = re.compile(r"what (is|are|does|do)|what's|whats|explain|define|meaning|mean\b|c'est quoi|qu'est-ce|que veut dire|"
                        r"définition|definition|explique|signifie|how does .* work", re.I)
_RESULTS_Q = re.compile(r"my result|my strateg|my portfolio|mes résultats|mes stratégies|mon portefeuille|which strateg|"
                        r"quelle stratégie|compare|comparer|summar|résum|recommend|the safest|la plus s[ûu]re|"
                        r"why (this|these|that) strateg|pourquoi (cette|ces) stratég|explain (my|the) (result|strateg)", re.I)
_FOLLOW_ON = re.compile(r"^\s*(and|et|what about|how about|same|même|pareil|instead|plutôt|ok|then|alors|with|avec)\b", re.I)


def concept(question: str) -> str | None:
    if not _CONCEPT_Q.search(question or ""):
        return None
    return next((k for k, (pat, _) in GLOSSARY.items() if re.search(pat, question, re.I)), None)


def with_context(q: dict, question: str, history: list[dict] | None, profile: dict) -> dict:
    """Follow-ups that lean on the previous question: "and with 5%?" reuses the last asset, "what about NVDA?" the
    last share, "and with a 15-year horizon?" the last position. Only from what the client asked before."""
    hist = [h for h in (history or [])[-6:] if h.get("question")]
    prev = with_context(parse(hist[-1]["question"], profile), hist[-1]["question"], hist[:-1], profile) if hist else None
    if not prev or q["intents"] and "position" in q["intents"]:
        return q
    short = len(question.split()) <= 7 or _FOLLOW_ON.search(question)
    if not short:
        return q
    pct = [m for m in _PCT.finditer(question)]
    if pct and not q["assets"] and prev["positions"]:                       # "and with 5%?"
        q = {**q, "positions": {t: _num(pct[0].group(1)) / 100 for t in prev["positions"]}}
    elif q["assets"] and not pct and prev["positions"] and not q["intents"]:  # "what about NVDA?"
        w = next(iter(prev["positions"].values()))
        q = {**q, "positions": {t: w for t in dict.fromkeys(q["assets"])}}
    elif q["changes"] and not q["positions"] and prev["positions"]:          # "and with a 15-year horizon?"
        q = {**q, "positions": dict(prev["positions"])}
    if q["positions"]:
        q = {**q, "intents": ["position"] + [i for i in q["intents"] if i not in ("position", "profile")],
             "changes": {**{k: v for k, v in prev["changes"].items() if k not in q["changes"]}, **q["changes"]}}
    return q


def _mock(question: str, rec: critic.Recorder, tools: dict, profile: dict | None = None,
          strategies: list[dict] | None = None, history: list[dict] | None = None) -> dict:
    """Deterministic analyst: reads the question (parse), calls the same tools, writes the answer from their results,
    in the question's language. Several requests in one question are checked together."""
    profile, strategies = profile or {}, strategies or []
    q = with_context(parse(question, profile), question, history, profile)
    lang, parts, ev = q["lang"], [], []
    display = {s["key"]: s["name"] for s in strategies}
    term = concept(question)
    if term and not q["positions"] and not q["changes"]:
        return {"answer": GLOSSARY[term][1], "evidence": []}

    def call(name, kwargs):
        r = rec.call(tools[name], name, kwargs)
        ev.append(r["call_id"]) if "call_id" in r else None
        return r

    if "position" in q["intents"]:
        (t, w), *rest = q["positions"].items()
        kw = {"ticker": t, "weight": w}
        if rest:
            kw["also"] = dict(rest)
        if q["changes"]:
            kw["profile_changes"] = dict(q["changes"])
        if q["changes"]:  # first what the change alone does, then the position under it
            (f, v), *more = q["changes"].items()
            parts.append(_part_profile(call("what_if_profile", {"field": f, "value": v, **({"also": dict(more)} if more else {})}), lang, display))
        parts.append(_part_position(call("what_if_position", kw), lang))
    elif "profile" in q["intents"] and q["changes"]:
        (f, v), *more = q["changes"].items()
        parts.append(_part_profile(call("what_if_profile", {"field": f, "value": v, **({"also": dict(more)} if more else {})}), lang, display))
    if "required_return" in q["intents"]:
        target = q["target"] or profile.get("target_amount")
        if not target:
            parts.append("Pour calculer le rendement nécessaire, il me faut votre montant cible, en $." if lang == "fr"
                         else "To compute the return you need, I need your target amount, in $.")
        else:
            parts.append(_part_required(call("required_return", {
                "capital": q["changes"].get("capital", profile.get("capital") or 0),
                "horizon_years": q["changes"].get("horizon_years", profile.get("horizon_years") or 0),
                "target_amount": target,
                "monthly_contribution": q["changes"].get("monthly_contribution", profile.get("monthly_contribution") or 0)}), lang))
    if "correlation" in q["intents"]:
        parts.append(_part_corr(call("correlation_between", {"tickers": list(dict.fromkeys(q["assets"]))[:10]}), lang))
    if "advice" in q["intents"]:
        parts.append("Je ne dis pas d'acheter ou de vendre : c'est une simulation, et le choix vous appartient." if lang == "fr"
                     else "I don't say buy or sell: this is a simulation, and the choice stays yours.")
        known = [t for t in dict.fromkeys(q["assets"]) if t in UNIVERSE]
        if known:
            parts.append(("Voici les faits passés : " if lang == "fr" else "Here are the past facts: ")
                         + _part_facts(call("asset_facts", {"tickers": known[:5]}), lang))
        parts.append(("Je peux aussi vérifier ce que donnerait une position précise dans cet actif (avec un pourcentage)."
                      if lang == "fr" else "I can also check a precise position in that asset (give a percentage).")
                     if known else HELP[lang])
    if "facts" in q["intents"]:
        parts.append(_part_facts(call("asset_facts", {"tickers": list(dict.fromkeys(q["assets"]))[:5]}), lang))
    if "stress" in q["intents"] and strategies:
        s = strategies[0]
        parts.append(_part_stress(call("stress_test", {"weights": s["weights"]}), s["name"], lang))
    if "why" in q["intents"]:
        name = ("crypto" if re.search(r"crypto|bitcoin", question, re.I) else
                next((t for t in q["assets"] if t in UNIVERSE), None) or
                ("loss_limit" if re.search(r"loss|perte|limit", question, re.I) else "defensive_floor"))
        parts.append(_part_why(call("limit_reason", {"name": name}), lang))
    if not parts and _RESULTS_Q.search(question) and strategies:
        parts.append(_part_results(call("results_overview", {}), lang))
    if not parts:
        return {"answer": (("Je ne suis pas sûr d'avoir compris. " if lang == "fr" else "I'm not sure I understood. ")
                           + HELP[lang]), "evidence": []}
    return {"answer": "\n\n".join(parts), "evidence": ev}


def _part_results(r: dict, lang: str) -> str:
    """The client's own results as a short Markdown table, from results_overview (every number from the tool)."""
    fr = lang == "fr"
    rows = []
    for s in r.get("strategies", []):
        rows.append(f"| {s['name']} | {_p(s['growth'], lang, 0)} | {_p(s['max_drawdown'], lang)} | "
                    f"{_p(s['return_2022'], lang)} | " + (_p(s['prob_loss'], lang, 0) if s.get('prob_loss') is not None else "–")
                    + " |")
    head = ("| Stratégie | Actions | Pire baisse | 2022 | Chance de perte* |\n|---|---|---|---|---|" if fr else
            "| Strategy | Stocks | Worst drop | 2022 | Chance of a loss* |\n|---|---|---|---|---|")
    lim = (f"Votre limite de perte est de {_p(r['loss_limit'], lang, 0)} et au moins {_p(r['defensive_floor'], lang, 0)} "
           f"reste en placements défensifs." if fr else
           f"Your loss limit is {_p(r['loss_limit'], lang, 0)} and at least {_p(r['defensive_floor'], lang, 0)} stays in "
           f"defensive investments.")
    foot = ("*Chance de finir sous le montant investi, sans supposer que les rendements passés se répètent." if fr else
            "*Chance of ending below what you put in, without assuming past returns repeat.")
    return lim + "\n\n" + head + "\n" + "\n".join(rows) + "\n\n" + foot


# ---- code enforces -------------------------------------------------------------------------------------

BANNED = re.compile(
    r"\b(you should (buy|sell|invest)|i (would )?recommend (buying|selling|investing)|buy now|sell now|"
    r"will (return|earn|gain|rise|go up|outperform|double)|guarantee[ds]?|risk[- ]free profit|"
    r"vous devriez (acheter|vendre|investir)|je (vous )?recommande d['’](acheter|investir)|je (vous )?recommande de vendre|"
    r"achetez|vendez|il faut (acheter|vendre)|(va|vont) (rapporter|monter|doubler|grimper)|"
    r"rendement garanti|garanti(e|es|s)?|sans risque)\b", re.I)
_THOUSANDS = re.compile(r"(?<=\d)[,   ](?=\d{3}(?!\d))")
_COUNT = re.compile(r"\b(\d{1,2})\s+(?:rule\(s\)|rules?|règle\(s\)|règles?|checks?|contrôles?|vérifications?|"
                    r"strateg(?:y|ies)|stratégies?|holdings?|positions?|assets?|actifs?)\b", re.I)
_YEAR = re.compile(r"(?<![\d.,])((?:19|20)\d{2})(?![\d.,])")
def data_years() -> set[int]:
    """Years inside the data window (2021-2026 on the starter pack, from 2004 with `make data-long`, decision #31)."""
    p = period()
    return set(range(int(p[0][:4]), int(p[1][:4]) + 1)) if p else set(range(2021, 2027))


def _normalize(text: str) -> str:
    """One way to write numbers: 106 121 $ / 106,121 $ → 106121; 13,7 % → 13.7%; − → -."""
    t = text.replace("−", "-")
    t = _THOUSANDS.sub("", t)
    t = re.sub(r"(?<=\d),(?=\d{1,2}(?!\d))", ".", t)
    return re.sub(r"(?<=\d)[\s  ]+%", "%", t)


def _labeled(x, labels: frozenset, known: set) -> list[tuple[float, frozenset]]:
    """Every number in a tool result, with the assets / strategies it belongs to (from keys like key, ticker, a, b,
    or from a dict keyed by ticker). Numbers outside any such context have no label (client-wide facts)."""
    if isinstance(x, bool):
        return []
    if isinstance(x, (int, float)):
        return [(float(x), labels)]
    if isinstance(x, str):
        return [(v, labels) for v in critic._result_numbers(x)]
    if isinstance(x, (list, tuple)):
        return [n for v in x for n in _labeled(v, labels, known)]
    if isinstance(x, dict):
        own = labels | {v for k, v in x.items() if k in ("key", "name", "ticker", "strategy", "a", "b")
                        and isinstance(v, str) and v in known}
        return [n for k, v in x.items() for n in _labeled(v, own | ({k} if k in known else set()), known)]
    return []


_RULE_ID = re.compile(r"^[CDEFG]\d{1,2}b?$")


def _counts(x, out: dict | None = None) -> dict[str, set[int]]:
    """How many of each KIND of thing the results list: rules (lists of check ids like G4, C3b), strategies (lists of
    dicts with a key), assets (dicts or lists of tickers). A "9 rules" claim must match a list of rules, not any list."""
    out = out if out is not None else {"rules": set(), "strategies": set(), "assets": set()}
    known = {t for t in UNIVERSE}
    if isinstance(x, dict):
        if x and all(k in known or k.upper() in known for k in x):
            out["assets"].add(len(x))
        for v in x.values():
            _counts(v, out)
    elif isinstance(x, (list, tuple)):
        if x and all(isinstance(v, str) and _RULE_ID.match(v) for v in x):
            out["rules"].add(len(x))
        elif x and all(isinstance(v, dict) and "key" in v for v in x):
            out["strategies"].add(len(x))
        elif x and all(isinstance(v, str) and v in known for v in x):
            out["assets"].add(len(x))
        for v in x:
            _counts(v, out)
    return out


def _kind(noun: str) -> str:
    n = noun.lower()
    if n.startswith(("rule", "règle", "check", "contrôle", "vérification")):
        return "rules"
    if n.startswith(("strateg", "stratég")):
        return "strategies"
    return "assets"


def entity_names(strategies: list[dict] | None = None) -> dict[str, str]:
    """Surface form (lower case) → label, for the attribution check: tickers, company names, strategy names."""
    out = {t.lower(): t for t in UNIVERSE}
    out.update({t.lower().removesuffix(".to"): t for t in UNIVERSE if t.endswith(".TO")})
    out.update({k: v for k, v in aliases().items() if len(k) > 3})
    for key, name in (("core", "Broad core"), ("income", "Income / dividends"), ("growth", "Growth tilt")):
        out[key] = key
        out[name.lower()] = key
    for s in strategies or []:
        out[s["key"]] = s["key"]
        out[s["name"].lower()] = s["key"]
    return out


def validate(ans: dict, calls: list[dict], names: dict[str, str] | None = None) -> tuple[str, list[str]]:
    """'valid' or 'replaced: <why>'. Checks, in order: cited calls exist; every number is in a cited result
    (thousands separators, French decimals and spaces before % understood); counts of rules/strategies match a
    count in the results; years are inside the data or in the results; a number written next to an asset or a
    strategy belongs to THAT asset or strategy (or is client-wide); no advice or forecast (English and French)."""
    by_id = {c["call_id"]: c for c in calls}
    text, ev = (ans or {}).get("answer", ""), (ans or {}).get("evidence", []) or []
    if not isinstance(text, str) or not text.strip():
        return "replaced: empty answer", []
    if any(e not in by_id for e in ev):
        return "replaced: cites a tool call it did not make", []
    if BANNED.search(text):
        return "replaced: advice or forecast wording", []
    plain = _normalize(text)
    results = [by_id[e]["result"] for e in ev]
    pool = [n for r in results for n in critic._result_numbers(r)]
    missing = [t for t in critic._claim_numbers(plain) if not critic._backed(t, pool)]
    if missing:
        return f"replaced: unbacked number(s) {', '.join(missing)}", missing
    counts = {"rules": set(), "strategies": set(), "assets": set()}
    for r in results:
        _counts(r, counts)
    wrong = [m.group(0) for m in _COUNT.finditer(plain)
             if int(m.group(1)) not in counts[_kind(m.group(0).split(None, 1)[1])]]
    if wrong:
        return f"replaced: count(s) not in the results: {', '.join(wrong)}", wrong
    years_ok = data_years() | {int(y) for r in results for y in re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", json.dumps(r, default=str))}
    bad_years = [y for y in _YEAR.findall(plain) if int(y) not in years_ok]
    if bad_years:
        return f"replaced: year(s) outside the data: {', '.join(bad_years)}", bad_years
    names = names or entity_names()
    known = set(names.values())
    labeled = []
    for e in ev:
        c = by_id[e]
        a = c.get("args") or {}
        base = {v for v in [a.get("ticker"), a.get("strategy"), *(a.get("tickers") or []), *(a.get("also") or {}),
                            *((a.get("weights") or {}) if c["tool"] != "stress_test" else [])] if isinstance(v, str) and v in known}
        labeled += _labeled(c["result"], frozenset(base), known)
    misattributed = []
    for seg in re.split(r"(?<=[.;!?])\s+|\n", plain):
        ents = {lab for surf, lab in names.items() if re.search(r"(?<![\w.&])" + re.escape(surf) + r"(?![\w&])", seg, re.I)}
        if not ents:
            continue
        for tok in critic._claim_numbers(seg):
            cands = [labs for v, labs in labeled if critic._backed(tok, [v])]
            if cands and not any((not labs) or (labs & ents) for labs in cands):
                misattributed.append(f"{tok} ({'/'.join(sorted(ents))})")
    if misattributed:
        return f"replaced: number(s) attributed to the wrong asset or strategy: {', '.join(misattributed)}", misattributed
    return "valid", []


# ---- entry points --------------------------------------------------------------------------------------

MAX_TURNS = 6  # previous turns the agent sees (questions and answers, without the disclaimer)


def _conversation(history: list[dict] | None) -> str:
    turns = (history or [])[-MAX_TURNS:]
    return "\n".join(f"Client: {h['question']}\nAnalyst: {strip_disclaimer(h.get('answer', ''))}" for h in turns)


def strip_disclaimer(text: str) -> str:
    return (text or "").replace(" " + DISCLAIMER, "").replace(" " + DISCLAIMER_FR, "").strip()


def _run_agent(question: str, f: dict, rec: critic.Recorder, tools: list, history: list[dict] | None = None) -> dict:
    from strands import Agent, tool
    from strands.models import BedrockModel

    model = BedrockModel(model_id=critic.model_id(), region_name=os.getenv("AWS_REGION", "us-east-1"), max_tokens=4000)
    agent = Agent(model=model, system_prompt=SYSTEM_PROMPT, tools=[tool(rec.wrap(t)) for t in tools],
                  callback_handler=None)
    convo = _conversation(history)
    text = str(agent("FACTS:\n" + json.dumps(f, ensure_ascii=False, default=str)
                     + (f"\n\nCONVERSATION SO FAR (oldest first):\n{convo}" if convo else "")
                     + "\n\nQUESTION:\n" + question))
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("no JSON object in the answer")
    return json.loads(text[a:b + 1])


def _hash(question: str, f: dict, history: list[dict] | None = None) -> str:
    prev = [h.get("question", "").strip().lower() for h in (history or [])[-2:]]  # same question in a new context ≠ same answer
    return hashlib.sha256(json.dumps([PROMPT_VERSION, critic.model_id(), question.strip().lower(), f] + ([prev] if prev else []),
                                     sort_keys=True, default=str).encode()).hexdigest()[:16]


def ask(question: str, res: dict, profile: dict, provider: str | None = None, rets=None, holdings=None,
        history: list[dict] | None = None) -> dict:
    """{answer, status, evidence, tool_calls, source, model, note, question}. Never raises on agent failure.
    history: the conversation so far ([{question, answer}], oldest first): the agent sees the last turns; the
    offline analyst reuses the last asset or share for short follow-ups ("and with 5%?")."""
    provider = (provider or os.getenv("LLM_PROVIDER", "mock")).lower()
    if holdings is None:
        from ..holdings import holdings as load_holdings
        holdings = load_holdings()
    f = critic.facts(res.get("strategies") or [], res["limits"], profile)
    h = _hash(question, f, history)
    tools = make_tools(res, profile, rets=rets, holdings=holdings)
    ans = calls = None
    src, note, model = "mock", "mock mode", ""
    for p in (DEMO_CACHE / f"{h}.json", LOCAL_CACHE / f"{h}.json"):
        if p.exists():
            c = json.loads(p.read_text())
            ans, calls, src, note, model = c["answer"], c["tool_calls"], f"cache ({p.parent.name})", "", c["model"]
            break
    with critic._tool_returns(rets):
        if ans is None and provider == "bedrock":
            rec = critic.Recorder(MAX_CALLS)
            try:
                ans = _run_agent(question, f, rec, tools, history)
                calls, src, note, model = rec.calls, "bedrock", "", critic.model_id()
                if validate(ans, calls, entity_names(res.get("strategies")))[0] == "valid":  # only valid answers are cached
                    LOCAL_CACHE.mkdir(parents=True, exist_ok=True)
                    (LOCAL_CACHE / f"{h}.json").write_text(json.dumps(
                        {"model": model, "prompt_version": PROMPT_VERSION, "question": question, "answer": ans,
                         "tool_calls": calls, "created": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                        ensure_ascii=False, indent=1, default=str))
            except Exception as e:  # noqa: BLE001 — any AWS/Strands/parse error → deterministic analyst
                ans, note = None, f"agent unavailable ({type(e).__name__}: {e})"[:300]
        names = entity_names(res.get("strategies"))
        status = validate(ans, calls or [], names)[0] if ans is not None else None
        if status is not None and status != "valid":   # the model's answer broke a rule: say so, answer deterministically
            note = (note + "; " if note else "") + f"model answer {status}"
            src = f"mock ({src} answer {status})"
        if status != "valid":
            rec = critic.Recorder(MAX_CALLS)
            ans = _mock(question, rec, {t.__name__: t for t in tools}, profile, res.get("strategies"), history)
            calls = rec.calls
            status = validate(ans, calls, names)[0]
            if status != "valid":  # even the deterministic answer broke a rule: say only what needs no number
                note = (note + "; " if note else "") + f"deterministic answer {status}"
                ans, status = {"answer": HELP[parse(question, profile)["lang"]], "evidence": []}, "valid"
    disclaimer = DISCLAIMER_FR if parse(question, profile)["lang"] == "fr" else DISCLAIMER
    return {"question": question, "answer": ans["answer"].rstrip() + " " + disclaimer, "status": status,
            "evidence": ans.get("evidence", []), "tool_calls": calls, "source": src, "model": model, "note": note,
            "facts_hash": h}


def save_demo(a: dict) -> str:
    """Copy a Bedrock answer into the committed demo cache (the demo replays it offline)."""
    if a["source"] != "bedrock" and not a["source"].startswith("cache"):
        raise ValueError(f"nothing to save: the answer came from the deterministic analyst ({a['note']})")
    DEMO_CACHE.mkdir(parents=True, exist_ok=True)
    p = DEMO_CACHE / f"{a['facts_hash']}.json"
    p.write_text(json.dumps({"model": a["model"], "prompt_version": PROMPT_VERSION, "question": a["question"],
                             "answer": {"answer": a["answer"].replace(" " + DISCLAIMER, "").replace(" " + DISCLAIMER_FR, ""),
                                        "evidence": a["evidence"]},
                             "tool_calls": a["tool_calls"],
                             "created": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                            ensure_ascii=False, indent=1, default=str))
    return str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)


def short(call: dict) -> str:
    """One readable line per tool call for the trace (the what-ifs; the rest as the Critic shows them)."""
    a, r = call["args"], call["result"]
    if call["tool"] == "what_if_position" and isinstance(r, dict) and "error" not in r:
        t = next(iter(r.get("request") or {"?": 0}))
        if r.get("not_assessable"):
            return f"{call['call_id']} what_if_position({t}) → no data"
        asked, fits = r.get("as_asked") or {}, r.get("fits")
        out = f"as asked {asked.get('verdict')} ({', '.join(asked.get('fails', [])) or 'nothing fails'})"
        return (f"{call['call_id']} what_if_position({t} {a.get('weight', 0):.0%}) → {out}"
                + (f"; fits at {fits['request_at'][t]:.1%}" if fits else ""))
    if call["tool"] == "what_if_profile" and isinstance(r, dict) and "error" not in r:
        g = lambda v: ", ".join(f"{s['key']} {s['growth']:.0%}" for s in v.get("strategies", []))
        return (f"{call['call_id']} what_if_profile({a.get('field')} {r.get('old')} → {a.get('value')}) → "
                f"stocks {g(r['before'])} → {g(r['after'])}")
    return critic._short(call)


def add_to_trace(res: dict, profile: dict, question: str, provider: str | None = None, rets=None,
                 holdings=None) -> dict:
    """Answer a follow-up on a pipeline result and append Client → Analyst → Client to res['trace']."""
    a = ask(question, res, profile, provider, rets=rets, holdings=holdings)
    tr = res.get("trace")
    if tr is not None:
        tr.step("Client", "Analyst", f"follow-up: {question}")
        calls = "; ".join(short(c) for c in a["tool_calls"]) or "no tool call"
        tr.step("Analyst", "Client", f"[{a['source']}] {a['status']}; tools: {calls}",
                output={k: a[k] for k in ("answer", "evidence", "status", "source", "model", "note")})
    res.setdefault("followups", []).append(a)
    return a
