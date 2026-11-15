"""Stand-ins: funds a client may hold that are NOT in our data, measured with a fund we have that tracks the same
(or a close) index. Market-data lane (Joud), branch portefeuille_existant.

Why: the BN workshop's own example (XSP.TO, iShares Core S&P 500 Index ETF, CAD-hedged) is not in the starter pack.
Saying "no data" every time a Canadian investor holds a common index ETF makes the review useless, and guessing
silently would be worse. So each stand-in is EXPLICIT, LABELLED and DISCLOSED:

- `STAND_INS`: ticker → (measured with, hedged to CAD?, name, how close). Only funds whose index we can name; a fund
  with its own mix (e.g. ZEQT, an all-equity portfolio) is NOT mapped and stays "no data".
- Unhedged stand-in (VFV.TO ≈ SPY): same index, same currency exposure → SPY's CAD returns. Differences: fees,
  tracking, distributions.
- CAD-hedged stand-in (XSP.TO ≈ SPY hedged): SPY's return in USD (the USD/CAD move removed, Bank of Canada FX)
  + the daily rate gap the hedge earns or pays (Bank of Canada overnight − U.S. fed funds, `macro_rates.csv`).
  Without the macro file the rate gap is left out, and the label says so.

Limits (said wherever a stand-in is used): no fees, no tracking error, hedging cost approximated by the overnight
rate gap, index composition of a "close index" differs (TSX 60 vs TSX Composite).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

SAME = "same index"
# ticker: (measured with, hedged to CAD, fund name, how close)
STAND_INS: dict[str, tuple[str, bool, str, str]] = {
    # S&P 500
    "XSP.TO": ("SPY", True, "iShares Core S&P 500 Index ETF (CAD-Hedged)", f"{SAME} (S&P 500)"),
    "VSP.TO": ("SPY", True, "Vanguard S&P 500 Index ETF (CAD-hedged)", f"{SAME} (S&P 500)"),
    "ZUE.TO": ("SPY", True, "BMO S&P 500 Hedged to CAD Index ETF", f"{SAME} (S&P 500)"),
    "VFV.TO": ("SPY", False, "Vanguard S&P 500 Index ETF", f"{SAME} (S&P 500)"),
    "ZSP.TO": ("SPY", False, "BMO S&P 500 Index ETF", f"{SAME} (S&P 500)"),
    "XUS.TO": ("SPY", False, "iShares Core S&P 500 Index ETF", f"{SAME} (S&P 500)"),
    "HXS.TO": ("SPY", False, "Global X S&P 500 Corporate Class ETF", f"{SAME} (S&P 500)"),
    "VOO": ("SPY", False, "Vanguard S&P 500 ETF", f"{SAME} (S&P 500)"),
    "IVV": ("SPY", False, "iShares Core S&P 500 ETF", f"{SAME} (S&P 500)"),
    # Nasdaq-100
    "XQQ.TO": ("QQQ", True, "iShares NASDAQ 100 Index ETF (CAD-Hedged)", f"{SAME} (Nasdaq-100)"),
    "ZQQ.TO": ("QQQ", True, "BMO NASDAQ 100 Equity Hedged to CAD Index ETF", f"{SAME} (Nasdaq-100)"),
    "ZNQ.TO": ("QQQ", False, "BMO NASDAQ 100 Equity Index ETF", f"{SAME} (Nasdaq-100)"),
    "QQQM": ("QQQ", False, "Invesco NASDAQ 100 ETF", f"{SAME} (Nasdaq-100)"),
    # Canadian equities
    "ZIU.TO": ("XIU.TO", False, "BMO S&P/TSX 60 Index ETF", f"{SAME} (S&P/TSX 60)"),
    "HXT.TO": ("XIU.TO", False, "Global X S&P/TSX 60 Index Corporate Class ETF", f"{SAME} (S&P/TSX 60)"),
    "XIC.TO": ("XIU.TO", False, "iShares Core S&P/TSX Capped Composite Index ETF",
               "close index (S&P/TSX Composite vs TSX 60: about 220 companies vs 60)"),
    "VCN.TO": ("XIU.TO", False, "Vanguard FTSE Canada All Cap Index ETF",
               "close index (FTSE Canada All Cap vs TSX 60)"),
    "ZCN.TO": ("XIU.TO", False, "BMO S&P/TSX Capped Composite Index ETF",
               "close index (S&P/TSX Composite vs TSX 60)"),
    # bonds, gold
    "ZAG.TO": ("XBB.TO", False, "BMO Aggregate Bond Index ETF", "close index (Canadian aggregate bonds)"),
    "VAB.TO": ("XBB.TO", False, "Vanguard Canadian Aggregate Bond Index ETF", "close index (Canadian aggregate bonds)"),
    "BND": ("AGG", False, "Vanguard Total Bond Market ETF", "close index (U.S. aggregate bonds)"),
    "IAU": ("GLD", False, "iShares Gold Trust", "same underlying (gold bullion)"),
}
LIMITS = ("fund fees shown apart, not taken out of the returns; no tracking error; a hedged fund's cost approximated by the overnight rate gap "
          "(Bank of Canada − U.S. fed funds); a close index holds different companies")


VALIDATION_FILE = Path(__file__).with_name("standins_validation.json")   # scripts/validate_standins.py


@lru_cache(maxsize=1)
def validation() -> dict:
    """Real fund vs stand-in, measured once against the fund's own prices (derived statistics only). {} if absent."""
    try:
        return json.loads(VALIDATION_FILE.read_text())
    except (OSError, ValueError):
        return {}


def canonical(ticker: str, have=()) -> str:
    """'xsp' → 'XSP.TO' when only the Toronto listing is known (here or in `have`, the tickers with data)."""
    t = str(ticker).strip().upper()
    if t in have or t in STAND_INS:
        return t
    return f"{t}.TO" if f"{t}.TO" in STAND_INS or f"{t}.TO" in have else t


def stand_in(ticker: str, have) -> dict | None:
    """The stand-in for a ticker we have no data for, if its source is in `have`; None otherwise."""
    if ticker in have or ticker not in STAND_INS:
        return None
    src, hedged, name, how = STAND_INS[ticker]
    if src not in have:
        return None
    out = {"ticker": ticker, "measured_with": src, "hedged": hedged, "name": name, "closeness": how,
           "label": f"{ticker} ({name}) measured with {src}, {how}" + (", currency hedge simulated" if hedged else "")}
    v = validation().get(ticker)
    if v:   # how close the stand-in came to the real fund, checked once on the fund's own prices
        out["checked_against_real"] = {"window": v["window"], "real_worst_drop": v["real"]["worst_drop"],
                                       "stand_in_worst_drop": v["stand_in"]["worst_drop"],
                                       "real_return_2022": v["real"]["return_2022"],
                                       "stand_in_return_2022": v["stand_in"]["return_2022"], "source": v["source"]}
    return out


def _rate_gap(index: pd.DatetimeIndex) -> pd.Series | None:
    """Daily carry of a CAD hedge on USD: (Bank of Canada overnight − U.S. fed funds), per calendar day elapsed."""
    from . import data
    try:
        m = data.macro()
    except SystemExit:
        return None
    rates = {}
    for sid in ("V39079", "DFF"):
        s = m[m.series_id == sid].set_index("date")["value"].sort_index()
        if s.empty:
            return None
        rates[sid] = s.reindex(index.union(s.index)).ffill().reindex(index) / 100
    days = index.to_series().diff().dt.days.fillna(1).clip(lower=1)
    return ((1 + rates["V39079"]) / (1 + rates["DFF"])) ** (days / 365.25) - 1


def hedged_returns(r_cad: pd.Series, fx_rets: pd.Series | None = None, gap: pd.Series | None = None
                   ) -> tuple[pd.Series | None, str]:
    """A USD fund's CAD returns → what a CAD-hedged version would have returned: currency move removed, rate gap
    added. (None, why) if the USD/CAD series is not available."""
    if fx_rets is None:
        from . import data
        try:
            fx = data.fx()
        except SystemExit:
            return None, "no USD/CAD data: the hedge could not be simulated"
        fx = fx.reindex(r_cad.index.union(fx.index)).sort_index().ffill().reindex(r_cad.index)
        fx_rets = fx.pct_change(fill_method=None)
    local = (1 + r_cad) / (1 + fx_rets.reindex(r_cad.index)) - 1
    if gap is None:
        gap = _rate_gap(r_cad.index)
    if gap is None:
        return local, "USD/CAD move removed; rate gap not available, left out"
    return (1 + local) * (1 + gap.reindex(r_cad.index).fillna(0)) - 1, \
        "USD/CAD move removed, overnight rate gap (Bank of Canada − fed funds) added"


def resolve_requests(profile: dict, have) -> tuple[dict, list[dict]]:
    """A request for a fund we have no data for ("10% in XSP") → the same request on its stand-in (SPY), labelled.
    Returns (profile copy, stand-ins used). The currency hedge is NOT simulated for requests (it is in the existing-
    portfolio review): the label says so. Unknown funds without a stand-in are left as they are ("no data")."""
    req = profile.get("requested_positions") or {}
    if not req:
        return profile, []
    out, used = {}, []
    for t, w in req.items():
        tk = canonical(t, have)
        si = None if tk in have else stand_in(tk, have)
        if si:
            used.append({**si, "asked": w,
                         "label": f"{tk} ({si['name']}) measured with {si['measured_with']}, {si['closeness']}"
                                  + (" (its currency hedge is not simulated here)" if si["hedged"] else "")})
            tk = si["measured_with"]
        out[tk] = out.get(tk, 0.0) + w
    if not used:
        return profile, []
    return {**profile, "requested_positions": out, "request_stand_ins": [u["label"] for u in used]}, used
