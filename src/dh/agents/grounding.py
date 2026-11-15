"""Additional checks for explicitly named percentage metrics in agent text.

The general numeric validators check membership and entity attribution. This layer
also checks common metric labels and gain/loss direction. It is deliberately a
bounded language check, not a proof of arbitrary prose or of causal explanations.
"""
from __future__ import annotations

import re

LABELS = {
    "drawdown": r"max(?:imum)?[ _-]?drawdown|worst(?: historical| observed)? drop|pire baisse|baisse maximale",
    "volatility": r"(?:annual(?:ised|ized)? )?volatility|volatilité",
    "gain": r"gained|earned|rose(?: by)?|grew(?: by)?|a gagné|a augmenté de",
}
PATTERNS = {
    kind: re.compile(r"\b(?:" + label + r")\b[^\d%;.!?+−-]{0,35}([+−-]?\d+(?:[.,]\d+)?)\s*%", re.I)
    for kind, label in LABELS.items()
}
KEYS = {
    "drawdown": {"max_drawdown", "worst_drop", "deepest_drop", "observed_drawdown"},
    "volatility": {"ann_vol", "volatility", "annual_volatility"},
    "gain": {"ann_return", "annual_return", "return_2022", "stress_2008", "stress_2020", "rendement_cumule"},
}


def _number(token: str) -> float:
    return float(token.replace("−", "-").replace(",", "."))


def _values(source, kind: str) -> list[float]:
    """Read typed fields, plus explicitly labelled metrics in code-produced reasons."""
    if isinstance(source, dict):
        out = [float(v) for k, v in source.items() if k in KEYS[kind]
               and isinstance(v, (int, float)) and not isinstance(v, bool)]
        return out + [n for v in source.values() for n in _values(v, kind)]
    if isinstance(source, (tuple, list)):
        return [n for v in source for n in _values(v, kind)]
    if isinstance(source, str):
        return [_number(m.group(1)) / 100 for m in PATTERNS[kind].finditer(source)]
    return []


def problems(text: str, sources: list) -> list[str]:
    """Reject relabelling volatility as drawdown, and reporting a loss as a gain.

    Unsigned drawdowns can describe a loss magnitude. Explicitly signed values must
    preserve their sign. Rounding tolerance follows the written precision.
    Entity and period attribution remain the caller's separate responsibility.
    """
    out = []
    for kind, pattern in PATTERNS.items():
        pool = _values(sources, kind)
        for m in pattern.finditer(text):
            token = m.group(1).replace("−", "-").replace(",", ".")
            value = float(token)
            decimals = len(token.split(".")[1]) if "." in token else 0
            tolerance = .5 * 10 ** -decimals + 1e-9
            signed = token.startswith(("-", "+"))
            candidates = [v * 100 for v in pool if kind != "gain" or v > 0]
            if kind == "drawdown" and not signed:
                candidates = [abs(v) for v in candidates]
            if not any(abs(v - value) <= tolerance for v in candidates):
                out.append(f"{kind} {token}% does not match that metric in the evidence")
    return out
