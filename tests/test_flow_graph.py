"""The live pipeline graph: built only from recorded hand-offs."""
from interface.ui import flow


def test_working_node_is_the_last_receiver_and_finishing_clears_it():
    steps = [{"agent": "Client", "to": "Profiler"}, {"agent": "Profiler", "to": "Market data"},
             {"agent": "Market data", "to": "Portfolio"}, {"agent": "Portfolio", "to": "Guardian"}]
    runs, used, working = flow.state(steps)
    assert working == "Guardian" and runs["Portfolio"] == 1 and ("Portfolio", "Guardian") in used
    assert flow.state(steps, finished=True)[2] is None
    assert flow.state([])[2] == "Profiler"


def test_repeat_runs_counted_and_unknown_agents_ignored():
    steps = [{"agent": "Guardian", "to": "Critic"}, {"agent": "Guardian", "to": "Client"},
             {"agent": "Fixed-income agent", "to": "Client"}, {"agent": "Trace store", "to": "Amazon S3"}]
    runs, _, _ = flow.state(steps, finished=True)
    assert runs["Guardian"] == 2 and "Fixed-income agent" not in runs and runs["Trace store"] == 1
    html = flow.svg(steps, finished=True)
    assert "×2" in html and "<svg" in html and "All steps recorded." in html
