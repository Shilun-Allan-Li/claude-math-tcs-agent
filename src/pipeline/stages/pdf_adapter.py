"""Stage 0a -- PDF to Markdown.

This adapts the summer's extraction pipeline rather than replacing it. Report 00 found
that stage healthy ("scripts, not agents ... the evidence supports the memory") and
recommended a specific, small set of fixes; those, and only those, are implemented here:

======  =========================================================================
report  change
======  =========================================================================
D1      the PDF-splitting step, which existed only as an unsaved shell command
D2/D3   one entry point with pinned, declared dependencies (poppler + a provider)
D4      ``manifest.jsonl`` -- one row per page binding pdf/page/output/model/prompt/cost
D5      token usage recorded from the response instead of discarded
D6      resume keyed on (prompt, model, dpi), not on "the output file exists"
D7      hand-repaired pages carry ``extractor: manual`` instead of a prose comment
D9      the printed-to-PDF page offset persisted as data (see ``corpora/*.json``)
======  =========================================================================

The extraction prompt itself is unchanged in substance and now lives in
``prompts/ingest/extract-page/v1.md``.

Rendering is injectable so the whole stage is exercisable offline: :class:`PopplerRenderer`
shells out to ``pdfseparate``/``pdftoppm``, and tests substitute a stub.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pipeline.prompts import Prompt, load_prompt
from pipeline.providers import LLMProvider, LLMRequest, call_with_retry

__all__ = [
    "PageRenderer",
    "PopplerRenderer",
    "PageRecord",
    "ExtractionManifest",
    "extract_pages",
    "plan_extraction",
    "PDF_ADAPTER_VERSION",
]

PDF_ADAPTER_VERSION = "pdf_adapter/v1"
NO_TEXT_SENTINEL = "[no extractable text]"


class PageRenderer(Protocol):
    """Turns one page of a PDF into a PNG. Injectable so ingestion is testable offline."""

    def render(self, pdf: Path, page: int, out_dir: Path, *, dpi: int) -> Path: ...
    def page_count(self, pdf: Path) -> int: ...


class PopplerRenderer:
    """The real renderer: ``pdfseparate`` then ``pdftoppm``, both from poppler.

    The split step is the one report 00 §A.3 found missing from the repository entirely
    -- ``render_page_to_png`` required ``pages/page_NNN.pdf`` to already exist, and no
    committed script produced them, so a fresh clone could not start the pipeline.
    """

    def __init__(self, *, pdfseparate: str = "pdfseparate", pdftoppm: str = "pdftoppm",
                 pdfinfo: str = "pdfinfo") -> None:
        self.pdfseparate = pdfseparate
        self.pdftoppm = pdftoppm
        self.pdfinfo = pdfinfo

    #: Where each binary comes from, by platform. Poppler is packaged everywhere, but
    #: it is a native dependency and will not be on a fresh machine.
    INSTALL_HINTS = {
        "darwin": "brew install poppler",
        "linux": "apt install poppler-utils   (or: dnf install poppler-utils)",
        "win32": "conda install -c conda-forge poppler   (or download poppler for Windows)",
    }

    def missing_binaries(self) -> list[str]:
        """Which of the three poppler tools are not on PATH."""
        import shutil  # noqa: PLC0415

        return [b for b in (self.pdfinfo, self.pdfseparate, self.pdftoppm)
                if shutil.which(b) is None]

    def preflight(self) -> None:
        """Fail with something actionable before shelling out.

        Without this the first symptom is ``FileNotFoundError: 'pdfinfo'`` from deep
        inside a subprocess call, which says nothing about what to install. PDF
        rendering is the one part of the pipeline that needs a native dependency, so it is
        also the one part that has to explain itself.
        """
        missing = self.missing_binaries()
        if not missing:
            return
        hint = self.INSTALL_HINTS.get(sys.platform, "install the poppler utilities")
        raise RuntimeError(
            f"PDF rendering needs poppler, and {', '.join(missing)} "
            f"{'is' if len(missing) == 1 else 'are'} not on PATH.\n"
            f"  install: {hint}\n"
            f"  or: skip PDF extraction entirely — `pipeline ingest` reads Markdown, so if "
            f"you already have the text you never need poppler. See README, "
            f"'Bringing your own source'."
        )

    def page_count(self, pdf: Path) -> int:
        self.preflight()
        out = subprocess.run(
            [self.pdfinfo, str(pdf)], check=True, capture_output=True, text=True
        ).stdout
        for line in out.splitlines():
            if line.startswith("Pages:"):
                return int(line.split()[1])
        raise RuntimeError(f"{self.pdfinfo} reported no page count for {pdf}")

    def split_page(self, pdf: Path, page: int, out_dir: Path) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"page_{page:03d}.pdf"
        if not target.exists():
            subprocess.run(
                [self.pdfseparate, "-f", str(page), "-l", str(page), str(pdf), str(target)],
                check=True, capture_output=True,
            )
        return target

    def render(self, pdf: Path, page: int, out_dir: Path, *, dpi: int) -> Path:
        self.preflight()
        single = self.split_page(pdf, page, out_dir / "pages")
        images = out_dir / "page_images"
        images.mkdir(parents=True, exist_ok=True)
        prefix = images / f"page_{page:03d}"
        png = prefix.with_suffix(".png")
        if not png.exists():
            subprocess.run(
                [self.pdftoppm, "-png", "-r", str(dpi), "-singlefile", str(single), str(prefix)],
                check=True, capture_output=True,
            )
        if not png.exists():
            raise RuntimeError(f"{self.pdftoppm} did not produce {png}")
        return png


@dataclass
class PageRecord:
    """One manifest row. This is report 00's D4, the highest-value change in that stage."""

    pdf_sha256: str
    pdf_page: int
    printed_page: int | None
    output_path: str
    output_sha256: str | None
    status: str  # ok | failed | skipped
    extractor: str  # api | manual
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    dpi: int | None = None
    attempts: int = 0
    retries: int = 0
    error: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    usd: float | None = None
    wall_ms: int | None = None
    figure_omissions: int = 0
    extracted_at: str = ""

    def resume_key(self) -> tuple[str | None, str | None, int | None]:
        """What makes a cached page still valid.

        Report 00 §B5: the summer keyed resume on "the .md exists and is non-empty", so a
        changed prompt, model or DPI silently regenerated nothing.
        """
        return (self.prompt_version, self.model, self.dpi)

    def to_json(self) -> str:
        return json.dumps(self.__dict__, sort_keys=True, ensure_ascii=False)


@dataclass
class ExtractionManifest:
    path: Path
    rows: dict[int, PageRecord] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> ExtractionManifest:
        rows: dict[int, PageRecord] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    data = json.loads(line)
                    rows[int(data["pdf_page"])] = PageRecord(**data)
        return cls(path=path, rows=rows)

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".jsonl.tmp")
        tmp.write_text(
            "".join(self.rows[k].to_json() + "\n" for k in sorted(self.rows)), encoding="utf-8"
        )
        os.replace(tmp, self.path)
        return self.path

    def totals(self) -> dict[str, object]:
        rows = list(self.rows.values())
        usd = [r.usd for r in rows if r.usd is not None]
        return {
            "pages": len(rows),
            "ok": sum(1 for r in rows if r.status == "ok"),
            "failed": sum(1 for r in rows if r.status == "failed"),
            "manual": sum(1 for r in rows if r.extractor == "manual"),
            "input_tokens": sum(r.input_tokens or 0 for r in rows),
            "output_tokens": sum(r.output_tokens or 0 for r in rows),
            "usd": round(sum(usd), 4) if usd else None,
            "figure_omissions": sum(r.figure_omissions for r in rows),
        }


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def plan_extraction(
    manifest: ExtractionManifest,
    pages: range | list[int],
    prompt: Prompt,
    model: str,
    dpi: int,
    *,
    force: bool = False,
) -> tuple[list[int], list[int]]:
    """Split pages into (to_extract, cached). Pure, so ``--plan`` costs nothing."""
    key = (prompt.id, model, dpi)
    todo, cached = [], []
    for page in pages:
        row = manifest.rows.get(page)
        if not force and row is not None and row.status == "ok" and row.resume_key() == key:
            cached.append(page)
        else:
            todo.append(page)
    return todo, cached


def extract_pages(
    pdf: Path,
    out_dir: Path,
    pages: range | list[int],
    *,
    provider: LLMProvider,
    renderer: PageRenderer,
    source_title: str,
    model: str | None = None,
    prompt: Prompt | None = None,
    dpi: int = 150,
    printed_page_offset: int | None = None,
    force: bool = False,
    max_attempts: int = 3,
    on_progress=None,
) -> ExtractionManifest:
    """Extract a page range to ``out_dir/extracted/page_NNN.md``, writing a manifest.

    Never silently overwrites: an existing page is reused only when its
    (prompt, model, dpi) matches the current run, and every decision is a manifest row.
    """
    prompt = prompt or load_prompt("ingest", "extract-page")
    model = model or prompt.model or "claude-opus-5"
    out_dir = Path(out_dir)
    extracted = out_dir / "extracted"
    extracted.mkdir(parents=True, exist_ok=True)

    manifest = ExtractionManifest.load(out_dir / "manifest.jsonl")
    pdf_hash = _sha256_file(pdf)
    todo, cached = plan_extraction(manifest, pages, prompt, model, dpi, force=force)

    for page in todo:
        target = extracted / f"page_{page:03d}.md"
        started = time.monotonic()
        row = PageRecord(
            pdf_sha256=pdf_hash,
            pdf_page=page,
            printed_page=(page - printed_page_offset) if printed_page_offset is not None else None,
            output_path=str(target.relative_to(out_dir)),
            output_sha256=None,
            status="failed",
            extractor="api",
            provider=provider.name,
            model=model,
            prompt_version=prompt.id,
            dpi=dpi,
            extracted_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        try:
            png = renderer.render(pdf, page, out_dir, dpi=dpi)
            request = LLMRequest(
                system=prompt.system,
                user=prompt.render(source_title=source_title, pdf_page=page),
                model=model,
                max_tokens=prompt.max_tokens,
                images=(png.read_bytes(),),
            )
            response, retries = call_with_retry(provider, request, attempts=max_attempts)
            text = response.text.strip()
            body = f"<!-- pdf page {page} -->\n\n{text}\n"
            target.write_text(body, encoding="utf-8")
            row.status = "ok"
            row.attempts = retries + 1
            row.retries = retries
            row.output_sha256 = _sha256_text(body)
            row.input_tokens = response.input_tokens
            row.output_tokens = response.output_tokens
            row.usd = response.usd
            row.figure_omissions = text.count("[figure omitted")
        except Exception as exc:  # noqa: BLE001 - the row records the failure
            row.error = f"{type(exc).__name__}: {exc}"
            row.attempts = max_attempts
        row.wall_ms = int((time.monotonic() - started) * 1000)
        manifest.rows[page] = row
        manifest.save()
        if on_progress is not None:
            on_progress(row)

    for page in cached:
        if on_progress is not None:
            on_progress(manifest.rows[page])
    return manifest
