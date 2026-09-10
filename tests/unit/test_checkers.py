"""The deterministic half of the semantic sanity checker.

These checks run with no model, so they are exactly reproducible and worth pinning. Both
answer the same question in different ways: *does the Lean signature carry a hypothesis the
source states?* A statement that silently drops one still elaborates, still compiles, and is
still wrong -- which is why the check is deterministic rather than delegated.

The size-condition pattern is also a corpus-genericity regression test. It was originally
written against one corpus's vocabulary and notation, so it recognised a size hypothesis
only when the source phrased it the way that book did; every other corpus passed the check
by not being understood by it. See ``tests/integration/test_corpus_agnostic.py``.
"""

from __future__ import annotations

import pytest

from pipeline.artifacts.models import (
    FindingCategory,
    Provenance,
    SourceItem,
    SourceItemKind,
)
from pipeline.artifacts.records import record_from_source_item
from pipeline.checkers.hybrid import _deterministic_sanity


def record(source_statement: str, lean_statement: str):
    """A minimal record carrying just the two statements the checks compare."""
    item = SourceItem(
        id="t-ch1-thm-1.1",
        document_id="t",
        chapter_id="t-ch1",
        chapter="1",
        kind=SourceItemKind.THEOREM,
        label="1.1",
        statement=source_statement,
        provenance=Provenance(producer="test"),
    )
    rec = record_from_source_item(item)
    rec.lean.name = "T.thm"
    rec.lean.statement = lean_statement
    return rec


def categories(source_statement: str, lean_statement: str) -> set[FindingCategory]:
    findings = _deterministic_sanity(
        record(source_statement, lean_statement), Provenance(producer="test")
    )
    return {f.category for f in findings}


class TestSizeConditionIsDomainNeutral:
    """A stated size hypothesis must be noticed whatever nouns the corpus uses."""

    @pytest.mark.parametrize(
        "statement",
        [
            "Let G be a graph with at least three vertices.",
            "Let S be a set with at least two elements.",
            "Suppose there are at most five primes below n.",
            "Let X be a nonempty compact space.",
            "Let U be a non-empty open interval.",
            r"Assume $\nu \geq 3$.",
            r"Let $n \geq 2$ be an integer.",
            "Assume n >= 2.",
            "Suppose there are more than three components.",
        ],
    )
    def test_a_size_condition_with_no_lean_bound_is_flagged(self, statement):
        assert FindingCategory.MISSING_CARDINALITY in categories(statement, "(a b : Nat) : a = b")

    @pytest.mark.parametrize(
        "statement",
        [
            r"If $a \mid b$ and $b \mid c$, then $a \mid c$.",
            "The sum of two even integers is even.",
            "Every continuous function on a closed interval is bounded.",
        ],
    )
    def test_a_statement_with_no_size_condition_is_not_flagged(self, statement):
        assert FindingCategory.MISSING_CARDINALITY not in categories(statement, "(a b : Nat) : a = b")

    @pytest.mark.parametrize(
        "signature",
        [
            "(G : Graph) (h : 3 <= G.card) : True",
            "[Nonempty V] (v : V) : True",
            "(n : Nat) (hn : 2 ≤ n) : True",
            "[Finite S] : True",
        ],
    )
    def test_no_warning_when_the_signature_already_carries_a_bound(self, signature):
        """The check is for a *dropped* hypothesis, not for the topic being mentioned."""
        source = "Let S be a set with at least two elements."
        assert FindingCategory.MISSING_CARDINALITY not in categories(source, signature)


class TestZeroParameter:
    """A natural-number parameter with no lower bound asserts the statement at zero."""

    def test_an_unbounded_natural_parameter_is_flagged(self):
        cats = categories("Any statement.", "(n : ℕ) : n ^ 2 >= n")
        assert FindingCategory.ZERO_PARAMETER in cats

    def test_a_bounded_natural_parameter_is_not_flagged(self):
        cats = categories("Any statement.", "(n : ℕ) (hn : 0 < n) : n ^ 2 >= n")
        assert FindingCategory.ZERO_PARAMETER not in cats


class TestFindingsAreWellFormed:
    """Whatever a checker reports has to be inspectable months later."""

    def test_every_finding_carries_evidence_and_identity(self):
        findings = _deterministic_sanity(
            record("Let S have at least two elements.", "(n : ℕ) : True"),
            Provenance(producer="test"),
        )
        assert findings, "the fixture should trip both checks"
        for finding in findings:
            assert finding.declaration_id == "t-ch1-thm-1.1"
            assert finding.message.strip()
            assert finding.evidence, f"{finding.category} reported nothing to look at"
            assert finding.confidence == 1.0, "a deterministic check is certain"

    def test_findings_are_stable_across_runs(self):
        """Re-running a stage must converge, so ids cannot depend on run order or time."""
        args = ("Let S have at least two elements.", "(n : ℕ) : True")
        first = [f.id for f in _deterministic_sanity(record(*args), Provenance(producer="test"))]
        second = [f.id for f in _deterministic_sanity(record(*args), Provenance(producer="test"))]
        assert first == second
