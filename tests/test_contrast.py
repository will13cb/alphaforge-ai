"""Same request, three clients (dh.agents.contrast): offline, synthetic returns from test_portfolio."""
from test_portfolio import fewer_scenarios, rets  # noqa: F401  (shared synthetic data and the fast-path fixture)

from dh.agents.contrast import contrast, markdown


def test_same_request_three_limits(rets):
    rows = contrast("TSLA", 0.25, rets=rets, holdings={})
    by = {r["persona"]: r for r in rows}
    assert list(by) == ["amira", "mateo", "robert"]
    # three different loss limits and caps, the cautious client gets the smallest cap
    assert by["robert"]["loss_limit"] < by["mateo"]["loss_limit"] < by["amira"]["loss_limit"]
    assert by["robert"]["cap"] < by["mateo"]["cap"] < by["amira"]["cap"]
    for r in rows:   # every row read from the pipeline: 25% as asked breaks a limit, the cap and reason are shown
        assert r["as_asked"]["verdict"] == "fail" and "G9" in r["as_asked"]["fails"]
        assert r["at_cap"] is not None and r["reason"]
        assert r["answer"].startswith(("up to", "not on this strategy"))
    md = markdown(rows)
    assert "Robert" in md and f"{by['robert']['cap']:.1%}" in md
