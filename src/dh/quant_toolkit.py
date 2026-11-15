"""
quant_toolkit.py — Boîte à outils quantitative pour évaluer des produits financiers.

Fusionne, corrige et complète erk.py (cours EDHEC) et evaluation.py.
Autonome : dépend seulement de numpy, pandas et scipy.

CONVENTIONS
-----------
* Rendements SIMPLES par période (0.01 = 1 %), dans une pd.Series (un produit) ou un
  pd.DataFrame (une colonne par produit). Les fonctions marquées « par colonne »
  acceptent les deux et renvoient alors une pd.Series (une valeur par colonne).
* periods_per_year : nombre de périodes par an (12 mensuel, 252 quotidien, 365 crypto…).
  S'il vaut None, il est déduit de l'index de dates.
* Taux annuels en décimal (0.03 = 3 %). Niveaux de VaR en pourcentage de queue (5 = VaR 95 %).
* Valeurs manquantes (NaN) : ignorées. Refusés avec un message explicite (aucune conversion
  silencieuse) : textes, booléens, valeurs infinies, dates en double ou NaT, index de dates
  en texte, rendements < -100 %, données qui ressemblent à des pourcentages ou à des prix,
  prix <= 0.
* Les entrées ne sont jamais modifiées.
* Exceptions : TypeError (mauvais type), ValueError (valeur invalide ou données insuffisantes),
  RuntimeError (échec d'optimisation). Ratio non défini (ex. volatilité nulle) : NaN.
* Les fonctions renvoient des nombres, des pd.Series/DataFrame ou des dict ; to_jsonable()
  convertit n'importe quel résultat en JSON pour un agent.

SECTIONS
--------
0. Validation et utilitaires       to_jsonable, infer_periods_per_year, list_tools
1. Données                          prices_to_returns, returns_to_wealth, resample_returns,
                                    convert_currency, standardize, unsmooth_returns,
                                    data_quality, capabilities
2. Rendement et performance         annualize_return, annualize_vol, sharpe_ratio, sortino_ratio,
                                    calmar_ratio, omega_ratio, probabilistic_sharpe, deflated_sharpe,
                                    summary_stats, scenario_analysis, worst_rolling_return
3. Risque                           drawdown, max_drawdown, drawdown_episodes, ulcer_index,
                                    downside_deviation, semideviation, skewness, kurtosis,
                                    jarque_bera, is_normal, var_historic, var_gaussian, cvar_historic,
                                    evt_var_es, hill_tail_index, ewma_vol, garch11, var_backtest,
                                    var_coverage_tests
4. Séries temporelles et régimes    ljung_box, variance_ratio, variance_breaks, regime_hmm,
                                    trend_signals, rolling_metrics
5. Référence et plusieurs actifs    benchmark_stats, rolling_beta, ledoit_wolf_cov,
                                    correlation_report, holdings_overlap, diversification_stats
6. Construction de portefeuille     portfolio_return, portfolio_vol, min_vol_for_target, gmv_weights,
                                    max_sharpe_weights, risk_parity_weights, efficient_frontier
7. Simulation et objectifs          gbm_paths, bootstrap_paths, bootstrap_ci, goal_probability,
                                    run_cppi, bt_mix, fixedmix_allocator, glidepath_allocator,
                                    floor_allocator, drawdown_allocator, terminal_values, terminal_stats
8. Taux et obligations              inst_to_ann, ann_to_inst, discount, pv, funding_ratio,
                                    bond_cash_flows, bond_price, bond_risk, macaulay_duration,
                                    match_durations, bond_total_return, cir
9. Prédiction et robustesse         walk_forward, oos_r2, diebold_mariano, qlike_loss,
                                    probability_backtest_overfitting
10. Synthèse                        ProductEvaluator
11. Compatibilité                   erk_compat : mêmes noms et signatures qu'erk.py
"""

from __future__ import annotations

import datetime as _dt
import functools
import math
import numbers
import warnings
from itertools import combinations
from types import SimpleNamespace

import numpy as np
import pandas as pd
from scipy import optimize, stats
from scipy.signal import lfilter
from scipy.special import xlogy

__version__ = "1.0.0"

_FREQS = np.array([1, 4, 12, 52, 252, 365])
_EULER_GAMMA = 0.5772156649015329


class QuantWarning(UserWarning):
    """Avertissement : le résultat est calculé mais sa validité est douteuse."""


# =============================================================================
# 0. VALIDATION ET UTILITAIRES
# =============================================================================
def _is_real(v) -> bool:
    return isinstance(v, (numbers.Real, np.integer, np.floating)) and not isinstance(v, (bool, np.bool_))


def _num(v, name, *, lo=None, hi=None, lo_open=False, hi_open=False, integer=False, hint=""):
    """Valide un paramètre numérique scalaire ; renvoie int (integer=True) ou float."""
    if v is None:
        raise TypeError(f"{name} : valeur obligatoire, reçu None")
    if not _is_real(v):
        raise TypeError(f"{name} : nombre attendu, reçu {type(v).__name__} ({v!r})")
    try:
        x = float(v)
    except OverflowError:
        raise ValueError(f"{name} : nombre trop grand ({v!r})") from None
    if not math.isfinite(x):
        raise ValueError(f"{name} : nombre fini attendu, reçu {v!r}")
    if integer:
        if not x.is_integer():
            raise ValueError(f"{name} : entier attendu, reçu {v!r}")
        x = int(x)
    if lo is not None and (x < lo or (lo_open and x == lo)):
        raise ValueError(f"{name} : doit être {'>' if lo_open else '>='} {lo}, reçu {v!r}{hint}")
    if hi is not None and (x > hi or (hi_open and x == hi)):
        raise ValueError(f"{name} : doit être {'<' if hi_open else '<='} {hi}, reçu {v!r}{hint}")
    return x


def _bool(v, name) -> bool:
    if not isinstance(v, (bool, np.bool_)):
        raise TypeError(f"{name} : booléen (True/False) attendu, reçu {type(v).__name__} ({v!r})")
    return bool(v)


def _choice(v, name, options):
    if not isinstance(v, str):
        raise TypeError(f"{name} : texte attendu parmi {sorted(options)}, reçu {type(v).__name__}")
    if v not in options:
        raise ValueError(f"{name} : valeur parmi {sorted(options)} attendue, reçu {v!r}")
    return v


def _seed(seed):
    if seed is None:
        return np.random.default_rng()
    return np.random.default_rng(_num(seed, "seed", lo=0, integer=True))


def _ppy(ppy, index=None, name="periods_per_year") -> int:
    if ppy is None:
        if index is None:
            raise TypeError(f"{name} : obligatoire ici (pas d'index de dates pour le déduire)")
        return infer_periods_per_year(index)
    return _num(ppy, name, lo=1, hi=100_000, integer=True)


def _level(level, name="level") -> float:
    return _num(level, name, lo=0, hi=50, lo_open=True, hi_open=True,
                hint=" (pourcentage de queue : 5 = VaR à 95 %, 1 = VaR à 99 %)")


def _rate(rate, name="riskfree_rate") -> float:
    return _num(rate, name, lo=-1, hi=1, lo_open=True, hint=" (taux annuel en décimal : 0.03 = 3 %)")


def _per_period(rate_annual: float, ppy: int) -> float:
    return (1.0 + rate_annual) ** (1.0 / ppy) - 1.0


def _safe_float(v):
    try:
        return float(v)
    except OverflowError:
        raise ValueError(f"valeur trop grande pour un calcul numérique : {v!r}") from None


def _to_float_series(s: pd.Series, name: str) -> pd.Series:
    """Convertit en float SANS interpréter de texte : les valeurs non numériques sont refusées."""
    dt = s.dtype
    if pd.api.types.is_bool_dtype(dt):
        raise TypeError(f"{name} : valeurs booléennes reçues, nombres attendus")
    if pd.api.types.is_complex_dtype(dt):
        raise TypeError(f"{name} : nombres complexes non acceptés")
    if pd.api.types.is_numeric_dtype(dt):
        return s.astype(float)
    if (isinstance(dt, pd.CategoricalDtype) or pd.api.types.is_datetime64_any_dtype(dt)
            or pd.api.types.is_timedelta64_dtype(dt)):
        raise TypeError(f"{name} : type {dt} non numérique")
    vals = s.tolist()
    bad = [v for v in vals if not (v is None or v is pd.NA or _is_real(v))]
    if bad:
        raise TypeError(f"{name} : {len(bad)} valeur(s) non numérique(s), ex. {bad[:3]!r} ; "
                        "aucune conversion automatique n'est faite (convertir explicitement)")
    return pd.Series([np.nan if (v is None or v is pd.NA) else _safe_float(v) for v in vals],
                     index=s.index, dtype=float, name=s.name)


def _clean_index(idx: pd.Index, name: str) -> pd.Index:
    if isinstance(idx, pd.MultiIndex):
        raise TypeError(f"{name} : index multiple (MultiIndex) non accepté")
    if isinstance(idx, pd.DatetimeIndex):
        if idx.hasnans:
            raise ValueError(f"{name} : dates manquantes (NaT) dans l'index")
        return idx
    if isinstance(idx, pd.PeriodIndex):
        if idx.hasnans:
            raise ValueError(f"{name} : périodes manquantes (NaT) dans l'index")
        return idx
    if pd.api.types.is_integer_dtype(idx.dtype):
        return idx
    if len(idx) and idx.dtype == object and all(isinstance(v, (_dt.date, np.datetime64)) for v in idx):
        return pd.DatetimeIndex(idx)
    if len(idx) == 0:
        return idx
    raise TypeError(f"{name} : index de type {idx.dtype} (ex. {list(idx[:2])!r}). Utiliser des dates "
                    "(pd.to_datetime(..., format=...)) ou des entiers ; les dates en texte ne sont pas "
                    "interprétées automatiquement (risque d'ambiguïté jour/mois)")


def _check_returns(s: pd.Series, name: str) -> None:
    low = s < -1
    if low.any():
        raise ValueError(f"{name} : {int(low.sum())} rendement(s) < -100 % (min {s.min():.4g}). Un rendement "
                         "simple est >= -1 : données en pourcentage (diviser par 100), prix ou log-rendements?")
    big = float((s.abs() > 1).mean())
    if big > 0.05:
        raise ValueError(f"{name} : {big:.0%} des valeurs dépassent ±100 % : probablement des pourcentages "
                         "(5 = 5 %) ou des prix. Diviser par 100, ou convertir les prix avec prices_to_returns")


def _as_series(x, name="r", *, kind="returns", min_obs=2) -> pd.Series:
    """Valide et renvoie une NOUVELLE Series float triée, sans NaN."""
    if isinstance(x, pd.DataFrame):
        if x.shape[1] != 1:
            raise TypeError(f"{name} : une seule série attendue, DataFrame de {x.shape[1]} colonnes reçu")
        x = x.iloc[:, 0]
    if isinstance(x, pd.Series):
        s = x
    elif isinstance(x, np.ndarray) and x.ndim == 1 and x.dtype != object:
        s = pd.Series(x)
    elif isinstance(x, (list, tuple, np.ndarray)):
        arr = np.asarray(x, dtype=object)
        if arr.ndim != 1:
            raise TypeError(f"{name} : données à 1 dimension attendues, reçu {arr.ndim} dimensions")
        s = pd.Series(arr.tolist(), dtype=object)
    else:
        raise TypeError(f"{name} : pd.Series, liste ou tableau numpy attendu, reçu {type(x).__name__}")
    s = _to_float_series(s, name)
    s.index = _clean_index(s.index, name)
    if len(s) == 0:
        raise ValueError(f"{name} : série vide")
    n_inf = int(np.isinf(s.to_numpy()).sum())
    if n_inf:
        raise ValueError(f"{name} : {n_inf} valeur(s) infinie(s)")
    if s.index.has_duplicates:
        raise ValueError(f"{name} : {int(s.index.duplicated().sum())} date(s) ou index en double")
    if not s.index.is_monotonic_increasing:
        s = s.sort_index()
    s = s.dropna()
    if len(s) < min_obs:
        raise ValueError(f"{name} : {len(s)} observation(s) valide(s), il en faut au moins {min_obs} pour ce calcul")
    if kind == "returns":
        _check_returns(s, name)
    elif kind == "prices" and (s <= 0).any():
        raise ValueError(f"{name} : {int((s <= 0).sum())} prix nul(s) ou négatif(s)")
    return s


def _as_frame(x, name="returns", *, kind="returns", min_obs=2, min_cols=1, dropna="any") -> pd.DataFrame:
    """Valide un tableau multi-colonnes ; renvoie un NOUVEAU DataFrame float trié."""
    if isinstance(x, pd.Series):
        x = x.to_frame()
    elif isinstance(x, np.ndarray):
        if x.ndim != 2:
            raise TypeError(f"{name} : tableau à 2 dimensions attendu, reçu {x.ndim}")
        x = pd.DataFrame(x)
    if not isinstance(x, pd.DataFrame):
        raise TypeError(f"{name} : pd.DataFrame attendu, reçu {type(x).__name__}")
    if x.shape[1] < min_cols:
        raise ValueError(f"{name} : au moins {min_cols} colonne(s) attendue(s), reçu {x.shape[1]}")
    if x.columns.has_duplicates:
        raise ValueError(f"{name} : noms de colonnes en double {list(x.columns[x.columns.duplicated()])}")
    fast = len(x.columns) > 0 and all(dt.kind == "f" for dt in x.dtypes)  # already float: validate in one pass
    if fast:
        df = pd.DataFrame(x.to_numpy(dtype=float, copy=True), index=x.index, columns=x.columns)
    else:
        df = pd.DataFrame({c: _to_float_series(x[c], f"{name}[{c!r}]") for c in x.columns}, index=x.index)
    df.index = _clean_index(df.index, name)
    if np.isinf(df.to_numpy()).any():
        raise ValueError(f"{name} : valeurs infinies présentes")
    if df.index.has_duplicates:
        raise ValueError(f"{name} : {int(df.index.duplicated().sum())} date(s) ou index en double")
    if not df.index.is_monotonic_increasing:
        df = df.sort_index()
    if dropna == "any":
        df = df.dropna(how="any")
    elif dropna == "all":
        df = df.dropna(how="all")
    if len(df) < min_obs:
        raise ValueError(f"{name} : {len(df)} ligne(s) complète(s), il en faut au moins {min_obs}")
    if fast:  # same checks as below, vectorised; on failure, re-run the per-column check for its exact message
        a = df.to_numpy()
        if kind == "returns":
            with np.errstate(invalid="ignore"):
                n = (~np.isnan(a)).sum(0)
                bad = ((a < -1).any(0)) | (np.where(n > 0, (np.abs(a) > 1).sum(0) / np.maximum(n, 1), 0) > 0.05)
        elif kind == "prices":
            with np.errstate(invalid="ignore"):
                bad = (a <= 0).any(0)
        else:
            bad = np.zeros(a.shape[1], dtype=bool)
        if not bad.any():
            return df
    for c in df.columns:
        col = df[c].dropna()
        if kind == "returns":
            _check_returns(col, f"{name}[{c!r}]")
        elif kind == "prices" and (col <= 0).any():
            raise ValueError(f"{name}[{c!r}] : prix nuls ou négatifs")
    return df


def _columnwise(func):
    """Applique func colonne par colonne si on lui passe un DataFrame de plusieurs colonnes."""
    @functools.wraps(func)
    def wrapper(r, *args, **kwargs):
        if isinstance(r, pd.DataFrame) and r.shape[1] != 1:
            if r.shape[1] == 0:
                raise ValueError(f"{func.__name__} : DataFrame sans colonne")
            if r.columns.has_duplicates:
                raise ValueError(f"{func.__name__} : noms de colonnes en double")
            out = {}
            for c in r.columns:
                try:
                    out[c] = func(r[c], *args, **kwargs)
                except (TypeError, ValueError) as e:
                    raise type(e)(f"colonne {c!r} : {e}") from e
            return pd.Series(out, name=func.__name__)
        return func(r, *args, **kwargs)
    return wrapper


def _date_str(x) -> str:
    if isinstance(x, pd.Timestamp) and x == x.normalize():
        return x.strftime("%Y-%m-%d")
    if isinstance(x, (_dt.datetime, _dt.date)) and not isinstance(x, pd.Timestamp):
        return x.isoformat()
    return str(x)


def to_jsonable(obj):
    """
    Convertit récursivement un résultat (dict, Series, DataFrame, numpy, dates) en objets JSON.
    NaN → None ; ±inf → "+inf"/"-inf" ; dates → "AAAA-MM-JJ" ; DataFrame → liste d'enregistrements.
    """
    if isinstance(obj, dict):
        return {str(k) if not isinstance(k, (pd.Timestamp, pd.Period)) else _date_str(k): to_jsonable(v)
                for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, pd.DataFrame):
        df = obj if isinstance(obj.index, pd.RangeIndex) else obj.reset_index()
        return to_jsonable(df.to_dict(orient="records"))
    if isinstance(obj, pd.Series):
        return {_date_str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, np.ndarray):
        return to_jsonable(obj.tolist())
    if obj is None or obj is pd.NA or obj is pd.NaT:
        return None
    if isinstance(obj, (pd.Timestamp, pd.Period, _dt.date)):
        return _date_str(obj)
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        f = float(obj)
        if math.isnan(f):
            return None
        if math.isinf(f):
            return "+inf" if f > 0 else "-inf"
        return f
    return obj


def infer_periods_per_year(index) -> int:
    """
    Déduit le nombre de périodes par an d'un index de dates (1, 4, 12, 52, 252 ou 365).

    PeriodIndex annuel, trimestriel, mensuel, hebdomadaire ou ouvré : lu directement.
    Sinon : nombre d'observations / années couvertes, arrondi à la fréquence standard la plus
    proche (en échelle log). 365 correspond à des données calendaires (cryptoactifs).
    Données intrajournalières : passer periods_per_year explicitement.
    """
    if isinstance(index, pd.PeriodIndex):
        code = index.freqstr.split("-")[0].upper()
        mapping = {"Y": 1, "A": 1, "Q": 4, "M": 12, "W": 52, "B": 252}
        if code in mapping:
            return mapping[code]
        index = index.to_timestamp()
    if not isinstance(index, pd.DatetimeIndex):
        raise ValueError("Impossible de déduire la fréquence : l'index n'est pas un index de dates. "
                         "Passer periods_per_year (ex. 12 mensuel, 252 quotidien)")
    idx = index.dropna().unique().sort_values()
    if len(idx) < 3:
        raise ValueError("Au moins 3 dates distinctes sont nécessaires pour déduire la fréquence")
    years = (idx[-1] - idx[0]).total_seconds() / (365.25 * 86400)
    if years <= 0:
        raise ValueError("Dates identiques : impossible de déduire la fréquence")
    raw = (len(idx) - 1) / years
    return int(_FREQS[np.argmin(np.abs(np.log(_FREQS / raw)))])


def _robust_z(a: np.ndarray) -> np.ndarray:
    med = np.median(a)
    mad = np.median(np.abs(a - med))
    if mad == 0:
        mad = np.mean(np.abs(a - med)) * 0.7979  # repli : écart absolu moyen ramené à l'échelle du MAD
        if mad == 0:
            return np.zeros_like(a)
    return 0.6745 * (a - med) / mad


# =============================================================================
# 1. DONNÉES : PRÉPARATION, TRANSFORMATION, QUALITÉ
# =============================================================================
def prices_to_returns(prices, *, log: bool = False):
    """
    Convertit des prix (ou une valeur liquidative) en rendements simples (log=True : log-rendements).

    Utiliser des prix AJUSTÉS (distributions réinvesties) pour un rendement total. Un prix manquant
    est ignoré : le rendement suivant couvre alors toute la période (prix à prix), ce qui reste exact.
    Prix <= 0 refusés. Accepte une Series ou un DataFrame (une colonne par produit).
    """
    log = _bool(log, "log")
    if isinstance(prices, pd.DataFrame) and prices.shape[1] > 1:
        df = _as_frame(prices, "prices", kind="prices", min_obs=2, dropna="all")
        out = {}
        for c in df.columns:
            p = df[c].dropna()
            out[c] = (np.log(p).diff() if log else p.pct_change()).iloc[1:]
        return pd.DataFrame(out)
    p = _as_series(prices, "prices", kind="prices", min_obs=2)
    return (np.log(p).diff() if log else p.pct_change()).iloc[1:]


def returns_to_wealth(r, *, start: float = 1.0) -> pd.Series:
    """Indice de richesse : start × produit cumulé de (1 + r). Une perte de -100 % donne 0."""
    s = _as_series(r, "r", min_obs=1)
    start = _num(start, "start", lo=0, lo_open=True)
    with np.errstate(divide="ignore"):
        return start * np.exp(np.cumsum(np.log1p(s)))


def resample_returns(r, rule: str = "ME", *, drop_incomplete: bool = True) -> pd.Series:
    """
    Agrège des rendements à une fréquence plus basse en les COMPOSANT : (1+r1)(1+r2)… - 1.
    rule : "W" (semaine), "ME" (mois), "QE" (trimestre), "YE" (année).
    drop_incomplete : retire la première et la dernière période si elles contiennent moins de la
    moitié du nombre habituel d'observations (ex. un trimestre qui ne compte qu'un mois).
    Utile pour comparer des produits observés à des fréquences différentes.
    """
    rules = {"W": "W", "ME": "ME", "M": "ME", "QE": "QE", "Q": "QE", "YE": "YE", "Y": "YE", "A": "YE"}
    rule = _choice(rule, "rule", set(rules))
    drop_incomplete = _bool(drop_incomplete, "drop_incomplete")
    s = _as_series(r, "r", min_obs=2)
    if isinstance(s.index, pd.PeriodIndex):
        s.index = s.index.to_timestamp()
    if not isinstance(s.index, pd.DatetimeIndex):
        raise TypeError("r : index de dates nécessaire pour changer de fréquence")
    with np.errstate(divide="ignore"):
        g = np.log1p(s).groupby(pd.Grouper(freq=rules[rule]))
        total, counts = g.sum(min_count=1), g.count()
    keep = counts > 0
    out, counts = np.expm1(total[keep]), counts[keep]
    if drop_incomplete and len(out) >= 3:
        med = counts.median()
        if counts.iloc[-1] < 0.5 * med:
            out = out.iloc[:-1]
        if counts.iloc[0] < 0.5 * med:
            out = out.iloc[1:]
    return out


def convert_currency(r_foreign, fx_returns) -> pd.Series:
    """
    Rendement en devise locale d'un placement libellé en devise étrangère :
    (1 + r_étranger)(1 + r_change) - 1.
    fx_returns : variation du prix de la devise étrangère en devise locale (USDCAD qui monte = +).
    Les dates doivent correspondre (au moins 90 % de dates communes), sinon ValueError.
    Montre l'effet du risque de change, ex. un FNB américain détenu en CAD (couvert vs non couvert).
    """
    a = _as_series(r_foreign, "r_foreign", min_obs=2)
    f = _as_series(fx_returns, "fx_returns", min_obs=2)
    if type(a.index) is not type(f.index):
        raise TypeError("r_foreign et fx_returns : types d'index différents")
    df = pd.concat([a.rename("a"), f.rename("f")], axis=1, join="inner")
    if len(df) < 0.9 * min(len(a), len(f)):
        raise ValueError(f"seulement {len(df)} dates communes sur {min(len(a), len(f))} : dates mal alignées?")
    return ((1 + df["a"]) * (1 + df["f"]) - 1).rename(a.name)


def standardize(x, *, method: str = "zscore", window: int | None = None, min_periods: int = 20) -> pd.Series:
    """
    Normalisation CAUSALE (sans fuite de données) : la valeur en t n'utilise que les données
    jusqu'à t inclus, sur une fenêtre croissante (window=None) ou glissante (window=n).
    method : "zscore" (moyenne/écart-type), "robust" (médiane / 1,4826 × MAD, peu sensible aux
    valeurs extrêmes), "rank" (rang centile dans la fenêtre, entre 0 et 1).
    Les premières valeurs (avant min_periods) sont NaN. Sert à préparer des variables pour des
    modèles prédictifs ; une normalisation sur tout l'échantillon utiliserait le futur.
    """
    method = _choice(method, "method", {"zscore", "robust", "rank"})
    s = _as_series(x, "x", kind="any", min_obs=2)
    mp = _num(min_periods, "min_periods", lo=2, integer=True)
    if window is not None:
        window = _num(window, "window", lo=2, integer=True)
        if mp > window:
            raise ValueError(f"min_periods ({mp}) ne peut pas dépasser window ({window})")
        roll = s.rolling(window, min_periods=mp)
    else:
        roll = s.expanding(min_periods=mp)
    if method == "zscore":
        out = (s - roll.mean()) / roll.std()
    elif method == "robust":
        med = roll.median()
        mad = roll.apply(lambda a: np.median(np.abs(a - np.median(a))), raw=True)
        out = (s - med) / (1.4826 * mad)
    else:
        out = roll.rank(pct=True)
    return out.replace([np.inf, -np.inf], np.nan)


def unsmooth_returns(r) -> dict:
    """
    Désaisonnement du lissage des prix (Geltner, 1993) : r*_t = (r_t - rho r_{t-1}) / (1 - rho),
    rho = autocorrélation d'ordre 1.
    Pour les actifs peu liquides ou évalués par modèle (immobilier, fonds privés, certains fonds
    alternatifs), les rendements publiés sont lissés et sous-estiment la volatilité réelle.
    Renvoie les rendements corrigés, rho, et le rapport des volatilités (corrigée / publiée).
    Limite : suppose un lissage AR(1) ; inutile si rho n'est pas significativement positif.
    """
    s = _as_series(r, "r", min_obs=24)
    x = s.to_numpy()
    xc = x - x.mean()
    rho = float(np.sum(xc[1:] * xc[:-1]) / np.sum(xc ** 2)) if np.sum(xc ** 2) > 0 else np.nan
    if not np.isfinite(rho) or abs(rho) >= 0.95:
        raise ValueError(f"autocorrélation d'ordre 1 = {rho:.3f} : correction instable (|rho| >= 0,95)")
    u = (s - rho * s.shift(1)).iloc[1:] / (1 - rho)
    return {"rendements": u, "rho": rho,
            "lissage_significatif": bool(rho > 2 / np.sqrt(len(s))),
            "ratio_volatilite": float(u.std() / s.std()) if s.std() > 0 else np.nan}


def data_quality(x, *, kind: str = "returns", z_threshold: float = 5.0) -> dict:
    """
    Diagnostic de qualité d'une série de prix ou de rendements. Ne plante pas sur des données
    sales : il les décrit. Contrôle : valeurs non numériques, manquantes ou infinies, dates en
    double ou désordonnées, prix <= 0, rendements < -100 %, unités suspectes (pourcentages ou prix
    passés comme rendements), prix figés (rendements nuls consécutifs), trous dans les dates,
    valeurs extrêmes (score z robuste ; Iglewicz & Hoaglin, 1993) et allers-retours suspects
    (forte hausse suivie d'une forte baisse qui l'annule : erreur de cotation probable).
    'utilisable' = False si un problème bloquant empêche les autres fonctions de calculer.
    """
    kind = _choice(kind, "kind", {"returns", "prices"})
    z_threshold = _num(z_threshold, "z_threshold", lo=1)
    if isinstance(x, pd.DataFrame):
        if x.shape[1] != 1:
            raise TypeError("x : une seule série attendue (diagnostiquer chaque colonne séparément)")
        x = x.iloc[:, 0]
    if isinstance(x, (list, tuple, np.ndarray)):
        arr = np.asarray(x, dtype=object)
        if arr.ndim != 1:
            raise TypeError("x : données à 1 dimension attendues")
        x = pd.Series(arr.tolist(), dtype=object)
    if not isinstance(x, pd.Series):
        raise TypeError(f"x : pd.Series, liste ou tableau attendu, reçu {type(x).__name__}")

    out = {"n_obs_brut": int(len(x)), "type_index": type(x.index).__name__}
    blocking, alerts = [], []
    if pd.api.types.is_bool_dtype(x.dtype):
        non_num = np.ones(len(x), bool)
        vals = pd.Series(np.nan, index=x.index)
    elif pd.api.types.is_numeric_dtype(x.dtype) and not pd.api.types.is_complex_dtype(x.dtype):
        non_num = np.zeros(len(x), bool)
        vals = x.astype(float)
    else:
        items = x.tolist()
        non_num = np.array([not (v is None or v is pd.NA or _is_real(v)) for v in items], bool)
        conv = []
        for v, bad in zip(items, non_num):
            try:
                conv.append(np.nan if bad or v is None or v is pd.NA else float(v))
            except OverflowError:
                conv.append(np.inf)
        vals = pd.Series(conv, index=x.index, dtype=float)
    out["valeurs_non_numeriques"] = int(non_num.sum())
    out["valeurs_manquantes"] = int(vals.isna().sum() - non_num.sum())
    inf_mask = np.isinf(vals.to_numpy())
    out["valeurs_infinies"] = int(inf_mask.sum())
    out["dates_en_double"] = int(x.index.duplicated().sum())
    try:
        out["index_trie"] = bool(x.index.is_monotonic_increasing)
    except TypeError:
        out["index_trie"] = False
    if out["valeurs_non_numeriques"]:
        blocking.append(f"{out['valeurs_non_numeriques']} non-numeric value(s)")
    if out["valeurs_infinies"]:
        blocking.append(f"{out['valeurs_infinies']} infinite value(s)")
    if out["dates_en_double"]:
        blocking.append(f"{out['dates_en_double']} duplicate date(s)")
    if not out["index_trie"]:
        alerts.append("index not sorted (the functions sort it automatically)")
    if len(x) and out["valeurs_manquantes"] / len(x) > 0.05:
        alerts.append(f"{out['valeurs_manquantes'] / len(x):.0%} missing values")

    clean = vals[~inf_mask].dropna()
    clean = clean[~clean.index.duplicated(keep="last")]
    try:
        clean = clean.sort_index()
    except TypeError:
        blocking.append("mixed index types: cannot sort")
    if kind == "prices":
        nonpos = int((clean <= 0).sum())
        out["prix_non_positifs"] = nonpos
        if nonpos:
            blocking.append(f"{nonpos} zero or negative price(s)")
        p = clean[clean > 0]
        r = p.pct_change().iloc[1:] if len(p) > 1 else p.iloc[0:0]
    else:
        r = clean
        below = int((r < -1).sum())
        frac = float((r.abs() > 1).mean()) if len(r) else 0.0
        out["rendements_sous_moins_100pct"], out["part_au_dela_100pct"] = below, frac
        if below:
            blocking.append(f"{below} return(s) below -100% (impossible for a simple return)")
        if frac > 0.05:
            blocking.append(f"{frac:.0%} of values exceed ±100%: percentages or prices?")
        elif len(r) >= 3 and (r > 0).all() and r.median() > 0.5:
            blocking.append("all values positive and large: probably prices (kind='prices')")
    out["n_obs_utilisables"] = int(len(r))
    if len(r) < 3:
        blocking.append("fewer than 3 usable observations")
        out.update(problemes_bloquants=blocking, alertes=blocking + alerts, utilisable=False)
        return out

    out["debut"], out["fin"] = _date_str(r.index[0]), _date_str(r.index[-1])
    try:
        ppy = infer_periods_per_year(r.index)
        out["periodes_par_an"], out["annees_couvertes"] = ppy, round(len(r) / ppy, 2)
    except ValueError:
        out["periodes_par_an"] = None
    zero = (r == 0).astype(int)
    out["plus_longue_serie_rendements_nuls"] = int(zero.groupby((zero != zero.shift()).cumsum()).cumsum().max())
    if out["plus_longue_serie_rendements_nuls"] >= 5:
        alerts.append(f"{out['plus_longue_serie_rendements_nuls']} consecutive zero returns (frozen price?)")
    if isinstance(r.index, (pd.DatetimeIndex, pd.PeriodIndex)):
        ts = r.index.to_timestamp() if isinstance(r.index, pd.PeriodIndex) else r.index
        gaps = pd.Series(ts).diff().dt.total_seconds().dropna() / 86400
        if len(gaps):
            out["ecart_median_jours"], out["plus_grand_trou_jours"] = float(gaps.median()), float(gaps.max())
            if out["plus_grand_trou_jours"] > 5 * max(out["ecart_median_jours"], 1):
                alerts.append(f"gap of {out['plus_grand_trou_jours']:.0f} days in the dates")
    a = r.to_numpy()
    z = _robust_z(a)
    extreme = np.abs(z) > z_threshold
    out["n_valeurs_extremes"] = int(extreme.sum())
    order = np.argsort(-np.abs(z))[: min(10, int(extreme.sum()))]
    out["valeurs_extremes"] = {_date_str(r.index[i]): float(a[i]) for i in order}
    if extreme.any():
        alerts.append(f"{int(extreme.sum())} extreme value(s) (|robust z| > {z_threshold:g}): "
                      "real crises or data errors?")
    rev = [i for i in range(len(a) - 1)
           if extreme[i] and extreme[i + 1] and a[i] * a[i + 1] < 0
           and abs((1 + a[i]) * (1 + a[i + 1]) - 1) < 0.2 * min(abs(a[i]), abs(a[i + 1]))]
    out["allers_retours_suspects"] = [_date_str(r.index[i]) for i in rev]
    if rev:
        alerts.append(f"{len(rev)} suspicious round trip(s): likely a pricing error")
    out.update(problemes_bloquants=blocking, alertes=blocking + alerts, utilisable=not blocking)
    return out


def capabilities(r, benchmark=None, periods_per_year=None) -> dict:
    """
    Indique quelles analyses sont réalisables avec ces données, et pourquoi.
    Aide l'agent à choisir les outils adaptés au dataset (longueur, fréquence, dates, référence).
    """
    s = _as_series(r, "r", min_obs=2)
    n = len(s)
    try:
        ppy = _ppy(periods_per_year, s.index)
    except ValueError:
        ppy = None
    dates = isinstance(s.index, (pd.DatetimeIndex, pd.PeriodIndex))
    overlap = 0
    if benchmark is not None:
        b = _as_series(benchmark, "benchmark", min_obs=2)
        overlap = len(s.index.intersection(b.index))

    def cap(ok, why):
        return {"possible": bool(ok), "condition": why}

    win = _default_var_window(ppy) if ppy else None
    return {
        "n_obs": n, "periodes_par_an": ppy, "index_de_dates": dates,
        "analyses": {
            "statistiques_de_base": cap(n >= 12 and ppy is not None, "≥ 12 obs. et fréquence connue"),
            "sharpe_probabiliste": cap(n >= 30 and ppy is not None, "≥ 30 obs."),
            "sharpe_ajuste_lo": cap(ppy is not None and ppy <= 52 and n >= 5 * ppy, "données ≤ hebdomadaires, ≥ 5 ans"),
            "intervalles_bootstrap": cap(n >= 30 and ppy is not None, "≥ 30 obs."),
            "backtest_var": cap(win is not None and n - win >= 50, "≥ fenêtre d'estimation + 50 obs."),
            "var_evt": cap(n >= 500, "≥ 500 obs. (≥ 25 dépassements au seuil de 95 %)"),
            "indice_de_queue_hill": cap(n >= 100, "≥ 100 obs."),
            "garch": cap(n >= 500 and ppy is not None and ppy >= 52, "≥ 500 obs., données quotidiennes ou hebdomadaires"),
            "regimes_hmm": cap(n >= 200, "≥ 200 obs."),
            "ruptures_volatilite": cap(n >= 60 and ppy is not None, "≥ 60 obs."),
            "metriques_glissantes_3_ans": cap(ppy is not None and n >= 3 * ppy + 12, "≥ 3 ans + 12 obs."),
            "pire_rendement_1_an": cap(ppy is not None and n > ppy, "> 1 an d'historique"),
            "scenarios_de_crise": cap(dates, "index de dates"),
            "comparaison_reference": cap(benchmark is not None and overlap >= 24, "référence avec ≥ 24 dates communes"),
        },
    }


# =============================================================================
# 2. RENDEMENT ET PERFORMANCE
# =============================================================================
@_columnwise
def annualize_return(r, periods_per_year=None) -> float:
    """
    Rendement annualisé géométrique : (Π(1 + r))^(périodes par an / n) - 1. Par colonne.
    Correction d'erk.annualize_rets : n = nombre d'observations VALIDES (erk comptait les NaN,
    ce qui sous-estimait fortement le rendement quand des données manquaient).
    """
    s = _as_series(r, "r", min_obs=1)
    ppy = _ppy(periods_per_year, s.index)
    with np.errstate(divide="ignore", over="ignore"):
        return float(np.expm1(np.log1p(s.to_numpy()).sum() * ppy / len(s)))


@_columnwise
def annualize_vol(r, periods_per_year=None) -> float:
    """Volatilité annualisée : écart-type (ddof=1) × racine(périodes par an). Par colonne."""
    s = _as_series(r, "r", min_obs=2)
    return float(s.std(ddof=1) * np.sqrt(_ppy(periods_per_year, s.index)))


def _lo_eta(x: np.ndarray, q: int) -> float:
    xc = x - x.mean()
    denom = np.sum(xc ** 2)
    rho = np.array([np.sum(xc[k:] * xc[:-k]) / denom for k in range(1, q)])
    inner = q + 2 * np.sum((q - np.arange(1, q)) * rho)
    return float(q / np.sqrt(inner)) if inner > 0 else np.nan


@_columnwise
def sharpe_ratio(r, periods_per_year=None, *, riskfree_rate: float = 0.0, method: str = "arithmetic",
                 autocorr_adjusted: bool = False) -> float:
    """
    Ratio de Sharpe annualisé (Sharpe, 1966). Par colonne.
    method="arithmetic" : moyenne / écart-type des rendements excédentaires × racine(ppy) (standard).
    method="geometric"  : rendement excédentaire annualisé géométrique / volatilité (version d'erk).
    autocorr_adjusted=True : annualisation corrigée de l'autocorrélation (Lo, 2002) ; la règle
    racine(ppy) suppose des rendements indépendants et surestime le Sharpe de rendements lissés.
    Réservé aux données au plus hebdomadaires (sinon trop de retards à estimer). NaN si volatilité nulle.
    """
    s = _as_series(r, "r", min_obs=3)
    ppy = _ppy(periods_per_year, s.index)
    rf = _rate(riskfree_rate)
    method = _choice(method, "method", {"arithmetic", "geometric"})
    adj = _bool(autocorr_adjusted, "autocorr_adjusted")
    ex = s - _per_period(rf, ppy)
    sd = ex.std(ddof=1)
    if sd == 0:
        return np.nan
    if method == "geometric":
        if adj:
            raise ValueError("autocorr_adjusted n'est disponible qu'avec method='arithmetic'")
        return float(annualize_return(ex, ppy) / (s.std(ddof=1) * np.sqrt(ppy)))
    sr = ex.mean() / sd
    if not adj:
        return float(sr * np.sqrt(ppy))
    if ppy > 52:
        raise ValueError("autocorr_adjusted : réservé aux données au plus hebdomadaires (ppy <= 52)")
    if len(s) < 5 * ppy:
        raise ValueError(f"autocorr_adjusted : au moins {5 * ppy} observations nécessaires (5 ans)")
    return float(sr * _lo_eta(ex.to_numpy(), ppy))


@_columnwise
def sortino_ratio(r, periods_per_year=None, *, riskfree_rate: float = 0.0) -> float:
    """
    Ratio de Sortino : (rendement annualisé - taux sans risque) / écart de baisse sous le taux sans
    risque (Sortino & Price, 1994). Ne pénalise que la volatilité à la baisse. NaN si aucune baisse.
    """
    s = _as_series(r, "r", min_obs=3)
    ppy = _ppy(periods_per_year, s.index)
    rf = _rate(riskfree_rate)
    dd = downside_deviation(s, ppy, target=rf)
    if dd == 0:
        return np.nan
    return float((annualize_return(s, ppy) - rf) / dd)


@_columnwise
def calmar_ratio(r, periods_per_year=None) -> float:
    """Ratio de Calmar : rendement annualisé / |perte maximale| (Young, 1991). NaN sans perte."""
    s = _as_series(r, "r", min_obs=2)
    mdd = max_drawdown(s)
    return np.nan if mdd == 0 else float(annualize_return(s, _ppy(periods_per_year, s.index)) / abs(mdd))


@_columnwise
def omega_ratio(r, *, threshold: float = 0.0) -> float:
    """
    Ratio Omega au seuil (par période) : somme des gains au-dessus / somme des pertes en dessous
    (Keating & Shadwick, 2002). Utilise toute la distribution. +inf s'il n'y a aucune perte.
    """
    s = _as_series(r, "r", min_obs=2)
    t = _num(threshold, "threshold", lo=-1, hi=1)
    gains, losses = np.maximum(s - t, 0).sum(), np.maximum(t - s, 0).sum()
    return float(gains / losses) if losses > 0 else np.inf


def probabilistic_sharpe(r, periods_per_year=None, *, riskfree_rate: float = 0.0,
                         benchmark_sharpe: float = 0.0, confidence: float = 0.95) -> dict:
    """
    Ratio de Sharpe probabiliste (PSR) et durée minimale d'historique (Bailey & López de Prado, 2012).

    PSR = probabilité que le vrai Sharpe dépasse benchmark_sharpe (annualisé), compte tenu de la
    longueur de l'historique, de l'asymétrie et de l'aplatissement. La durée minimale est le nombre
    d'observations nécessaires pour que le Sharpe observé soit significatif au niveau `confidence`.
    Un Sharpe élevé mesuré sur peu de données, ou avec des queues épaisses, obtient un PSR faible.
    """
    s = _as_series(r, "r", min_obs=10)
    ppy = _ppy(periods_per_year, s.index)
    rf = _rate(riskfree_rate)
    sr_b = _num(benchmark_sharpe, "benchmark_sharpe", lo=-20, hi=20)
    conf = _num(confidence, "confidence", lo=0.5, hi=1, hi_open=True)
    ex = (s - _per_period(rf, ppy)).to_numpy()
    sd = ex.std(ddof=1)
    out = {"n_obs": len(ex)}
    if sd == 0:
        return {**out, "sharpe_annualise": np.nan, "psr": np.nan, "duree_min_periodes": np.nan, "duree_min_annees": np.nan}
    sr = ex.mean() / sd
    sr_star = sr_b / np.sqrt(ppy)
    xc = ex - ex.mean()
    m2 = np.mean(xc ** 2)
    g3, g4 = np.mean(xc ** 3) / m2 ** 1.5, np.mean(xc ** 4) / m2 ** 2
    denom = 1 - g3 * sr + (g4 - 1) / 4 * sr ** 2
    out["sharpe_annualise"] = float(sr * np.sqrt(ppy))
    if denom <= 0:
        return {**out, "psr": np.nan, "duree_min_periodes": np.nan, "duree_min_annees": np.nan}
    out["psr"] = float(stats.norm.cdf((sr - sr_star) * np.sqrt(len(ex) - 1) / np.sqrt(denom)))
    if sr > sr_star:
        mintrl = 1 + denom * (stats.norm.ppf(conf) / (sr - sr_star)) ** 2
        out["duree_min_periodes"], out["duree_min_annees"] = float(mintrl), float(mintrl / ppy)
    else:
        out["duree_min_periodes"] = out["duree_min_annees"] = np.inf
    return out


def deflated_sharpe(r, periods_per_year=None, *, n_trials=None, trials_sharpe_std=None, trials=None,
                    riskfree_rate: float = 0.0) -> dict:
    """
    Ratio de Sharpe dégonflé (DSR ; Bailey & López de Prado, 2014).

    Quand on choisit le meilleur produit ou la meilleure stratégie parmi N essais, le meilleur Sharpe
    est gonflé par la chance. Le DSR est le PSR calculé contre le Sharpe maximal attendu sous
    l'hypothèse « aucun essai n'a de vrai talent ». Fournir soit `trials` (DataFrame des rendements
    de tous les essais), soit n_trials et trials_sharpe_std (écart-type des Sharpe annualisés des essais).
    """
    s = _as_series(r, "r", min_obs=10)
    ppy = _ppy(periods_per_year, s.index)
    if trials is not None:
        t = _as_frame(trials, "trials", min_obs=10, min_cols=2)
        srs = np.array([sharpe_ratio(t[c], ppy, riskfree_rate=riskfree_rate) for c in t.columns])
        srs = srs[np.isfinite(srs)]
        if len(srs) < 2:
            raise ValueError("trials : au moins 2 essais avec un Sharpe défini")
        n_trials = len(srs) if n_trials is None else n_trials
        trials_sharpe_std = float(np.std(srs, ddof=1))
    n = _num(n_trials, "n_trials", lo=2, integer=True)
    sd = _num(trials_sharpe_std, "trials_sharpe_std", lo=0, lo_open=True)
    v = (sd / np.sqrt(ppy)) ** 2
    sr0 = np.sqrt(v) * ((1 - _EULER_GAMMA) * stats.norm.ppf(1 - 1 / n)
                        + _EULER_GAMMA * stats.norm.ppf(1 - 1 / (n * np.e)))
    psr = probabilistic_sharpe(s, ppy, riskfree_rate=riskfree_rate, benchmark_sharpe=float(sr0 * np.sqrt(ppy)))
    return {"dsr": psr["psr"], "sharpe_annualise": psr["sharpe_annualise"],
            "sharpe_max_attendu_par_chance": float(sr0 * np.sqrt(ppy)), "n_essais": n,
            "ecart_type_sharpe_essais": sd}


def summary_stats(r, periods_per_year=None, *, riskfree_rate: float = 0.0, level: float = 5) -> pd.DataFrame:
    """
    Tableau récapitulatif par produit : rendement et volatilité annualisés, asymétrie, aplatissement,
    VaR Cornish-Fisher, CVaR historique, Sharpe, Sortino, perte maximale.
    Remplace erk.summary_stats, qui supposait toujours des données mensuelles.
    """
    df = _as_frame(r, "r", min_obs=4, dropna="all")
    lvl, rf = _level(level), _rate(riskfree_rate)
    rows = {}
    for c in df.columns:
        s = df[c].dropna()
        ppy = _ppy(periods_per_year, s.index)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", QuantWarning)
            cf = var_gaussian(s, lvl, modified=True)
        rows[c] = {"rendement_annualise": annualize_return(s, ppy), "volatilite_annualisee": annualize_vol(s, ppy),
                   "asymetrie": skewness(s), "aplatissement": kurtosis(s),
                   f"var_cornish_fisher_{lvl:g}pct": cf, f"cvar_historique_{lvl:g}pct": cvar_historic(s, lvl),
                   "sharpe": sharpe_ratio(s, ppy, riskfree_rate=rf), "sortino": sortino_ratio(s, ppy, riskfree_rate=rf),
                   "perte_maximale": max_drawdown(s)}
    return pd.DataFrame(rows).T


DEFAULT_SCENARIOS = {
    "bulle_techno_2000_2002": ("2000-03-24", "2002-10-09"),
    "crise_financiere_2007_2009": ("2007-10-09", "2009-03-09"),
    "dette_europeenne_2011": ("2011-04-29", "2011-10-03"),
    "chute_fin_2018": ("2018-09-20", "2018-12-24"),
    "covid_2020": ("2020-02-19", "2020-03-23"),
    "hausse_des_taux_2022": ("2022-01-03", "2022-10-12"),
}
"""Fenêtres sommet-creux du S&P 500 (indicatives). Passer ses propres scénarios au besoin."""


def scenario_analysis(r, scenarios: dict | None = None) -> pd.DataFrame:
    """
    Comportement du produit pendant des crises historiques : rendement cumulé et pire baisse dans
    chaque fenêtre. Par défaut : DEFAULT_SCENARIOS (sommets et creux du S&P 500).
    Avec des données mensuelles, une crise courte (COVID) n'est vue qu'approximativement :
    la colonne 'precision' le signale. Les fenêtres hors des données sont omises.
    """
    s = _as_series(r, "r", min_obs=2)
    if not isinstance(s.index, (pd.DatetimeIndex, pd.PeriodIndex)):
        raise TypeError("r : index de dates nécessaire pour l'analyse de scénarios")
    scen = DEFAULT_SCENARIOS if scenarios is None else scenarios
    if not isinstance(scen, dict) or not scen:
        raise TypeError("scenarios : dict non vide {nom: (début, fin)} attendu")
    if isinstance(s.index, pd.PeriodIndex):
        starts, ends = s.index.to_timestamp(how="start"), s.index.to_timestamp(how="end")
    else:
        starts = ends = s.index
    if getattr(starts, "tz", None) is not None:
        starts, ends = starts.tz_localize(None), ends.tz_localize(None)
    try:
        ppy = infer_periods_per_year(s.index)
    except ValueError:
        ppy = None
    rows = []
    for name, window in scen.items():
        if not isinstance(window, (tuple, list)) or len(window) != 2:
            raise TypeError(f"scénario {name!r} : (début, fin) attendu")
        try:
            a, b = (pd.to_datetime(w, format="ISO8601") for w in window)
        except (ValueError, TypeError) as e:
            raise ValueError(f"scénario {name!r} : dates au format AAAA-MM-JJ attendues ({e})") from None
        if a >= b:
            raise ValueError(f"scénario {name!r} : la date de début doit précéder la date de fin")
        mask = (ends >= a) & (starts <= b)
        sub = s[np.asarray(mask)]
        if len(sub) == 0:
            continue
        rows.append({"scenario": name, "debut": _date_str(a), "fin": _date_str(b), "n_obs": len(sub),
                     "rendement_cumule": float(np.prod(1 + sub) - 1),
                     "pire_baisse_dans_fenetre": float(drawdown(sub)["Drawdown"].min()),
                     "precision": "approximative" if (ppy is not None and ppy < 52) else "bonne"})
    return pd.DataFrame(rows, columns=["scenario", "debut", "fin", "n_obs", "rendement_cumule",
                                       "pire_baisse_dans_fenetre", "precision"])


def worst_rolling_return(r, periods_per_year=None, *, horizon_years: float = 1.0) -> dict:
    """
    Pire, médian et meilleur rendement composé sur toutes les fenêtres glissantes de `horizon_years`,
    et part des fenêtres positives. C'est la mesure la plus parlante pour un investisseur
    (« la pire année aurait coûté X % »). Les fenêtres se chevauchent : elles ne sont pas indépendantes.
    """
    s = _as_series(r, "r", min_obs=2)
    ppy = _ppy(periods_per_year, s.index)
    hy = _num(horizon_years, "horizon_years", lo=0, lo_open=True)
    h = int(round(hy * ppy))
    if h < 1 or h > len(s):
        raise ValueError(f"horizon de {h} périodes incompatible avec {len(s)} observations")
    with np.errstate(divide="ignore"):
        roll = np.expm1(np.log1p(s).rolling(h).sum()).dropna()
    return {"horizon_periodes": h, "n_fenetres": len(roll), "pire": float(roll.min()),
            "date_fin_pire": _date_str(roll.idxmin()), "mediane": float(roll.median()),
            "meilleure": float(roll.max()), "part_fenetres_positives": float((roll > 0).mean())}


# =============================================================================
# 3. RISQUE
# =============================================================================
def drawdown(r, *, start: float = 1000.0) -> pd.DataFrame:
    """
    Indice de richesse, sommet précédent et drawdown (colonnes identiques à erk.drawdown).
    Correction : le capital initial compte comme premier sommet ; erk ignorait une perte à la
    première période.
    """
    s = _as_series(r, "r", min_obs=1)
    start = _num(start, "start", lo=0, lo_open=True)
    with np.errstate(divide="ignore"):
        wealth = start * np.exp(np.cumsum(np.log1p(s.to_numpy())))
    peaks = np.maximum.accumulate(np.maximum(wealth, start))
    return pd.DataFrame({"Wealth": wealth, "Previous Peak": peaks, "Drawdown": wealth / peaks - 1}, index=s.index)


@_columnwise
def max_drawdown(r) -> float:
    """Perte maximale depuis un sommet (valeur négative ou nulle). Par colonne."""
    return float(drawdown(r)["Drawdown"].min())


def drawdown_episodes(r, *, top: int = 5) -> pd.DataFrame:
    """
    Pires épisodes de perte : sommet, creux, date de récupération (vide si pas encore récupéré),
    profondeur, nombre de périodes de baisse et de récupération.
    """
    top = _num(top, "top", lo=1, integer=True)
    dd = drawdown(r)["Drawdown"]
    idx, vals = dd.index, dd.to_numpy()
    under = vals < 0
    rows, i, n = [], 0, len(vals)
    while i < n:
        if not under[i]:
            i += 1
            continue
        j = i
        while j < n and under[j]:
            j += 1
        t = int(np.argmin(vals[i:j])) + i
        rows.append({"sommet": _date_str(idx[i - 1]) if i > 0 else "début", "creux": _date_str(idx[t]),
                     "recuperation": _date_str(idx[j]) if j < n else None, "profondeur": float(vals[t]),
                     "periodes_baisse": t - i + 1, "periodes_recuperation": (j - t) if j < n else None})
        i = j
    cols = ["sommet", "creux", "recuperation", "profondeur", "periodes_baisse", "periodes_recuperation"]
    return pd.DataFrame(rows, columns=cols).sort_values("profondeur").head(top).reset_index(drop=True)


@_columnwise
def ulcer_index(r) -> float:
    """Ulcer Index : racine de la moyenne des drawdowns au carré (Martin & McCann, 1989). Par colonne."""
    return float(np.sqrt((drawdown(r)["Drawdown"] ** 2).mean()))


@_columnwise
def downside_deviation(r, periods_per_year=None, *, target=0.0, annualize: bool = True) -> float:
    """
    Écart de baisse sous une cible : racine(moyenne(min(r - cible, 0)²)) (Sortino & van der Meer, 1991).
    target : taux ANNUEL (converti par période) ou "mean" (semi-écart-type sous la moyenne ;
    Markowitz, 1959). Toutes les observations comptent au dénominateur. Par colonne.
    """
    s = _as_series(r, "r", min_obs=2)
    annualize = _bool(annualize, "annualize")
    if isinstance(target, str):
        _choice(target, "target", {"mean"})
        thr = s.mean()
        ppy = _ppy(periods_per_year, s.index) if annualize else None
    else:
        t = _rate(target, "target")
        ppy = _ppy(periods_per_year, s.index) if (annualize or t != 0) else None
        thr = _per_period(t, ppy) if t != 0 else 0.0
    dd = float(np.sqrt(np.mean(np.minimum(s.to_numpy() - thr, 0) ** 2)))
    return dd * np.sqrt(ppy) if annualize else dd


@_columnwise
def semideviation(r) -> float:
    """
    Semi-écart-type sous la moyenne, par période (Markowitz, 1959). Par colonne.
    Correction d'erk.semideviation : erk prenait l'écart-type des seuls rendements négatifs autour
    de LEUR moyenne ; des pertes toutes égales à -5 % y donnaient un risque nul.
    """
    return downside_deviation(r, target="mean", annualize=False)


def _moments(s: pd.Series):
    x = s.to_numpy()
    xc = x - x.mean()
    m2 = np.mean(xc ** 2)
    return xc, m2


@_columnwise
def skewness(r) -> float:
    """Asymétrie (moments de population, comme erk). < 0 : grosses pertes plus fréquentes. NaN si constant."""
    xc, m2 = _moments(_as_series(r, "r", kind="any", min_obs=3))
    return float(np.mean(xc ** 3) / m2 ** 1.5) if m2 > 0 else np.nan


@_columnwise
def kurtosis(r, *, excess: bool = False) -> float:
    """Aplatissement (moments de population). Normale = 3 (ou 0 si excess=True). NaN si constant."""
    excess = _bool(excess, "excess")
    xc, m2 = _moments(_as_series(r, "r", kind="any", min_obs=4))
    if m2 == 0:
        return np.nan
    k = float(np.mean(xc ** 4) / m2 ** 2)
    return k - 3 if excess else k


def jarque_bera(r, *, level: float = 0.01) -> dict:
    """
    Test de normalité de Jarque-Bera (1987) : statistique, p-value, normalité non rejetée au seuil.
    Peu puissant sous 100 observations ('fiable' l'indique).
    """
    s = _as_series(r, "r", kind="any", min_obs=8)
    lvl = _num(level, "level", lo=0, hi=1, lo_open=True, hi_open=True)
    res = stats.jarque_bera(s.to_numpy())
    return {"statistique": float(res.statistic), "p_value": float(res.pvalue),
            "normal": bool(res.pvalue > lvl), "n_obs": len(s), "fiable": len(s) >= 100}


@_columnwise
def is_normal(r, level: float = 0.01) -> bool:
    """
    True si la normalité n'est pas rejetée par Jarque-Bera. Par colonne.
    Correction : erk.is_normal(DataFrame) mélangeait toutes les colonnes en un seul test.
    """
    return jarque_bera(r, level=level)["normal"]


@_columnwise
def var_historic(r, level: float = 5) -> float:
    """VaR historique (perte positive) au niveau `level` % (5 = 95 %). Par colonne. NaN ignorés."""
    s = _as_series(r, "r", min_obs=2)
    return float(-np.percentile(s.to_numpy(), _level(level)))


def _cf_valid(sk: float, ku: float) -> bool:
    """Cornish-Fisher n'est valide que si la transformation des quantiles est croissante (Maillard, 2012)."""
    z = np.linspace(-5, 5, 2001)
    d = 1 + z * sk / 3 + (3 * z ** 2 - 3) * (ku - 3) / 24 - (6 * z ** 2 - 5) * sk ** 2 / 36
    return bool(np.all(d > 0))


@_columnwise
def var_gaussian(r, level: float = 5, modified: bool = False) -> float:
    """
    VaR paramétrique gaussienne ; modified=True : développement de Cornish-Fisher (Favre & Galeano,
    2002), qui tient compte de l'asymétrie et de l'aplatissement. Par colonne.
    Si l'asymétrie ou l'aplatissement sont trop forts, Cornish-Fisher sort de son domaine de
    validité (Maillard, 2012) : un QuantWarning est émis.
    """
    s = _as_series(r, "r", min_obs=4)
    lvl = _level(level)
    modified = _bool(modified, "modified")
    z = stats.norm.ppf(lvl / 100)
    xc, m2 = _moments(s)
    if modified and m2 > 0:
        sk, ku = float(np.mean(xc ** 3) / m2 ** 1.5), float(np.mean(xc ** 4) / m2 ** 2)
        if not _cf_valid(sk, ku):
            warnings.warn(f"Cornish-Fisher hors de son domaine de validité (asymétrie {sk:.2f}, aplatissement "
                          f"{ku:.2f}) : préférer la VaR historique ou EVT", QuantWarning, stacklevel=2)
        z = z + (z ** 2 - 1) * sk / 6 + (z ** 3 - 3 * z) * (ku - 3) / 24 - (2 * z ** 3 - 5 * z) * sk ** 2 / 36
    return float(-(s.mean() + z * np.sqrt(m2)))


@_columnwise
def cvar_historic(r, level: float = 5) -> float:
    """CVaR historique (Expected Shortfall) : perte moyenne au-delà de la VaR historique. Par colonne."""
    s = _as_series(r, "r", min_obs=2)
    v = var_historic(s, level)
    return float(-s[s <= -v].mean())


def evt_var_es(r, *, level: float = 1.0, threshold_quantile: float = 0.95) -> dict:
    """
    VaR et Expected Shortfall par la théorie des valeurs extrêmes (dépassements de seuil, loi de
    Pareto généralisée ; McNeil & Frey, 2000 ; Embrechts, Klüppelberg & Mikosch, 1997).
    Modélise seulement la queue des pertes : plus fiable que la VaR historique ou gaussienne pour
    les niveaux extrêmes (1 %, 0,5 %). Requiert au moins 30 pertes au-delà du seuil, et un niveau
    plus extrême que le seuil. xi > 0 : queue épaisse ; xi >= 1 : ES infini.
    """
    s = _as_series(r, "r", min_obs=100)
    lvl = _level(level)
    tq = _num(threshold_quantile, "threshold_quantile", lo=0.5, hi=0.995)
    p = lvl / 100
    losses = -s.to_numpy()
    u = float(np.quantile(losses, tq))
    exc = losses[losses > u] - u
    n, nu = len(losses), len(exc)
    if nu < 30:
        raise ValueError(f"{nu} dépassements du seuil (il en faut >= 30) : abaisser threshold_quantile ou ajouter des données")
    if p >= nu / n:
        raise ValueError(f"level={lvl:g} % n'est pas plus extrême que le seuil ({100 * nu / n:.1f} % des obs.) : "
                         "choisir un niveau plus petit ou un seuil plus élevé")
    xi, _, beta = stats.genpareto.fit(exc, floc=0)
    if beta <= 0 or not np.isfinite(xi):
        raise RuntimeError("ajustement de la loi de Pareto généralisée impossible")
    ratio = n * p / nu
    var = u + beta / xi * (ratio ** (-xi) - 1) if abs(xi) > 1e-8 else u - beta * np.log(ratio)
    es = (var + beta - xi * u) / (1 - xi) if xi < 1 else np.inf
    return {"var": float(var), "es": float(es), "xi": float(xi), "beta": float(beta), "seuil": u,
            "n_depassements": nu, "indice_de_queue": float(1 / xi) if xi > 0 else np.inf}


def hill_tail_index(r, *, tail: str = "left", k: int | None = None) -> dict:
    """
    Indice de queue alpha de Hill (1975), sur les k plus grandes pertes (tail="left") ou gains.
    alpha < 4 : l'aplatissement n'est pas fiable ; alpha < 2 : variance infinie. Sensible à k
    (par défaut racine de n) ; à interpréter avec son erreur type.
    """
    s = _as_series(r, "r", min_obs=50)
    tail = _choice(tail, "tail", {"left", "right"})
    x = (-s if tail == "left" else s).to_numpy()
    x = np.sort(x[x > 0])[::-1]
    k = int(np.sqrt(len(s))) if k is None else _num(k, "k", lo=10, integer=True)
    k = min(k, len(x) - 1)
    if k < 10:
        raise ValueError(f"seulement {len(x)} valeurs dans cette queue : il en faut au moins 11")
    alpha = 1 / np.mean(np.log(x[:k]) - np.log(x[k]))
    return {"alpha": float(alpha), "k": int(k), "erreur_type": float(alpha / np.sqrt(k))}


def ewma_vol(r, periods_per_year=None, *, lam: float | None = None, warmup: int | None = None) -> dict:
    """
    Volatilité conditionnelle EWMA annualisée (RiskMetrics, 1996) :
    sigma²_t = lam sigma²_{t-1} + (1 - lam) r²_{t-1}. La valeur à la date t n'utilise que les
    données ANTÉRIEURES à t (aucune fuite de données). Initialisation : moyenne de r² sur les
    `warmup` premières périodes, qui ne reçoivent pas de prévision.
    lam par défaut : 0,94 (quotidien) ou 0,97 (autres fréquences).
    """
    s = _as_series(r, "r", min_obs=10)
    ppy = _ppy(periods_per_year, s.index)
    lam = (0.94 if ppy >= 252 else 0.97) if lam is None else _num(lam, "lam", lo=0, hi=1, lo_open=True, hi_open=True)
    warmup = min(30, len(s) // 3) if warmup is None else _num(warmup, "warmup", lo=2, integer=True)
    if warmup >= len(s):
        raise ValueError(f"warmup ({warmup}) doit être inférieur au nombre d'observations ({len(s)})")
    x2 = s.to_numpy() ** 2
    seed = float(np.mean(x2[:warmup]))
    y = lfilter([1 - lam], [1, -lam], x2[warmup:], zi=[lam * seed])[0]
    forecasts = np.concatenate([[seed], y[:-1]])
    vol = pd.Series(np.sqrt(forecasts * ppy), index=s.index[warmup:], name="vol_ewma")
    return {"vol_conditionnelle": vol, "prevision_prochaine_periode": float(np.sqrt(y[-1] * ppy)), "lambda": lam}


def garch11(r, periods_per_year=None, *, horizon: int | None = None) -> dict:
    """
    GARCH(1,1) estimé par quasi-maximum de vraisemblance (Bollerslev, 1986 ; Bollerslev &
    Wooldridge, 1992) : sigma²_t = omega + alpha e²_{t-1} + beta sigma²_{t-1}.
    Renvoie : persistance alpha + beta, demi-vie d'un choc, volatilité de long terme, volatilité
    prévue pour la prochaine période et moyenne prévue sur `horizon` périodes (1 an par défaut).
    Limites : paramètres estimés sur tout l'échantillon (la série conditionnelle est donc une analyse
    ex post) ; au moins 500 observations recommandées ; pas d'effet de levier (GJR, EGARCH).
    """
    s = _as_series(r, "r", min_obs=250)
    ppy = _ppy(periods_per_year, s.index)
    h = ppy if horizon is None else _num(horizon, "horizon", lo=1, hi=100_000, integer=True)
    x = s.to_numpy() - s.mean()
    scale = x.std()
    if scale == 0:
        raise ValueError("r : volatilité nulle, GARCH non défini")
    z2 = (x / scale) ** 2
    n = len(z2)

    def variances(p):
        om, a, b = p
        out = np.empty(n)
        out[0] = 1.0
        out[1:] = lfilter([1.0], [1.0, -b], om + a * z2[:-1], zi=[b * out[0]])[0]
        return out

    def nll(p):
        om, a, b = p
        if om <= 0 or a < 0 or b < 0 or a + b >= 0.999999:
            return 1e12
        v = variances(p)
        if not np.all(np.isfinite(v)) or np.any(v <= 0):
            return 1e12
        return 0.5 * np.sum(np.log(v) + z2 / v)

    cons = [{"type": "ineq", "fun": lambda p: 0.999999 - p[1] - p[2]}]
    best = None
    for a0, b0 in ((0.05, 0.90), (0.10, 0.80), (0.03, 0.95), (0.15, 0.60)):
        res = optimize.minimize(nll, x0=[1 - a0 - b0, a0, b0], method="SLSQP", constraints=cons,
                                bounds=[(1e-8, 10), (0, 1), (0, 1)], options={"maxiter": 500, "ftol": 1e-10})
        if best is None or res.fun < best.fun:
            best = res
    om, a, b = best.x
    if best.fun >= 1e12:
        raise RuntimeError("GARCH(1,1) : l'optimisation n'a pas trouvé de paramètres valides")
    v = variances(best.x) * scale ** 2
    omega = om * scale ** 2
    pers = a + b
    next_var = omega + a * x[-1] ** 2 + b * v[-1]
    lr_var = omega / (1 - pers)
    steps = np.arange(h)
    path = lr_var + pers ** steps * (next_var - lr_var)
    ll = -(best.fun + n * np.log(scale) + 0.5 * n * np.log(2 * np.pi))
    return {"omega": float(omega), "alpha": float(a), "beta": float(b), "persistance": float(pers),
            "demi_vie_periodes": float(np.log(0.5) / np.log(pers)) if 0 < pers < 1 else np.inf,
            "vol_long_terme_annualisee": float(np.sqrt(lr_var * ppy)),
            "prevision_vol_prochaine_periode": float(np.sqrt(next_var * ppy)),
            "prevision_vol_moyenne_horizon": float(np.sqrt(path.mean() * ppy)), "horizon_periodes": h,
            "vol_conditionnelle": pd.Series(np.sqrt(v * ppy), index=s.index, name="vol_garch"),
            "log_vraisemblance": float(ll), "convergence": bool(best.success), "n_obs": n}


def _default_var_window(ppy: int) -> int:
    return max(ppy, 60) if ppy >= 52 else max(5 * ppy, 20)


def var_coverage_tests(exceptions, level: float = 5) -> dict:
    """
    Tests de backtest d'une VaR à partir de la série des exceptions (True = perte au-delà de la VaR) :
    - couverture non conditionnelle de Kupiec (1995) : le taux d'exceptions égale-t-il le niveau?
    - indépendance de Christoffersen (1998) : les exceptions arrivent-elles en grappes?
    - couverture conditionnelle (les deux à la fois).
    p-value < 0,05 : modèle de VaR rejeté.
    """
    if isinstance(exceptions, (pd.Series, np.ndarray)) and pd.api.types.is_bool_dtype(np.asarray(exceptions).dtype):
        exceptions = pd.Series(np.asarray(exceptions, dtype=float))
    e = _as_series(exceptions, "exceptions", kind="any", min_obs=20).to_numpy()
    if not np.all(np.isin(e, (0.0, 1.0))):
        raise ValueError("exceptions : seulement des 0/1 (ou False/True) attendus")
    p = _level(level) / 100
    n, x = len(e), int(e.sum())
    ph = x / n
    lr_pof = -2 * ((n - x) * np.log(1 - p) + x * np.log(p) - xlogy(n - x, 1 - ph) - xlogy(x, ph))
    a, b = e[:-1].astype(int), e[1:].astype(int)
    n00, n01 = int(np.sum((a == 0) & (b == 0))), int(np.sum((a == 0) & (b == 1)))
    n10, n11 = int(np.sum((a == 1) & (b == 0))), int(np.sum((a == 1) & (b == 1)))
    pi01 = n01 / (n00 + n01) if n00 + n01 else 0.0
    pi11 = n11 / (n10 + n11) if n10 + n11 else 0.0
    pi = (n01 + n11) / (n00 + n01 + n10 + n11)
    l0 = xlogy(n00 + n10, 1 - pi) + xlogy(n01 + n11, pi)
    l1 = xlogy(n00, 1 - pi01) + xlogy(n01, pi01) + xlogy(n10, 1 - pi11) + xlogy(n11, pi11)
    lr_ind = max(-2 * (l0 - l1), 0.0)
    lr_cc = lr_pof + lr_ind
    return {"n_tests": n, "exceptions": x, "taux_exceptions": ph, "taux_attendu": p,
            "kupiec_LR": float(lr_pof), "kupiec_p_value": float(stats.chi2.sf(lr_pof, 1)),
            "christoffersen_LR": float(lr_ind), "christoffersen_p_value": float(stats.chi2.sf(lr_ind, 1)),
            "couverture_conditionnelle_p_value": float(stats.chi2.sf(lr_cc, 2))}


def var_backtest(r, periods_per_year=None, *, level: float = 5, window: int | None = None) -> pd.DataFrame:
    """
    Backtest HORS ÉCHANTILLON des VaR historique, gaussienne et Cornish-Fisher : à chaque date, la
    VaR est estimée sur les `window` périodes précédentes seulement (aucune fuite), puis comparée
    au rendement réalisé. Tests de Kupiec et de Christoffersen pour chaque méthode.
    Sert à choisir la mesure de VaR crédible POUR CE produit. Calcul vectorisé.
    """
    s = _as_series(r, "r", min_obs=30)
    ppy = _ppy(periods_per_year, s.index)
    lvl = _level(level)
    w = _default_var_window(ppy) if window is None else _num(window, "window", lo=20, integer=True)
    if len(s) - w < 50:
        raise ValueError(f"historique trop court pour un backtest : {len(s)} obs. pour une fenêtre de {w} "
                         "(il faut au moins 50 tests hors échantillon)")
    v = s.to_numpy()
    wins = np.lib.stride_tricks.sliding_window_view(v[:-1], w)
    realized = v[w:]
    z = stats.norm.ppf(lvl / 100)
    hist, gauss, cf = (np.empty(len(realized)) for _ in range(3))
    for a in range(0, len(realized), 2000):  # par blocs pour limiter la mémoire
        W = wins[a:a + 2000]
        hist[a:a + 2000] = -np.percentile(W, lvl, axis=1)
        mu = W.mean(1)
        xc = W - mu[:, None]
        m2 = (xc ** 2).mean(1)
        sd = np.sqrt(m2)
        gauss[a:a + 2000] = -(mu + z * sd)
        with np.errstate(invalid="ignore", divide="ignore"):
            sk = (xc ** 3).mean(1) / m2 ** 1.5
            ku = (xc ** 4).mean(1) / m2 ** 2
        zc = z + (z ** 2 - 1) * sk / 6 + (z ** 3 - 3 * z) * (ku - 3) / 24 - (2 * z ** 3 - 5 * z) * sk ** 2 / 36
        cf[a:a + 2000] = -(mu + zc * sd)
    rows = []
    for name, var in (("historique", hist), ("gaussienne", gauss), ("cornish_fisher", cf)):
        ok = np.isfinite(var)
        rows.append({"methode": name, **var_coverage_tests(pd.Series(realized[ok] < -var[ok]), lvl)})
    return pd.DataFrame(rows)


# =============================================================================
# 4. SÉRIES TEMPORELLES ET RÉGIMES
# =============================================================================
def ljung_box(x, *, lags: int = 10, robust: bool = False) -> dict:
    """
    Test de Ljung & Box (1978) : H0 = aucune autocorrélation jusqu'au retard `lags`.
    Sur les rendements : prévisibilité ou prix lissés. Sur les rendements au carré : volatilité
    en grappes, effet ARCH (McLeod & Li, 1983). Renvoie aussi les premières autocorrélations.
    robust=True : version de Lobato, Nankervis & Savin (2001), valide quand la volatilité varie
    dans le temps ; le test classique rejette alors trop souvent. À utiliser sur des rendements.
    """
    s = _as_series(x, "x", kind="any", min_obs=10)
    lags = _num(lags, "lags", lo=1, integer=True)
    robust = _bool(robust, "robust")
    if lags >= len(s) - 2:
        raise ValueError(f"lags ({lags}) doit être inférieur au nombre d'observations - 2 ({len(s) - 2})")
    v = s.to_numpy() - s.mean()
    n, denom = len(v), np.sum(v ** 2)
    if denom == 0:
        return {"Q": np.nan, "p_value": np.nan, "lags": lags, "autocorrelations": [], "robuste": robust}
    ks = np.arange(1, lags + 1)
    rho = np.array([np.sum(v[k:] * v[:-k]) / denom for k in ks])
    if robust:
        m2 = denom / n
        tau = np.array([np.mean(v[k:] ** 2 * v[:-k] ** 2) for k in ks]) / m2 ** 2
        q = n * np.sum(rho ** 2 / tau)
    else:
        q = n * (n + 2) * np.sum(rho ** 2 / (n - ks))
    return {"Q": float(q), "p_value": float(stats.chi2.sf(q, lags)), "lags": lags,
            "autocorrelations": [float(x) for x in rho[:10]], "robuste": robust}


def variance_ratio(r, *, q: int = 4) -> dict:
    """
    Test du ratio de variance de Lo & MacKinlay (1988), robuste à l'hétéroscédasticité.
    VR = Var(rendement sur q périodes) / (q × Var(rendement sur 1 période)).
    VR ≈ 1 : marche aléatoire ; > 1 : persistance (momentum ou prix lissés, Getmansky, Lo &
    Makarov, 2004) ; < 1 : retour à la moyenne.
    """
    s = _as_series(r, "r", min_obs=8)
    q = _num(q, "q", lo=2, integer=True)
    if len(s) < 4 * q:
        raise ValueError(f"au moins {4 * q} observations nécessaires pour q={q}")
    x = np.log1p(s.to_numpy())
    n, mu = len(x), x.mean()
    dev = x - mu
    var1 = np.sum(dev ** 2) / (n - 1)
    if var1 == 0:
        return {"VR": np.nan, "z": np.nan, "p_value": np.nan, "q": q}
    xq = np.convolve(x, np.ones(q), mode="valid")
    m = q * (n - q + 1) * (1 - q / n)
    vr = (np.sum((xq - q * mu) ** 2) / m) / var1
    dev2 = dev ** 2
    total = np.sum(dev2) ** 2
    theta = sum(((2 * (q - j) / q) ** 2) * n * np.sum(dev2[j:] * dev2[:-j]) / total for j in range(1, q))
    z = (vr - 1) * np.sqrt(n) / np.sqrt(theta) if theta > 0 else np.nan
    return {"VR": float(vr), "z": float(z), "p_value": float(2 * stats.norm.sf(abs(z))), "q": q}


def _kappa2(a: np.ndarray) -> tuple[float, int]:
    t = len(a)
    e2 = a ** 2
    c = np.cumsum(e2)
    if c[-1] == 0:
        return 0.0, 0
    g = c - np.arange(1, t + 1) / t * c[-1]
    u = e2 - e2.mean()
    m = int(4 * (t / 100) ** 0.25)
    omega = np.sum(u ** 2) / t + 2 / t * sum((1 - l / (m + 1)) * np.sum(u[l:] * u[:-l]) for l in range(1, m + 1))
    if omega <= 0:
        return 0.0, 0
    k = int(np.argmax(np.abs(g)))
    return float(abs(g[k]) / np.sqrt(t * omega)), k


def variance_breaks(r, periods_per_year=None, *, critical: float = 1.358, min_size: int | None = None,
                    max_breaks: int = 5) -> dict:
    """
    Ruptures de volatilité (changements de régime permanents) par segmentation binaire, avec la
    statistique kappa-2 de Sansó, Aragó & Carrion (2004), version robuste aux queues épaisses et
    aux grappes de volatilité du test d'Inclán & Tiao (1994). 1,358 = valeur critique à 5 %.
    Renvoie les dates de rupture et la volatilité et le rendement annualisés de chaque régime.
    """
    s = _as_series(r, "r", min_obs=60)
    ppy = _ppy(periods_per_year, s.index)
    crit = _num(critical, "critical", lo=0, lo_open=True)
    ms = max(ppy // 2, 20) if min_size is None else _num(min_size, "min_size", lo=10, integer=True)
    mb = _num(max_breaks, "max_breaks", lo=1, hi=50, integer=True)
    vals = s.to_numpy() - s.mean()
    breaks: list[int] = []

    def split(lo: int, hi: int):
        if hi - lo < 2 * ms or len(breaks) >= mb:
            return
        stat, k = _kappa2(vals[lo:hi])
        pos = lo + k + 1
        if stat > crit and ms <= pos - lo <= hi - lo - ms:
            breaks.append(pos)
            split(lo, pos)
            split(pos, hi)

    split(0, len(vals))
    bounds = [0] + sorted(breaks) + [len(vals)]
    regimes = [{"debut": _date_str(s.index[a]), "fin": _date_str(s.index[b - 1]), "n_obs": b - a,
                "vol_annualisee": annualize_vol(s.iloc[a:b], ppy),
                "rendement_annualise": annualize_return(s.iloc[a:b], ppy)}
               for a, b in zip(bounds[:-1], bounds[1:])]
    return {"ruptures": [_date_str(s.index[i]) for i in sorted(breaks)], "regimes": regimes}


def _hmm_em(x, mu, var, A, pi, max_iter, tol, var_floor):
    n, K = len(x), len(mu)
    ll_old = -np.inf
    for it in range(max_iter):
        B = np.exp(-0.5 * (x[:, None] - mu) ** 2 / var) / np.sqrt(2 * np.pi * var)
        B = np.maximum(B, 1e-300)
        Bl, Al = B.tolist(), A.tolist()
        alpha = [None] * n
        c = [0.0] * n
        row = [pi[k] * Bl[0][k] for k in range(K)]
        c[0] = sum(row)
        alpha[0] = [v / c[0] for v in row]
        for t in range(1, n):
            prev, bt = alpha[t - 1], Bl[t]
            row = [sum(prev[i] * Al[i][j] for i in range(K)) * bt[j] for j in range(K)]
            ct = sum(row)
            c[t] = ct
            alpha[t] = [v / ct for v in row]
        beta = [None] * n
        beta[-1] = [1.0] * K
        for t in range(n - 2, -1, -1):
            nb = [Bl[t + 1][j] * beta[t + 1][j] for j in range(K)]
            beta[t] = [sum(Al[i][j] * nb[j] for j in range(K)) / c[t + 1] for i in range(K)]
        al, be, cn = np.array(alpha), np.array(beta), np.array(c)
        gamma = al * be
        gamma /= gamma.sum(1, keepdims=True)
        xi = (al[:-1, :, None] * A[None] * (B[1:] * be[1:])[:, None, :] / cn[1:, None, None]).sum(0)
        ll = float(np.sum(np.log(cn)))
        pi = gamma[0]
        A = xi / xi.sum(1, keepdims=True)
        w = gamma.sum(0)
        mu = gamma.T @ x / w
        var = np.maximum((gamma * (x[:, None] - mu) ** 2).sum(0) / w, var_floor)
        if abs(ll - ll_old) < tol * max(1.0, abs(ll)):
            return mu, var, A, pi, ll, al, gamma, True
        ll_old = ll
    return mu, var, A, pi, ll, al, gamma, False


def regime_hmm(r, periods_per_year=None, *, n_states: int = 2, n_init: int = 3, max_iter: int = 200,
               tol: float = 1e-7, seed: int = 0) -> dict:
    """
    Régimes de marché récurrents par chaîne de Markov cachée gaussienne (Hamilton, 1989 ;
    algorithme de Baum-Welch). États triés du plus calme (0) au plus agité.
    Renvoie pour chaque état : rendement et volatilité annualisés, part du temps, durée moyenne ;
    la matrice de transition ; les probabilités FILTRÉES (n'utilisent que le passé à chaque date,
    à paramètres donnés) et LISSÉES (utilisent tout l'échantillon : analyse ex post seulement) ;
    l'état actuel. Limite : les paramètres sont estimés sur tout l'échantillon ; pour un backtest
    strict, ré-estimer en walk-forward. Vérifier que le BIC justifie le nombre d'états.
    """
    s = _as_series(r, "r", min_obs=100)
    ppy = _ppy(periods_per_year, s.index)
    K = _num(n_states, "n_states", lo=2, hi=4, integer=True)
    n_init = _num(n_init, "n_init", lo=1, hi=20, integer=True)
    max_iter = _num(max_iter, "max_iter", lo=10, hi=10_000, integer=True)
    tol = _num(tol, "tol", lo=0, lo_open=True, hi=1e-2)
    if len(s) < 30 * K:
        raise ValueError(f"au moins {30 * K} observations nécessaires pour {K} états")
    x = s.to_numpy()
    if x.std() == 0:
        raise ValueError("r : série constante, aucun régime à détecter")
    rng = _seed(seed)
    v0 = x.var()
    best = None
    for i in range(n_init):
        order = np.argsort(np.abs(x - np.median(x)))
        groups = np.array_split(order, K) if i == 0 else np.array_split(rng.permutation(len(x)), K)
        mu = np.array([x[g].mean() for g in groups])
        var = np.array([max(x[g].var(), 1e-3 * v0) for g in groups])
        if i > 0:
            var = var * rng.uniform(0.5, 2.0, K)
        A = np.full((K, K), 0.05 / (K - 1))
        np.fill_diagonal(A, 0.95)
        res = _hmm_em(x, mu, var, A, np.full(K, 1 / K), max_iter, tol, 1e-3 * v0)
        if best is None or res[4] > best[4]:
            best = res
    mu, var, A, pi, ll, filt, smooth, conv = best
    order = np.argsort(var)
    mu, var, A = mu[order], var[order], A[np.ix_(order, order)]
    filt, smooth = filt[:, order], smooth[:, order]
    n_par = K * (K - 1) + 2 * K + (K - 1)
    states = [{"etat": k, "rendement_annualise": float(mu[k] * ppy), "vol_annualisee": float(np.sqrt(var[k] * ppy)),
               "part_du_temps": float(smooth[:, k].mean()),
               "duree_moyenne_periodes": float(1 / (1 - A[k, k])) if A[k, k] < 1 else np.inf} for k in range(K)]
    cols = [f"etat_{k}" for k in range(K)]
    return {"etats": states, "matrice_transition": A, "log_vraisemblance": ll,
            "bic": float(-2 * ll + n_par * np.log(len(x))), "convergence": conv,
            "etat_actuel": int(np.argmax(filt[-1])), "prob_etat_actuel": float(filt[-1].max()),
            "prob_filtrees": pd.DataFrame(filt, index=s.index, columns=cols),
            "prob_lissees": pd.DataFrame(smooth, index=s.index, columns=cols)}


def trend_signals(r, periods_per_year=None) -> dict:
    """
    Indicateurs de tendance DESCRIPTIFS (aucune garantie de prévision) : momentum 12-1
    (Jegadeesh & Titman, 1993 ; Moskowitz, Ooi & Pedersen, 2012), position par rapport à la
    moyenne mobile 10 mois (Faber, 2007), part des périodes positives sur 12 mois.
    """
    s = _as_series(r, "r", min_obs=2)
    ppy = _ppy(periods_per_year, s.index)
    month = max(ppy // 12, 1)
    out = {}
    if len(s) > ppy:
        win = s.iloc[-ppy:-month] if month < ppy else s.iloc[-ppy:]
        out["momentum_12_1"] = float(np.prod(1 + win) - 1)
        out["part_periodes_positives_12m"] = float((s.iloc[-ppy:] > 0).mean())
    n_sma = max(int(round(10 * ppy / 12)), 2)
    if len(s) >= n_sma:
        wealth = returns_to_wealth(s)
        sma = wealth.rolling(n_sma).mean().iloc[-1]
        out["ecart_moyenne_mobile_10m"] = float(wealth.iloc[-1] / sma - 1)
        out["au_dessus_moyenne_mobile_10m"] = bool(wealth.iloc[-1] > sma)
    return out


def rolling_metrics(r, periods_per_year=None, *, window: int | None = None, riskfree_rate: float = 0.0) -> pd.DataFrame:
    """
    Rendement, volatilité et Sharpe annualisés sur fenêtre glissante (3 ans par défaut).
    Juge la STABILITÉ : un bon Sharpe moyen peut cacher de longues mauvaises périodes.
    """
    s = _as_series(r, "r", min_obs=3)
    ppy = _ppy(periods_per_year, s.index)
    w = 3 * ppy if window is None else _num(window, "window", lo=3, integer=True)
    if len(s) < w:
        raise ValueError(f"fenêtre de {w} périodes plus longue que l'historique ({len(s)})")
    rf = _per_period(_rate(riskfree_rate), ppy)
    with np.errstate(divide="ignore"):
        ann_ret = np.expm1(np.log1p(s).rolling(w).sum() * ppy / w)
    vol = s.rolling(w).std() * np.sqrt(ppy)
    sharpe = (s - rf).rolling(w).mean() / s.rolling(w).std() * np.sqrt(ppy)
    return pd.DataFrame({"rendement": ann_ret, "volatilite": vol, "sharpe": sharpe}).dropna()


# =============================================================================
# 5. RÉFÉRENCE ET PLUSIEURS ACTIFS
# =============================================================================
def _align2(r, b, min_common=24):
    a = _as_series(r, "r", min_obs=2)
    c = _as_series(b, "benchmark", min_obs=2)
    if type(a.index) is not type(c.index):
        raise TypeError("r et benchmark : types d'index différents (dates vs entiers?)")
    df = pd.concat([a.rename("r"), c.rename("b")], axis=1, join="inner")
    if len(df) < min_common:
        raise ValueError(f"seulement {len(df)} dates communes avec la référence (minimum {min_common})")
    return df["r"], df["b"]


def _newey_west(X, e, lags):
    Xe = X * e[:, None]
    S = Xe.T @ Xe
    for l in range(1, lags + 1):
        G = Xe[l:].T @ Xe[:-l]
        S += (1 - l / (lags + 1)) * (G + G.T)
    inv = np.linalg.inv(X.T @ X)
    return inv @ S @ inv


def benchmark_stats(r, benchmark, periods_per_year=None, *, riskfree_rate: float = 0.0, tail_q: float = 0.10,
                    hac_lags: int | None = None) -> dict:
    """
    Comparaison à un indice de référence (dates communes seulement) :
    - bêta, alpha de Jensen (1968) annualisé, statistiques t classique et robuste de Newey-West
      (1987) — la seconde tient compte de l'hétéroscédasticité et de l'autocorrélation ;
    - R², corrélations de Pearson et de Spearman ;
    - erreur de suivi, ratio d'information (Grinold & Kahn, 2000) ;
    - captures à la hausse et à la baisse GÉOMÉTRIQUES (convention Morningstar) ;
    - co-dépassement : P(produit dans ses pires tail_q | référence dans ses pires tail_q),
      = tail_q si indépendance, 1 si les pires périodes coïncident toujours.
    """
    a, b = _align2(r, benchmark)
    ppy = _ppy(periods_per_year, a.index)
    rf = _per_period(_rate(riskfree_rate), ppy)
    tq = _num(tail_q, "tail_q", lo=0.01, hi=0.5)
    y, x = (a - rf).to_numpy(), (b - rf).to_numpy()
    if np.std(x) == 0:
        raise ValueError("benchmark : rendements constants, bêta non défini")
    n = len(y)
    X = np.column_stack([np.ones(n), x])
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X @ coef
    se_ols = np.sqrt(np.diag(e @ e / (n - 2) * np.linalg.inv(X.T @ X)))
    L = int(4 * (n / 100) ** (2 / 9)) if hac_lags is None else _num(hac_lags, "hac_lags", lo=0, hi=n - 3, integer=True)
    se_hac = np.sqrt(np.diag(_newey_west(X, e, L)))
    te = float((a - b).std() * np.sqrt(ppy))
    active = annualize_return(a, ppy) - annualize_return(b, ppy)

    def cap(mask):
        if mask.sum() < 2:
            return np.nan
        ga, gb = annualize_return(a[mask], ppy), annualize_return(b[mask], ppy)
        return float(ga / gb) if gb != 0 else np.nan

    in_tail = b <= b.quantile(tq)
    return {"beta": float(coef[1]), "alpha_annualise": float(coef[0] * ppy),
            "alpha_t_stat": float(coef[0] / se_ols[0]) if se_ols[0] > 0 else np.nan,
            "alpha_t_stat_newey_west": float(coef[0] / se_hac[0]) if se_hac[0] > 0 else np.nan,
            "r2": float(1 - e @ e / np.sum((y - y.mean()) ** 2)),
            "correlation": float(np.corrcoef(a, b)[0, 1]),
            "correlation_spearman": float(stats.spearmanr(a, b).statistic),
            "erreur_de_suivi": te, "rendement_actif_annualise": float(active),
            "ratio_information": float(active / te) if te > 0 else np.nan,
            "capture_hausse": cap(b > 0), "capture_baisse": cap(b < 0),
            f"co_depassement_{tq:.0%}": float((a[in_tail] <= a.quantile(tq)).mean()),
            "n_obs_communes": n, "retards_newey_west": L}


def rolling_beta(r, benchmark, *, window: int) -> pd.DataFrame:
    """Bêta et corrélation glissants : la sensibilité au marché est-elle stable dans le temps?"""
    a, b = _align2(r, benchmark, min_common=4)
    w = _num(window, "window", lo=3, integer=True)
    if w > len(a):
        raise ValueError(f"window ({w}) dépasse le nombre de dates communes ({len(a)})")
    return pd.DataFrame({"beta": a.rolling(w).cov(b) / b.rolling(w).var(),
                         "correlation": a.rolling(w).corr(b)}).dropna()


def ledoit_wolf_cov(returns, periods_per_year=None) -> dict:
    """
    Covariance annualisée avec réduction de Ledoit & Wolf (2004) vers une matrice identité mise
    à l'échelle (même formule que sklearn.covariance.LedoitWolf). Plus stable que la covariance
    d'échantillon quand il y a beaucoup d'actifs pour peu de dates : à utiliser dans les
    optimiseurs de portefeuille. Renvoie aussi l'intensité de réduction (0 = aucune, 1 = totale).
    """
    df = _as_frame(returns, "returns", min_obs=3, min_cols=2)
    ppy = _ppy(periods_per_year, df.index)
    X = df.to_numpy()
    X = X - X.mean(0)
    n, p = X.shape
    emp = X.T @ X / n
    mu = np.trace(emp) / p
    X2 = X ** 2
    delta_ = np.sum((X.T @ X) ** 2) / n ** 2
    beta = (np.sum(X2.T @ X2) / n - delta_) / (p * n)
    delta = (delta_ - 2 * mu * np.trace(emp) + p * mu ** 2) / p
    beta = min(beta, delta)
    shrink = 0.0 if beta == 0 else float(beta / delta)
    cov = (1 - shrink) * emp + shrink * mu * np.eye(p)
    return {"covariance": pd.DataFrame(cov * ppy, index=df.columns, columns=df.columns),
            "covariance_echantillon": pd.DataFrame(emp * ppy, index=df.columns, columns=df.columns),
            "intensite_reduction": shrink, "n_obs": n}


def correlation_report(returns, periods_per_year=None, *, top: int = 5) -> dict:
    """
    Corrélations entre produits : Pearson, Spearman (rangs, robuste aux extrêmes), corrélation
    moyenne, paires les plus corrélées, conditionnement de la covariance (grand = optimisation
    instable) et covariance réduite de Ledoit-Wolf.
    """
    df = _as_frame(returns, "returns", min_obs=12, min_cols=2)
    top = _num(top, "top", lo=1, integer=True)
    pear = df.corr()
    iu = np.triu_indices(df.shape[1], 1)
    pairs = sorted(((df.columns[i], df.columns[j], float(pear.iat[i, j])) for i, j in zip(*iu)),
                   key=lambda t: -abs(t[2]))[:top]
    lw = ledoit_wolf_cov(df, periods_per_year)
    return {"pearson": pear, "spearman": df.corr(method="spearman"),
            "correlation_moyenne": float(pear.to_numpy()[iu].mean()),
            "paires_les_plus_correlees": [{"a": a, "b": b, "correlation": c} for a, b, c in pairs],
            "conditionnement_covariance": float(np.linalg.cond(lw["covariance_echantillon"].to_numpy())),
            "covariance_ledoit_wolf": lw["covariance"], "intensite_reduction": lw["intensite_reduction"],
            "n_obs": len(df)}


def _weights_map(w, name) -> pd.Series:
    if isinstance(w, dict):
        w = pd.Series(w, dtype=object)
    if not isinstance(w, pd.Series):
        raise TypeError(f"{name} : dict ou pd.Series {{titre: poids}} attendu, reçu {type(w).__name__}")
    s = _to_float_series(w, name)
    if s.index.has_duplicates:
        raise ValueError(f"{name} : titres en double")
    if s.isna().any() or np.isinf(s.to_numpy()).any():
        raise ValueError(f"{name} : poids manquants ou infinis")
    if (s < 0).any():
        raise ValueError(f"{name} : poids négatifs")
    if s.sum() > 1 + 1e-6:
        raise ValueError(f"{name} : somme des poids = {s.sum():.4g} > 1 ; poids en pourcentage? Diviser par 100")
    return s


def holdings_overlap(weights_a, weights_b, *, top: int = 10) -> dict:
    """
    Chevauchement des positions de deux fonds : somme sur les titres communs du plus petit des
    deux poids (0 = aucun titre commun, 1 = portefeuilles identiques). Mesure directe de la fausse
    diversification (ex. deux FNB qui détiennent les mêmes grandes sociétés).
    Données : poids par titre de chaque fonds (fraction ; sommes <= 1 si la liste est partielle).
    """
    a, b = _weights_map(weights_a, "weights_a"), _weights_map(weights_b, "weights_b")
    top = _num(top, "top", lo=1, integer=True)
    common = a.index.intersection(b.index)
    m = np.minimum(a[common], b[common]).sort_values(ascending=False)
    return {"chevauchement": float(m.sum()), "n_titres_communs": len(common),
            "poids_total_a": float(a.sum()), "poids_total_b": float(b.sum()),
            "principaux_titres_communs": {str(k): float(v) for k, v in m.head(top).items()}}


def _er_cov(er, cov, *, need_er=True):
    if isinstance(cov, pd.DataFrame):
        labels = list(cov.columns)
        if list(cov.index) != labels:
            raise ValueError("cov : les lignes et les colonnes doivent avoir les mêmes noms, dans le même ordre")
        if cov.columns.has_duplicates:
            raise ValueError("cov : noms d'actifs en double")
        C = np.column_stack([_to_float_series(cov[c], f"cov[{c!r}]").to_numpy() for c in cov.columns]) \
            if cov.shape[1] else np.empty((0, 0))
    else:
        labels = None
        try:
            C = np.asarray(cov, dtype=float)
        except (TypeError, ValueError):
            raise TypeError("cov : matrice numérique attendue") from None
    if C.ndim != 2 or C.shape[0] != C.shape[1] or C.shape[0] < 1:
        raise ValueError(f"cov : matrice carrée attendue, reçu la forme {C.shape}")
    if not np.all(np.isfinite(C)):
        raise ValueError("cov : valeurs manquantes ou infinies")
    scale = max(1.0, float(np.abs(C).max()))
    if not np.allclose(C, C.T, atol=1e-10 * scale):
        raise ValueError("cov : matrice non symétrique")
    if np.linalg.eigvalsh((C + C.T) / 2).min() < -1e-10 * scale:
        raise ValueError("cov : matrice non semi-définie positive (pas une vraie covariance)")
    if not need_er:
        return None, C, labels
    if isinstance(er, pd.Series):
        if labels is not None and list(er.index) != labels:
            raise ValueError("er et cov : noms d'actifs différents ou dans un ordre différent")
        labels = labels or list(er.index)
        E = _to_float_series(er, "er").to_numpy()
    else:
        E = _vec(er, "er")
    if len(E) != C.shape[0]:
        raise ValueError(f"er ({len(E)} actifs) et cov ({C.shape[0]} actifs) : tailles différentes")
    if not np.all(np.isfinite(E)):
        raise ValueError("er : valeurs manquantes ou infinies")
    return E, C, labels


def _vec(x, name) -> np.ndarray:
    """Vecteur numérique 1D sans valeur manquante (les NaN sont refusés, pas ignorés)."""
    if isinstance(x, (pd.DataFrame, dict)) or isinstance(x, (str, bytes)) or np.isscalar(x) or x is None:
        raise TypeError(f"{name} : vecteur (liste, tableau ou Series) attendu, reçu {type(x).__name__}")
    s = pd.Series(list(x.values) if isinstance(x, pd.Series) else (x.tolist() if isinstance(x, np.ndarray) else list(x)), dtype=object)
    if isinstance(x, np.ndarray) and x.ndim != 1:
        raise TypeError(f"{name} : vecteur à 1 dimension attendu")
    v = _to_float_series(s, name).to_numpy()
    if len(v) == 0:
        raise ValueError(f"{name} : vecteur vide")
    if not np.all(np.isfinite(v)):
        raise ValueError(f"{name} : valeurs manquantes ou infinies")
    return v


def _w_vector(weights, n, name="weights") -> np.ndarray:
    w = _vec(weights, name)
    if len(w) != n:
        raise ValueError(f"{name} : {len(w)} poids pour {n} actifs")
    return w


def portfolio_return(weights, er) -> float:
    """Rendement attendu du portefeuille : w · er (mêmes longueurs exigées)."""
    E = _vec(er, "er")
    return float(_w_vector(weights, len(E)) @ E)


def portfolio_vol(weights, covmat) -> float:
    """Volatilité du portefeuille : racine(w' Σ w) (covariance validée : carrée, symétrique, positive)."""
    _, C, _ = _er_cov(None, covmat, need_er=False)
    w = _w_vector(weights, C.shape[0])
    return float(np.sqrt(max(w @ C @ w, 0.0)))


def diversification_stats(weights, cov) -> dict:
    """
    Diversification d'un portefeuille (poids >= 0, somme 1) :
    - nombre effectif de positions 1 / Σ w² (inverse de l'indice de Herfindahl) ;
    - ratio de diversification Σ w σ / σ_p (Choueifaty & Coignard, 2008) ; 1 = aucune diversification ;
    - contributions au risque (décomposition d'Euler ; Maillard, Roncalli & Teïletche, 2010) :
      part de la volatilité totale due à chaque position.
    """
    _, C, labels = _er_cov(None, cov, need_er=False)
    w = _w_vector(weights, C.shape[0])
    if (w < -1e-12).any():
        raise ValueError("weights : poids négatifs (outil prévu pour des portefeuilles sans vente à découvert)")
    if abs(w.sum() - 1) > 1e-6:
        raise ValueError(f"weights : somme = {w.sum():.6g}, doit valoir 1")
    vol = float(np.sqrt(w @ C @ w))
    if vol == 0:
        raise ValueError("portefeuille de volatilité nulle : contributions non définies")
    mrc = C @ w
    names = labels or (list(weights.index) if isinstance(weights, pd.Series) else list(range(len(w))))
    return {"vol_portefeuille": vol, "n_effectif_positions": float(1 / np.sum(w ** 2)),
            "ratio_diversification": float(w @ np.sqrt(np.diag(C)) / vol),
            "contribution_risque_pct": pd.Series(w * mrc / vol ** 2, index=names),
            "contribution_risque_abs": pd.Series(w * mrc / vol, index=names)}


# =============================================================================
# 6. CONSTRUCTION DE PORTEFEUILLE
# =============================================================================
def _bounds(bounds, n):
    if not isinstance(bounds, (tuple, list)) or len(bounds) != 2:
        raise TypeError("bounds : (minimum, maximum) attendu, ex. (0, 1)")
    lo = _num(bounds[0], "bounds[0]", lo=-1, hi=1)
    hi = _num(bounds[1], "bounds[1]", lo=0, hi=2)
    if lo >= hi:
        raise ValueError(f"bounds : minimum ({lo}) >= maximum ({hi})")
    if n * lo > 1 + 1e-12 or n * hi < 1 - 1e-12:
        raise ValueError(f"bounds ({lo}, {hi}) incompatibles avec {n} actifs et une somme des poids égale à 1")
    return [(lo, hi)] * n


def _solve(fun, n, bnds, cons, jac=None, x0=None, what="optimisation"):
    lo, hi = [b[0] for b in bnds], [b[1] for b in bnds]
    x0 = np.clip(np.repeat(1 / n, n) if x0 is None else x0, lo, hi)

    def feasible(w):
        return abs(w.sum() - 1) < 1e-6 and all(c["fun"](w) > -1e-6 if c["type"] == "ineq"
                                               else abs(c["fun"](w)) < 1e-6 for c in cons)

    # SLSQP can stall ("Positive directional derivative for linesearch", iteration limit) depending on the start and
    # the scipy version: retry from where it stopped with a slightly looser tolerance, then from a random feasible-ish
    # start. Only a result that satisfies every constraint is accepted; the best one (lowest objective) wins.
    best, res = None, None
    starts = [(x0, 1e-12), (None, 1e-10), (np.random.default_rng(0).dirichlet(np.ones(n)), 1e-10)]
    for start, ftol in starts:
        start = np.clip(res.x if start is None and res is not None else (x0 if start is None else start), lo, hi)
        res = optimize.minimize(fun, start, jac=jac, method="SLSQP", bounds=bnds, constraints=cons,
                                options={"maxiter": 3000, "ftol": ftol})
        if res.success and feasible(res.x) and (best is None or fun(res.x) < fun(best)):
            best = res.x
            break
    if best is None:
        raise RuntimeError(f"{what} : échec de l'optimiseur ({res.message})")
    return best


def _label(w, labels):
    return pd.Series(w, index=labels) if labels is not None else w


def min_vol_for_target(target_return, er, cov, *, bounds=(0, 1)):
    """
    Poids de volatilité minimale pour un rendement attendu cible (point de la frontière efficiente).
    Correction d'erk.minimize_vol : une cible impossible est REFUSÉE avec la plage atteignable
    (erk renvoyait en silence un portefeuille qui ne l'atteignait pas), et l'échec de l'optimiseur
    est signalé.
    """
    E, C, labels = _er_cov(er, cov)
    t = _num(target_return, "target_return")
    bnds = _bounds(bounds, len(E))
    lo_r = optimize.linprog(E, A_eq=np.ones((1, len(E))), b_eq=[1], bounds=bnds).fun
    hi_r = -optimize.linprog(-E, A_eq=np.ones((1, len(E))), b_eq=[1], bounds=bnds).fun
    if not lo_r - 1e-9 <= t <= hi_r + 1e-9:
        raise ValueError(f"target_return={t:.4g} impossible avec ces bornes : plage atteignable [{lo_r:.4g}, {hi_r:.4g}]")
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1}, {"type": "eq", "fun": lambda w: w @ E - t}]
    w = _solve(lambda w: w @ C @ w, len(E), bnds, cons, jac=lambda w: 2 * C @ w, what="min_vol_for_target")
    return _label(w, labels)


def gmv_weights(cov, *, bounds=(0, 1)):
    """Portefeuille de variance minimale globale (GMV) : ne dépend pas des rendements attendus, peu sensibles à l'erreur d'estimation."""
    _, C, labels = _er_cov(None, cov, need_er=False)
    n = C.shape[0]
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1}]
    w = _solve(lambda w: w @ C @ w, n, _bounds(bounds, n), cons, jac=lambda w: 2 * C @ w, what="gmv_weights")
    return _label(w, labels)


def max_sharpe_weights(er, cov, *, riskfree_rate: float = 0.0, bounds=(0, 1)):
    """
    Portefeuille de Sharpe maximal (tangent). Refusé si aucun actif ne dépasse le taux sans risque.
    Attention (Michaud, 1989 ; DeMiguel, Garlappi & Uppal, 2009) : très sensible aux erreurs sur les
    rendements attendus ; préférer des estimations prudentes et la covariance de Ledoit-Wolf.
    """
    E, C, labels = _er_cov(er, cov)
    rf = _rate(riskfree_rate)
    if E.max() <= rf:
        raise ValueError("aucun actif n'a un rendement attendu supérieur au taux sans risque : Sharpe maximal non défini")
    bnds = _bounds(bounds, len(E))
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1}]

    def neg_sr(w):
        v = w @ C @ w
        return -(w @ E - rf) / np.sqrt(v) if v > 0 else 1e10

    best = None
    for x0 in (None, np.eye(len(E))[int(np.argmax(E))] * 0.5 + 0.5 / len(E)):
        try:
            w = _solve(neg_sr, len(E), bnds, cons, x0=x0, what="max_sharpe_weights")
        except RuntimeError:
            continue
        if best is None or neg_sr(w) < neg_sr(best):
            best = w
    if best is None:
        raise RuntimeError("max_sharpe_weights : échec de l'optimiseur")
    return _label(best, labels)


def risk_parity_weights(cov, *, budget=None):
    """
    Parité de risque (contributions égales au risque, ou proportionnelles à `budget` ; Maillard,
    Roncalli & Teïletche, 2010), par la formulation convexe de Spinu (2013) : solution unique.
    N'utilise pas les rendements attendus. Chaque actif doit avoir une variance > 0.
    """
    _, C, labels = _er_cov(None, cov, need_er=False)
    n = C.shape[0]
    if np.any(np.diag(C) <= 0):
        raise ValueError("cov : variance nulle pour au moins un actif ; parité de risque impossible")
    b = np.repeat(1 / n, n) if budget is None else _w_vector(budget, n, "budget")
    if budget is not None and (np.any(b <= 0) or abs(b.sum() - 1) > 1e-6):
        raise ValueError("budget : valeurs > 0 de somme 1 attendues")
    res = optimize.minimize(lambda y: 0.5 * y @ C @ y - b @ np.log(y), x0=1 / np.sqrt(np.diag(C)),
                            jac=lambda y: C @ y - b / y, method="L-BFGS-B", bounds=[(1e-12, None)] * n,
                            options={"maxiter": 5000, "gtol": 1e-12})
    w = res.x / res.x.sum()
    rc = w * (C @ w) / (w @ C @ w)
    if not np.allclose(rc, b, atol=1e-4):
        raise RuntimeError("risk_parity_weights : contributions au risque non égalisées (optimiseur)")
    return _label(w, labels)


def efficient_frontier(er, cov, *, n_points: int = 25, bounds=(0, 1), riskfree_rate: float = 0.0) -> dict:
    """
    Frontière efficiente sous forme de données (remplace les graphiques plot_ef/plot_ef2 d'erk) :
    pour n_points rendements cibles entre celui du GMV et le maximum atteignable, le portefeuille
    de volatilité minimale. Renvoie aussi les portefeuilles GMV, Sharpe maximal et équipondéré.
    """
    E, C, labels = _er_cov(er, cov)
    n_points = _num(n_points, "n_points", lo=2, hi=500, integer=True)
    rf = _rate(riskfree_rate)
    names = labels or [f"actif_{i}" for i in range(len(E))]
    w_g = np.asarray(gmv_weights(C, bounds=bounds))
    bnds = _bounds(bounds, len(E))
    hi_r = -optimize.linprog(-E, A_eq=np.ones((1, len(E))), b_eq=[1], bounds=bnds).fun
    rows = []
    for t in np.linspace(w_g @ E, hi_r, n_points):
        w = np.asarray(min_vol_for_target(float(t), E, C, bounds=bounds))
        v = float(np.sqrt(w @ C @ w))
        rows.append({"rendement": float(w @ E), "volatilite": v,
                     "sharpe": (float(w @ E) - rf) / v if v > 0 else np.nan, **dict(zip(names, w))})

    def point(w):
        v = float(np.sqrt(w @ C @ w))
        return {"rendement": float(w @ E), "volatilite": v, "sharpe": (float(w @ E) - rf) / v if v > 0 else np.nan,
                "poids": dict(zip(names, map(float, w)))}

    out = {"frontiere": pd.DataFrame(rows), "gmv": point(w_g), "equipondere": point(np.repeat(1 / len(E), len(E)))}
    try:
        out["sharpe_max"] = point(np.asarray(max_sharpe_weights(E, C, riskfree_rate=rf, bounds=bounds)))
    except (ValueError, RuntimeError) as e:  # optimiser can fail (e.g. a near-zero-vol asset)
        out["sharpe_max"] = str(e)
    return out


# =============================================================================
# 7. SIMULATION ET OBJECTIFS
# =============================================================================
def gbm_paths(n_years: float = 10, n_scenarios: int = 1000, *, mu: float = 0.07, sigma: float = 0.15,
              steps_per_year: int = 12, s0: float = 100.0, prices: bool = True, seed=None) -> pd.DataFrame:
    """
    Trajectoires de mouvement brownien géométrique EXACT (loi log-normale) :
    S_{t+dt} = S_t exp((ln(1+mu) - sigma²/2) dt + sigma racine(dt) Z) ; mu = rendement annuel
    attendu. Correction d'erk.gbm : erk tirait des rendements bruts NORMAUX (prix négatifs
    possibles quand sigma est grand), ajoutait une ligne de rendements nuls en tête et n'avait pas
    de graine (résultats non reproductibles). prices=False : rendements (une ligne par période).
    """
    ny = _num(n_years, "n_years", lo=0, lo_open=True, hi=200)
    ns = _num(n_scenarios, "n_scenarios", lo=1, hi=1_000_000, integer=True)
    mu = _num(mu, "mu", lo=-1, lo_open=True, hi=10)
    sigma = _num(sigma, "sigma", lo=0, hi=5)
    spy = _num(steps_per_year, "steps_per_year", lo=1, hi=100_000, integer=True)
    s0 = _num(s0, "s0", lo=0, lo_open=True)
    prices = _bool(prices, "prices")
    steps = int(round(ny * spy))
    if steps < 1:
        raise ValueError("n_years × steps_per_year doit donner au moins 1 période")
    if steps * ns > 50_000_000:
        raise ValueError(f"{steps} × {ns} valeurs : trop volumineux (maximum 50 millions)")
    dt = 1 / spy
    lr = (np.log1p(mu) - 0.5 * sigma ** 2) * dt + sigma * np.sqrt(dt) * _seed(seed).standard_normal((steps, ns))
    if not prices:
        return pd.DataFrame(np.expm1(lr))
    return pd.DataFrame(s0 * np.exp(np.vstack([np.zeros((1, ns)), np.cumsum(lr, axis=0)])))


def _stationary_indices(n, length, n_boot, block, rng):
    starts = rng.integers(0, n, size=(n_boot, length))
    new = rng.random((n_boot, length)) < 1.0 / block
    new[:, 0] = True
    pos = np.arange(length)
    last = np.maximum.accumulate(np.where(new, pos, 0), axis=1)
    return (np.take_along_axis(starts, last, axis=1) + pos - last) % n


def bootstrap_paths(r, *, n_periods: int, n_scenarios: int = 1000, block_size: float | None = None,
                    seed=None) -> pd.DataFrame:
    """
    Scénarios de rendements futurs tirés de l'historique par bootstrap STATIONNAIRE (blocs de
    longueur aléatoire, moyenne block_size ; Politis & Romano, 1994) : conserve l'autocorrélation
    et les grappes de volatilité, sans supposer de loi. Bloc moyen par défaut : n^(1/3).
    Limite : ne peut produire que des rendements déjà observés (pas de crise « nouvelle »).
    """
    s = _as_series(r, "r", min_obs=20)
    T = _num(n_periods, "n_periods", lo=1, hi=100_000, integer=True)
    N = _num(n_scenarios, "n_scenarios", lo=1, hi=1_000_000, integer=True)
    b = len(s) ** (1 / 3) if block_size is None else _num(block_size, "block_size", lo=1, hi=len(s))
    if T * N > 50_000_000:
        raise ValueError("n_periods × n_scenarios trop volumineux (maximum 50 millions)")
    idx = _stationary_indices(len(s), T, N, b, _seed(seed))
    return pd.DataFrame(s.to_numpy()[idx].T)


def _boot_sharpe(M, rf, ppy):
    sd = M.std(1, ddof=1)
    out = np.full(len(M), np.nan)
    ok = sd > 0
    out[ok] = (M[ok].mean(1) - rf) / sd[ok] * np.sqrt(ppy)
    return out


def bootstrap_ci(r, statistic="sharpe", periods_per_year=None, *, n_boot: int = 1000, block_size: float | None = None,
                 ci: float = 0.95, riskfree_rate: float = 0.0, seed=None) -> dict:
    """
    Intervalle de confiance d'une statistique par bootstrap stationnaire (Politis & Romano, 1994),
    qui respecte la dépendance temporelle. statistic : "mean", "annual_return", "volatility",
    "sharpe", "max_drawdown", "cvar" (5 %) — calcul vectorisé — ou une fonction Series -> float.
    Permet de dire « Sharpe 0,6 [0,1 ; 1,1] » au lieu d'un chiffre isolé.
    Limite : intervalle des centiles (pas BCa) ; peut être trop étroit sur de petits échantillons.
    """
    s = _as_series(r, "r", min_obs=20)
    ppy = _ppy(periods_per_year, s.index)
    nb = _num(n_boot, "n_boot", lo=100, hi=100_000, integer=True)
    conf = _num(ci, "ci", lo=0.5, hi=1, hi_open=True)
    rf = _per_period(_rate(riskfree_rate), ppy)
    b = len(s) ** (1 / 3) if block_size is None else _num(block_size, "block_size", lo=1, hi=len(s))
    vec = {
        "mean": lambda M: M.mean(1),
        "annual_return": lambda M: np.expm1(np.log1p(M).sum(1) * ppy / M.shape[1]),
        "volatility": lambda M: M.std(1, ddof=1) * np.sqrt(ppy),
        "sharpe": lambda M: _boot_sharpe(M, rf, ppy),
        "max_drawdown": lambda M: (np.cumprod(1 + M, 1) / np.maximum.accumulate(np.maximum(np.cumprod(1 + M, 1), 1), axis=1) - 1).min(1),
        "cvar": lambda M: -np.nanmean(np.where(M <= np.percentile(M, 5, axis=1)[:, None], M, np.nan), axis=1),
    }
    if isinstance(statistic, str):
        _choice(statistic, "statistic", set(vec))
        f = vec[statistic]
    elif callable(statistic):
        user = statistic

        def f(M):
            out = np.array([user(pd.Series(row)) for row in M], dtype=float)
            return out
    else:
        raise TypeError("statistic : nom de statistique ou fonction attendue")
    x = s.to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        est = float(f(x[None, :])[0])
        rng = _seed(seed)
        vals = []
        for a in range(0, nb, max(1, 20_000_000 // len(x))):
            k = min(nb - a, max(1, 20_000_000 // len(x)))
            vals.append(f(x[_stationary_indices(len(x), len(x), k, b, rng)]))
        vals = np.concatenate(vals)
    vals = vals[np.isfinite(vals)]
    if len(vals) < 0.9 * nb:
        raise ValueError("statistique non définie sur plus de 10 % des échantillons bootstrap")
    lo, hi = np.percentile(vals, [(1 - conf) / 2 * 100, (1 + conf) / 2 * 100])
    return {"estimation": est, "borne_inf": float(lo), "borne_sup": float(hi), "erreur_type": float(vals.std(ddof=1)),
            "niveau": conf, "n_boot": nb, "taille_bloc_moyenne": float(b)}


def goal_probability(scenarios, *, initial: float, target: float, contribution: float = 0.0,
                     contribution_every: int = 1, inflation: float = 0.0, periods_per_year: int | None = None) -> dict:
    """
    Probabilité d'atteindre un objectif financier à partir de scénarios de rendements (une ligne par
    période, une colonne par scénario ; voir gbm_paths(prices=False) ou bootstrap_paths).
    Versements de `contribution` en début de période, toutes les `contribution_every` périodes.
    target est en dollars d'aujourd'hui si inflation > 0 (il faut alors periods_per_year).
    Renvoie la probabilité de succès, les quantiles de la richesse finale, le manque médian en cas
    d'échec et la probabilité de finir sous le total investi.
    """
    R = _as_frame(scenarios, "scenarios", min_obs=1).to_numpy()
    W0 = _num(initial, "initial", lo=0)
    tgt = _num(target, "target", lo=0, lo_open=True)
    c = _num(contribution, "contribution", lo=0)
    every = _num(contribution_every, "contribution_every", lo=1, integer=True)
    infl = _num(inflation, "inflation", lo=-0.5, hi=1)
    if W0 == 0 and c == 0:
        raise ValueError("initial et contribution nuls : aucun capital à faire fructifier")
    T, N = R.shape
    if infl != 0:
        ppy = _ppy(periods_per_year, None)
        tgt = tgt * (1 + infl) ** (T / ppy)
    W = np.full(N, W0)
    invested = W0
    for t in range(T):
        if c and t % every == 0:
            W = W + c
            invested += c
        W = W * (1 + R[t])
    q = np.percentile(W, [5, 25, 50, 75, 95])
    miss = W < tgt
    return {"probabilite_atteinte": float(1 - miss.mean()), "cible_nominale": float(tgt),
            "total_investi": float(invested), "richesse_finale_quantiles": dict(zip(["p5", "p25", "p50", "p75", "p95"], map(float, q))),
            "manque_median_si_echec": float(np.median(tgt - W[miss])) if miss.any() else 0.0,
            "probabilite_sous_total_investi": float((W < invested).mean()), "n_scenarios": N, "horizon_periodes": T}


def _as_matrix(x, name):
    if isinstance(x, pd.Series):
        x = x.to_frame()
    return _as_frame(x, name, min_obs=1, dropna="none")


def run_cppi(risky_r, safe_r=None, *, m: float = 3, start: float = 1000, floor: float = 0.8,
             riskfree_rate: float = 0.03, drawdown=None, periods_per_year=None) -> dict:
    """
    Backtest de la stratégie CPPI (Black & Jones, 1987 ; Black & Perold, 1992) : exposition au
    risque = m × coussin, coussin = (valeur - plancher) / valeur, bornée entre 0 et 1.
    drawdown (ex. 0.2) : plancher = (1 - drawdown) × sommet atteint.
    Corrections d'erk.run_cppi : plante plus sous pandas 3 (écriture dans un tableau en lecture
    seule), taux sans risque converti selon la vraie fréquence (erk divisait toujours par 12),
    calcul vectorisé. Clés du résultat identiques à erk.
    """
    R = _as_matrix(risky_r, "risky_r")
    if R.isna().any().any():
        raise ValueError("risky_r : valeurs manquantes")
    m = _num(m, "m", lo=0, hi=100)
    start = _num(start, "start", lo=0, lo_open=True)
    floor = _num(floor, "floor", lo=0, hi=1, hi_open=True)
    dd = None if drawdown is None else _num(drawdown, "drawdown", lo=0, hi=1, lo_open=True, hi_open=True)
    if safe_r is None:
        ppy = _ppy(periods_per_year, R.index)
        S = pd.DataFrame(_per_period(_rate(riskfree_rate), ppy), index=R.index, columns=R.columns)
    else:
        S = _as_matrix(safe_r, "safe_r")
        if S.shape != R.shape:
            raise ValueError(f"safe_r {S.shape} et risky_r {R.shape} : formes différentes")
        S = pd.DataFrame(S.to_numpy(), index=R.index, columns=R.columns)
    r, s = R.to_numpy(), S.to_numpy()
    T, N = r.shape
    acct, fl, peak = np.full(N, start), np.full(N, start * floor), np.full(N, start)
    hist, wh, cush = (np.empty((T, N)) for _ in range(3))
    for t in range(T):
        if dd is not None:
            peak = np.maximum(peak, acct)
            fl = peak * (1 - dd)
        c = np.divide(acct - fl, acct, out=np.zeros(N), where=acct > 0)
        w = np.clip(m * c, 0, 1)
        acct = acct * (1 + w * r[t] + (1 - w) * s[t])
        hist[t], wh[t], cush[t] = acct, w, c
    df = lambda a: pd.DataFrame(a, index=R.index, columns=R.columns)
    return {"Wealth": df(hist), "Risky Wealth": start * (1 + R).cumprod(), "Risk Budget": df(cush),
            "Risky Allocation": df(wh), "m": m, "start": start, "floor": floor, "risky_r": R, "safe_r": S}


def bt_mix(r1, r2, allocator, **kwargs) -> pd.DataFrame:
    """
    Simule un mélange de deux actifs selon une règle d'allocation (périodes × scénarios).
    allocator(r1, r2, **kwargs) doit renvoyer des poids de r1 entre 0 et 1, de même forme.
    """
    A, B = _as_matrix(r1, "r1"), _as_matrix(r2, "r2")
    if A.shape != B.shape:
        raise ValueError(f"r1 {A.shape} et r2 {B.shape} : formes différentes")
    if not callable(allocator):
        raise TypeError("allocator : fonction attendue")
    w = allocator(A, B, **kwargs)
    w = _as_matrix(w, "poids renvoyés par allocator")
    if w.shape != A.shape:
        raise ValueError("allocator : poids de forme différente des rendements")
    if (w.to_numpy() < -1e-9).any() or (w.to_numpy() > 1 + 1e-9).any():
        raise ValueError("allocator : poids hors de [0, 1]")
    return pd.DataFrame(w.to_numpy() * A.to_numpy() + (1 - w.to_numpy()) * B.to_numpy(), index=A.index, columns=A.columns)


def fixedmix_allocator(r1, r2, w1, **kwargs) -> pd.DataFrame:
    """Allocation constante w1 dans r1 (0 <= w1 <= 1)."""
    A = _as_matrix(r1, "r1")
    return pd.DataFrame(_num(w1, "w1", lo=0, hi=1), index=A.index, columns=A.columns)


def glidepath_allocator(r1, r2, start_glide: float = 1, end_glide: float = 0.0) -> pd.DataFrame:
    """
    Trajectoire de glissement : poids de r1 passant linéairement de start_glide à end_glide
    (fonds à date cible : on réduit le risque à l'approche de l'échéance d'un projet).
    """
    A = _as_matrix(r1, "r1")
    a, b = _num(start_glide, "start_glide", lo=0, hi=1), _num(end_glide, "end_glide", lo=0, hi=1)
    path = np.linspace(a, b, len(A))
    return pd.DataFrame(np.repeat(path[:, None], A.shape[1], axis=1), index=A.index, columns=A.columns)


def _floor_like_allocator(psp_r, ghp_r, floor_fn, m):
    P, G = _as_matrix(psp_r, "psp_r"), _as_matrix(ghp_r, "ghp_r")
    if P.shape != G.shape:
        raise ValueError(f"psp_r {P.shape} et ghp_r {G.shape} : formes différentes")
    m = _num(m, "m", lo=0, hi=100)
    p, g = P.to_numpy(), G.to_numpy()
    T, N = p.shape
    acct, peak = np.ones(N), np.ones(N)
    out = np.empty((T, N))
    for t in range(T):
        fl = floor_fn(t, peak)
        c = np.divide(acct - fl, acct, out=np.zeros(N), where=acct > 0)
        w = np.clip(m * c, 0, 1)
        acct = acct * (1 + w * p[t] + (1 - w) * g[t])
        peak = np.maximum(peak, acct)
        out[t] = w
    return pd.DataFrame(out, index=P.index, columns=P.columns)


def floor_allocator(psp_r, ghp_r, floor, zc_prices, m=3) -> pd.DataFrame:
    """
    Allocation de type CPPI qui protège un plancher = floor × prix d'une obligation zéro-coupon
    (valeur actuelle du plancher). Renvoie les poids du portefeuille de performance (float).
    """
    fl = _num(floor, "floor", lo=0, hi=2)
    Z = _as_matrix(zc_prices, "zc_prices").to_numpy()
    if Z.shape != _as_matrix(psp_r, "psp_r").shape:
        raise ValueError("zc_prices : même forme que psp_r attendue")
    if (Z <= 0).any():
        raise ValueError("zc_prices : prix strictement positifs attendus")
    return _floor_like_allocator(psp_r, ghp_r, lambda t, peak: fl * Z[t], m)


def drawdown_allocator(psp_r, ghp_r, maxdd, m=3) -> pd.DataFrame:
    """Allocation de type CPPI qui limite la perte depuis le sommet à maxdd (ex. 0.25)."""
    md = _num(maxdd, "maxdd", lo=0, hi=1, lo_open=True, hi_open=True)
    return _floor_like_allocator(psp_r, ghp_r, lambda t, peak: (1 - md) * peak, m)


def terminal_values(rets) -> pd.Series:
    """Richesse finale par dollar investi pour chaque scénario (colonnes)."""
    return (1 + _as_matrix(rets, "rets")).prod()


def terminal_stats(rets, floor: float = 0.8, cap: float = np.inf, name: str = "Stats") -> pd.DataFrame:
    """
    Statistiques de la richesse finale par dollar : moyenne, écart-type, probabilité de passer sous
    le plancher (p_breach) et manque moyen (e_short), probabilité d'atteindre le plafond (p_reach)
    et surplus moyen (e_surplus). Correction d'erk : p_breach et p_reach valent 0 (et non NaN)
    quand l'événement ne se produit jamais ; e_short et e_surplus restent NaN (non définis).
    """
    tw = terminal_values(rets)
    fl = _num(floor, "floor", lo=0)
    cp = float(cap) if (isinstance(cap, (float, np.floating)) and np.isinf(cap) and cap > 0) else _num(cap, "cap", lo=0, lo_open=True)
    if cp <= fl:
        raise ValueError(f"cap ({cp}) doit dépasser floor ({fl})")
    breach, reach = tw < fl, tw >= cp
    return pd.DataFrame.from_dict({
        "mean": tw.mean(), "std": tw.std(), "p_breach": float(breach.mean()),
        "e_short": float((fl - tw[breach]).mean()) if breach.any() else np.nan,
        "p_reach": float(reach.mean()), "e_surplus": float((tw[reach] - cp).mean()) if reach.any() else np.nan,
    }, orient="index", columns=[str(name)])


# =============================================================================
# 8. TAUX ET OBLIGATIONS
# =============================================================================
def inst_to_ann(r):
    """Taux instantané (continu) → taux annuel composé : exp(r) - 1."""
    a = np.asarray(r, dtype=float) if not isinstance(r, (pd.Series, pd.DataFrame)) else r.astype(float)
    if not np.all(np.isfinite(np.asarray(a, dtype=float))):
        raise ValueError("r : valeurs finies attendues")
    return np.expm1(a)


def ann_to_inst(r):
    """Taux annuel composé → taux instantané : ln(1 + r). (Docstring d'erk corrigée : elle décrivait l'inverse.)"""
    a = np.asarray(r, dtype=float) if not isinstance(r, (pd.Series, pd.DataFrame)) else r.astype(float)
    arr = np.asarray(a, dtype=float)
    if not np.all(np.isfinite(arr)) or np.any(arr <= -1):
        raise ValueError("r : taux finis et > -100 % attendus")
    return np.log1p(a)


def discount(t, r) -> pd.DataFrame:
    """
    Facteurs d'actualisation (1 + r)^(-t) pour des échéances t (en périodes) et un taux par période
    r (scalaire, ou Series/vecteur de scénarios). DataFrame : une ligne par échéance, une colonne
    par taux (comme erk).
    """
    tt = np.asarray(t, dtype=float).ravel()
    if tt.size == 0 or not np.all(np.isfinite(tt)):
        raise ValueError("t : échéances finies attendues")
    cols = list(r.index) if isinstance(r, pd.Series) else None
    rr = np.atleast_1d(np.asarray(r, dtype=float)).ravel()
    if not np.all(np.isfinite(rr)) or np.any(rr <= -1):
        raise ValueError("r : taux finis et > -100 % attendus")
    return pd.DataFrame((1 + rr[None, :]) ** (-tt[:, None]), index=pd.Index(tt), columns=cols)


def pv(flows, r):
    """
    Valeur actuelle de flux (Series indexée par l'échéance en périodes) au taux par période r.
    Renvoie un float si r est un scalaire, une Series (un par scénario) sinon.
    """
    if not isinstance(flows, pd.Series):
        raise TypeError("flows : pd.Series {échéance: montant} attendue")
    f = _to_float_series(flows, "flows")
    if f.isna().any() or np.isinf(f.to_numpy()).any():
        raise ValueError("flows : montants manquants ou infinis")
    d = discount(f.index.to_numpy(dtype=float), r)
    out = d.multiply(f.to_numpy(), axis="rows").sum()
    return float(out.iloc[0]) if np.ndim(r) == 0 else out


def funding_ratio(assets, liabilities, r):
    """
    Ratio de financement = valeur de l'actif / valeur actuelle du passif.
    assets : valeur actuelle (nombre) OU flux d'actifs (Series, actualisés).
    Correction : erk plantait avec un actif numérique.
    """
    pv_l = pv(liabilities, r)
    pv_a = _num(assets, "assets", lo=0) if _is_real(assets) else pv(assets, r)
    return pv_a / pv_l


def bond_cash_flows(maturity, principal=100, coupon_rate=0.03, coupons_per_year=12) -> pd.Series:
    """Flux d'une obligation à coupons fixes, indexés par le numéro de coupon (1, 2, …)."""
    mat = _num(maturity, "maturity", lo=0, lo_open=True, hi=200)
    pr = _num(principal, "principal", lo=0, lo_open=True)
    cr = _num(coupon_rate, "coupon_rate", lo=0, hi=1)
    cpy = _num(coupons_per_year, "coupons_per_year", lo=1, hi=365, integer=True)
    n = mat * cpy
    if abs(n - round(n)) > 1e-9:
        raise ValueError(f"maturity × coupons_per_year = {n:g} n'est pas un nombre entier de coupons")
    n = int(round(n))
    cf = pd.Series(pr * cr / cpy, index=np.arange(1, n + 1), dtype=float)
    cf.iloc[-1] += pr
    return cf


def bond_price(maturity, principal=100, coupon_rate=0.03, coupons_per_year=12, discount_rate=0.03):
    """
    Prix d'une obligation à coupons fixes. discount_rate : taux ANNUEL (float → prix float), ou
    DataFrame de taux annuels indexé par le numéro de coupon (une colonne par scénario, comme erk)
    → DataFrame des prix au fil du temps. Correction : erk renvoyait une Series pour un prix unique.
    """
    if isinstance(discount_rate, pd.DataFrame):
        cpy = _num(coupons_per_year, "coupons_per_year", lo=1, integer=True)
        out = pd.DataFrame(index=discount_rate.index, columns=discount_rate.columns, dtype=float)
        for t in discount_rate.index:
            rem = maturity - t / cpy
            row = discount_rate.loc[t]
            if rem <= 1e-12:
                out.loc[t] = principal + principal * coupon_rate / cpy
            else:
                out.loc[t] = pv(bond_cash_flows(rem, principal, coupon_rate, cpy), row / cpy).to_numpy()
        return out
    y = _num(discount_rate, "discount_rate", lo=-0.5, hi=1)
    cf = bond_cash_flows(maturity, principal, coupon_rate, coupons_per_year)
    return pv(cf, y / int(coupons_per_year))


def bond_risk(maturity, principal=100, coupon_rate=0.03, coupons_per_year=2, yield_rate=0.03) -> dict:
    """
    Sensibilité d'une obligation aux taux (Macaulay, 1938 ; Fabozzi) : prix, duration de Macaulay
    et modifiée (en années), convexité, et variation de prix estimée pour +1 point de taux
    (-D_mod × 1 % + ½ × convexité × 1 %²). Explique « une obligation baisse quand les taux montent ».
    """
    cpy = _num(coupons_per_year, "coupons_per_year", lo=1, integer=True)
    y = _num(yield_rate, "yield_rate", lo=-0.5, hi=1)
    cf = bond_cash_flows(maturity, principal, coupon_rate, cpy)
    k = cf.index.to_numpy(dtype=float)
    v = (1 + y / cpy) ** (-k)
    price = float(cf.to_numpy() @ v)
    mac = float((k / cpy * cf.to_numpy() * v).sum() / price)
    dmod = mac / (1 + y / cpy)
    conv = float((cf.to_numpy() * k * (k + 1) * v / (1 + y / cpy) ** 2).sum() / (price * cpy ** 2))
    return {"prix": price, "duration_macaulay_ans": mac, "duration_modifiee": dmod, "convexite": conv,
            "variation_prix_pour_plus_1pct": -dmod * 0.01 + 0.5 * conv * 0.01 ** 2}


def macaulay_duration(flows, discount_rate) -> float:
    """Duration de Macaulay en PÉRIODES (comme erk) de flux indexés par période, au taux par période."""
    f = _to_float_series(flows, "flows") if isinstance(flows, pd.Series) else None
    if f is None:
        raise TypeError("flows : pd.Series attendue")
    d = discount(f.index.to_numpy(dtype=float), discount_rate).iloc[:, 0].to_numpy()
    w = f.to_numpy() * d
    if w.sum() <= 0:
        raise ValueError("flows : valeur actuelle nulle ou négative")
    return float(np.average(f.index.to_numpy(dtype=float), weights=w))


def match_durations(cf_t, cf_s, cf_l, discount_rate) -> float:
    """Poids de l'obligation courte (cf_s) qui, avec l'obligation longue (cf_l), égalise la duration de cf_t."""
    d_t, d_s, d_l = (macaulay_duration(c, discount_rate) for c in (cf_t, cf_s, cf_l))
    if abs(d_l - d_s) < 1e-12:
        raise ValueError("cf_s et cf_l ont la même duration : couverture impossible")
    return (d_l - d_t) / (d_l - d_s)


def bond_total_return(monthly_prices, principal, coupon_rate, coupons_per_year) -> pd.DataFrame:
    """
    Rendement total mensuel d'une obligation (prix + coupons réinvestis). Ligne i = mois i.
    Correction d'erk : erk plaçait les coupons avec np.linspace arrondi, ce qui décalait les dates de
    paiement quand la durée n'était pas un multiple exact de la période de coupon (ex. coupon au mois
    121 au lieu de 120). Ici : un coupon tous les 12 / coupons_per_year mois exactement.
    """
    P = _as_matrix(monthly_prices, "monthly_prices")
    if (P.to_numpy() <= 0).any():
        raise ValueError("monthly_prices : prix strictement positifs attendus")
    cpy = _num(coupons_per_year, "coupons_per_year", lo=1, hi=12, integer=True)
    if 12 % cpy:
        raise ValueError("coupons_per_year doit diviser 12 (1, 2, 3, 4, 6 ou 12)")
    step = 12 // cpy
    months = np.arange(len(P))
    coupon = np.where((months > 0) & (months % step == 0), _num(principal, "principal", lo=0) * _num(coupon_rate, "coupon_rate", lo=0, hi=1) / cpy, 0.0)
    v = P.to_numpy()
    tr = (v[1:] + coupon[1:, None]) / v[:-1] - 1
    return pd.DataFrame(tr, index=P.index[1:], columns=P.columns)


def cir(n_years: float = 10, n_scenarios: int = 1, a: float = 0.05, b: float = 0.03, sigma: float = 0.05,
        steps_per_year: int = 12, r_0=None, seed=None):
    """
    Taux d'intérêt simulés par le modèle de Cox, Ingersoll & Ross (1985), et prix de l'obligation
    zéro-coupon d'échéance n_years. b et r_0 sont des taux annuels ; les taux renvoyés aussi.
    Corrections d'erk : b est converti en taux instantané comme r_0 (erk mélangeait les deux) ;
    graine pour des résultats reproductibles. Condition de Feller 2ab >= sigma² vérifiée (sinon
    QuantWarning : le taux touche 0 et le schéma par réflexion s'applique).
    Renvoie (taux, prix) comme erk.
    """
    ny = _num(n_years, "n_years", lo=0, lo_open=True, hi=100)
    ns = _num(n_scenarios, "n_scenarios", lo=1, hi=1_000_000, integer=True)
    a = _num(a, "a", lo=0, lo_open=True)
    b_inst = float(ann_to_inst(_rate(b, "b")))
    sigma = _num(sigma, "sigma", lo=0, lo_open=True)
    spy = _num(steps_per_year, "steps_per_year", lo=1, hi=10_000, integer=True)
    r0 = b_inst if r_0 is None else float(ann_to_inst(_rate(r_0, "r_0")))
    if r0 < 0 or b_inst < 0:
        raise ValueError("cir : taux négatifs non pris en charge par le modèle CIR")
    if 2 * a * b_inst < sigma ** 2:
        warnings.warn("condition de Feller non respectée (2ab < sigma²) : le taux peut toucher 0", QuantWarning, stacklevel=2)
    dt = 1 / spy
    steps = int(ny * spy) + 1
    shock = _seed(seed).normal(0, np.sqrt(dt), size=(steps, ns))
    rates = np.empty_like(shock)
    rates[0] = r0
    h = math.sqrt(a ** 2 + 2 * sigma ** 2)

    def price(ttm, r):
        A = ((2 * h * math.exp((h + a) * ttm / 2)) / (2 * h + (h + a) * (math.exp(h * ttm) - 1))) ** (2 * a * b_inst / sigma ** 2)
        B = (2 * (math.exp(h * ttm) - 1)) / (2 * h + (h + a) * (math.exp(h * ttm) - 1))
        return A * np.exp(-B * r)

    prices = np.empty_like(shock)
    prices[0] = price(ny, r0)
    for t in range(1, steps):
        rt = rates[t - 1]
        rates[t] = np.abs(rt + a * (b_inst - rt) * dt + sigma * np.sqrt(rt) * shock[t])
        prices[t] = price(ny - t * dt, rates[t])
    return pd.DataFrame(inst_to_ann(rates)), pd.DataFrame(prices)


# =============================================================================
# 9. PRÉDICTION ET ROBUSTESSE
# =============================================================================
def oos_r2(actual, predicted, benchmark) -> float:
    """
    R² hors échantillon de Campbell & Thompson (2008) : 1 - Σ(y - prévision)² / Σ(y - référence)².
    > 0 : la prévision bat la référence (souvent la moyenne historique). Goyal & Welch (2008) ont
    montré que la plupart des prédicteurs de rendements échouent à ce test.
    """
    y, p, b = (np.asarray(_as_series(v, nm, kind="any", min_obs=2)) for v, nm in
               ((actual, "actual"), (predicted, "predicted"), (benchmark, "benchmark")))
    if not len(y) == len(p) == len(b):
        raise ValueError("actual, predicted et benchmark : longueurs différentes")
    den = np.sum((y - b) ** 2)
    return float(1 - np.sum((y - p) ** 2) / den) if den > 0 else np.nan


def diebold_mariano(loss_1, loss_2, *, h: int = 1) -> dict:
    """
    Test de Diebold & Mariano (1995), avec la correction de petit échantillon de Harvey, Leybourne
    & Newbold (1997) : les deux prévisions ont-elles la même perte moyenne?
    Entrées : pertes par date de chaque modèle (ex. erreurs au carré, ou qlike_loss pour la volatilité).
    """
    l1 = _as_series(loss_1, "loss_1", kind="any", min_obs=10).to_numpy()
    l2 = _as_series(loss_2, "loss_2", kind="any", min_obs=10).to_numpy()
    if len(l1) != len(l2):
        raise ValueError("loss_1 et loss_2 : longueurs différentes")
    h = _num(h, "h", lo=1, hi=len(l1) // 3, integer=True)
    d = l1 - l2
    n = len(d)
    dc = d - d.mean()
    lrv = np.sum(dc ** 2) / n + 2 * sum(np.sum(dc[k:] * dc[:-k]) / n for k in range(1, h))
    if lrv <= 0:
        return {"statistique": np.nan, "p_value": np.nan, "meilleur": "indéterminé (pertes identiques)"}
    dm = d.mean() / np.sqrt(lrv / n)
    dm *= np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    p = float(2 * stats.t.sf(abs(dm), n - 1))
    best = "aucun (différence non significative)" if p >= 0.05 else ("modele_2" if dm > 0 else "modele_1")
    return {"statistique": float(dm), "p_value": p, "meilleur": best, "n_obs": n}


def qlike_loss(realized_var, forecast_var) -> np.ndarray:
    """
    Perte QLIKE pour évaluer des prévisions de VARIANCE : rv/fv - ln(rv/fv) - 1. Robuste au bruit
    de la mesure de volatilité réalisée (Patton, 2011). Valeurs > 0 exigées.
    """
    rv = _as_series(realized_var, "realized_var", kind="any", min_obs=1).to_numpy()
    fv = _as_series(forecast_var, "forecast_var", kind="any", min_obs=1).to_numpy()
    if len(rv) != len(fv):
        raise ValueError("realized_var et forecast_var : longueurs différentes")
    if (rv <= 0).any() or (fv <= 0).any():
        raise ValueError("variances strictement positives attendues")
    q = rv / fv
    return q - np.log(q) - 1


def walk_forward(y, X=None, *, model="historical_mean", min_train: int = 60, window: int | None = None,
                 refit_every: int = 1) -> dict:
    """
    Évaluation prédictive SANS FUITE DE DONNÉES (validation « walk-forward »).
    Pour chaque date t >= min_train, le modèle est entraîné sur les lignes ANTÉRIEURES à t
    seulement (fenêtre croissante, ou glissante de `window` lignes), puis prévoit y_t à partir de
    la ligne X_t. IMPORTANT : X_t doit être connu AVANT y_t (ex. variables décalées d'une période,
    X.shift(1)). Aucun alignement automatique : X doit avoir exactement le même index que y.
    model : "historical_mean", "zero", "ols" (régression linéaire sur X) ou une fonction
    f(y_train, X_train, x_next) -> float. Référence : moyenne historique de la même fenêtre.
    Renvoie les prévisions, le R² hors échantillon (Campbell & Thompson, 2008), le test de
    Diebold-Mariano contre la référence et le taux de bon signe.
    """
    if X is not None:
        if not isinstance(y, pd.Series) or not isinstance(X, (pd.Series, pd.DataFrame)):
            raise TypeError("y (Series) et X (Series ou DataFrame) doivent être des objets pandas avec index")
        if not y.index.equals(X.index):
            raise ValueError("X et y : index différents. Aligner explicitement (aucun alignement automatique, "
                             "pour éviter une fuite de données)")
        Xf = _as_frame(X if isinstance(X, pd.DataFrame) else X.to_frame(), "X", kind="any", min_obs=1, dropna="none")
        ys = _to_float_series(y, "y")
        both = pd.concat([ys.rename("__y__"), Xf], axis=1).dropna()
        if np.isinf(both.to_numpy()).any():
            raise ValueError("y ou X : valeurs infinies")
        yv, Xv, idx = both["__y__"].to_numpy(), both.drop(columns="__y__").to_numpy(), both.index
    else:
        ys = _as_series(y, "y", kind="any", min_obs=3)
        yv, Xv, idx = ys.to_numpy(), None, ys.index
    mt = _num(min_train, "min_train", lo=2, integer=True)
    w = None if window is None else _num(window, "window", lo=2, integer=True)
    re = _num(refit_every, "refit_every", lo=1, integer=True)
    n = len(yv)
    if n - mt < 10:
        raise ValueError(f"{n} observations pour min_train={mt} : il faut au moins 10 prévisions hors échantillon")
    if isinstance(model, str):
        _choice(model, "model", {"historical_mean", "zero", "ols"})
        if model == "ols" and Xv is None:
            raise ValueError("model='ols' nécessite X")
    elif not callable(model):
        raise TypeError("model : nom de modèle ou fonction attendue")
    preds, bench, coef = np.empty(n - mt), np.empty(n - mt), None
    for i, t in enumerate(range(mt, n)):
        lo = 0 if w is None else max(0, t - w)
        ytr = yv[lo:t]
        bench[i] = ytr.mean()
        if model == "historical_mean":
            preds[i] = bench[i]
        elif model == "zero":
            preds[i] = 0.0
        elif model == "ols":
            if coef is None or i % re == 0:
                A = np.column_stack([np.ones(t - lo), Xv[lo:t]])
                coef = np.linalg.lstsq(A, ytr, rcond=None)[0]
            preds[i] = float(np.concatenate([[1.0], Xv[t]]) @ coef)
        else:
            p = model(ytr.copy(), None if Xv is None else Xv[lo:t].copy(), None if Xv is None else Xv[t].copy())
            if not _is_real(p) or not math.isfinite(float(p)):
                raise ValueError(f"model : la fonction doit renvoyer un nombre fini, reçu {p!r}")
            preds[i] = float(p)
    act = yv[mt:]
    res = pd.DataFrame({"reel": act, "prevision": preds, "reference": bench}, index=idx[mt:])
    out = {"predictions": res, "n_previsions": len(act), "r2_hors_echantillon": oos_r2(act, preds, bench),
           "erreur_quadratique_moyenne": float(np.mean((act - preds) ** 2)),
           "taux_bon_signe": float(np.mean(np.sign(preds[act != 0]) == np.sign(act[act != 0]))) if (act != 0).any() else np.nan}
    if not np.allclose(preds, bench):
        out["diebold_mariano_vs_reference"] = diebold_mariano((act - preds) ** 2, (act - bench) ** 2)
    return out


def probability_backtest_overfitting(returns, *, n_splits: int = 16) -> dict:
    """
    Probabilité de surajustement du backtest (PBO) par validation croisée combinatoire symétrique
    (CSCV ; Bailey, Borwein, López de Prado & Zhu, 2017).
    Données : rendements de N variantes de stratégie ou de N produits candidats (colonnes) sur les
    mêmes dates. Pour chaque façon de couper l'historique en deux moitiés, on prend la meilleure
    variante (Sharpe) sur la première moitié et on regarde son rang sur l'autre moitié.
    PBO = probabilité que la « meilleure » soit sous la médiane hors échantillon. ~0,5 : le choix du
    meilleur n'apporte rien ; proche de 0 : choix robuste.
    """
    df = _as_frame(returns, "returns", min_obs=8, min_cols=2)
    S = _num(n_splits, "n_splits", lo=4, hi=16, integer=True)
    if S % 2:
        raise ValueError("n_splits doit être pair")
    if len(df) < 4 * S:
        raise ValueError(f"au moins {4 * S} dates nécessaires pour n_splits={S}")
    M = df.to_numpy()
    blocks = np.array_split(np.arange(len(M)), S)
    s1 = np.array([M[b].sum(0) for b in blocks])
    s2 = np.array([(M[b] ** 2).sum(0) for b in blocks])
    cnt = np.array([len(b) for b in blocks], dtype=float)
    combos = np.array([[i in c for i in range(S)] for c in combinations(range(S), S // 2)], dtype=float)

    def sharpe(mask):
        n_ = mask @ cnt
        m1, m2 = mask @ s1, mask @ s2
        mean = m1 / n_[:, None]
        var = (m2 - m1 ** 2 / n_[:, None]) / (n_[:, None] - 1)
        return mean / np.sqrt(np.where(var > 0, var, np.nan))

    sr_is, sr_oos = sharpe(combos), sharpe(1 - combos)
    best = np.nanargmax(np.where(np.isfinite(sr_is), sr_is, -np.inf), axis=1)
    rows = np.arange(len(combos))
    oos_best = sr_oos[rows, best]
    N = M.shape[1]
    rank = (np.where(np.isfinite(sr_oos), sr_oos, -np.inf) < oos_best[:, None]).sum(1) + 1
    omega = rank / (N + 1)
    logit = np.log(omega / (1 - omega))
    slope = float(np.polyfit(sr_is[rows, best], oos_best, 1)[0]) if len(rows) > 2 else np.nan
    return {"pbo": float(np.mean(logit <= 0)), "logit_median": float(np.median(logit)),
            "pente_degradation": slope, "prob_perte_hors_echantillon": float(np.mean(oos_best < 0)),
            "n_combinaisons": len(combos), "n_variantes": N}


# =============================================================================
# 10. SYNTHÈSE : ÉVALUATION COMPLÈTE D'UN PRODUIT
# =============================================================================
class ProductEvaluator:
    """
    Évaluation complète d'un produit à partir de son historique (prix ou rendements), avec un
    indice de référence facultatif. Choisit automatiquement les analyses réalisables (capabilities)
    et explique celles qui ne le sont pas.

        ev = ProductEvaluator(prix, kind="prices", benchmark=prix_ref, benchmark_kind="prices",
                              riskfree_rate=0.03, name="XSP")
        rapport = ev.report()          # dict JSON, avec 'alertes' en français pour l'agent
    """

    def __init__(self, data, *, kind: str = "returns", benchmark=None, benchmark_kind: str | None = None,
                 riskfree_rate: float = 0.0, periods_per_year=None, name: str = "produit", var_level: float = 5,
                 n_boot: int = 500, seed: int = 0, include_models: bool = True):
        self.kind = _choice(kind, "kind", {"returns", "prices"})
        if isinstance(data, pd.DataFrame) and data.shape[1] != 1:
            raise TypeError("data : un seul produit à la fois (une colonne) ; évaluer chaque colonne séparément")
        self._raw = data
        self.r = prices_to_returns(data) if self.kind == "prices" else _as_series(data, "data", min_obs=12)
        if len(self.r) < 12:
            raise ValueError(f"data : {len(self.r)} rendements, il en faut au moins 12")
        self.ppy = _ppy(periods_per_year, self.r.index)
        self.rf = _rate(riskfree_rate)
        self.level = _level(var_level)
        self.name = str(name)
        self.n_boot = _num(n_boot, "n_boot", lo=100, hi=10_000, integer=True)
        self.seed = _num(seed, "seed", lo=0, integer=True)
        self.include_models = _bool(include_models, "include_models")
        self.b = None
        if benchmark is not None:
            bk = _choice(benchmark_kind or self.kind, "benchmark_kind", {"returns", "prices"})
            self.b = prices_to_returns(benchmark) if bk == "prices" else _as_series(benchmark, "benchmark", min_obs=12)
        self.caps = capabilities(self.r, self.b, self.ppy)["analyses"]
        self.skipped: dict[str, str] = {}

    def _try(self, key, fn):
        try:
            return fn()
        except (ValueError, RuntimeError) as e:
            self.skipped[key] = str(e)
            return None

    def _can(self, key):
        if self.caps[key]["possible"]:
            return True
        self.skipped[key] = "données insuffisantes : " + self.caps[key]["condition"]
        return False

    def quality(self) -> dict:
        return data_quality(self._raw, kind=self.kind)

    def performance(self) -> dict:
        r, p, rf = self.r, self.ppy, self.rf
        out = {"rendement_annualise": annualize_return(r, p), "volatilite_annualisee": annualize_vol(r, p),
               "sharpe": sharpe_ratio(r, p, riskfree_rate=rf), "sortino": sortino_ratio(r, p, riskfree_rate=rf),
               "calmar": calmar_ratio(r, p), "omega": omega_ratio(r, threshold=_per_period(rf, p)),
               "rendement_cumule": float(np.prod(1 + r) - 1), "pct_periodes_positives": float((r > 0).mean())}
        if self._can("sharpe_probabiliste"):
            out["sharpe_probabiliste"] = self._try("sharpe_probabiliste", lambda: probabilistic_sharpe(r, p, riskfree_rate=rf))
        if self._can("sharpe_ajuste_lo"):
            out["sharpe_ajuste_lo"] = self._try("sharpe_ajuste_lo", lambda: sharpe_ratio(r, p, riskfree_rate=rf, autocorr_adjusted=True))
        if self._can("intervalles_bootstrap"):
            out["ic_sharpe"] = self._try("ic_sharpe", lambda: bootstrap_ci(r, "sharpe", p, n_boot=self.n_boot, riskfree_rate=rf, seed=self.seed))
            out["ic_perte_maximale"] = self._try("ic_perte_maximale", lambda: bootstrap_ci(r, "max_drawdown", p, n_boot=self.n_boot, seed=self.seed))
        if self._can("pire_rendement_1_an"):
            out["fenetres_1_an"] = self._try("fenetres_1_an", lambda: worst_rolling_return(r, p))
        return out

    def risk(self) -> dict:
        r, p, lvl = self.r, self.ppy, self.level
        xc, m2 = _moments(r)
        sk, ku = (float(np.mean(xc ** 3) / m2 ** 1.5), float(np.mean(xc ** 4) / m2 ** 2)) if m2 > 0 else (np.nan, np.nan)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", QuantWarning)
            cf = var_gaussian(r, lvl, modified=True)
        out = {"perte_maximale": max_drawdown(r), "drawdown_actuel": float(drawdown(r)["Drawdown"].iloc[-1]),
               "pires_episodes": drawdown_episodes(r, top=3), "ulcer_index": ulcer_index(r),
               "ecart_baisse_annualise": downside_deviation(r, p, target=self.rf),
               f"var_historique_{lvl:g}pct": var_historic(r, lvl), f"var_gaussienne_{lvl:g}pct": var_gaussian(r, lvl),
               f"var_cornish_fisher_{lvl:g}pct": cf, "cornish_fisher_valide": _cf_valid(sk, ku) if m2 > 0 else False,
               f"cvar_historique_{lvl:g}pct": cvar_historic(r, lvl)}
        ew = self._try("ewma", lambda: ewma_vol(r, p))
        if ew:
            out["vol_ewma_prochaine_periode"] = ew["prevision_prochaine_periode"]
        if self._can("backtest_var"):
            out["backtest_var"] = self._try("backtest_var", lambda: var_backtest(r, p, level=lvl))
        if self._can("var_evt"):
            out["evt_1pct"] = self._try("var_evt", lambda: evt_var_es(r, level=1.0))
        if self.include_models and self._can("garch"):
            g = self._try("garch", lambda: garch11(r, p))
            if g:
                g.pop("vol_conditionnelle")
                out["garch"] = g
        if self._can("scenarios_de_crise"):
            out["scenarios_de_crise"] = self._try("scenarios_de_crise", lambda: scenario_analysis(r))
        return out

    def distribution(self) -> dict:
        r = self.r
        out = {"asymetrie": skewness(r), "aplatissement": kurtosis(r),
               "jarque_bera": self._try("jarque_bera", lambda: jarque_bera(r))}
        if self._can("indice_de_queue_hill"):
            out["hill_queue_gauche"] = self._try("hill", lambda: hill_tail_index(r))
        return out

    def dependence(self) -> dict:
        lags = min(10, max(len(self.r) // 5, 1))
        return {"ljung_box_rendements": self._try("ljung_box", lambda: ljung_box(self.r, lags=lags, robust=True)),
                "ljung_box_carres_arch": self._try("arch", lambda: ljung_box((self.r - self.r.mean()) ** 2, lags=lags)),
                "ratio_variance": self._try("ratio_variance", lambda: variance_ratio(self.r, q=4 if self.ppy <= 12 else 5))}

    def regimes(self) -> dict:
        out = {"tendance": trend_signals(self.r, self.ppy)}
        if self._can("ruptures_volatilite"):
            out["ruptures_volatilite"] = self._try("ruptures_volatilite", lambda: variance_breaks(self.r, self.ppy))
        if self.include_models and self._can("regimes_hmm"):
            h = self._try("regimes_hmm", lambda: regime_hmm(self.r, self.ppy, seed=self.seed))
            if h:
                for k in ("prob_filtrees", "prob_lissees"):
                    h.pop(k)
                out["regimes_hmm"] = h
        if self._can("metriques_glissantes_3_ans"):
            rm = self._try("glissant", lambda: rolling_metrics(self.r, self.ppy, riskfree_rate=self.rf))
            if rm is not None:
                out["sharpe_glissant_3_ans"] = {"min": rm["sharpe"].min(), "median": rm["sharpe"].median(),
                                                "max": rm["sharpe"].max(),
                                                "part_fenetres_rendement_positif": float((rm["rendement"] > 0).mean())}
        return out

    def relative(self):
        if self.b is None:
            return None
        if not self._can("comparaison_reference"):
            return None
        return self._try("comparaison_reference", lambda: benchmark_stats(self.r, self.b, self.ppy, riskfree_rate=self.rf))

    def _alerts(self, rep: dict) -> list:
        a = list(rep["qualite"].get("alertes", []))
        years = len(self.r) / self.ppy
        if years < 3:
            a.append(f"historique court ({years:.1f} an(s)) : mesures peu fiables")
        perf, risk, dist, dep, reg = rep["performance"], rep["risque"], rep["distribution"], rep["dependance"], rep["regimes"]
        psr = (perf.get("sharpe_probabiliste") or {})
        if psr.get("psr") is not None and psr["psr"] < 0.95:
            a.append(f"Sharpe pas significativement positif (PSR = {psr['psr']:.2f} < 0,95)")
        if isinstance(psr.get("duree_min_annees"), (int, float)) and psr["duree_min_annees"] > years:
            a.append(f"il faudrait {psr['duree_min_annees']:.1f} ans d'historique pour confirmer ce Sharpe")
        ic = perf.get("ic_sharpe") or {}
        if ic.get("borne_inf") is not None and ic["borne_inf"] <= 0 <= ic["borne_sup"]:
            a.append(f"l'intervalle de confiance du Sharpe [{ic['borne_inf']:.2f} ; {ic['borne_sup']:.2f}] contient 0")
        jb = dist.get("jarque_bera") or {}
        if jb and not jb.get("normal", True):
            a.append("rendements non normaux : la VaR gaussienne est peu fiable")
        if not risk.get("cornish_fisher_valide", True):
            a.append("asymétrie/aplatissement trop forts : VaR Cornish-Fisher hors de son domaine de validité")
        hill = dist.get("hill_queue_gauche") or {}
        if hill.get("alpha") is not None and hill["alpha"] < 3:
            a.append(f"queue des pertes épaisse (alpha de Hill = {hill['alpha']:.1f})")
        arch = dep.get("ljung_box_carres_arch") or {}
        if arch.get("p_value") is not None and arch["p_value"] < 0.05:
            a.append("volatilité en grappes : préférer la volatilité EWMA ou GARCH à la volatilité historique")
        lb = dep.get("ljung_box_rendements") or {}
        ac = (lb.get("autocorrelations") or [None])[0]
        if lb.get("p_value") is not None and lb["p_value"] < 0.05 and ac is not None and ac > 0:
            a.append("rendements autocorrélés positivement : prix possiblement lissés (illiquidité) ; voir unsmooth_returns")
        for row in risk.get("backtest_var") or []:
            if row.get("kupiec_p_value") is not None and row["kupiec_p_value"] < 0.05:
                a.append(f"VaR {row['methode']} rejetée par le backtest ({row['taux_exceptions']:.1%} d'exceptions vs {row['taux_attendu']:.0%})")
        g = risk.get("garch") or {}
        if g.get("persistance") is not None and g["persistance"] > 0.98:
            a.append(f"chocs de volatilité très persistants (demi-vie {g['demi_vie_periodes']:.0f} périodes)")
        if risk.get("drawdown_actuel") is not None and risk["drawdown_actuel"] < -0.10:
            a.append(f"actuellement {abs(risk['drawdown_actuel']):.0%} sous son dernier sommet")
        f1 = perf.get("fenetres_1_an") or {}
        if f1.get("pire") is not None:
            a.append(f"pire rendement sur 12 mois glissants : {f1['pire']:.0%} (fin {f1['date_fin_pire']})")
        rv = reg.get("ruptures_volatilite") or {}
        if rv.get("ruptures"):
            a.append(f"{len(rv['ruptures'])} changement(s) durable(s) de régime de volatilité")
        hm = reg.get("regimes_hmm") or {}
        if hm.get("etat_actuel") is not None and hm["etat_actuel"] > 0 and hm["prob_etat_actuel"] > 0.7:
            a.append("le produit est actuellement dans un régime agité (modèle à régimes)")
        rel = rep.get("relatif") or {}
        if rel.get("alpha_t_stat_newey_west") is not None and abs(rel["alpha_t_stat_newey_west"]) < 2:
            a.append("alpha non significatif par rapport à la référence (|t de Newey-West| < 2)")
        return a

    def report(self) -> dict:
        """Rapport complet en JSON : métadonnées, analyses, alertes, analyses non réalisées (avec la raison)."""
        self.skipped = {}
        rep = {"produit": self.name,
               "meta": {"periodes_par_an": self.ppy, "n_obs": len(self.r), "debut": _date_str(self.r.index[0]),
                        "fin": _date_str(self.r.index[-1]), "taux_sans_risque": self.rf, "niveau_var_pct": self.level,
                        "type_donnees": self.kind, "version_boite_a_outils": __version__},
               "qualite": self.quality(), "performance": self.performance(), "risque": self.risk(),
               "distribution": self.distribution(), "dependance": self.dependence(), "regimes": self.regimes(),
               "relatif": self.relative()}
        rep = to_jsonable(rep)
        rep["alertes"] = self._alerts(rep)
        rep["analyses_non_realisees"] = dict(self.skipped)
        return rep


# =============================================================================
# 11. REGISTRE DES OUTILS ET COMPATIBILITÉ ERK
# =============================================================================
_TOOL_TABLE = [
    ("Données", "série de prix", [prices_to_returns]),
    ("Données", "rendements", [returns_to_wealth, resample_returns, standardize, unsmooth_returns, data_quality, capabilities]),
    ("Données", "rendements en devise + taux de change", [convert_currency]),
    ("Performance", "rendements", [annualize_return, annualize_vol, sharpe_ratio, sortino_ratio, calmar_ratio, omega_ratio,
                                   probabilistic_sharpe, summary_stats, worst_rolling_return]),
    ("Performance", "rendements + rendements des autres essais", [deflated_sharpe]),
    ("Performance", "rendements datés", [scenario_analysis]),
    ("Risque", "rendements", [drawdown, max_drawdown, drawdown_episodes, ulcer_index, downside_deviation, semideviation,
                              skewness, kurtosis, jarque_bera, is_normal, var_historic, var_gaussian, cvar_historic,
                              evt_var_es, hill_tail_index, ewma_vol, garch11, var_backtest]),
    ("Risque", "série d'exceptions 0/1", [var_coverage_tests]),
    ("Séries temporelles", "rendements", [ljung_box, variance_ratio, variance_breaks, regime_hmm, trend_signals, rolling_metrics]),
    ("Plusieurs actifs", "rendements + référence", [benchmark_stats, rolling_beta]),
    ("Plusieurs actifs", "rendements de plusieurs produits", [ledoit_wolf_cov, correlation_report]),
    ("Plusieurs actifs", "poids par titre de deux fonds", [holdings_overlap]),
    ("Portefeuille", "poids + covariance (+ rendements attendus)", [diversification_stats, portfolio_return, portfolio_vol]),
    ("Portefeuille", "rendements attendus + covariance", [min_vol_for_target, gmv_weights, max_sharpe_weights,
                                                          risk_parity_weights, efficient_frontier]),
    ("Simulation", "paramètres ou rendements historiques", [gbm_paths, bootstrap_paths, bootstrap_ci, goal_probability]),
    ("Simulation", "rendements de deux actifs (scénarios)", [run_cppi, bt_mix, fixedmix_allocator, glidepath_allocator,
                                                             floor_allocator, drawdown_allocator, terminal_values, terminal_stats]),
    ("Taux et obligations", "taux, flux, caractéristiques d'obligations", [inst_to_ann, ann_to_inst, discount, pv, funding_ratio,
                                                                          bond_cash_flows, bond_price, bond_risk, macaulay_duration,
                                                                          match_durations, bond_total_return, cir]),
    ("Prédiction et robustesse", "cible + variables, ou rendements de variantes", [walk_forward, oos_r2, diebold_mariano,
                                                                                    qlike_loss, probability_backtest_overfitting]),
]

TOOLS = {f.__name__: {"fonction": f, "categorie": cat, "donnees": data,
                      "description": (f.__doc__ or "").strip().split("\n")[0]}
         for cat, data, fns in _TOOL_TABLE for f in fns}


def list_tools(category: str | None = None) -> pd.DataFrame:
    """Catalogue des outils (nom, catégorie, données nécessaires, description) pour un agent."""
    rows = [{"nom": k, "categorie": v["categorie"], "donnees": v["donnees"], "description": v["description"]}
            for k, v in TOOLS.items()]
    df = pd.DataFrame(rows)
    if category is not None:
        _choice(category, "category", set(df["categorie"]))
        df = df[df["categorie"] == category].reset_index(drop=True)
    return df


_ERK_NAMES = {"rendement_annualise": "Annualized Return", "volatilite_annualisee": "Annualized Vol",
              "asymetrie": "Skewness", "aplatissement": "Kurtosis", "var_cornish_fisher_5pct": "Cornish-Fisher VaR (5%)",
              "cvar_historique_5pct": "Historic CVaR (5%)", "sharpe": "Sharpe Ratio", "perte_maximale": "Max Drawdown"}

erk_compat = SimpleNamespace(
    drawdown=lambda return_series: drawdown(return_series),
    semideviation=semideviation, skewness=skewness, kurtosis=kurtosis, is_normal=is_normal,
    var_historic=var_historic, var_gaussian=var_gaussian, cvar_historic=cvar_historic,
    annualize_rets=lambda r, periods_per_year: annualize_return(r, periods_per_year),
    annualize_vol=lambda r, periods_per_year: annualize_vol(r, periods_per_year),
    sharpe_ratio=lambda r, riskfree_rate, periods_per_year: sharpe_ratio(r, periods_per_year, riskfree_rate=riskfree_rate, method="geometric"),
    portfolio_return=portfolio_return, portfolio_vol=portfolio_vol,
    minimize_vol=lambda target_return, er, cov: np.asarray(min_vol_for_target(target_return, er, cov)),
    optimal_weights=lambda n_points, er, cov: [np.asarray(min_vol_for_target(float(t), er, cov)) for t in np.linspace(np.min(er), np.max(er), n_points)],
    msr=lambda riskfree_rate, er, cov: np.asarray(max_sharpe_weights(er, cov, riskfree_rate=riskfree_rate)),
    gmv=lambda cov: np.asarray(gmv_weights(cov)),
    summary_stats=lambda r, riskfree_rate=0.03: summary_stats(r, 12, riskfree_rate=riskfree_rate).drop(columns="sortino").rename(columns=_ERK_NAMES),
    gbm=lambda n_years=10, n_scenarios=1000, mu=0.07, sigma=0.15, steps_per_year=12, s_0=100.0, prices=True, seed=None:
        gbm_paths(n_years, n_scenarios, mu=mu, sigma=sigma, steps_per_year=steps_per_year, s0=s_0, prices=prices, seed=seed),
    run_cppi=lambda risky_r, safe_r=None, m=3, start=1000, floor=0.8, riskfree_rate=0.03, drawdown=None:
        run_cppi(risky_r, safe_r, m=m, start=start, floor=floor, riskfree_rate=riskfree_rate, drawdown=drawdown, periods_per_year=12),
    discount=discount, pv=pv, funding_ratio=funding_ratio, inst_to_ann=inst_to_ann, ann_to_inst=ann_to_inst, cir=cir,
    bond_cash_flows=bond_cash_flows, bond_price=bond_price, macaulay_duration=macaulay_duration,
    match_durations=match_durations, bond_total_return=bond_total_return, bt_mix=bt_mix,
    fixedmix_allocator=fixedmix_allocator, terminal_values=terminal_values, terminal_stats=terminal_stats,
    glidepath_allocator=glidepath_allocator, floor_allocator=floor_allocator, drawdown_allocator=drawdown_allocator,
)
"""Mêmes noms et signatures qu'erk.py, pour l'ancien code : `from quant_toolkit import erk_compat as erk`.
Les résultats suivent les versions corrigées (voir les docstrings)."""
