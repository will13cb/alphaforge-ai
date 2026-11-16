"""CLI:  python -m dh {check,board,scenarios}"""

from __future__ import annotations

import argparse



def cmd_check(_):
    from . import data
    from .data import load_config
    from .metrics import summary

    cfg = load_config()
    u, p = data.universe(), data.prices()
    print(f"universe: {len(u)} assets  {u.asset_class.value_counts().to_dict()}")
    print(f"prices: {len(p):,} rows, {p.date.min():%Y-%m-%d} -> {p.date.max():%Y-%m-%d}")
    print(f"macro series: {sorted(data.macro().series_id.unique())}")
    from .agents.market import cash_rate
    rf = cash_rate()
    print(f"\nfull-period stats in {cfg.base_currency} ({cfg.calendar} calendar), Sharpe vs cash (ZST.TO {rf:.2%}/yr):")
    print(summary(data.returns(), rf=rf).sort_values("sharpe", ascending=False).round(3).to_string())


def cmd_board(_):
    from .metrics import board

    df = board()
    print(df.to_string(index=False) if not df.empty else "results.csv is empty")


def cmd_scenarios(a):
    from .agents.scenarios import SCENARIOS, run_all
    from .metrics import log_run

    rate = run_all(verbose=a.verbose)
    if a.log:
        rid = log_run(rate, experiment="guardian-scenarios", metric="pass_rate",
                      notes=f"{len(SCENARIOS)} fictional profiles, src/dh/agents/scenarios.py")
        print(f"logged {rid}")


def _cli_profile(persona: str) -> dict:
    """CLI personas; `robert` is Robert with his 25% TSLA request (the demo case, cached in cache/explainer/)."""
    from .agents.scenarios import DEMO_PROFILES

    return DEMO_PROFILES["robert_tsla" if persona == "robert" else persona]


def cmd_propose(a):
    from .agents.pipeline import run

    res = run(_cli_profile(a.persona))
    print(res["trace"].markdown())
    print(f"\nverdict: {res['verdict']}")
    for s in res.get("strategies", []):
        print(f"\n## {s['name']}  {s['split']['growth']:.0%} growth / {s['split']['defensive']:.0%} defensive"
              f"  (floor {s['split_range']['floor']}, ceiling {s['split_range']['ceiling']:.0%})")
        print("   " + ", ".join(f"{t} {w:.1%}" for t, w in s["weights"].items()))
        print("   stats: " + ", ".join(f"{k} {v:.3f}" for k, v in s["stats"].items() if isinstance(v, float)))
        if s.get("checks"):
            from dh.agents.checks import summary
            print("   checks C-F: " + summary(s["checks"]))
            for c in s["checks"]:
                if c["status"] != "pass":
                    print(f"     {'⚠' if c['status'] == 'warn' else '✘'} {c['check']}: {c['reason']}")
        for n in s["adjustments"]:
            print(f"   · {n}")
        for x in s.get("pros") or []:
            print(f"   + {x}")
        for x in s.get("cons") or []:
            print(f"   - {x}")
    c = res.get("request_comparison")
    if c:
        print(f"\n## Request side by side (on '{c['base']}')")
        for t, why in c["why"].items():
            print(f"   {t}: {why}")
        for key in ("as_asked", "fits"):
            v = c.get(key)
            if v:
                money = f" = {v['drawdown_cad']:,} $ vs {v['loss_limit_cad']:,} $" if v.get("drawdown_cad") else ""
                print(f"   {v['label']:>16}: " + ", ".join(f"{t} {x:.1%}" for t, x in v["real_weight"].items())
                      + f" | worst drop {v['max_drawdown']:.1%}{money} | {v['verdict']}"
                      + (" | ✘ " + ", ".join(f["id"] for f in v["fails"]) if v["fails"] else ""))
        if c.get("not_assessable"):
            print("   no data for " + ", ".join(c["not_assessable"]))


def cmd_explain(a):
    from .agents import explainer
    from .agents.pipeline import run

    profile = _cli_profile(a.persona)
    res = run(profile)
    e = explainer.add_to_trace(res, profile)
    if not a.no_store:
        from .tracestore import save_run
        save_run(res, profile, persona=a.persona)
    print(res["trace"].markdown())
    print("\n" + "-" * 80 + "\n" + e["text"] + "\n" + "-" * 80)
    print(f"source: {e['source']}  model: {e['model'] or '-'}  verdict: {e['verdict']}  facts: {e['facts_hash']}")
    if e["note"]:
        print(f"note: {e['note']}")
    c = res.get("critic") or {}
    if c:
        print(f"critic: {c['source']}  model: {c['model'] or '-'}  tool calls: {len(c['tool_calls'])}  "
              f"facts: {c['facts_hash']}" + (f"  note: {c['note']}" if c["note"] else ""))
    if a.save_demo:
        if c and c["source"] != "mock":
            from .agents import critic
            print(f"saved for the offline demo: {critic.save_demo(c)} (commit it)")
        print(f"saved for the offline demo: {explainer.save_demo(e)} (commit it)")


def cmd_ask(a):
    from .agents import analyst
    from .agents.pipeline import run

    profile = _cli_profile(a.persona)
    res = run(profile, critic=False)
    ans = analyst.add_to_trace(res, profile, a.question)
    for c in ans["tool_calls"]:
        print("   " + analyst.short(c))
    print("\n" + ans["answer"])
    print(f"\nsource: {ans['source']}  status: {ans['status']}  model: {ans['model'] or '-'}  facts: {ans['facts_hash']}"
          + (f"\nnote: {ans['note']}" if ans["note"] else ""))
    if a.save_demo:
        print(f"saved for the offline demo: {analyst.save_demo(ans)} (commit it)")


def cmd_log_personas(a):
    """Rule 3: log the persona numbers the pitch quotes (strategies + request facts) to results.csv."""
    from .agents.pipeline import run
    from .agents.scenarios import AMIRA, MATEO, ROBERT
    from .metrics import log_run

    profiles = {"amira": AMIRA, "mateo": MATEO, "robert": {**ROBERT, "requested_positions": {"TSLA": 0.25}}}
    n = 0
    for name, profile in profiles.items():
        res = run(profile)
        lim = res["limits"]
        for k in ("loss_limit", "min_defensive", "max_crypto"):
            log_run(lim[k], "persona-limits", k, persona=name, notes="pipeline.run on the starter data"); n += 1
        for r in lim.get("request_checks") or []:
            for k in ("asked", "worst_drop", "loss_at_asked", "fits_up_to"):
                if r.get(k) is not None:
                    log_run(r[k], "persona-request", f"{r['ticker']}_{k}", persona=name, notes=r["reason"][:120]); n += 1
        for s in res.get("strategies", []):
            vals = {"growth": s["split"]["growth"], **{k: s["stats"].get(k) for k in
                    ("max_drawdown", "return_2022", "stress_2022", "ann_vol", "prob_loss")}}
            for k, v in vals.items():
                if v is not None:
                    log_run(v, "persona-strategies", f"{s['key']}_{k}", persona=name, notes=s["name"]); n += 1
    print(f"logged {n} rows to results.csv (commit it)")
def cmd_contrast(a):
    """Same request, three clients (Amira, Mateo, Robert): three limits, three verdicts, three reasons."""
    from .agents.contrast import contrast, markdown

    rows = contrast(a.ticker, a.weight)
    print(markdown(rows))
    if a.log:
        from .metrics import log_run
        n = 0
        for r in rows:
            vals = {"cap": r["cap"], "loss_limit": r["loss_limit"],
                    "as_asked_drawdown_cad": r["as_asked"]["drawdown_cad"],
                    "as_asked_fails": len(r["as_asked"]["fails"]),
                    "at_cap_drawdown_cad": (r["at_cap"] or {}).get("drawdown_cad"),
                    "at_cap_chance_beyond_limit": (r["at_cap"] or {}).get("chance_beyond_limit"),
                    "at_cap_fails": len((r["at_cap"] or {}).get("fails", [])) if r["at_cap"] else None}
            for k, v in vals.items():
                if v is not None:
                    log_run(v, "persona-contrast", f"{r['ticker']}{round(r['asked'] * 100)}_{k}", persona=r["persona"],
                            notes=f"{r['answer']}; base {r['base']}"); n += 1
        print(f"logged {n} rows to results.csv (commit it)")


def cmd_extract(a):
    import json

    from .agents import extractor

    ex = extractor.extract(a.text)
    print(extractor.describe(ex))
    print(json.dumps(ex["profile"], indent=1, ensure_ascii=False))
    for q in ex["questions"]:
        print(f"? {q['field']}: {q['question']}")
    print(f"source: {ex['source']}  model: {ex['model'] or '-'}  hash: {ex['hash']}" + (f"  note: {ex['note']}" if ex["note"] else ""))
    if a.save_demo:
        print(f"saved for the offline demo: {extractor.save_demo(ex, a.text)} (commit it)")


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m dh")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="load the starter data and print a summary").set_defaults(fn=cmd_check)
    sub.add_parser("board", help="latest result per experiment/persona/metric").set_defaults(fn=cmd_board)
    sc = sub.add_parser("scenarios", help="run the test profiles against Profiler + Guardian")
    sc.add_argument("-v", "--verbose", action="store_true", help="print each agent hand-off")
    sc.add_argument("--log", action="store_true", help="log the pass rate to results.csv")
    sc.set_defaults(fn=cmd_scenarios)
    pr = sub.add_parser("propose", help="run the pipeline on a persona with the starter data (needs data/raw)")
    pr.add_argument("persona", choices=["amira", "mateo", "robert"])
    pr.set_defaults(fn=cmd_propose)
    ex = sub.add_parser("explain", help="pipeline + Explainer on a persona (LLM_PROVIDER=bedrock for Opus)")
    ex.add_argument("persona", choices=["amira", "mateo", "robert"])
    ex.add_argument("--save-demo", action="store_true", help="save the Bedrock Critic review and text to cache/critic/ and cache/explainer/ (commit them)")
    ex.add_argument("--no-store", action="store_true", help="don't save the run's trace (S3 or outputs/traces/)")
    ex.set_defaults(fn=cmd_explain)
    ak = sub.add_parser("ask", help='follow-up question to the Analyst, e.g. ask robert "what if I put 10%% in NVDA?"')
    ak.add_argument("persona", choices=["amira", "mateo", "robert"])
    ak.add_argument("question")
    ak.add_argument("--save-demo", action="store_true", help="save the Bedrock answer to cache/analyst/ (commit it)")
    ak.set_defaults(fn=cmd_ask)
    sub.add_parser("log-personas", help="log persona limits, requests and strategies to results.csv (rule 3)"
                   ).set_defaults(fn=cmd_log_personas)
    ct = sub.add_parser("contrast", help="same request (default 25%% TSLA) for Amira, Mateo and Robert side by side")
    ct.add_argument("--ticker", default="TSLA")
    ct.add_argument("--weight", type=float, default=0.25)
    ct.add_argument("--log", action="store_true", help="log the numbers to results.csv (rule 3)")
    ct.set_defaults(fn=cmd_contrast)
    xt = sub.add_parser("extract", help="free text → profile facts + follow-up questions (LLM_PROVIDER=bedrock for Opus)")
    xt.add_argument("text")
    xt.add_argument("--save-demo", action="store_true", help="save the Bedrock answer to cache/extractor/ (commit it)")
    xt.set_defaults(fn=cmd_extract)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
