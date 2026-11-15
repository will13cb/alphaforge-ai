"""Runs the deterministic part of the pipeline and records each hand-off in a Trace.

    Profiler (rules) → Market data → Portfolio (≤ 3 strategies, split computed, #17) → Guardian on each
    → Critic (agent + tools, ≤ 3 objections, one revision round, #30) → [Explainer: explainer.add_to_trace]

No strategy passed → the Portfolio proposes them (needs the starter CSVs, or `rets`). Passing a hand-made `strategy`
(the scenarios do, with propose=False) skips market data and Portfolio and checks only that strategy.
"""

from __future__ import annotations

from . import guardian
from .profiler import derive_limits
from .trace import Trace, describe_checks, describe_limits


def run(profile: dict, strategy: dict | None = None, explanation: str | None = None, holdings=None,
        propose: bool = True, rets=None, drops: dict | None = None, critic: bool = True) -> dict:
    """holdings=None → real issuer holdings (dh.holdings); pass {} to force "direct only".
    rets=None → starter data (dh.data.returns()); tests pass synthetic returns.
    drops = each asset's worst drop for the company caps (#24): None → from `rets` if given, else the market data."""
    tr = Trace()
    if drops is None and rets is not None:
        from ..metrics import max_drawdown
        drops = {c: max_drawdown(rets[c]) for c in rets.columns}
    limits = derive_limits(profile, drops)
    checks = guardian.check_profile(limits)
    tr.step("Profiler", "Portfolio, Guardian", describe_limits(limits), output=limits, checks=checks)
    if limits.get("missing"):
        tr.step("Guardian", "Profiler", describe_checks("Profiler", checks, "fail"), checks=checks)
        return dict(limits=limits, checks=checks, verdict="fail", trace=tr)

    if strategy is None and propose:
        from . import market, portfolio

        facts = market.market_facts(rets=rets)
        tr.step("Market data", "Portfolio", market.describe(facts),
                output={"period": facts["period"], "base_currency": facts["base_currency"]}, sources=facts["sources"])
        proposed = portfolio.propose(profile, limits, rets=rets, holdings=holdings)
        tr.step("Portfolio", "Guardian", portfolio.describe(proposed, limits), output=proposed)
        kept, dropped = [], []
        for s in proposed:
            c = guardian.check_strategy(s, limits, profile, holdings)
            v = guardian.verdict(c)
            s["guardian"] = dict(verdict=v, checks=c)
            tr.step("Guardian", "Critic" if v != "fail" else "Portfolio",
                    f"'{s['name']}': " + describe_checks("Portfolio", c, v), checks=c)
            failed_cf = [x for x in s.get("checks") or [] if x["status"] == "fail"]  # H: a ✘ in C-F drops it too
            (dropped if v == "fail" or failed_cf else kept).append(s)
        for s in dropped:  # P10: dropped, and the trace says why
            why = [f"{c['rule']} {c['detail']}" for c in s["guardian"]["checks"] if c["status"] == "fail"]
            why += [f"{c['check']} {c['reason']}" for c in s.get("checks") or [] if c["status"] == "fail"]
            tr.step("Portfolio", "Client", f"'{s['name']}' dropped: " + ", ".join(why))
        res = dict(limits=limits, checks=checks, strategies=kept, dropped=dropped, trace=tr)
        if critic and kept:  # one round: objections, at most one recomputed fix per strategy, Guardian re-check
            from . import critic as critic_agent
            critic_agent.add_to_trace(res, profile, rets=rets, holdings=holdings)
        kept = res["strategies"]
        from . import requests as rq
        objections = {id(s): list(s.get("cons") or []) for s in kept}  # the Critic's, before pros_cons rewrites cons
        rq.pros_cons(kept, limits, profile)  # H: from the final strategies' own numbers, never the LLM
        for s in kept:
            s["cons"] = list(s.get("cons") or []) + [c for c in objections[id(s)] if c not in (s.get("cons") or [])]
        comparison = rq.compare(profile, limits, kept, rets=rets, holdings=holdings)  # G: request side by side
        if comparison:
            tr.step("Portfolio", "Client", comparison["summary"], output=comparison)
            # a copy, not an in-place change (audit P15): G12 reads the side-by-side numbers from res["limits"]
            limits = res["limits"] = {**limits, "request_comparison": comparison}
        res["request_comparison"] = comparison
        res["verdict"] = "fail" if not kept else guardian.verdict([c for s in kept for c in s["guardian"]["checks"]])
        return res

    if strategy is not None:
        s = guardian.check_strategy(strategy, limits, profile, holdings)
        v = guardian.verdict(s)
        tr.step("Portfolio", "Guardian", f"strategy '{strategy.get('name', '?')}': "
                + ", ".join(f"{k} {w:.0%}" for k, w in strategy["weights"].items()), output=strategy)
        tr.step("Guardian", "Critic" if v != "fail" else "Portfolio", describe_checks("Portfolio", s, v), checks=s)
        checks += s

    if explanation is not None and strategy is not None:  # TODO Explainer agent produces this
        e = guardian.check_explanation(explanation, strategy, limits, profile)
        v = guardian.verdict(e)
        tr.step("Explainer", "Guardian", "client text, " + str(len(explanation)) + " characters", output=explanation)
        tr.step("Guardian", "Client" if v != "fail" else "Explainer", describe_checks("Explainer", e, v), checks=e)
        checks += e

    return dict(limits=limits, checks=checks, verdict=guardian.verdict(checks), trace=tr)
