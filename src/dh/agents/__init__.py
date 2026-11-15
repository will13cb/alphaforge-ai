"""Agents. Deterministic parts (Profiler rules, Guardian, trace) live here; LLM agents (extractor, Critic,
Explainer) call dh.llm.ask. Contract between them: notes/contract.md."""

from .pipeline import run
from .profiler import derive_limits
