"""Offline and stable: the company caps (#24) use a fixed copy of the worst drops, never data/raw."""
import os

import pytest

os.environ.setdefault("AF_LANG", "en")  # app tests read the English UI; French is tested in test_i18n.py (#49)

from dh.agents import profiler
from dh.agents.scenarios import DROPS_DEMO


@pytest.fixture(autouse=True)
def _fixed_worst_drops(monkeypatch):
    monkeypatch.setattr(profiler, "worst_drops", lambda: dict(DROPS_DEMO))


@pytest.fixture(autouse=True)
def _traces_stay_in_the_test(monkeypatch, tmp_path):
    """A test run is not evidence: no trace goes to S3 (`make test` loads .env, so S3_BUCKET may be set) nor to the
    repo's outputs/traces/ (which `make backup` commits). Tests that check the S3 path patch `_put_s3` themselves."""
    from dh import tracestore

    monkeypatch.delenv("S3_BUCKET", raising=False)
    monkeypatch.setattr(tracestore, "LOCAL_DIR", tmp_path / "traces")


@pytest.fixture(autouse=True)
def _fewer_loss_paths(monkeypatch):
    """The Portfolio's loss model (decision R1) with fewer simulated paths in tests: same method, faster suite."""
    from dh.agents import portfolio
    for k in ("N_LOSS", "N_LOSS_FINAL", "N_RANGE"):
        monkeypatch.setattr(portfolio, k, 300)
