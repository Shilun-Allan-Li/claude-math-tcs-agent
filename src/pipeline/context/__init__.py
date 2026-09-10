"""Bounded context construction.

Rule 4: an agent's input is assembled by *querying the corpus graph*, never by replaying a
conversation or concatenating prior chapters. Every package records what it supplied and
why, so "what did the agent actually see?" is answerable after the fact.
"""

from pipeline.context.builders import (
    build_annotation_context,
    build_formalization_context,
    build_proof_context,
    package_id,
)

__all__ = ["build_annotation_context", "build_formalization_context",
           "build_proof_context", "package_id"]
