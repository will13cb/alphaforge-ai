"""(F) Results stay tied to the weights and data they were computed on.

Root cause fixed here (audit A6): `portfolio.assemble` computes the outlook, then `fix_diversification` may change
the weights; stats are recomputed, the outlook and `prob_loss` are not. Nothing in a strategy says which weights a
section describes, so the gap is invisible. Here every computed section carries a stamp
{weights, data, producer}; `verify` lists sections whose stamp no longer matches the final weights, and `refresh`
recomputes exactly those (each section is recomputed by its own producer, never by another module).

Recompute triggers (anything that changes a stamp input): weights changed (rounding, diversification fix, Critic
revision, level), data changed (window, stand-ins), assumption changed (goals), limits changed (checks only).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

import pandas as pd

from .contracts import Issue

STAMPS = "stamps"     # strategy["stamps"][section] = {"weights", "data", "producer"}: kept beside the sections, so
                      # sections like `stats` keep only numbers (G12 and the Explainer read them as such)
SECTIONS = ("stats", "outlook", "diversification", "checks", "risk")   # sections that describe the weights


def fingerprint_weights(weights: dict[str, float], ndigits: int = 6) -> str:
    """Order-independent hash of the weights, rounded so 0.1 + 0.2 and 0.3 agree. Zero weights are ignored."""
    if not weights:
        raise ValueError("empty weights")
    items = sorted((t, round(float(w), ndigits)) for t, w in weights.items() if round(float(w), ndigits) != 0)
    return hashlib.sha256(json.dumps(items).encode()).hexdigest()[:16]


def fingerprint_data(rets: pd.DataFrame) -> str:
    """Hash of the returns actually used: columns, first/last date, rows, column sums (cheap, catches a window or
    stand-in change)."""
    if rets is None or rets.empty:
        raise ValueError("empty returns")
    key = [list(map(str, rets.columns)), str(rets.index[0]), str(rets.index[-1]), len(rets),
           [round(float(x), 10) for x in rets.sum(skipna=True).to_numpy()]]
    return hashlib.sha256(json.dumps(key).encode()).hexdigest()[:16]


def stamp_of(weights: dict[str, float], rets: pd.DataFrame | None, producer: str) -> dict:
    """The stamp of a section computed on these weights and data. `rets=None` only for sections that read no data."""
    return {"weights": fingerprint_weights(weights), "data": fingerprint_data(rets) if rets is not None else None,
            "producer": producer}


def stamp(strategy: dict, sections, rets: pd.DataFrame | None, producer: str) -> dict:
    """Copy of the strategy with `sections` stamped as computed on its CURRENT weights. Call it right after computing
    those sections, never later (a later call would hide a stale section)."""
    st = dict(strategy.get(STAMPS) or {})
    for name in ([sections] if isinstance(sections, str) else sections):
        st[name] = stamp_of(strategy["weights"], rets, producer)
    return {**strategy, STAMPS: st}


def verify(strategy: dict, rets: pd.DataFrame | None = None) -> list[Issue]:
    """Issues for every present section that is missing a stamp or was computed on other weights/data than the final
    ones. 'block' for stale sections: they must never be shown as describing the strategy."""
    fw = fingerprint_weights(strategy["weights"])
    fd = fingerprint_data(rets) if rets is not None else None
    stamps = strategy.get(STAMPS) or {}
    out = []
    for name in SECTIONS:
        if strategy.get(name) is None:
            continue
        st = stamps.get(name)
        if st is None:
            out.append(Issue("F-unstamped", "disclose", "technical", f"'{name}' has no stamp: its weights are unknown",
                             {"section": name}))
        elif st["weights"] != fw:
            out.append(Issue("F-stale-weights", "block", "interpretation",
                             f"'{name}' ({st['producer']}) describes other weights than the final ones",
                             {"section": name, "stamped": st["weights"], "final": fw}))
        elif fd is not None and st["data"] not in (None, fd):
            out.append(Issue("F-stale-data", "block", "interpretation", f"'{name}' was computed on other data",
                             {"section": name}))
    return out


def refresh(strategy: dict, producers: dict[str, Callable[[dict], dict]], rets: pd.DataFrame | None = None) -> dict:
    """Recompute the stale sections with their own producer (section name → f(weights) → section) and stamp them.
    A stale section with no producer stays and keeps its blocking issue: never silently shown."""
    stale = {i.evidence.get("section") for i in verify(strategy, rets) if i.code.startswith("F-stale")}
    new = dict(strategy)
    for name in sorted(stale):
        if name in producers:
            new[name] = producers[name](new["weights"])
            new = stamp(new, name, rets, getattr(producers[name], "__name__", "producer"))
    return new
