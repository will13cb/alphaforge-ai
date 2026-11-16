"""“What if March 2020 happened again?” — replay the COVID crash on a proposed strategy (decision #50).

Every calculation of the submission stays on the starter window 2021-2026 (decision #48). This module only *replays*
one older episode on the weights the Portfolio already chose, from a second, separate history in data/raw_stress/
(built with the organizers' own script, `make data-stress`). Nothing here sets a weight, a split or a limit: it is
evidence the client and the judges can read next to the 2021-2026 numbers.

    from dh import stress
    res = stress.replay({"XIU.TO": .3, "XBB.TO": .6, "GLD": .1}, loss_limit=.15, capital=400_000)
    stress.sentence(res, "fr")   # « Entre le 19 février et le 23 mars 2020, cette stratégie aurait perdu … »

Same engine as every other number: returns from `dh.data` (adj_close, CAD, weekday calendar, FX carried forward),
daily-rebalanced fixed weights (`dh.metrics.portfolio_returns`), worst drop inside the window from the same
`quant_toolkit.scenario_analysis` the market agent uses for its stress keys. Past, not a forecast.
"""

from __future__ import annotations

import os
import threading
from dataclasses import replace
from pathlib import Path

import pandas as pd

from . import data, metrics
from . import quant_toolkit as qt

STRESS_DIR = data.ROOT / "data" / "raw_stress"
FILES = ("prices_daily.csv", "assets_universe.csv", "fx_usdcad_daily.csv", "macro_rates.csv")
# S&P 500 close-to-close peak and trough of the COVID crash (same dates as market.STRESS_MORE["2020"]); the build
# window adds context before and after, for the chart.
WINDOWS = {
    "covid_2020": {"peak": "2020-02-19", "trough": "2020-03-23", "build": ("2019-12-02", "2020-06-30"),
                   "en": "the March 2020 crash (COVID)", "fr": "le krach de mars 2020 (COVID)"},
}
SOURCE = ("Yahoo Finance adj_close via the organizers' build_dataset.py (scripts/build_long_data.py), "
          "USD/CAD Bank of Canada FXUSDCAD; window = S&P 500 peak 2020-02-19 to trough 2020-03-23")
_LOCK = threading.Lock()


def config(folder: Path | None = None) -> data.Config:
    """The harness's settings (CAD, weekdays, stand-ins) on the stress folder, whole file, no extra catalogue."""
    return replace(data.load_config(), data_dir=Path(folder or STRESS_DIR), start="", extra=())


def available(folder: Path | None = None) -> bool:
    return all((Path(folder or STRESS_DIR) / f).exists() for f in FILES)


def build(window: str = "covid_2020", folder: Path | None = None) -> int:
    """Download the window with the organizers' script (needs internet: Yahoo, Bank of Canada, FRED). Never in git."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_long_data", data.ROOT / "scripts" / "build_long_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    a, b = WINDOWS[window]["build"]
    return mod.main(["--start", a, "--end", b, "--out", str(folder or STRESS_DIR)])


def ensure() -> tuple[bool, str]:
    """(ready, note). On a host with AF_AUTO_DATA=1, builds data/raw_stress/ once; never raises (the screen says why)."""
    if available():
        return True, ""
    if os.getenv("AF_AUTO_DATA") != "1":
        return False, "data/raw_stress/ is missing: run `make data-stress` (needs internet)"
    with _LOCK:
        if not available():
            try:
                build()
            except (Exception, SystemExit) as e:  # noqa: BLE001
                return False, f"could not build data/raw_stress/ ({type(e).__name__}: {str(e)[:160]})"
    return available(), "" if available() else "the build finished but some files are missing"


def _not_available(window: str, reason: str, **kw) -> dict:
    return {"available": False, "window": window, "reason": reason, **kw}


def replay(weights: dict[str, float], loss_limit: float | None = None, capital: float | None = None,
           window: str = "covid_2020", folder: Path | None = None) -> dict:
    """The strategy's weights replayed through the window. Fractions (−0.098 = a 9.8% drop), amounts in CAD.

    Returns {available, window, peak, trough, cumulative_return, deepest_drop, deepest_drop_cad, loss_limit,
    loss_limit_cad, within_limit, margin, worst_holdings [{ticker, weight, return, contribution}], usdcad
    {start, end}, path [{date, value}], source, assumptions}; or {available: False, reason, missing?}.
    """
    w = {t: float(v) for t, v in (weights or {}).items() if v and float(v) > 0}
    if not w:
        return _not_available(window, "no weights")
    if not available(folder):
        return _not_available(window, "data/raw_stress/ is missing: run `make data-stress` (needs internet)")
    spec = WINDOWS[window]
    cfg = config(folder)
    try:
        rets = data.returns(cfg=cfg)
    except (Exception, SystemExit) as e:  # noqa: BLE001 — a broken file: say so, don't crash the screen
        return _not_available(window, f"could not read data/raw_stress/ ({type(e).__name__}: {str(e)[:120]})")
    peak, trough = pd.Timestamp(spec["peak"]), pd.Timestamp(spec["trough"])
    inside = rets.loc[(rets.index > peak) & (rets.index <= trough)]
    missing = sorted(t for t in w if t not in inside.columns or inside[t].isna().any())
    if missing:   # never fill a holding with 0% (decision #31): no replay rather than a calmer, wrong one
        return _not_available(window, "no 2020 prices for " + ", ".join(missing), missing=missing)
    port = metrics.portfolio_returns(rets, w)
    if port.empty or port.index[0] > peak or port.index[-1] < trough:
        return _not_available(window, "the stress history does not cover the whole window")
    sc = qt.scenario_analysis(port, {window: (spec["peak"], spec["trough"])})
    cum, drop = float(sc["rendement_cumule"].iloc[0]), float(sc["pire_baisse_dans_fenetre"].iloc[0])
    total = sum(w.values())
    holdings = []
    for t, v in w.items():
        r = float((1 + inside[t]).prod() - 1)
        holdings.append({"ticker": t, "weight": v / total, "return": r, "contribution": v / total * r})
    holdings.sort(key=lambda h: h["contribution"])
    fxs = data._files(cfg)[2].sort_index()
    usdcad = {k: float(fxs[fxs.index <= d].iloc[-1]) for k, d in (("start", peak), ("end", trough))
              if (fxs.index <= d).any()}
    value = (1 + port).cumprod()
    value = value / float(value[value.index <= peak].iloc[-1]) if (value.index <= peak).any() else value
    return {
        "available": True, "window": window, "label": {"en": spec["en"], "fr": spec["fr"]},
        "peak": spec["peak"], "trough": spec["trough"],
        "cumulative_return": cum, "deepest_drop": drop,
        "deepest_drop_cad": round(-drop * capital) if capital else None,
        "loss_limit": loss_limit, "loss_limit_cad": round(loss_limit * capital) if capital and loss_limit else None,
        "within_limit": (-drop <= loss_limit) if loss_limit else None,
        "margin": (loss_limit + drop) if loss_limit else None,   # > 0: room left under the limit
        "worst_holdings": holdings[:3], "usdcad": usdcad,
        "path": [{"date": d.date().isoformat(), "value": float(v)} for d, v in value.items()],
        "source": SOURCE,
        "assumptions": _assumptions(usdcad.get("end", 0) > usdcad.get("start", float("inf")), "en"),
        "assumptions_fr": _assumptions(usdcad.get("end", 0) > usdcad.get("start", float("inf")), "fr"),
    }


def _assumptions(cad_fell: bool, lang: str) -> list[str]:
    if lang == "fr":
        out = ["Rejeu d'un seul épisode passé avec les pondérations d'aujourd'hui, rééquilibrées chaque jour ; ce n'est "
               "pas une prévision du prochain krach.",
               "Pondérations et limites viennent de l'analyse 2021-2026 ; les prix de 2020 ne servent qu'à ce rejeu."]
        if cad_fell:
            out.append("En dollars canadiens : le huard a baissé pendant la fenêtre (USD/CAD en hausse), ce qui a "
                       "amorti la baisse des placements américains pour un investisseur canadien.")
        return out
    out = ["Replay of one past episode on today's weights, rebalanced daily; not a forecast of the next crash.",
           "Weights and limits come from the 2021-2026 analysis; 2020 prices are used only for this replay."]
    if cad_fell:
        out.append("In CAD: the Canadian dollar fell over the window (USD/CAD up), which softened the drop of U.S. "
                   "holdings for a Canadian investor.")
    return out


def _pct(x: float, lang: str, nd: int = 1) -> str:
    s = f"{abs(x) * 100:.{nd}f}"
    return f"{s.replace('.', ',')} %" if lang == "fr" else f"{s}%"


def _cad(x: float, lang: str) -> str:
    return f"{x:,.0f}".replace(",", " ") + " $" if lang == "fr" else f"${x:,.0f}"


def sentence(res: dict, lang: str = "en") -> str:
    """One plain sentence, numbers filled by code (the Explainer's rule: the LLM never types a figure)."""
    if not res.get("available"):
        return ("Rejeu de mars 2020 indisponible : " if lang == "fr" else "March 2020 replay not available: ") \
            + res.get("reason", "")
    drop = _pct(res["deepest_drop"], lang)
    cad = res.get("deepest_drop_cad")
    if lang == "fr":
        s = f"Entre le 19 février et le 23 mars 2020, cette stratégie aurait perdu au pire {drop}"
        s += f" (environ {_cad(cad, lang)})" if cad else ""
        if res.get("loss_limit"):
            lim = _pct(res["loss_limit"], lang, 0)
            s += f", sous votre limite de {lim}" if res["within_limit"] else f", au-delà de votre limite de {lim}"
            s += f" ({_cad(res['loss_limit_cad'], lang)})" if res.get("loss_limit_cad") else ""
        return s + "."
    s = f"Between February 19 and March 23, 2020, this strategy would have lost at worst {drop}"
    s += f" (about {_cad(cad, lang)})" if cad else ""
    if res.get("loss_limit"):
        lim = _pct(res["loss_limit"], lang, 0)
        s += f", within your {lim} limit" if res["within_limit"] else f", beyond your {lim} limit"
        s += f" ({_cad(res['loss_limit_cad'], lang)})" if res.get("loss_limit_cad") else ""
    return s + "."
