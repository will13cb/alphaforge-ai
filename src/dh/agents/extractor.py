"""Extractor (layer 0): the client's own words → `profile` facts (contract §1) + follow-up questions.

A Strands agent on Amazon Bedrock (Claude Opus 5.5) reads the text and decides which fields it can fill. It NEVER
scores anything: the Profiler (rules) turns the facts into limits. "The LLM argues, code enforces" (#2):

- **Schema** (code): every field is type- and range-checked, enums must be one of the contract's values, tickers are
  mapped to the universe spelling. Anything else is dropped, and the note says why.
- **Grounding** (code): every NUMBER in the profile must appear in the client's words (400k, 400,000, "four years"
  all count). A number the agent inferred or invented is dropped and asked instead.
- **Follow-up questions** (code): one fixed question per missing KYC essential (rules.ESSENTIAL_FIELDS), so the
  Profiler asks instead of guessing (G1).

The agent has one tool, `check_profile`, that runs those same checks on its draft (≤ 3 calls), then answers with JSON.

Modes (LLM_PROVIDER, like the Explainer): `bedrock` → committed demo cache, local cache, then the agent; `mock`
(default, tests, offline demo) → committed demo cache if this exact text was saved, else the rule-based parser below.
If the agent fails or returns no JSON, the rule-based parser is used and the note says why.
Rule 5 exception, as for the Explainer (#23): Strands calls Bedrock itself; caching is done here.

    from dh.agents import extractor
    ex = extractor.extract("I'm 59, retiring in about 4 years, I can't lose more than 15%. Put 25% in Tesla.")
    ex["profile"], ex["missing"], ex["questions"]
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone

from ..data import ROOT
from .rules import CRYPTO, ESSENTIAL_FIELDS, EXCLUSIONS, UNIVERSE

PROMPT_VERSION = "extractor-v1"
DEMO_CACHE = ROOT / "cache" / "extractor"      # committed: the demo replays offline
LOCAL_CACHE = ROOT / ".cache" / "extractor"    # gitignored
MAX_CHECKS = 3
from ..llm import DEFAULT_MODEL_ID  # noqa: E402  (one default for every agent, verified on the event account)

# ---- schema (contract §1 `profile`) ---------------------------------------------------------------------
ENUMS = {
    "objective": ["growth", "retirement", "major_project", "income", "legacy", "safety_cushion"],
    "income_stability": ["stable", "variable", "uncertain"],
    "loss_reaction": ["sell_all", "sell_some", "hold", "buy_more"],
    "knowledge_level": ["none", "basic", "intermediate", "advanced"],
    "investment_mode": ["market", "fixed_rate"],
    "fixed_income_market": ["both", "canada", "us"],
}
NUMBERS = {  # field → (min, max); all must be grounded in the text
    "fixed_rate_pct": (0, 100), "ev_answer_pct": (-100, 100),
    "age": (16, 100), "horizon_years": (0.5, 60), "capital": (0, 1e9), "monthly_contribution": (0, 1e7),
    "target_amount": (1, 1e10), "emergency_fund_months": (0, 120), "max_loss_pct": (0, 100),
    "years_experience": (0, 80), "withdrawal_share_3y": (0, 1),
}
LISTS = {
    "products_held": {"stocks", "etfs", "bonds", "crypto", "gics", "funds"},
    "interests": {"ai", "tech", "crypto", "esg", "dividends", "canada", "us", "gold", "bonds"},
    "exclusions": set(EXCLUSIONS) | UNIVERSE,
}
SECTORS = ["Information Technology", "Health Care", "Financials", "Energy", "Industrials", "Consumer Discretionary",
           "Consumer Staples", "Communication Services", "Utilities", "Materials", "Real Estate"]
TEXT_FIELDS = {"name", "request"}

# Company names → universe tickers (the starter pack's 31 assets). Unknown tickers are kept: the Profiler explains
# that it has no data for them (e.g. XSP), it never invents numbers.
ALIASES = {
    "tesla": "TSLA", "nvidia": "NVDA", "apple": "AAPL", "microsoft": "MSFT", "google": "GOOGL", "alphabet": "GOOGL",
    "amazon": "AMZN", "jpmorgan": "JPM", "jp morgan": "JPM", "johnson & johnson": "JNJ", "johnson and johnson": "JNJ",
    "procter": "PG", "exxon": "XOM", "bitcoin": "BTC-USD", "btc": "BTC-USD", "ethereum": "ETH-USD", "eth": "ETH-USD",
    "shopify": "SHOP.TO", "royal bank": "RY.TO", "rbc": "RY.TO", "td bank": "TD.TO", "manulife": "MFC.TO",
    "enbridge": "ENB.TO", "canadian natural": "CNQ.TO", "cn rail": "CNR.TO", "canadian national": "CNR.TO",
    "fortis": "FTS.TO", "couche-tard": "ATD.TO", "couche tard": "ATD.TO", "constellation software": "CSU.TO",
    "s&p 500": "SPY", "s&p500": "SPY", "nasdaq": "QQQ", "tsx 60": "XIU.TO", "gold": "GLD",
}
TICKER_SPELLING = {t.split(".")[0].split("-")[0]: t for t in UNIVERSE}   # "RY" → "RY.TO", "BTC" → "BTC-USD"

QUESTIONS = {
    "age": "How old are you?",
    "horizon_years": "In how many years will you need most of this money?",
    "objective": "What is this money for: growing it, retirement, a major project, income, passing it on, or a safety cushion?",
    "loss_reaction": "If your investments dropped 20% in three months, what would you do: sell everything, sell some, "
                     "hold, or buy more?",
    "max_loss_pct": "What is the largest drop from a high point, at any time while invested, that you could live "
                    "with, in %?",
    "emergency_fund_months": "How many months of expenses do you have set aside for emergencies?",
    "income_stability": "Is your income stable, variable, or uncertain?",
    "knowledge_level": "How would you describe your investing knowledge: none, basic, intermediate, or advanced?",
}

# ---- numbers the client actually wrote ---------------------------------------------------------------------
_UNITS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                       "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}
_WORDNUM = re.compile(r"\b(" + "|".join(_TENS) + r")(?:[\s-](" + "|".join(list(_UNITS)[1:10]) + r"))?\b|\b("
                      + "|".join(_UNITS) + r")\b|\b(a|one) half\b|\bhalf\b", re.I)


def normalize(text: str) -> str:
    """Number words → digits ("four years" → "4 years", "twenty-five" → "25", "half" → "50%")."""
    def sub(m):
        if m.group(1):
            return str(_TENS[m.group(1).lower()] + (_UNITS[m.group(2).lower()] if m.group(2) else 0))
        if m.group(3):
            return str(_UNITS[m.group(3).lower()])
        return "50%"
    from .french_profile import numeric_text
    return _WORDNUM.sub(sub, numeric_text(text))


_NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(k\b|m\b|thousand|millions?|mille\b|mil\b)?", re.I)
_MULT = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "mil": 1e6, "mille": 1e3, "millions": 1e6}


def numbers_in(text: str) -> set[float]:
    """Every number written in the text, with its k/million expansion (400k → 400 and 400000)."""
    out = set()
    for raw, unit in _NUM.findall(normalize(text)):
        v = float(raw.replace(",", ""))
        out.add(v)
        if unit:
            out.add(v * _MULT[unit.lower()])
    return out


def _in(v: float, nums: set[float]) -> bool:
    return any(abs(v - n) <= max(1e-6, 1e-6 * abs(n)) for n in nums)


def ticker_of(name: str) -> str:
    s = name.strip().strip(".,;:!?'\"").lower()
    if s in ALIASES:
        return ALIASES[s]
    up = s.upper()
    return up if up in UNIVERSE else TICKER_SPELLING.get(up, up)


# ---- the checks (code enforces) --------------------------------------------------------------------------------

def validate(raw: dict, text: str) -> tuple[dict, list[str]]:
    """Keep only fields that fit the schema AND whose numbers appear in the client's words. Returns (profile, notes)."""
    nums, out, notes = numbers_in(text), {}, []
    for k, v in (raw or {}).items():
        if v is None or v == "" or v == [] or v == {}:
            continue
        if k in ENUMS:
            v = str(v).strip().lower().replace(" ", "_").replace("-", "_")
            if v in ENUMS[k]:
                out[k] = v
            else:
                notes.append(f"{k}: '{v}' is not one of {', '.join(ENUMS[k])}, dropped")
        elif k in NUMBERS:
            try:
                x = float(v)
            except (TypeError, ValueError):
                notes.append(f"{k}: '{v}' is not a number, dropped")
                continue
            lo, hi = NUMBERS[k]
            if k == "withdrawal_share_3y" and x > 1:
                x /= 100
            grounded = _in(x * 100, nums) if k == "withdrawal_share_3y" else _in(x, nums)
            if k == "withdrawal_share_3y" and not grounded and raw.get("capital"):
                grounded = _in(round(x * float(raw["capital"])), nums)
            if k == "withdrawal_share_3y" and x == 0 and re.search(r"aucun retrait|pas de retrait|no withdrawals?", text, re.I):
                grounded = True
            if not lo <= x <= hi:
                notes.append(f"{k}: {x:g} is outside {lo:g}-{hi:g}, dropped")
            elif k == "capital" and x == 0 and not _in(0, nums):
                continue
            elif not grounded:
                notes.append(f"{k}: {x:g} is not written in the client's words, dropped (asked instead)")
            else:
                out[k] = int(x) if k == "age" else x
        elif k in LISTS:
            items = v if isinstance(v, list) else [v]
            items = [str(i).strip().lower().replace(" ", "_") if str(i).upper() not in UNIVERSE else str(i).upper()
                     for i in items]
            ok = [i for i in items if i in LISTS[k]]
            if len(ok) < len(items):
                notes.append(f"{k}: dropped {', '.join(i for i in items if i not in ok)} (not a known value)")
            if ok:
                out[k] = sorted(set(ok))
        elif k == "kyc_bets":
            from .. import kyc
            bets = {}
            for key, value in (v.items() if isinstance(v, dict) else []):
                try:
                    bet = kyc.BY_ID[key]
                    ce = float(value)
                    kyc.rank(bet, ce)
                    if not (_in(ce * 100, nums) or _in(round(bet.amount * (1 + ce)), nums)):
                        raise ValueError("answer not written in the client's words")
                    bets[key] = ce
                except (KeyError, ValueError, TypeError):
                    notes.append(f"kyc_bets.{key}: invalid or unsupported answer, dropped")
            if bets:
                out[k] = bets
        elif k == "employment_sector":
            m = next((s for s in SECTORS if s.lower() == str(v).strip().lower()), None)
            if m:
                out[k] = m
            else:
                notes.append(f"employment_sector: '{v}' is not a sector name, dropped")
        elif k == "requested_positions":
            req = {}
            for t, w in (v.items() if isinstance(v, dict) else []):
                try:
                    w = float(w)
                except (TypeError, ValueError):
                    continue
                w = w / 100 if w > 1 else w
                if not 0 < w <= 1:
                    notes.append(f"request {t}: weight {w:g} outside 0-100%, dropped")
                elif not _in(round(w * 100, 6), nums):
                    notes.append(f"request {t}: {w:.0%} is not written in the client's words, dropped")
                else:
                    req[ticker_of(str(t))] = w
            if req:
                out[k] = req
        elif k == "existing_positions":   # holdings already owned: amounts must be written in the client's words
            flat = numbers_in(re.sub(r"(?<=\d)[ \u00a0\u202f](?=\d{3}\b)", "", text)) | nums
            held = {}
            for t, a_ in (v.items() if isinstance(v, dict) else []):
                try:
                    a_ = float(a_)
                except (TypeError, ValueError):
                    continue
                if a_ <= 0:
                    continue
                if not (_in(a_, flat) or _in(a_ / 1e3, flat)):
                    notes.append(f"holding {t}: {a_:,.0f} $ is not written in the client's words, dropped")
                    continue
                from .. import standins
                held[standins.canonical(ticker_of(str(t)), UNIVERSE)] = a_
            if held:
                out[k] = held
        elif k in TEXT_FIELDS:
            out[k] = str(v)[:300]
        else:
            notes.append(f"{k}: not a profile field, dropped")
    rate = re.search(r"(?:fixed(?:[- ]rate| return| interest| coupon)?|coupon|taux fixe)(?:\s+(?:of|at|de|à))?\s*(\d+(?:[.,]\d+)?)\s*%", text, re.I)
    rate = rate or re.search(r"(?:bonds?|obligations?|gic|cpg)(?:\s+(?:at|à|a|de|paying|with|fixed|a fixed))*\s+(\d+(?:[.,]\d+)?)\s*%", text, re.I)
    if out.get("investment_mode") != "market" and rate and re.search(r"\bbonds?\b|obligations?|\bgic\b|\bcpg\b", text, re.I):
        value = float(rate[1].replace(",", "."))
        if 0 <= value <= 100:
            out["investment_mode"] = "fixed_rate"
            out["fixed_rate_pct"] = value
    return out, notes


def missing(profile: dict) -> list[str]:
    return [f for f in ESSENTIAL_FIELDS if profile.get(f) is None]


def questions(miss: list[str]) -> list[dict]:
    return [{"field": f, "question": QUESTIONS[f]} for f in miss]


# ---- rule-based parser (offline mode, and the fallback when the agent fails) ---------------------------------

def _has(t: str, *words) -> bool:
    return any(re.search(w, t) for w in words)


def _money(t: str, pattern: str) -> float | None:
    m = re.search(pattern, t)
    if not m:
        return None
    v = float(m.group("n").replace(",", ""))
    return v * _MULT.get((m.group("u") or "").lower(), 1) if "u" in m.groupdict() else v


_AMT = r"\$?\s?(?P<n>\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?![\d.,]*\d)\s*(?P<u>k\b|m\b|thousand|million)?\s*(?:\$|dollars|cad)?"


_HOLD_VERB = re.compile(r"\b(?:i (?:already )?(?:have|hold|own)|i've got|j'ai|j’ai|je d[ée]tiens|je poss[èe]de|"
                        r"my (?:current )?(?:portfolio|holdings?)|mon portefeuille)\b", re.I)
_HELD = re.compile(r"(?<![\d%])(\d{1,3}(?:[ ,\u00a0\u202f]\d{3})+|\d+(?:[.,]\d+)?)\s*(k|m)?\s*(?:\$|cad|dollars?)?\s*"
                   r"(?:of|in|into|dans|en|de|d'|d’)\s+(?:l'|le |la |les )?([A-Za-z][\w.&\-]*)", re.I)


def existing_from_text(text: str) -> dict[str, float]:
    """Holdings the client says they ALREADY own ("I have 10k in XIU", "j'ai 10 000 $ dans XSP et 5 k$ dans RY").
    Only sentences with a holding verb; only names that map to an asset we know (or a stand-in fund, or a ticker
    written in capitals). Amounts in $; a % is a request, not a holding."""
    from .. import standins
    out: dict[str, float] = {}
    for sent in re.split(r"(?<=[.!?;])\s+|\n", text):
        if not _HOLD_VERB.search(sent):
            continue
        for raw, unit, name in _HELD.findall(sent):
            if re.match(r"\s*%", sent[sent.find(raw) + len(raw):]):
                continue
            digits = re.sub(r"[ ,\u00a0\u202f]", "", raw) if re.search(r"[ ,\u00a0\u202f]\d{3}\b", raw) else raw.replace(",", ".")
            v = float(digits) * {"k": 1e3, "m": 1e6}.get(unit.lower(), 1)
            cand = name.strip(".,;:!?")
            tk = standins.canonical(ticker_of(cand), UNIVERSE)
            if tk in UNIVERSE or tk in standins.STAND_INS or (cand.isupper() and len(cand) >= 2):
                out[tk] = out.get(tk, 0.0) + v
    return out


def rule_parse(text: str) -> dict:
    """Deterministic, conservative: fills a field only on a clear pattern. Leaves the rest to the follow-up questions."""
    t = normalize(text).lower()
    p: dict = {}
    m = re.search(r"\b(?:i'?m|i am|age[d:]?)\s*(\d{2})\b|\b(\d{2})\s*(?:years? old|yo\b|y/o)", t)
    if m:
        p["age"] = int(m.group(1) or m.group(2))
    for m in re.finditer(r"(?:in|within|for|over|next|horizon of|retir\w*)\s+(?:about|around|roughly|approximately|"
                         r"the next)?\s*(\d+(?:\.\d+)?)\s*(?:years?|yrs?)(?!\s*old)(?!\s*(?:of )?(?:experience|investing))", t):
        if "invest" not in t[max(0, m.start() - 20):m.start()]:  # "investing for 20 years" is experience, not horizon
            p["horizon_years"] = float(m.group(1))
            break
    if (v := _money(t, r"(?:have|saved|savings of|capital of|portfolio of|invest(?:ing)?)\s+(?:about|around)?\s*" + _AMT
                    + r"(?!\s*(?:a|per|/|each)\s*month)")) is not None:
        p["capital"] = v
    if (v := _money(t, _AMT + r"\s*(?:a|per|/|each|every)\s*month")) is not None:
        p["monthly_contribution"] = v
    if (v := _money(t, r"(?:reach|target of|goal of|end up with|get to)\s+" + _AMT)) is not None:
        p["target_amount"] = v
    loss_pcts = [float(a or b) for a, b in re.findall(r"(?:lose|loss|drop|fall|down)\D{0,40}?(\d+(?:\.\d+)?)\s*%|"
                                                      r"(\d+(?:\.\d+)?)\s*%\s*(?:loss|drop)", t)]
    if not p.get("horizon_years") and (m := re.search(r"(?:long[- ]term|horizon)\D{0,15}?(\d+(?:\.\d+)?)\s*years?", t)):
        p["horizon_years"] = float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*months?\D{0,40}(?:emergenc|aside|expenses|cushion)|"
                  r"emergency fund\D{0,20}(\d+(?:\.\d+)?)\s*months?", t)
    if m:
        p["emergency_fund_months"] = float(m.group(1) or m.group(2))
    elif _has(t, r"no emergency fund", r"no savings set aside"):
        p["emergency_fund_months"] = 0.0
    m = re.search(r"(\d+)\s*years? (?:of )?(?:investing|experience|in the market)", t)
    if m:
        p["years_experience"] = float(m.group(1))

    for obj, pats in [("retirement", [r"retir"]), ("safety_cushion", [r"emergency cushion", r"safety cushion", r"rainy day"]),
                      ("major_project", [r"\bhouse\b", r"down ?payment", r"\bwedding\b", r"\bproject\b", r"tuition"]),
                      ("income", [r"\bincome from\b", r"generate income", r"live off"]),
                      ("legacy", [r"inherit", r"pass (?:it )?on", r"legacy", r"my (?:kids|children)"]),
                      ("growth", [r"\bgrow", r"long[- ]term", r"build wealth"])]:
        if _has(t, *pats):
            p["objective"] = obj
            break
    for r_, pats in [("sell_all", [r"sell (?:it )?all", r"sell everything", r"get out"]), ("sell_some", [r"sell some", r"sell part"]),
                     ("buy_more", [r"buy more", r"buy the dip"]), ("hold", [r"\bhold\b", r"do nothing", r"stay invested", r"wait it out"])]:
        if _has(t, *pats):
            p["loss_reaction"] = r_
            break
    for lvl, pats in [("none", [r"beginner", r"new to investing", r"never invested", r"no experience", r"know nothing"]),
                      ("advanced", [r"advanced", r"experienced investor", r"\bexpert\b", r"follow the markets? (?:closely|actively)"]),
                      ("intermediate", [r"intermediate", r"some experience", r"decent knowledge"]),
                      ("basic", [r"\bbasic", r"a little", r"not much experience"])]:
        if _has(t, *pats):
            p["knowledge_level"] = lvl
            break
    for inc, pats in [("uncertain", [r"uncertain", r"unstable", r"might lose my job", r"no steady"]),
                      ("variable", [r"variable", r"freelance", r"commission", r"irregular"]),
                      ("stable", [r"stable", r"steady", r"secure job", r"salaried", r"tenured"])]:
        if _has(t, *pats):
            p["income_stability"] = inc
            break

    p["interests"] = sorted({k for k, pats in [("ai", [r"\bai\b", r"artificial intelligence"]), ("tech", [r"\btech"]),
                                              ("crypto", [r"crypto", r"bitcoin"]), ("esg", [r"\besg\b", r"sustainab", r"ethical"]),
                                              ("dividends", [r"dividend"]), ("canada", [r"canad"])]
                             if _has(t, *pats)})
    neg = r"(?:no|not|avoid|without|exclude|don'?t (?:want|like)|stay away from|nothing in)\b[^.]{0,25}"
    excl = {k for k, pats in [("crypto", [neg + r"(?:crypto|bitcoin)"]),
                               ("fossil_fuels", [neg + r"(?:fossil|oil|gas|pipelines?)"])] if _has(t, *pats)}
    p["exclusions"] = sorted(excl)
    if "crypto" in excl:
        p["interests"] = [i for i in p["interests"] if i != "crypto"]
    p["products_held"] = sorted({k for k, pats in [("stocks", [r"\bstocks?\b", r"shares"]), ("etfs", [r"\betfs?\b"]),
                                                  ("bonds", [r"\bbonds?\b"]), ("crypto", [r"own (?:some )?crypto"])]
                                 if _has(t, r"(?:own|hold|have|bought)[^.]{0,30}" + pats[0])})
    for sec, pats in [("Health Care", [r"health ?care", r"hospital", r"nurse", r"doctor", r"pharma"]),
                      ("Energy", [r"oil and gas", r"in energy", r"oil company"]),
                      ("Information Technology", [r"software", r"in tech", r"engineer at"]),
                      ("Financials", [r"\bbank(?:er|ing)?\b(?! account)", r"in finance", r"insurance"])]:
        if _has(t, r"(?:work|job|career|employed)[^.]{0,40}(?:" + "|".join(pats) + ")", *[r"i'?m an? [^.]{0,20}" + x for x in pats],
                r"software (?:engineer|developer)" if sec == "Information Technology" else r"$^"):
            p["employment_sector"] = sec
            break
    req = {}
    for w, name in re.findall(r"(\d+(?:\.\d+)?)\s*%\s*(?:of (?:my|the) [\w\s]{1,20}?\s)?(?:in|into|on)\s+([a-z][\w.&\-]*(?: [a-z][\w&\-]*)?)", t):
        for cand in (name.strip(".,;:!?"), name.split()[0].strip(".,;:!?")):
            tk = ticker_of(cand)
            if tk in UNIVERSE or re.search(r"\b" + re.escape(cand.upper()) + r"\b", text):  # known, or a ticker in CAPS
                req[tk] = float(w) / 100
                break
    asked = {round(w * 100, 6) for w in req.values()}  # "lose much, put 25% in Tesla": 25% is the request, not the loss
    if (pct := next((x for x in loss_pcts if x not in asked), None)) is not None:
        p["max_loss_pct"] = pct
    if req:
        p["requested_positions"] = req
        if any(t_ in CRYPTO for t_ in req) and "crypto" in p.get("exclusions", []):
            p["exclusions"].remove("crypto")
    held = existing_from_text(text)
    if held:
        p["existing_positions"] = held
        if p.get("capital") in held.values():   # "I have 10k in XIU" is a holding, not the capital: ask instead
            p.pop("capital")
    m = re.search(r"\b(?:my name is|call me)\s+([a-z]+)", t)
    if m:
        p["name"] = m.group(1).title()
    from .french_profile import parse as french_parse
    p.update(french_parse(text))
    return {k: v for k, v in p.items() if v not in (None, [], {})}


# ---- Strands agent on Bedrock -----------------------------------------------------------------------------------

SYSTEM_PROMPT = f"""You turn a fictional investor's own words into a JSON profile for an investment-analysis
simulation. Read French and English, including French number words, decimal commas and space-grouped CAD amounts.
Return the schema keys and enum values below in English, regardless of input language.
You only EXTRACT what the client said; you never judge risk, never advise, never set limits.

Fields (omit any the client did not state or clearly imply):
- investment_mode: market or fixed_rate (only for explicit fixed-rate bonds/deposits held to maturity); fixed_rate_pct: requested annual percentage; fixed_income_market: both, canada or us. A loss-limit percentage is not a requested interest rate.
- name (str), age (int), horizon_years (number: years until most of the money is needed)
- objective: one of {ENUMS['objective']}
- capital, monthly_contribution, target_amount (CAD amounts)
- emergency_fund_months (number), income_stability: one of {ENUMS['income_stability']}
- withdrawal_share_3y (0-1: share of the money needed within 3 years)
- loss_reaction (to a 20% drop): one of {ENUMS['loss_reaction']}
- max_loss_pct (0-100: largest drop they say they could accept)
- knowledge_level: one of {ENUMS['knowledge_level']}, years_experience (number)
- ev_answer_pct: the explicitly stated answer to the expected-return quiz, in percentage points (not an investment-return target)
- kyc_bets: optional object with bet_small, bet_large, bet_savings: the client's explicitly selected guaranteed returns as fractions (8.3% = 0.083); never infer from risk tolerance
- products_held: subset of {sorted(LISTS['products_held'])}
- interests: subset of {sorted(LISTS['interests'])}
- exclusions: subset of {sorted(EXCLUSIONS)} (or tickers)
- employment_sector: one of {SECTORS}
- existing_positions ({{ticker: CAD amount}}: what they say they ALREADY hold, e.g. "I have 10k in XIU" → {{"XIU.TO": 10000}})
- request (str: what they asked for, in their words), requested_positions ({{ticker: weight 0-1}}; tickers from:
  {', '.join(sorted(UNIVERSE))}; keep any other ticker as written)

Hard rules:
- Every number you output must be written in the client's text (as digits or words). Never compute, convert or
  guess a number; if it isn't there, leave the field out and it will be asked.
- Before answering, call check_profile with your draft JSON. Fix what it reports, at most {MAX_CHECKS} calls.
- Answer with the JSON object only, no other text.
"""


def model_id() -> str:
    return os.getenv("BEDROCK_EXTRACTOR_MODEL_ID") or os.getenv("BEDROCK_MODEL_ID") or DEFAULT_MODEL_ID


def _json_from(s: str) -> dict:
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("no JSON object in the agent's answer")
    return json.loads(s[a:b + 1])


def _run_agent(text: str) -> tuple[dict, int]:
    """(raw profile dict, number of check_profile calls). Strands imported lazily (tests and mock don't need it)."""
    from strands import Agent, tool
    from strands.models import BedrockModel

    calls = {"n": 0}

    @tool
    def check_profile(profile_json: str) -> dict:
        """Check a draft profile: schema, values, and that every number is written in the client's text.
        Returns the problems (empty = fine) and which essential fields are still missing (they will be asked).

        Args:
            profile_json: the draft profile as a JSON object string.
        """
        calls["n"] += 1
        if calls["n"] > MAX_CHECKS:
            return {"error": f"check limit ({MAX_CHECKS}) reached: answer now"}
        try:
            draft = json.loads(profile_json)
        except json.JSONDecodeError as e:
            return {"error": f"not valid JSON: {e}"}
        prof, notes = validate(draft, text)
        return {"problems": notes, "still_missing": missing(prof)}

    model = BedrockModel(model_id=model_id(), region_name=os.getenv("AWS_REGION", "us-east-1"), max_tokens=4000)
    agent = Agent(model=model, system_prompt=SYSTEM_PROMPT, tools=[check_profile], callback_handler=None)
    res = agent("CLIENT TEXT:\n" + text)
    return _json_from(str(res)), calls["n"]


# ---- entry point --------------------------------------------------------------------------------------------------

def text_hash(text: str, mid: str = "") -> str:
    return hashlib.sha256(json.dumps([PROMPT_VERSION, mid, text.strip()]).encode()).hexdigest()[:16]


def _cache_paths(h: str):
    return DEMO_CACHE / f"{h}.json", LOCAL_CACHE / f"{h}.json"


def extract(text: str, provider: str | None = None) -> dict:
    """{profile, missing, questions, notes, source, model, check_calls, hash, note}. Never raises on agent failure."""
    provider = (provider or os.getenv("LLM_PROVIDER", "mock")).lower()
    mid = model_id()
    h = text_hash(text, mid)
    raw, source, calls, note = None, "", 0, ""
    failure_type = ""
    for p in _cache_paths(h):
        if p.exists():
            c = json.loads(p.read_text())
            raw, source, calls = c["raw"], f"cache ({p.parent.parent.name}/{p.parent.name})", c.get("check_calls", 0)
            break
    if raw is None and provider == "bedrock":
        try:
            raw, calls = _run_agent(text)
            source = "bedrock"
            LOCAL_CACHE.mkdir(parents=True, exist_ok=True)
            _cache_paths(h)[1].write_text(json.dumps(
                {"model": mid, "prompt_version": PROMPT_VERSION, "text": text, "raw": raw, "check_calls": calls,
                 "created": datetime.now(timezone.utc).isoformat(timespec="seconds")}, ensure_ascii=False, indent=1))
        except Exception as e:  # noqa: BLE001 — any AWS/Strands/JSON error → rules, reported in the trace
            failure_type = type(e).__name__
            note = f"agent unavailable ({failure_type}: {e})"[:300]
    if raw is None:
        raw, source = rule_parse(text), "rules"
        note = note or "mock mode: rule-based parser"
    profile, notes = validate(raw, text)
    # Complete explicit facts omitted by a model/cache, using the same grounding
    # checks as model outputs. Never replace a valid model answer with a guess.
    explicit, _ = validate(rule_parse(text), text)
    supplemented = [key for key in explicit if key not in profile]
    for key in supplemented:
        profile[key] = explicit[key]
    profile.setdefault("name", "Client")
    profile.setdefault("request", text.strip()[:300])
    miss = missing(profile)
    return {"profile": profile, "missing": miss, "questions": questions(miss), "notes": notes, "source": source,
            "model": mid if source != "rules" else "", "check_calls": calls, "hash": h, "note": note,
            "supplemented_fields": supplemented, "failure_type": failure_type}


def save_demo(ex: dict, text: str) -> str:
    """Copy an agent answer into the committed demo cache (so the demo replays it offline)."""
    if ex["source"] == "rules":
        raise ValueError(f"nothing to save: the profile came from the rule-based parser ({ex['note']})")
    src = _cache_paths(ex["hash"])[1]
    DEMO_CACHE.mkdir(parents=True, exist_ok=True)
    dst = DEMO_CACHE / src.name
    dst.write_text(src.read_text() if src.exists() else json.dumps({"text": text, "raw": ex["profile"]}))
    return str(dst.relative_to(ROOT))


def describe(ex: dict) -> str:
    """Extractor → Profiler hand-off line for the trace."""
    filled = [k for k in ex["profile"] if k not in ("name", "request")]
    src = {"bedrock": "Strands agent on Bedrock", "rules": "rule-based parser (offline)"}.get(ex["source"], ex["source"])
    s = f"{len(filled)} facts from the client's words ({src}"
    s += f", {ex['check_calls']} self-check(s))" if ex["check_calls"] else ")"
    s += ": " + ", ".join(filled) + "."
    if ex["notes"]:
        s += " Dropped by the checks: " + "; ".join(ex["notes"]) + "."
    if ex["missing"]:
        s += " Missing, asked: " + ", ".join(ex["missing"]) + "."
    return s


def add_to_trace(res: dict, ex: dict, answered: list[str] | None = None) -> None:
    """Put the Extractor step (and the client's answers to the follow-up questions) at the start of a pipeline trace."""
    from .trace import Trace

    tr = Trace()
    tr.step("Extractor", "Profiler", describe(ex), output={"profile": ex["profile"], "missing": ex["missing"],
                                                           "notes": ex["notes"], "source": ex["source"]})
    if answered:
        tr.step("Client", "Profiler", "answered the follow-up questions: " + ", ".join(answered))
    res["trace"].steps[:0] = tr.steps
    res["extraction"] = ex
