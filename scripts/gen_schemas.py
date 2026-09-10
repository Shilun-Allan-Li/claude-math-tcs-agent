"""Emit JSON Schema for every persisted artifact type.

Generated, never hand-edited: the pydantic models are the source of truth, and a schema
that could drift from them would be worse than none. Regenerate with:

    python scripts/gen_schemas.py
"""
import json
from pathlib import Path

from pipeline.artifacts.models import (
    AnnotatedDeclaration, CheckerFinding, ContextPackage, DeclarationRecord,
    DependencyEdge, FormalizationProposal, ProofAttempt, ReviewDecision,
    SourceChapter, SourceDocument, SourceItem, SourceLeanMapping, StageRun,
)
from pipeline.orchestrator.state import PipelineRun

MODELS = [
    SourceDocument, SourceChapter, SourceItem, AnnotatedDeclaration,
    FormalizationProposal, SourceLeanMapping, DependencyEdge, CheckerFinding,
    ReviewDecision, ProofAttempt, ContextPackage, StageRun, DeclarationRecord,
    PipelineRun,
]
out = Path(__file__).resolve().parents[1] / "schemas"
out.mkdir(exist_ok=True)
index = []
for model in MODELS:
    name = model.__name__
    schema = model.model_json_schema()
    (out / f"{name}.schema.json").write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    index.append({"artifact": name, "schema": f"{name}.schema.json",
                  "title": schema.get("description", "").split("\n")[0]})
(out / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
print(f"wrote {len(MODELS)} schemas to {out}")
