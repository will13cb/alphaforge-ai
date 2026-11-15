"""Resolution layer for the quantitative audit (notes/risk-architecture.md). PHASE 1 SKELETON: nothing here is wired
into the pipeline yet; `dh.agents.*` behaves exactly as before.

One module per responsibility, one shared vocabulary (`contracts`):

    contracts        enums and dataclasses every module speaks: which return measure, which loss measure, which
                     return assumption, an Issue. No computation, no dependency.
    loss_model   (A) distribution of FUTURE losses over the client's horizon (not one past drawdown), exceedance
                     probability, equity ceiling with its uncertainty, window sensitivity, out-of-sample check.
    goals        (B) goal feasibility under named return assumptions; a status, never "more than 100% stocks".
    levels       (C) multi-dimensional risk vector; ordering that reports contradictions instead of inventing one.
    kyc_validation (D) comparability of the KYC bets, cautious vs inconsistent answers, question/measure match.
    frontier     (E) one return measure per frontier, dominated points, backtracking.
    sync         (F) fingerprints of weights and data stamped on every result; stale results detected.
    controls     (G) registry of controls by kind; duplicates and circular checks detected.

Dependency rule (tested in tests/test_risk_controls.py): `dh.risk` may import `dh.metrics`, `dh.quant_toolkit`,
`dh.data` and `dh.agents.rules` only. It never imports the Portfolio, Guardian, checks or LLM agents: in phase 2
they import `dh.risk`, so no cycle can appear.
"""
