"""Profiler: profile (facts the client gave) → limits (conclusions, each with its reason).

Deterministic on purpose: the same answers always give the same limits. The LLM is only used upstream,
to pull these facts out of free text (extractor); it never sets a score. See notes/contract.md.
"""

from __future__ import annotations

from functools import lru_cache

from .rules import (BEGINNER_MAX_KNOWLEDGE, CRYPTO, ESSENTIAL_FIELDS, LOSS_SHARE_ONE_COMPANY, MIN_COMPANIES, RISK_LEVELS,
                    SAFETY_MIN_DEFENSIVE, STOCKS, UNIVERSE, company_cap, excluded_tickers, horizon_max_growth)

LEVEL_FROM_DECLARED = {"none": 1, "basic": 2, "intermediate": 3, "advanced": 4}
QUIZ_CAP = {0: 2, 1: 3, 2: 4, 3: 5}  # right answers out of 3 → highest knowledge score allowed
REACTION = {"sell_all": 1, "sell_some": 2, "hold": 4, "buy_more": 5}


def knowledge_score(p: dict) -> tuple[int, list[str]]:
    lvl = p.get("knowledge_level")
    s = LEVEL_FROM_DECLARED.get(lvl, 1)
    why = [f"declared knowledge '{lvl}' → {s}"]
    if s < 5 and (p.get("years_experience") or 0) >= 5 and set(p.get("products_held") or []) & {"stocks", "etfs"}:
        s += 1
        why.append(f"5+ years investing in stocks/ETFs → {s}")
    quiz = p.get("quiz_correct")
    if quiz is not None and s > QUIZ_CAP[quiz]:
        s = QUIZ_CAP[quiz]
        why.append(f"quiz {quiz}/3 caps knowledge at {s}")
    ev = expected_value_check(p)
    if ev and not ev["correct"] and s > EV_WRONG_CAP:
        s = EV_WRONG_CAP
        why.append(f"expected-value question answered {ev['answer']:g}% (it is {ev['expected']:g}%) → knowledge "
                   f"capped at {s}")
    return s, why


# ---- KYC bets (decision #40): Joud's questionnaire (dh.kyc) as a cross-check, never a limit ----------------
EV_WRONG_CAP = 3          # one wrong answer on expected value: at most "intermediate"
EV_TOLERANCE = 0.5        # percentage points


def expected_value_check(p: dict) -> dict | None:
    """'This investment ends the year at +25% or -5% with equal chances: what return do you expect on average?'
    (dh.kyc's first bet). Right answer: +10%. Tests whether the client understands average vs risk."""
    ans = p.get("ev_answer_pct")
    if ans is None:
        return None
    from ..kyc import BETS
    exp = round(100 * BETS[0].mean, 2)
    return {"answer": float(ans), "expected": exp, "correct": abs(float(ans) - exp) <= EV_TOLERANCE}


def kyc_check(p: dict, tolerance: int) -> dict | None:
    """Risk aversion A from the three KYC bets (dh.kyc.score) compared with the tolerance from the other answers.
    Cross-check only: the limits don't change. If the bets say the client is MORE cautious than their other
    answers, the trace flags it for clarification, as an advisor would (KYC: conflicting answers → clarify)."""
    bets = p.get("kyc_bets")
    ev = expected_value_check(p)
    if not bets and not ev:
        return None
    out = {"expected_value": ev, "flags": []}
    if bets:
        from .. import kyc
        try:
            sc = kyc.score({**bets, "loss_reaction": p.get("loss_reaction")})
        except ValueError as e:
            out["error"] = str(e)
            sc = None
        if sc:
            a = sc["A"]
            lo, hi = (4, 5) if a < kyc.AVERAGE_BAND[0] else (3, 3) if a <= kyc.AVERAGE_BAND[1] else (1, 2)
            out.update(A=a, band=sc["band"], A_by_bet=sc["A_by_bet"], implied_tolerance=[lo, hi],
                       tolerance=tolerance, agrees=lo <= tolerance <= hi, reasons=sc["reasons"])
            out["flags"] += [f"KYC bets: {f}" for f in sc["flags"]]
            if tolerance > hi:
                out["flags"].append(f"KYC bets give A = {a:.1f} ({sc['band']}), more cautious than the tolerance "
                                    f"{tolerance} from the other answers: to clarify with the client")
    msg = []
    if "A" in out:
        rel = ("agree with" if out["agrees"] else "are more cautious than" if tolerance > out["implied_tolerance"][1]
               else "are bolder than")
        msg.append(f"KYC bets: A = {out['A']:.1f} ({out['band']}), they {rel} tolerance {tolerance}")
    if ev:
        msg.append(f"expected-value question {'right' if ev['correct'] else 'wrong'} ({ev['answer']:g}% vs "
                   f"{ev['expected']:g}%)")
    out["message"] = "; ".join(msg) + "; cross-check only, limits unchanged" + (
        " (flagged: " + "; ".join(out["flags"]) + ")" if out["flags"] else "")
    return out


def _loss_score(pct: float) -> int:
    return 1 if pct <= 10 else 2 if pct <= 15 else 3 if pct <= 25 else 4 if pct <= 35 else 5


def risk_tolerance(p: dict) -> tuple[int, list[str]]:
    a, b = REACTION[p["loss_reaction"]], _loss_score(p["max_loss_pct"])
    return min(a, b), [f"reaction to a 20% drop '{p['loss_reaction']}' → {a}",
                       f"max acceptable loss {p['max_loss_pct']}% → {b}",
                       f"tolerance = the more cautious of the two → {min(a, b)}"]


def _horizon_score(y: float) -> int:
    return 1 if y < 3 else 2 if y < 5 else 3 if y < 10 else 4 if y < 15 else 5


def risk_capacity(p: dict) -> tuple[int, list[str]]:
    c = _horizon_score(p["horizon_years"])
    why = [f"horizon {p['horizon_years']} years → {c}"]
    wd = p.get("withdrawal_share_3y") or 0
    for cond, text in [
        (p["emergency_fund_months"] < 3, f"emergency fund {p['emergency_fund_months']} months (< 3)"),
        (p["income_stability"] == "uncertain", "uncertain income"),
        (wd >= 0.25, f"{wd:.0%} may be withdrawn within 3 years"),
    ]:
        if cond and c > 1:
            c -= 1
            why.append(f"{text} → {c}")
    if p["objective"] == "safety_cushion" and c > 1:
        c = 1
        why.append("objective is a safety cushion → 1")
    return c, why


def missing_fields(p: dict) -> list[str]:
    return [f for f in ESSENTIAL_FIELDS if p.get(f) is None]


@lru_cache(maxsize=1)
def _data_summary() -> tuple:
    """(ticker, worst drop in CAD over its own data, 'YYYY-YYYY' window) per asset (market data, Joud).
    Empty if the data isn't loaded."""
    try:
        from .market import asset_summary
        a = asset_summary()
        return tuple((t, float(r["max_drawdown"]), f"{str(r['start'])[:4]}-{str(r['end'])[:4]}")
                     for t, r in a.iterrows() if r["max_drawdown"] == r["max_drawdown"])
    except (Exception, SystemExit):  # noqa: BLE001 — no data: caps assume a company can lose 100% (stricter)
        return ()


def worst_drops() -> dict[str, float]:
    return {t: dd for t, dd, _ in _data_summary()}


def drop_window(ticker: str | None = None) -> str:
    """The years an asset's worst drop was measured on (its own history), else the data window."""
    from ..data import period_label
    return next((w for t, dd, w in _data_summary() if t == ticker), None) or period_label()


def _caps(loss_limit: float, max_growth: float, share: float, drops: dict) -> tuple[dict, dict, float, str]:
    """Per-company caps {ticker: (cap, binding)}, plus the crypto cap and what binds it (decision #24)."""
    caps = {t: company_cap(loss_limit, drops.get(t), max_growth, share) for t in STOCKS}
    crypto_dd = min((drops[t] for t in CRYPTO if t in drops), default=None)
    cap_c, why_c = company_cap(loss_limit, crypto_dd, max_growth, share)
    return {t: c for t, (c, _) in caps.items()}, {t: b for t, (_, b) in caps.items()}, cap_c, why_c


def derive_limits(p: dict, drops: dict | None = None) -> dict:
    """The Profiler's output. If essentials are missing, returns only `missing` (ask, don't guess).
    drops = {ticker: worst drop over its data}; None → from the market data ({} → assume -100% for every asset)."""
    missing = missing_fields(p)
    if missing:
        return dict(missing=missing, flags=[f"missing essential info: {', '.join(missing)}"], reasons=[])

    tol, r_tol = risk_tolerance(p)
    cap, r_cap = risk_capacity(p)
    know, r_know = knowledge_score(p)
    level = min(tol, cap)
    t = dict(RISK_LEVELS[level])
    reasons = r_tol + r_cap + [f"risk level = lower of tolerance {tol} and capacity {cap} → {level} ({t['name']})"]
    reasons += r_know

    beginner = know <= BEGINNER_MAX_KNOWLEDGE

    # Loss limit (decision #17, formula = assumption #19): the smaller of what the client says they'd accept
    # (tolerance) and what their situation allows (capacity, via the capacity level's drawdown).
    tol_loss = p["max_loss_pct"] / 100
    cap_loss = RISK_LEVELS[cap]["max_drawdown"]
    loss_limit = min(tol_loss, cap_loss)
    source = "tolerance" if tol_loss <= cap_loss else "capacity"
    t["max_drawdown"] = loss_limit
    capital = p.get("capital")
    loss_cad = round(capital * loss_limit) if capital else None
    reasons.append(f"loss limit = smaller of the drop you'd accept ({tol_loss:.0%}) and what your situation allows "
                   f"(capacity {cap}: {cap_loss:.0%}) → {loss_limit:.0%}"
                   + (f", i.e. {loss_cad:,} $ on {capital:,.0f} $" if loss_cad else ""))

    # Defensive floor = the strictest of: money needed within 3 years (#17), the horizon cap (#22: the sooner the
    # money is needed, the less growth), and the safety net (never 100% growth).
    wd = p.get("withdrawal_share_3y") or 0
    hcap = horizon_max_growth(p["horizon_years"])
    floors = {"liquidity": wd, "horizon": round(1 - hcap, 4), "safety": SAFETY_MIN_DEFENSIVE}
    t["min_defensive"] = max(floors.values())
    binding = max(floors, key=floors.get)
    why = {"liquidity": f"{wd:.0%} may be withdrawn within 3 years",
           "horizon": f"horizon {p['horizon_years']:g} years → at most {hcap:.0%} in stocks",
           "safety": "safety net, never 100% growth"}[binding]
    reasons.append(f"defensive floor {t['min_defensive']:.0%}: {why}")
    t["min_defensive_source"], t["min_defensive_why"] = binding, {
        "liquidity": f"the money you need within 3 years ({wd:.0%}) stays defensive",
        "horizon": f"the horizon rule, a judgment rule not a data result (decision #22): {p['horizon_years']:g} years "
                   f"→ at most {hcap:.0%} in stocks",
        "safety": "the safety net: never 100% growth"}[binding]

    # One company / crypto (decision #24): computed from this client's loss limit and stock room, and each asset's
    # own worst drop. No fixed per-level cap.
    drops = worst_drops() if drops is None else drops
    max_growth = round(1 - t["min_defensive"], 4)
    share = LOSS_SHARE_ONE_COMPANY / (2 if beginner else 1)
    caps, binding, cap_c, why_c = _caps(loss_limit, max_growth, share, drops)
    t["company_caps"], t["max_single"] = caps, max(caps.values())
    crypto_excluded = "crypto" in (p.get("exclusions") or [])
    t["max_crypto"] = 0.0 if beginner or crypto_excluded else cap_c
    reasons.append(f"one company: its own worst drop in the data ({drop_window()}) may cost at most {share:.0%} of your loss limit "
                   f"({share * loss_limit:.1%} of the portfolio), and no company above 1/{MIN_COMPANIES} of the "
                   f"{max_growth:.0%} you can hold in stocks ({max_growth / MIN_COMPANIES:.1%})"
                   + (f"; halved budget, knowledge {know} ≤ {BEGINNER_MAX_KNOWLEDGE}" if beginner else ""))
    reasons.append("crypto: not proposed, knowledge ≤ 2" if beginner else "crypto: you excluded it" if crypto_excluded
                   else f"crypto (BTC + ETH as one bet): same rule → at most {cap_c:.1%}")

    excluded = excluded_tickers(p.get("exclusions"))
    if t["max_crypto"] == 0:
        excluded |= CRYPTO
    allowed = sorted(UNIVERSE - excluded)

    flags, requests = [], []
    for tk, w in (p.get("requested_positions") or {}).items():
        dd = drops.get(tk)
        r = {"ticker": tk, "asked": w, "worst_drop": dd, "loss_at_asked": round(w * dd, 4) if dd else None,
             "window": drop_window(tk) if dd else None}
        if tk not in UNIVERSE:
            r["reason"] = "not in the 31 assets we have data for, so we can't assess it"
        elif tk in excluded:
            r["reason"] = ("crypto isn't proposed for this profile (knowledge ≤ 2)" if beginner and tk in CRYPTO
                           else "you asked to exclude crypto" if tk in CRYPTO else "it is in a category you excluded")
        elif tk in CRYPTO | STOCKS:
            fit = t["max_crypto"] if tk in CRYPTO else caps[tk]
            r["fits_up_to"] = fit
            if w > fit + 1e-9:
                bind = why_c if tk in CRYPTO else binding[tk]
                parts = []
                if dd:
                    hit = abs(w * dd)
                    parts.append(f"{tk}'s worst drop in {r['window']} was {dd:.1%}; at {w:.0%} that alone would be "
                                 f"{w * dd:.1%} of the portfolio, "
                                 + (f"more than your whole {loss_limit:.0%} loss limit" if hit > loss_limit else
                                    f"more than the {share:.0%} of your {loss_limit:.0%} loss limit one asset may use"))
                if bind == "spread":
                    parts.append(f"you can hold about {max_growth:.0%} in stocks, and one company is kept to "
                                 f"1/{MIN_COMPANIES} of that")
                r["reason"] = "; ".join(parts) + f"; it fits up to {fit:.1%}"
        if "reason" in r:
            requests.append(r)
            flags.append(f"request {tk} {w:.0%}: {r['reason']}")

    out = dict(risk_tolerance=tol, risk_capacity=cap, risk_level=level, risk_name=t.pop("name"),
               knowledge_score=know, **t, loss_limit=loss_limit, loss_limit_source=source, loss_limit_cad=loss_cad,
               liquidity_floor=wd, horizon_max_growth=hcap, allowed_assets=allowed, reasons=reasons, flags=flags,
               request_checks=requests, missing=[], kyc=kyc_check(p, tol))
    out["reasons_plain"] = plain_reasons(p, out)
    return out


# ---- the same reasons, written for the client (screens only) ------------------------------------------------
# `reasons` above stay as they are: the Explainer's facts (and so its cache hash) and the Critic's tool read them.
# These say what each score means. Same numbers, same order; nothing here decides anything.
SCALE_NOTE = ("Scores run from 1 to 5. Risk: 1 = Preserve, 2 = Cautious, 3 = Balanced, 4 = Growth, 5 = Aggressive. "
              "Knowledge: 1 = none, 2 = basic, 3 = intermediate, 4 = advanced, 5 = experienced.")
REACTION_TEXT = {"sell_all": "sell everything", "sell_some": "sell part of it", "hold": "hold on",
                 "buy_more": "buy more"}
KNOWLEDGE_NAME = {1: "none", 2: "basic", 3: "intermediate", 4: "advanced", 5: "experienced"}


def _risk(n: int) -> str:
    return f"{n}/5 ({RISK_LEVELS[n]['name']})"


def _know(n: int) -> str:
    return f"{n}/5 ({KNOWLEDGE_NAME.get(n, n)})"


def plain_reasons(p: dict, lim: dict) -> list[str]:
    """The Profiler's reasons in the client's words: every score says what scale it is on and what it means."""
    a, b = REACTION[p["loss_reaction"]], _loss_score(p["max_loss_pct"])
    tol, cap, level, know = lim["risk_tolerance"], lim["risk_capacity"], lim["risk_level"], lim["knowledge_score"]
    out = [f"If your investments fell 20%, you would {REACTION_TEXT.get(p['loss_reaction'], p['loss_reaction'])}: "
           f"risk tolerance {_risk(a)}.",
           f"The largest drop you would accept is {p['max_loss_pct']:g}%: risk tolerance {_risk(b)}.",
           f"We keep the more cautious of these two answers: your risk tolerance is {_risk(tol)}."]
    c = _horizon_score(p["horizon_years"])
    out.append(f"Your money stays invested about {p['horizon_years']:g} years: capacity to take risk {_risk(c)}.")
    wd = p.get("withdrawal_share_3y") or 0
    for cond, text in [(p["emergency_fund_months"] < 3,
                        f"Your emergency fund covers {p['emergency_fund_months']:g} months (less than 3)"),
                       (p["income_stability"] == "uncertain", "Your income is uncertain"),
                       (wd >= 0.25, f"{wd:.0%} of the money may be needed within 3 years")]:
        if cond and c > 1:
            c -= 1
            out.append(f"{text}: capacity lowered to {_risk(c)}.")
    if p["objective"] == "safety_cushion" and c > 1:
        out.append(f"Your goal is a safety cushion: capacity lowered to {_risk(1)}.")
    out.append(f"Your risk level is the lower of your tolerance ({tol}/5) and your capacity ({cap}/5): "
               f"{_risk(level)}.")
    lvl = p.get("knowledge_level")
    s = LEVEL_FROM_DECLARED.get(lvl, 1)
    out.append(f"You describe your investing knowledge as {lvl or 'not given'}: knowledge {_know(s)}.")
    if s < 5 and (p.get("years_experience") or 0) >= 5 and set(p.get("products_held") or []) & {"stocks", "etfs"}:
        s += 1
        out.append(f"You have invested in stocks or ETFs for 5 years or more: knowledge raised to {_know(s)}.")
    quiz = p.get("quiz_correct")
    if quiz is not None and s > QUIZ_CAP[quiz]:
        s = QUIZ_CAP[quiz]
        out.append(f"You answered {quiz} of 3 quiz questions correctly: knowledge capped at {_know(s)}.")
    ev = expected_value_check(p)
    if ev and not ev["correct"] and s > EV_WRONG_CAP:
        s = EV_WRONG_CAP
        out.append(f"Average-return question: you answered {ev['answer']:g}%, the answer is {ev['expected']:g}%: "
                   f"knowledge capped at {_know(s)}.")
    beginner = know <= BEGINNER_MAX_KNOWLEDGE
    if beginner:
        out.append(f"At knowledge {BEGINNER_MAX_KNOWLEDGE}/5 or less, crypto is not proposed and the budget for "
                   "any single company is halved.")

    ll, capital, cad = lim["loss_limit"], p.get("capital"), lim.get("loss_limit_cad")
    cap_loss = RISK_LEVELS[cap]["max_drawdown"]
    out.append(f"Your loss limit is {ll:.0%}" + (f" ({cad:,} $ of {capital:,.0f} $)" if cad and capital else "")
               + f": the smaller of the drop you would accept ({p['max_loss_pct'] / 100:.0%}) and what a "
               f"capacity of {cap}/5 can absorb ({cap_loss:.0%}).")
    floor, hcap = lim["min_defensive"], lim["horizon_max_growth"]
    why = {"liquidity": f"{wd:.0%} of the money may be needed within 3 years",
           "horizon": f"with {p['horizon_years']:g} years ahead, at most {hcap:.0%} goes in stocks",
           "safety": "we never put 100% in stocks"}[lim["min_defensive_source"]]
    out.append(f"At least {floor:.0%} stays in safer investments (bonds and cash): {why}.")
    mg = round(1 - floor, 4)
    share = LOSS_SHARE_ONE_COMPANY / (2 if beginner else 1)
    out.append(f"One company: if it fell again as much as at its worst ({drop_window()}), that alone may use at most "
               f"{share:.0%} of your loss limit ({share * ll:.1%} of the portfolio). And no company gets more than "
               f"1/{MIN_COMPANIES} of the {mg:.0%} you can hold in stocks ({mg / MIN_COMPANIES:.1%}). Each company's "
               "cap is the lower of the two.")
    excl = "crypto" in (p.get("exclusions") or [])
    out.append("Crypto: not proposed at your knowledge level." if beginner and not excl
               else "Crypto: left out, as you asked." if excl
               else f"Crypto (Bitcoin and Ether counted as one bet): the same rule allows at most "
                    f"{lim['max_crypto']:.1%}.")
    return out
