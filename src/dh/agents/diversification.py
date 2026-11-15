"""Diversification of a strategy: how spread out it really is. DETERMINISTIC, no LLM (decision #18).

The brief tests it for every persona ("must maintain a logic of diversification and be able to explain its choices";
Amira "does not want to invest exclusively in technology"). Five dimensions, all from code already in the repo:

- asset classes    equity / bonds / gold / crypto (groups in rules.py)
- companies        what the client really owns through the ETFs: Will's `dh.metrics.look_through` on the issuer
                   holdings of `dh.holdings` (decision #6); largest company, top 5, effective number of companies
- sectors          look-through sectors (stock sector from the universe, ETF holdings sector from the issuer file)
- currency         CAD vs USD exposure
- correlation      diversification ratio, weighted average correlation, near-duplicate pairs; ETF overlap
                   (`dh.metrics.overlap`) when both ETFs have holdings data

`report(weights)` measures; `check(report)` applies rules C3/C4/C6 (team assumptions, same ✔/✘ format as the Guardian);
`describe(report)` is the one-line hand-off for the trace. ETFs without holdings data stay as one block: their
sector share is then a LOWER bound, and the report says so (`look_through_coverage`).

    from dh.agents import diversification as dv
    rep = dv.report({"XIU.TO": .3, "SPY": .3, "XBB.TO": .3, "GLD": .1})
    dv.check(rep), dv.describe(rep)
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from .. import data, metrics
from ..holdings import default_path, holdings as load_holdings
from . import market
from .rules import BOND_ETFS, CRYPTO, EQUITY_ETFS, ETFS, GOLD, STOCKS

# ---- rules (team assumptions, to validate; see notes/decisions.md #18) -----------------------------
MAX_SECTOR = 0.40        # C3: no single sector above 40% of the portfolio (look-through)
MAX_PAIR_CORR = 0.95     # C6: never hold two assets this correlated (e.g. SPY and ESGV, 0.99): same bet twice
MIN_CLASSES = 2          # C4: at least 2 of equity / bonds / gold / crypto, each >= 1% (a 60/40 passes)
MIN_CLASS_WEIGHT = 0.01
HIGH_ETF_OVERLAP = 0.50  # reported only: two ETFs sharing half their holdings

RULES = {
    "C3": f"No sector above {MAX_SECTOR:.0%} of the portfolio (⚠ above 30%), counted through the ETFs",
    "C6": f"No two holdings correlated above {MAX_PAIR_CORR:.2f} (same bet twice)",
    "C4": f"At least {MIN_CLASSES} asset classes (equity, bonds, gold, crypto)",
}

CLASS_OF = {**{t: "equity" for t in STOCKS | EQUITY_ETFS}, **{t: "bonds" for t in BOND_ETFS},
            **{t: "gold" for t in GOLD}, **{t: "crypto" for t in CRYPTO}}
NOT_A_SECTOR = ("Broad market", "Bonds", "Gold", "Crypto", "ETF remainder", "Unknown")


@lru_cache(maxsize=2)
def _holding_sectors(path: str | None = None) -> dict[str, str]:
    """Sector of each ETF holding, from the same issuer file as dh.holdings (empty if not built)."""
    p = default_path() if path is None else path
    try:
        df = pd.read_csv(p, usecols=["holding", "sector"])
    except (FileNotFoundError, ValueError):
        return {}
    return dict(zip(df.holding, df.sector.fillna("Unknown")))


def _universe_col(col: str) -> dict[str, str]:
    meta = market._meta()
    return {} if meta is None else meta[col].dropna().to_dict()


def _currency(t: str, known: dict[str, str]) -> str:
    return known.get(t) or ("CAD" if t.endswith(".TO") else "USD")


def report(weights: dict[str, float], rets: pd.DataFrame | None = None, holdings: dict | None = None,
           sectors: dict[str, str] | None = None, correlations: bool = True) -> dict:
    """Diversification facts for one strategy. holdings=None → issuer files (dh.holdings), {} → no look-through.
    sectors: optional {ticker or holding: sector} override (tests). correlations=False skips the return-based part
    (no data needed: the Guardian uses it on hand-made strategies)."""
    w = {t: float(v) for t, v in weights.items() if v > 0}
    tot = sum(w.values())
    w = {t: v / tot for t, v in w.items()}
    h = load_holdings() if holdings is None else holdings
    uni_sector = _universe_col("sector")
    sector_of = {**_holding_sectors(), **uni_sector, **(sectors or {})}
    ccy = _universe_col("currency")

    # asset classes
    classes: dict[str, float] = {}
    for t, v in w.items():
        k = CLASS_OF.get(t, "other")
        classes[k] = classes.get(k, 0.0) + v

    # companies and sectors, through the ETFs (Will's look_through)
    eff = metrics.look_through(w, h)
    companies = {k: v for k, v in eff.items() if k in STOCKS or (k not in ETFS and k not in CRYPTO
                                                                and not k.endswith("(other)") and k not in w)}
    secs: dict[str, float] = {}
    for k, v in eff.items():
        if k.endswith("(other)"):
            s = "ETF remainder (no detail)"
        elif k in BOND_ETFS:
            s = "Bonds"
        elif k in GOLD:
            s = "Gold"
        elif k in CRYPTO:
            s = "Crypto"
        else:
            s = sector_of.get(k, "Unknown")
        secs[s] = secs.get(s, 0.0) + v
    real = {s: v for s, v in secs.items() if not s.startswith(NOT_A_SECTOR)}
    eq_etfs = {t: v for t, v in w.items() if t in EQUITY_ETFS}
    covered = sum(v * min(1.0, sum(h.get(t, {}).values())) for t, v in eq_etfs.items())
    coverage = covered / sum(eq_etfs.values()) if eq_etfs else 1.0

    top = sorted(companies.items(), key=lambda kv: -kv[1])
    share = np.array([v for _, v in top])
    eff_n_comp = float(1 / ((share / share.sum()) ** 2).sum()) if share.sum() > 0 else 0.0

    # currency
    cur: dict[str, float] = {}
    for t, v in w.items():
        c = _currency(t, ccy)
        cur[c] = cur.get(c, 0.0) + v

    # correlation (daily returns, same calendar as every other number)
    pairs, div_ratio, avg_corr = [], 1.0, None
    if correlations and len(w) > 1:
        r = (data.returns() if rets is None else rets)[list(w)].dropna()
        c = corr_matrix(r)
        names = list(w)
        num = den = 0.0
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                rho = float(c.loc[a, b])
                num += w[a] * w[b] * rho
                den += w[a] * w[b]
                if rho >= MAX_PAIR_CORR:
                    pairs.append({"a": a, "b": b, "correlation": rho})
        avg_corr = num / den if den else None
        port = metrics.portfolio_returns(r, w)
        vol_p = metrics.ann_vol(port)
        div_ratio = sum(w[t] * metrics.ann_vol(r[t]) for t in names) / vol_p if vol_p > 0 else 1.0
    overlaps = [{"a": a, "b": b, "overlap": metrics.overlap(h[a], h[b])}
                for i, a in enumerate(sorted(eq_etfs)) for b in sorted(eq_etfs)[i + 1:] if a in h and b in h]
    overlaps = [o for o in overlaps if o["overlap"] >= HIGH_ETF_OVERLAP]

    largest_sector = max(real.items(), key=lambda kv: kv[1], default=("-", 0.0))
    return market._round({
        "n_holdings": len(w),
        "effective_n_holdings": 1 / sum(v * v for v in w.values()),
        "asset_classes": dict(sorted(classes.items(), key=lambda kv: -kv[1])),
        "n_asset_classes": sum(v >= MIN_CLASS_WEIGHT for k, v in classes.items() if k != "other"),
        "companies_top5": [{"name": k, "weight": v} for k, v in top[:5]],
        "largest_company": {"name": top[0][0], "weight": top[0][1]} if top else None,
        "effective_n_companies": eff_n_comp,
        "sectors": dict(sorted(secs.items(), key=lambda kv: -kv[1])),
        "largest_sector": {"name": largest_sector[0], "weight": largest_sector[1]},
        "tech_share": real.get("Information Technology", 0.0),
        "look_through_coverage": coverage,
        "currency": dict(sorted(cur.items(), key=lambda kv: -kv[1])),
        "avg_correlation": avg_corr,
        "diversification_ratio": div_ratio,
        "redundant_pairs": pairs,
        "etf_overlaps": overlaps,
    })


def corr_matrix(r: pd.DataFrame) -> pd.DataFrame:
    """Correlation of daily returns, except pairs with crypto: weekly (audit P21). Crypto is stamped in UTC days, stocks
    at the New York close, so same-day crypto/stock pairs are misaligned (BTC/SPY 0.38 daily vs 0.23 weekly on
    2021-2026). Weekly = compounded Monday-Friday returns, on days where both have data."""
    r = r.dropna()
    c = r.corr()
    cr = [t for t in r.columns if t in CRYPTO]
    if cr and len(r) > 30:
        wk = (1 + r).resample("W-FRI").prod() - 1
        cw = wk.corr()
        for a in cr:
            for b in r.columns:
                if a != b:
                    c.loc[a, b] = c.loc[b, a] = cw.loc[a, b]
    return c


def _c(rule: str, ok: bool, detail: str) -> dict:
    return dict(rule=rule, status="pass" if ok else "fail", detail=detail, text=RULES[rule])


def check(rep: dict) -> list[dict]:
    """Rules C3/C4/C6 on a report, in the Guardian's format. C3 and C4 come from checks.py, the one implementation
    (audit P10: this function used to say ✔ at 35% tech where checks.c3_sector said ⚠). C6 here sees only the hard
    case (pairs >= 0.95, ✘); the near-duplicate warning needs the weights and holdings: see strategy["checks"] C6."""
    from . import checks as ck  # local: checks imports this module
    c3, c4 = ck.c3_sector(rep), ck.c4_classes(rep)
    pairs = rep["redundant_pairs"]
    d2 = "ok" if not pairs else "; ".join(f"{p['a']}/{p['b']} {p['correlation']:.2f}" for p in pairs)
    return [dict(rule="C3", status=c3["status"], detail=c3["reason"], text=RULES["C3"]),
            _c("C6", not pairs, d2),
            dict(rule="C4", status=c4["status"], detail=c4["reason"], text=RULES["C4"])]


def describe(rep: dict) -> str:
    """One line for the trace, numbers only from the report."""
    cls = ", ".join(f"{k} {v:.0%}" for k, v in rep["asset_classes"].items())
    s = f"{rep['n_holdings']} holdings ({rep['effective_n_holdings']:.1f} effective), {cls}."
    if rep["largest_company"]:
        lc = rep["largest_company"]
        s += f" Largest company through the ETFs: {lc['name']} {lc['weight']:.1%}."
    ls = rep["largest_sector"]
    if ls["weight"] > 0:
        s += f" Largest sector: {ls['name']} {ls['weight']:.0%}."
    s += " Currency: " + ", ".join(f"{k} {v:.0%}" for k, v in rep["currency"].items()) + "."
    if rep["avg_correlation"] is not None:
        s += (f" Average correlation {rep['avg_correlation']:.2f}, diversification ratio "
              f"{rep['diversification_ratio']:.2f} (1 = none).")
    if rep["redundant_pairs"]:
        s += " Same bet twice: " + ", ".join(f"{p['a']}/{p['b']}" for p in rep["redundant_pairs"]) + "."
    return s
