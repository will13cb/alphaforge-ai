"""Log the personas' numbers in results.csv (rule 3: no number in the pitch unless it is logged).

For each persona, the pipeline's strategies (Robert with his 25% TSLA request): worst drop, 2022, chance of ending
below what was put in (risk-only view), growth share, and for Robert the request side by side (as asked vs fits).
Run after committing the code:  PYTHONPATH=src python experiments/data/persona_numbers.py [--log]
"""

from __future__ import annotations

import sys

from dh import log_run
from dh.agents.pipeline import run
from dh.agents.scenarios import AMIRA, MATEO, ROBERT

PROFILES = {"amira": AMIRA, "mateo": MATEO, "robert": {**ROBERT, "requested_positions": {"TSLA": 0.25}}}


def rows() -> list[tuple]:
    out = []
    for name, prof in PROFILES.items():
        res = run(prof)
        for s in res["strategies"]:
            exp = f"proposal-{s.get('key', s['name']).lower().replace(' ', '-')}"
            st = s["stats"]
            out += [(st["max_drawdown"], exp, "max_drawdown", name), (st["return_2022"], exp, "return_2022", name),
                    (s["split"]["growth"], exp, "growth_share", name)]
            if "prob_loss" in st:
                out.append((st["prob_loss"], exp, "risk_only_prob_loss", name))
        c = res.get("request_comparison")
        for key in ("as_asked", "fits"):
            v = (c or {}).get(key)
            if v:
                out += [(v["max_drawdown"], f"request-{key}", "max_drawdown", name),
                        (len(v["fails"]), f"request-{key}", "n_failing_checks", name)]
                out += [(x, f"request-{key}", f"real_weight_{t}", name) for t, x in v["real_weight"].items()]
                if v.get("drawdown_cad") is not None:
                    out.append((v["drawdown_cad"], f"request-{key}", "drawdown_cad", name))
    return out


if __name__ == "__main__":
    rs = rows()
    for v, exp, metric, persona in rs:
        print(f"{persona:7s} {exp:28s} {metric:22s} {v:,.4g}")
    if "--log" in sys.argv:
        for v, exp, metric, persona in rs:
            log_run(float(v), exp, metric, persona=persona, notes="pipeline.run on the starter data, experiments/data/persona_numbers.py")
        print(f"logged {len(rs)} rows to results.csv")
