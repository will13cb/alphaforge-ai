"""Every tool the Critic and the Analyst hand to Strands must build a JSON schema (the Bedrock path).

Regression: `market.required_return` has an internal `rets: pd.DataFrame` parameter; Strands couldn't build its schema
(PydanticSchemaGenerationError), so on Bedrock the Critic and the Analyst fell back offline for every call."""
import inspect

import pytest

from dh.agents import analyst, critic, market
from dh.agents.pipeline import run
from dh.agents.scenarios import DEMO_PROFILES, DROPS_DEMO


def _all_tools():
    res = run(DEMO_PROFILES["robert_tsla"], propose=False, drops=DROPS_DEMO)
    return (list(market.AGENT_TOOLS) + critic.make_tools([], res["limits"], {})
            + analyst.make_tools(res, DEMO_PROFILES["robert_tsla"], holdings={}))


def test_wrapped_tools_hide_internal_parameters():
    rec = critic.Recorder()
    for t in _all_tools():
        params = inspect.signature(rec.wrap(t)).parameters
        assert not set(params) & critic.INTERNAL_PARAMS, t.__name__


def test_strands_builds_every_tool_schema():
    strands = pytest.importorskip("strands")
    rec = critic.Recorder()
    for t in _all_tools():
        spec = strands.tool(rec.wrap(t)).tool_spec
        assert spec["name"] == t.__name__ and "rets" not in spec["inputSchema"]["json"].get("properties", {})
