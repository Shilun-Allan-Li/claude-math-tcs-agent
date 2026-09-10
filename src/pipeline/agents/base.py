"""The executable agent contract.

A prompt is not an agent. A prompt is a Markdown file under ``prompts/``; an agent is the
code in this package that decides what to retrieve, renders that prompt against the
retrieved context, calls a provider, parses the reply, validates it against a schema,
persists the result, and returns a typed artifact.

Every agent runs the same eight steps, in this order::

    load structured input      ← the artifact store, never a caller's memory
    build bounded context      ← a deterministic query against the CorpusGraph
    load prompt                ← a version-controlled file under prompts/
    invoke model               ← the provider adapter
    parse result               ← text → payload
    validate schema            ← pydantic, extra="forbid"; a bad reply is a failed run
    persist artifact           ← the artifact store
    return structured output   ← a typed artifact, not a string

:meth:`Agent.run` is that sequence, written once. Subclasses supply the parts, and the
parts are separately replaceable: swapping a prompt version changes no code, and swapping
a context builder changes no prompt.

What is deliberately absent from every signature below is a conversation. An agent
receives a registry and a declaration id. It cannot be handed a transcript, so it cannot
come to depend on one.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from pipeline.corpus import CorpusRegistry
from pipeline.artifacts.models import ContextPackage, Stage
from pipeline.prompts import Prompt, load_prompt
from pipeline.providers import LLMProvider

__all__ = ["Agent", "AgentResult", "AgentError"]


class AgentError(RuntimeError):
    """Raised when an agent's output cannot be validated or persisted."""


@dataclass
class AgentResult:
    """What one agent invocation produced."""

    agent: str
    stage: Stage
    target_id: str
    artifacts: list[Any] = field(default_factory=list)
    context: ContextPackage | None = None
    stage_run_id: str | None = None
    warnings: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return bool(self.artifacts) or not self.warnings


class Agent(ABC):
    """One executable pipeline worker."""

    #: Stable name, used in run records and in ``pipeline agents``.
    name: ClassVar[str]
    #: Which pipeline stage this agent implements.
    stage: ClassVar[Stage]
    #: ``(stage, name)`` resolved against ``prompts/<stage>/<name>/v<N>.md``. ``None`` for
    #: an agent that consults no model, or that fans out over several prompts.
    prompt_ref: ClassVar[tuple[str, str] | None] = None
    #: Typed inputs, for documentation and for the worker table.
    input_model: ClassVar[tuple[type, ...]] = ()
    #: The artifact type every element of ``artifacts`` must be an instance of.
    output_model: ClassVar[type]
    #: False for agents that are wholly deterministic.
    requires_provider: ClassVar[bool] = True
    description: ClassVar[str] = ""

    # ---------------------------------------------------------------- the parts

    def load_prompt(self, version: str | None = None) -> Prompt | None:
        """Step 3. The prompt is data on disk, loaded per run, never inlined here."""
        if self.prompt_ref is None:
            return None
        return load_prompt(*self.prompt_ref, version)

    def build_context(
        self, registry: CorpusRegistry, target_id: str
    ) -> ContextPackage | None:
        """Step 2. A deterministic query against the corpus graph.

        ``None`` means the agent reads the record directly and retrieves nothing — true
        of the checkers, which are given the declaration and compare it against itself.
        """
        return None

    @abstractmethod
    def execute(
        self,
        registry: CorpusRegistry,
        target_id: str,
        *,
        provider: LLMProvider | None = None,
        **options: Any,
    ) -> AgentResult:
        """Steps 1 and 4-7: load, invoke, parse, validate, persist.

        Implementations delegate to the stage functions in :mod:`pipeline.stages`, which
        already enforce their own contracts (rule 6's proof-body rejection, the registry
        name barrier, the annotator's verbatim-quote requirement). This method's job is
        to present that work through one uniform surface.
        """

    # ------------------------------------------------------------------ the whole

    def run(
        self,
        registry: CorpusRegistry,
        target_id: str,
        *,
        provider: LLMProvider | None = None,
        **options: Any,
    ) -> AgentResult:
        """The full sequence, with schema validation enforced at the boundary."""
        if self.requires_provider and provider is None:
            raise AgentError(f"{self.name} needs a provider and none was supplied")
        result = self.execute(registry, target_id, provider=provider, **options)
        self.validate(result)
        return result

    def validate(self, result: AgentResult) -> None:
        """Step 6, enforced here so no subclass can skip it.

        The stage functions build typed artifacts already; this asserts the agent
        returned what its class declared, which is the part a refactor breaks silently.
        """
        for artifact in result.artifacts:
            if not isinstance(artifact, self.output_model):
                raise AgentError(
                    f"{self.name} returned {type(artifact).__name__}, "
                    f"expected {self.output_model.__name__}"
                )

    def describe(self) -> dict[str, Any]:
        prompt = self.prompt_ref
        return {
            "agent": self.name,
            "stage": self.stage.value,
            "input": [m.__name__ for m in self.input_model],
            "output": self.output_model.__name__,
            "prompt": "/".join(prompt) if prompt else None,
            "context_builder": type(self).build_context is not Agent.build_context,
            "requires_provider": self.requires_provider,
            "description": self.description,
        }
