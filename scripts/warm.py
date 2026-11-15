"""Fill the committed demo caches with real Bedrock answers, in one go, before the AWS account closes (Mon ~11:30).

    make warm            # LLM_PROVIDER=bedrock in .env: makes the calls, copies answers to cache/*/ (commit them)
    make warm DRY=1      # or without Bedrock: lists the calls, makes none

What it calls (the exact inputs the demo uses, so the facts hashes match and the app/interface replay offline):
- Critic + Explainer on the 4 demo clients (scenarios.DEMO_PROFILES), via pipeline.run (Critic on, like both UIs);
- the Extractor on the app's sample text (app/app.py SAMPLE_TEXT);
- the Analyst on every suggested question (app FOLLOW_UPS + interface SUGGESTIONS), for each demo client, as the
  first question of a conversation (no history). A suggestion asked later in a chat has another hash → live call.
Lists are read from the UI files with `ast` (single source, no Streamlit import). Only answers that passed the
code checks are saved; the rest are reported.
"""
from __future__ import annotations

import argparse
import ast
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _const(path: str, name: str):
    for node in ast.parse((ROOT / path).read_text()).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise SystemExit(f"{name} not found in {path}")


def plan() -> dict:
    from dh.agents.scenarios import DEMO_PROFILES

    qs = list(dict.fromkeys(_const("app/app.py", "FOLLOW_UPS") + _const("interface/views/chat.py", "SUGGESTIONS")))
    return {"clients": list(DEMO_PROFILES), "text": _const("app/app.py", "SAMPLE_TEXT"), "questions": qs,
            # existing portfolio (#42): Robert via "Try with an example client" + "Try an example portfolio"
            "existing": {"client": "robert", "positions": _const("interface/views/holdings_input.py", "EXAMPLE"),
                         "questions": _const("interface/views/holdings_input.py", "EXISTING_QUESTIONS")}}


def existing_profile(p: dict) -> dict:
    """The exact profile the guided interface sends for the existing-portfolio demo, so the facts hashes match: the
    demo client's answers as the form round-trips them (wizard), plus the example portfolio."""
    sys.path.insert(0, str(ROOT))
    from dh.agents.scenarios import DEMO_PROFILES
    from interface.core import wizard
    prof = wizard.to_profile(wizard.all_values(wizard.from_profile(DEMO_PROFILES[p["existing"]["client"]]))[0])
    return {**prof, "existing_positions": dict(p["existing"]["positions"])}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry", action="store_true", help="list the calls, make none")
    a = ap.parse_args(argv)
    p = plan()
    live = os.getenv("LLM_PROVIDER", "mock").lower() == "bedrock" and not a.dry
    n = 2 * (2 * len(p["clients"]) + len(p["clients"]) * len(p["questions"]) + 3 + len(p["existing"]["questions"])) + 1
    print(f"{'LIVE (Bedrock)' if live else 'DRY RUN: no call made'} · {n} calls")
    for c in p["clients"]:
        print(f"  critic + explainer  {c}")
    print(f"  extractor           {p['text'][:70]}…")
    ex_ = p["existing"]
    print(f"  critic ×2 + explainer  {ex_['client']} + existing portfolio {ex_['positions']}")
    for q in ex_["questions"]:
        print(f"  analyst             {ex_['client']:12} (existing) {q}")
    for c in p["clients"]:
        for q in p["questions"]:
            print(f"  analyst             {c:12} {q}")
    if not live:
        print("\nTo run: LLM_PROVIDER=bedrock in .env, then `make warm`, then commit cache/.")
        return 0

    from dh.agents import analyst, critic, explainer, extractor, pipeline
    from dh.agents.scenarios import DEMO_PROFILES

    saved, failed = [], []

    def keep(what, fn, obj, *extra):
        try:
            saved.append(fn(obj, *extra))
            print(f"✔ {what}")
        except Exception as e:  # noqa: BLE001 — report and continue: one failure must not stop the warm-up
            failed.append(f"{what}: {e}")
            print(f"✘ {what}: {e}")

    from dh.i18n import tr
    for lang in ("en", "fr"):  # both languages of the app (#49): French answers get their own cache entries
        os.environ["AF_LANG"] = lang
        for c in p["clients"]:
            prof = DEMO_PROFILES[c]
            res = pipeline.run(prof)
            cr = res.get("critic") or {}
            if cr and cr.get("source") != "mock":
                keep(f"[{lang}] critic {c} ({cr['source']})", critic.save_demo, cr)
            else:
                failed.append(f"critic {c}: no review ({cr.get('note', 'not run')})")
            e = explainer.add_to_trace(res, prof)
            keep(f"[{lang}] explainer {c} ({e['source']}, {e['verdict']})", explainer.save_demo, e)
            for q in p["questions"]:
                ans = analyst.ask(tr(q, to=lang), res, prof)
                if ans["status"] != "valid":
                    failed.append(f"analyst {c} «{q}»: {ans['status']} ({ans['note']})")
                    print(f"✘ analyst {c} «{q}»: {ans['status']}")
                    continue
                keep(f"[{lang}] analyst {c} «{q}» ({ans['source']})", analyst.save_demo, ans)
        prof = existing_profile(p)          # existing portfolio (#42): proposals' Critic, the review's Critic, Explainer
        res = pipeline.run(prof)
        for what, cr in (("critic", res.get("critic") or {}),
                         ("critic (existing)", (res.get("existing_review") or {}).get("critic") or {})):
            if cr and cr.get("source") != "mock":
                keep(f"{what} robert+portfolio ({cr['source']})", critic.save_demo, cr)
            else:
                failed.append(f"{what} robert+portfolio: no review ({cr.get('note', 'not run')})")
        e = explainer.add_to_trace(res, prof)
        keep(f"explainer robert+portfolio ({e['source']}, {e['verdict']})", explainer.save_demo, e)
        for q in p["existing"]["questions"]:
            ans = analyst.ask(tr(q, to=lang), res, prof)
            if ans["status"] != "valid":
                failed.append(f"analyst robert+portfolio «{q}»: {ans['status']} ({ans['note']})")
                continue
            keep(f"analyst robert+portfolio «{q}» ({ans['source']})", analyst.save_demo, ans)
    ex = extractor.extract(p["text"])
    keep(f"extractor ({ex['source']})", extractor.save_demo, ex, p["text"])

    print(f"\n{len(saved)} saved, {len(failed)} not saved")
    for f in failed:
        print("  - " + f)
    print("Next: git add cache/ && git commit -m 'Demo cache: Bedrock answers' && git push")
    return 1 if failed and not saved else 0


if __name__ == "__main__":
    sys.exit(main())
