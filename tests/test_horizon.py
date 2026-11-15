"""Horizon directive (decision #22): the sooner the money is needed, the less growth, estimated per client."""
import pytest

from dh.agents.profiler import derive_limits
from dh.agents.rules import H_FULL_GROWTH, H_NO_GROWTH, horizon_max_growth
from dh.agents.scenarios import AMIRA, ROBERT


def test_directive_shape():
    assert horizon_max_growth(H_NO_GROWTH) == 0 and horizon_max_growth(1) == 0
    assert horizon_max_growth(3) < 0.10                      # 3 years: almost no stocks
    assert horizon_max_growth(H_FULL_GROWTH) == 1 == horizon_max_growth(30)
    ys = [2, 3, 4, 5, 8, 10, 12, 15]
    assert all(horizon_max_growth(a) <= horizon_max_growth(b) for a, b in zip(ys, ys[1:]))


def test_profiler_uses_the_strictest_floor_and_says_why():
    r = derive_limits(ROBERT)                                # 4 years, 20% withdrawals
    assert r["horizon_max_growth"] == pytest.approx(horizon_max_growth(4))
    assert r["min_defensive"] == pytest.approx(1 - horizon_max_growth(4))
    assert any("horizon 4 years" in x for x in r["reasons"])
    a = derive_limits(AMIRA)                                 # long horizon: the directive doesn't bind
    assert a["horizon_max_growth"] == 1 and a["min_defensive"] < 0.5
    cash = derive_limits(dict(AMIRA, withdrawal_share_3y=0.6))
    assert cash["min_defensive"] == pytest.approx(0.6) and any("withdrawn" in x for x in cash["reasons"])
