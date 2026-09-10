"""Executable agents: the workers that call models.

`prompts/` holds model instructions. This package holds the code that runs them. The
separation is the point — a prompt cannot load an artifact, query the graph, validate a
schema or persist a result, and nothing here embeds instruction text.
"""

from pipeline.agents.base import Agent, AgentError, AgentResult
from pipeline.agents.workers import (
    AGENTS,
    Annotator,
    CheckerOrchestrator,
    Formalizer,
    ProofWorker,
)

__all__ = [
    "Agent", "AgentResult", "AgentError", "AGENTS",
    "Annotator", "Formalizer", "CheckerOrchestrator", "ProofWorker",
]


def agent_for(stage) -> Agent:
    if stage not in AGENTS:
        raise KeyError(f"no agent for stage {getattr(stage, 'value', stage)!r}")
    return AGENTS[stage]


def describe_agents() -> list[dict]:
    """The agent table, for ``pipeline agents`` and for the docs."""
    return [a.describe() for a in AGENTS.values()]
