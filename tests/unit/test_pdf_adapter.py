"""Stage 0a: the PDF -> Markdown adapter.

Runs entirely offline. Rendering and the provider are both injected, so the stage's
logic -- manifest, resume, failure recording, cost accounting -- is testable without a
key or a network. One test exercises the real poppler renderer when it is available.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pipeline.prompts import load_prompt
from pipeline.providers import LLMResponse, ScriptedProvider, TransientProviderError
from pipeline.stages.pdf_adapter import (
    ExtractionManifest,
    PopplerRenderer,
    extract_pages,
    plan_extraction,
)

HISTORICAL_PDF = Path(
    "/Users/rxw/Desktop/projects/research/pdf_extractions/graph theory application.pdf"
)


class StubRenderer:
    """Produces a deterministic 'PNG' per page without poppler."""

    def __init__(self) -> None:
        self.rendered: list[int] = []

    def page_count(self, pdf: Path) -> int:
        return 270

    def render(self, pdf: Path, page: int, out_dir: Path, *, dpi: int) -> Path:
        self.rendered.append(page)
        images = Path(out_dir) / "page_images"
        images.mkdir(parents=True, exist_ok=True)
        png = images / f"page_{page:03d}.png"
        png.write_bytes(f"PNG:{page}:{dpi}".encode())
        return png


@pytest.fixture
def fake_pdf(tmp_path):
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    return pdf


def _provider(text="**Theorem 3.1** $\\kappa \\le \\kappa'$.\n[figure omitted]"):
    return ScriptedProvider(
        lambda r: LLMResponse(
            text=text, model=r.model, provider="scripted",
            input_tokens=1200, output_tokens=300, usd=0.0135, wall_ms=900,
        )
    )


def test_extraction_writes_pages_and_a_manifest(tmp_path, fake_pdf):
    manifest = extract_pages(
        fake_pdf, tmp_path / "out", [50, 51],
        provider=_provider(), renderer=StubRenderer(),
        source_title="Graph Theory with Applications", printed_page_offset=8,
    )
    assert (tmp_path / "out/extracted/page_050.md").exists()
    assert (tmp_path / "out/manifest.jsonl").exists()
    row = manifest.rows[50]
    assert row.status == "ok"
    assert row.printed_page == 42
    assert row.prompt_version == "ingest/extract-page/v1"
    assert row.output_sha256 and row.input_tokens == 1200 and row.usd == 0.0135


def test_the_manifest_totals_are_the_cost_report_the_summer_lacked(tmp_path, fake_pdf):
    manifest = extract_pages(
        fake_pdf, tmp_path / "out", [50, 51, 52],
        provider=_provider(), renderer=StubRenderer(), source_title="t",
    )
    totals = manifest.totals()
    assert totals["pages"] == 3 and totals["ok"] == 3
    assert totals["input_tokens"] == 3600
    assert totals["usd"] == pytest.approx(0.0405)
    assert totals["figure_omissions"] == 3


def test_resume_skips_cached_pages(tmp_path, fake_pdf):
    renderer = StubRenderer()
    extract_pages(fake_pdf, tmp_path / "out", [50, 51], provider=_provider(),
                  renderer=renderer, source_title="t")
    assert renderer.rendered == [50, 51]
    extract_pages(fake_pdf, tmp_path / "out", [50, 51, 52], provider=_provider(),
                  renderer=renderer, source_title="t")
    assert renderer.rendered == [50, 51, 52], "only the new page should be rendered"


def test_a_changed_prompt_or_model_invalidates_the_cache(tmp_path, fake_pdf):
    """Report 00 §B5: the summer's resume was keyed on file existence, so a changed
    prompt regenerated nothing and the corpus silently mixed generations."""
    renderer = StubRenderer()
    extract_pages(fake_pdf, tmp_path / "out", [50], provider=_provider(),
                  renderer=renderer, source_title="t", model="claude-opus-5")
    extract_pages(fake_pdf, tmp_path / "out", [50], provider=_provider(),
                  renderer=renderer, source_title="t", model="claude-sonnet-5")
    assert renderer.rendered == [50, 50]


def test_force_reextracts(tmp_path, fake_pdf):
    renderer = StubRenderer()
    for force in (False, True):
        extract_pages(fake_pdf, tmp_path / "out", [50], provider=_provider(),
                      renderer=renderer, source_title="t", force=force)
    assert renderer.rendered == [50, 50]


def test_a_failure_is_recorded_not_swallowed(tmp_path, fake_pdf):
    def boom(_request):
        raise TransientProviderError("503 service unavailable")

    manifest = extract_pages(
        fake_pdf, tmp_path / "out", [139], provider=ScriptedProvider(boom),
        renderer=StubRenderer(), source_title="t", max_attempts=2,
    )
    row = manifest.rows[139]
    assert row.status == "failed"
    assert "503" in row.error
    assert row.attempts == 2
    assert not (tmp_path / "out/extracted/page_139.md").exists()
    assert manifest.totals()["failed"] == 1


def test_a_failed_page_is_retried_on_the_next_run(tmp_path, fake_pdf):
    def boom(_request):
        raise TransientProviderError("timeout")

    extract_pages(fake_pdf, tmp_path / "out", [139], provider=ScriptedProvider(boom),
                  renderer=StubRenderer(), source_title="t", max_attempts=1)
    manifest = extract_pages(fake_pdf, tmp_path / "out", [139], provider=_provider(),
                             renderer=StubRenderer(), source_title="t")
    assert manifest.rows[139].status == "ok"


def test_manifest_round_trips(tmp_path, fake_pdf):
    extract_pages(fake_pdf, tmp_path / "out", [50], provider=_provider(),
                  renderer=StubRenderer(), source_title="t")
    reloaded = ExtractionManifest.load(tmp_path / "out/manifest.jsonl")
    assert reloaded.rows[50].status == "ok"


def test_planning_is_free_and_pure(tmp_path, fake_pdf):
    manifest = ExtractionManifest.load(tmp_path / "nope/manifest.jsonl")
    todo, cached = plan_extraction(manifest, range(9, 12), load_prompt("ingest", "extract-page"),
                                   "claude-opus-5", 150)
    assert todo == [9, 10, 11] and cached == []


@pytest.mark.skipif(
    not HISTORICAL_PDF.exists() or shutil.which("pdftoppm") is None,
    reason="needs poppler and the historical PDF",
)
def test_the_real_renderer_supplies_the_missing_split_step(tmp_path):
    """Report 00 §A.3: no committed script produced pages/page_NNN.pdf, so a fresh clone
    could not start the pipeline at all. This is that step, committed and exercised."""
    renderer = PopplerRenderer()
    assert renderer.page_count(HISTORICAL_PDF) == 270
    png = renderer.render(HISTORICAL_PDF, 51, tmp_path, dpi=72)
    assert png.exists() and png.stat().st_size > 1000
    assert (tmp_path / "pages/page_051.pdf").exists()
