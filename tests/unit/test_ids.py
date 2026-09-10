"""Identity is the architectural keystone (rule 2), so it is tested hardest."""

from __future__ import annotations

import pytest

from pipeline.corpus.ids import (
    IdentityError,
    content_fingerprint,
    declaration_id,
    normalize_label,
    normalize_slug,
    parse_declaration_id,
)
from pipeline.artifacts.models import SourceItemKind as K


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Theorem 3.2", "3.2"),
        ("theorem 3.2", "3.2"),
        ("3.2", "3.2"),
        ("Corollary 3.2.1", "3.2.1"),
        ("1.2.8(b)", "1.2.8b"),
        ("Ex 4.2.11 (a)", "4.2.11a"),
        ("8.5.2(a)*", "8.5.2a"),
        ("3.2.6*", "3.2.6"),
        ("  Exercise  1.1.3  ", "1.1.3"),
    ],
)
def test_label_normalisation_is_stable_across_printed_forms(raw, expected):
    assert normalize_label(raw) == expected


def test_starred_exercise_is_the_same_exercise():
    """B&M stars exercises that have hints; it is not a different exercise."""
    assert normalize_label("3.2.6*") == normalize_label("3.2.6")


def test_labelled_id_matches_the_documented_shape():
    assert declaration_id("euler-analysis", "3", K.THEOREM, label="Theorem 3.2") == "ea-ch3-thm-3.2"


def test_same_number_different_kind_yields_different_ids():
    """Sources number corollaries and exercises independently, so both 3.2.1 exist."""
    cor = declaration_id("euler-analysis", "3", K.COROLLARY, label="3.2.1")
    ex = declaration_id("euler-analysis", "3", K.EXERCISE, label="3.2.1")
    assert cor != ex
    assert cor == "ea-ch3-cor-3.2.1"
    assert ex == "ea-ch3-ex-3.2.1"


def test_unlabelled_items_use_section_and_ordinal():
    a = declaration_id("bm", "3", K.DEFINITION, section="3.1", ordinal=1)
    b = declaration_id("bm", "3", K.DEFINITION, section="3.1", ordinal=2)
    assert a == "bm-ch3-def-3.1-1"
    assert a != b


def test_identity_is_never_derived_from_statement_text():
    """The failure this module exists to prevent: LLM wording becoming identity."""
    with pytest.raises(IdentityError):
        declaration_id("bm", "3", K.DEFINITION)


def test_ordinal_is_one_based():
    with pytest.raises(IdentityError):
        declaration_id("bm", "3", K.DEFINITION, section="3.1", ordinal=0)


def test_ids_round_trip_through_the_parser():
    for did in ("bm-ch3-thm-3.2", "bm-ch1-ex-1.2.8b", "bm-ch3-def-3.1-1"):
        parsed = parse_declaration_id(did)
        assert parsed["corpus"] == "bm"


def test_malformed_ids_are_rejected():
    for bad in ("bm_ch3_thm_3.2", "ch3-thm-3.2", "BM-CH3-THM-3.2", ""):
        with pytest.raises(IdentityError):
            parse_declaration_id(bad)


def test_fingerprint_separates_identity_from_content():
    """Same theorem, re-extracted with different whitespace, is the same declaration."""
    assert content_fingerprint("a", "b") == content_fingerprint("a", "b")
    assert content_fingerprint("a", "b") != content_fingerprint("a", "b ")
    # None is distinguishable from empty string: "no proof" != "empty proof".
    assert content_fingerprint("a", None) != content_fingerprint("a", "")


def test_slug_is_not_used_for_identity_but_is_stable():
    assert normalize_slug("A vertex cut of G") == "a-vertex-cut-of-g"
