"""The ONLY door from the interface to the engine. Every call is inside one error boundary.

- `UserError`: something the person can fix or understand (data not installed, profile incomplete). Its message is
  shown as is, in plain words.
- Anything else is an internal error: the full traceback goes to `logs/interface.log`, the person sees one short
  sentence and a reference number to quote. A Python traceback is never shown on screen.

No Streamlit here (tests/test_interface_services.py). Nothing is computed here either: the numbers come from
`pipeline.run`, `explainer`, `extractor`, `analyst`.
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

from dh import data, tracestore
from dh.agents import analyst, explainer, extractor, pipeline
from dh.agents.scenarios import DEMO_LABELS, DEMO_PROFILES
from dh.personas import DISCLAIMER

LOG_DIR = data.ROOT / "logs"
MAX_QUESTION = 500          # characters sent to the Analyst; longer questions are cut, and the person is told
MAX_TEXT = 3000             # characters of free text sent to the extractor
FILES = ("assets_universe.csv", "prices_daily.csv", "fx_usdcad_daily.csv")


class UserError(Exception):
    """A problem the person can understand; its message is shown on screen."""


class InternalError(Exception):
    """An unexpected failure; logged in full, shown as one sentence with a reference."""

    def __init__(self, ref: str, where: str):
        super().__init__(f"Something went wrong on our side while {where}. Please try again; if it happens again, "
                         f"quote reference {ref}.")
        self.ref = ref


def logger() -> logging.Logger:
    log = logging.getLogger("interface")
    if not any(getattr(h, "af_interface", False) for h in log.handlers):
        try:
            LOG_DIR.mkdir(exist_ok=True)
            h = logging.FileHandler(LOG_DIR / "interface.log", encoding="utf-8")
        except OSError:          # read-only disk: log to the console instead, never fail because of the log
            h = logging.StreamHandler()
        h.af_interface = True
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(h)
        log.setLevel(logging.INFO)
        log.propagate = False
    return log


def _guard(where: str, fn, *a, **kw):
    """Run fn; UserError passes through, anything else becomes InternalError (traceback in the log)."""
    try:
        return fn(*a, **kw)
    except UserError:
        raise
    except SystemExit as e:  # dh.data raises SystemExit when a CSV is missing
        logger().warning("%s: %s", where, e)
        raise UserError(NO_DATA) from None
    except Exception:  # noqa: BLE001 — the boundary: every engine failure ends here
        ref = uuid.uuid4().hex[:8]
        logger().exception("ref=%s while %s", ref, where)
        raise InternalError(ref, where) from None


NO_DATA = ("The market data is not installed on this computer, so no analysis can run yet. Whoever set up the app "
           "can install it with `make data` (see the README).")


def data_ready() -> tuple[bool, str]:
    folder = data.load_config().data_dir
    missing = [f for f in FILES if not (Path(folder) / f).exists()]
    return (not missing, "" if not missing else NO_DATA)


def mode() -> dict:
    """Which engine answers: Claude on Amazon Bedrock (live) or the offline mode. Shown to the person, never hidden."""
    live = os.getenv("LLM_PROVIDER", "mock").lower() == "bedrock"
    return {"live": live,
            "label": "Live: Claude on Amazon Bedrock" if live else "Offline: limited answers",
            "help": ("The assistant is a Strands agent on Amazon Bedrock. It chooses which checks to run; code checks "
                     "every number it writes." if live else
                     "No AI model is connected. The assistant recognises a set of question types (a position, a "
                     "change to your profile, a concept, your results) and answers them with the same checks. It may "
                     "not understand other questions, and says so.")}


def demo_clients() -> dict[str, tuple[str, dict]]:
    return {k: (DEMO_LABELS.get(k, k), dict(p)) for k, p in DEMO_PROFILES.items()}


def run_analysis(profile: dict) -> dict:
    """pipeline.run + the Explainer's text. Refuses an incomplete profile before calling the engine."""
    miss = extractor.missing(profile)
    if miss:
        raise UserError("Some answers are missing: " + ", ".join(m.replace("_", " ") for m in miss) + ".")
    ok, msg = data_ready()
    if not ok:
        raise UserError(msg)

    def go():
        res = pipeline.run(profile)
        explainer.add_to_trace(res, profile)
        return res

    res = _guard("running the analysis", go)
    store(res, profile)
    logger().info("analysis ok: %d strategies, verdict %s", len(res.get("strategies", [])), res.get("verdict"))
    return res


def store(res: dict, profile: dict) -> dict | None:
    """Evidence on AWS (slide 7, #25): the run's trace to S3, local copy if S3 fails. Never blocks the client."""
    try:
        out = tracestore.save_run(res, profile, persona="interface")
        logger().info("trace stored (%s): %s%s", out["stored"], out["where"], f" ({out['note']})" if out["note"] else "")
        return out
    except Exception:  # noqa: BLE001 — saving the evidence must never break the analysis
        logger().exception("trace store failed")
        return None


def extract_text(text: str) -> dict:
    """Free text → {profile, missing, questions, notes, source}. Empty or too long text is refused politely."""
    t = (text or "").strip()
    if len(t) < 15:
        raise UserError("Please write a few sentences about your situation (age, amount, horizon, goal).")
    return _guard("reading your text", extractor.extract, t[:MAX_TEXT])


def ask_analyst(question: str, res: dict, profile: dict, history: list[dict] | None = None) -> dict:
    """One turn of the conversation. Returns the Analyst's answer dict plus `cut` (question shortened) ."""
    q = " ".join((question or "").split())
    if not q:
        raise UserError("Please type a question.")
    if not res or not res.get("strategies"):
        raise UserError("Run the analysis first: the assistant answers about your own results.")
    cut = len(q) > MAX_QUESTION
    q = q[:MAX_QUESTION]
    turns = [{"question": h["question"], "answer": h.get("answer", "")} for h in (history or []) if h.get("question")]
    a = _guard("answering your question", analyst.ask, q, res, profile, history=turns)
    logger().info("analyst %s via %s, %d tool call(s)", a.get("status"), a.get("source"), len(a.get("tool_calls", [])))
    return {**a, "cut": cut, "text": analyst.strip_disclaimer(a.get("answer", "")), "disclaimer": DISCLAIMER}


def charts(res: dict) -> dict:
    """Charts from the engine's own chart functions (same numbers as the trace). A chart that fails is left out
    (logged), it never breaks the results page."""
    from dh.agents import market_charts
    from dh.agents import portfolio_charts as pc

    out, strategies = {}, res.get("strategies", [])
    try:
        out["growth"] = market_charts.growth_chart(market_charts.growth_data({s["name"]: s["weights"] for s in strategies}))
    except Exception:  # noqa: BLE001
        logger().exception("growth chart")
    for s in strategies:
        try:
            out[("split", s["key"])] = pc.split_curve_chart(pc.split_curve_data(s), res["limits"], s)
            df = pc.outcome_frame(s)
            if df is not None:
                out[("outcome", s["key"])] = market_charts.outcome_chart(df)
        except Exception:  # noqa: BLE001
            logger().exception("strategy chart %s", s.get("key"))
    return out


def caps_shown(res: dict, profile: dict) -> dict:
    """The per-company caps the Explainer shows, as {ticker: 'x%'} (engine function, nothing computed here)."""
    try:
        return explainer._caps_shown(res.get("strategies", []), res["limits"], profile)
    except Exception:  # noqa: BLE001
        logger().exception("caps")
        return {}
