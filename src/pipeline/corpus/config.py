"""Corpus configuration.

A corpus is a book plus the per-chapter facts that ingestion cannot infer: where its
Markdown lives, which PDF pages it covers, and the offset between PDF page numbers and
the page numbers the book prints.

That last field is the point. Report 00 §B8: the summer's extraction indexed PDF pages
while every downstream citation used printed pages, and nothing recorded the mapping, so
chapter 3's Lean cites "p. 50" for what the book prints as page 42. Here it is data.

Configuration is JSON, discovered in ``corpora/`` and in any directory named by
``PIPELINE_CORPORA_PATH``. The second is what keeps a private or copyrighted corpus
outside the repository altogether: the engine is public, the corpora it is pointed at
need not be, and mounting one must not mean copying it into the tree.

Paths inside a config resolve relative to the config's *own* directory first, then to
the repository root. An externally mounted corpus is therefore self-contained -- config
and sources travel together -- while the committed demo, whose paths are written
repo-relative, keeps working unchanged.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import cache
from pathlib import Path

__all__ = [
    "CorpusConfig",
    "corpus_for_slug",
    "ChapterConfig",
    "ConfigError",
    "load_corpus",
    "default_corpus",
    "available_corpora",
    "corpora_dirs",
    "ENV_CORPORA_PATH",
    "REPO_ROOT",
]

#: Repository root: src/pipeline/corpus/config.py -> up four.
REPO_ROOT = Path(__file__).resolve().parents[3]
CORPORA_DIR = REPO_ROOT / "corpora"
#: Environment variable naming extra corpus directories, ``os.pathsep``-separated.
#: A corpus mounted this way lives entirely outside the repository.
ENV_CORPORA_PATH = "PIPELINE_CORPORA_PATH"


def corpora_dirs() -> tuple[Path, ...]:
    """Every directory searched for corpus configs, in priority order.

    ``corpora/`` first, then each entry of ``PIPELINE_CORPORA_PATH``. Read fresh on every
    call rather than captured at import: a long-lived process that mounts a corpus should
    see it, and tests should not have to reach into module state to arrange one.
    """
    dirs: list[Path] = [CORPORA_DIR]
    for part in os.environ.get(ENV_CORPORA_PATH, "").split(os.pathsep):
        if not (part := part.strip()):
            continue
        candidate = Path(part).expanduser()
        if candidate not in dirs:
            dirs.append(candidate)
    return tuple(dirs)


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChapterConfig:
    """One top-level division of a source.

    ``type`` is the *source's own* word for the division -- "chapter" for a textbook,
    but "unit", "part", "lecture" or "appendix" elsewhere. It is a label carried for
    rendering, never a branch in pipeline logic: nothing downstream reads it.
    """

    number: str
    title: str
    markdown: Path
    type: str = "chapter"
    pdf_page_start: int | None = None
    pdf_page_end: int | None = None
    printed_page_offset: int | None = None

    @property
    def printed_page_start(self) -> int | None:
        if self.pdf_page_start is None or self.printed_page_offset is None:
            return None
        return self.pdf_page_start - self.printed_page_offset

    @property
    def printed_page_end(self) -> int | None:
        if self.pdf_page_end is None or self.printed_page_offset is None:
            return None
        return self.pdf_page_end - self.printed_page_offset


@dataclass(frozen=True)
class CorpusConfig:
    corpus: str
    slug: str
    title: str
    authors: tuple[str, ...]
    chapters: tuple[ChapterConfig, ...]
    path: Path
    source_type: str = "book"

    @property
    def divisions(self) -> tuple[ChapterConfig, ...]:
        """Generic alias. A division happens to be a chapter in every corpus so far."""
        return self.chapters

    def division(self, number: str | int) -> ChapterConfig:
        return self.chapter(number)

    def chapter(self, number: str | int) -> ChapterConfig:
        want = str(number)
        for ch in self.chapters:
            if ch.number == want:
                return ch
        raise ConfigError(
            f"corpus {self.corpus!r} has no chapter {want!r}; "
            f"available: {', '.join(c.number for c in self.chapters)}"
        )


def default_corpus() -> str:
    """The corpus to use when none is named.

    In order: ``[corpus] default`` in ``pipeline.toml``, then ``PIPELINE_CORPUS``, then -- if
    exactly one book is configured -- that one. There is no built-in corpus, so with
    several configured and no default set, the caller has to say which.
    """
    import os  # noqa: PLC0415

    if configured := os.environ.get("PIPELINE_CORPUS"):
        return configured
    settings_path = REPO_ROOT / "pipeline.toml"
    if settings_path.exists():
        import tomllib  # noqa: PLC0415

        data = tomllib.loads(settings_path.read_text(encoding="utf-8"))
        if named := data.get("corpus", {}).get("default"):
            return str(named)
    corpora = available_corpora()
    if len(corpora) == 1:
        return corpora[0]
    if not corpora:
        raise ConfigError(
            f"no corpus is configured. Add one to {CORPORA_DIR}/<name>.json; "
            "see the README for the shape."
        )
    raise ConfigError(
        f"several corpora are configured ({', '.join(corpora)}) and no default is set. "
        "Pass --corpus, set PIPELINE_CORPUS, or add [corpus] default to pipeline.toml."
    )


def load_corpus(name: str | None = None) -> CorpusConfig:
    """Load a corpus config by name, or the default one.

    The default is resolved *before* the cache, deliberately. Caching on ``None`` would
    pin whichever corpus happened to be default at the first call for the life of the
    process -- so a second corpus, or a changed ``PIPELINE_CORPUS``, would be silently
    ignored. The bug that costs is the silent one.
    """
    return _load_corpus(name or default_corpus())


def _load_corpus(name: str) -> CorpusConfig:
    """Resolve ``name`` against the current search path, then load it.

    The search path is part of the cache key. Caching on the name alone would pin a
    corpus to whichever directory happened to hold it at the first call, so mounting or
    unmounting one mid-process would be ignored -- silently, which is the expensive kind.
    """
    path = corpus_path(name)
    if path is None:
        searched = ", ".join(str(d) for d in corpora_dirs())
        raise ConfigError(
            f"no corpus config for {name!r}. Searched: {searched}. "
            f"Available: {available_corpora()}. "
            f"To mount one from outside the repository, add its directory to "
            f"{ENV_CORPORA_PATH}."
        )
    return _load_corpus_from(path, name)


@cache
def _load_corpus_from(path: Path, name: str) -> CorpusConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    chapters = []
    for raw in data.get("divisions") or data["chapters"]:
        md = _resolve_source(path, raw["markdown"])
        if not md.exists():
            raise ConfigError(
                f"corpus {name!r} chapter {raw['number']!r} points at {raw['markdown']!r}, "
                f"which does not exist relative to {path.parent} or {REPO_ROOT}"
            )
        chapters.append(
            ChapterConfig(
                number=str(raw["number"]),
                title=raw["title"],
                markdown=md,
                pdf_page_start=raw.get("pdf_page_start"),
                pdf_page_end=raw.get("pdf_page_end"),
                printed_page_offset=raw.get("printed_page_offset"),
                type=str(raw.get("type", "chapter")),
            )
        )
    return CorpusConfig(
        corpus=data["corpus"],
        slug=data["slug"],
        title=data["title"],
        authors=tuple(data.get("authors", ())),
        chapters=tuple(chapters),
        path=path,
        source_type=str(data.get("source_type", "book")),
    )


def _resolve_source(config_path: Path, raw: str) -> Path:
    """Resolve a path written inside a corpus config.

    An absolute path is taken as given. A relative one is tried against the config's own
    directory first so that a mounted corpus is self-contained, then against the
    repository root, which is how the committed demo config is written.
    """
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return candidate
    local = config_path.parent / candidate
    return local if local.exists() else REPO_ROOT / candidate


def corpus_for_slug(slug: str) -> CorpusConfig | None:
    """Find the configured corpus whose artifact-store slug is ``slug``.

    A view holding a registry knows the slug it was opened with and nothing else, so
    resolving through :func:`default_corpus` would answer for the wrong book whenever
    more than one is configured -- silently, and only in the labels.
    """
    for name in available_corpora():
        try:
            config = load_corpus(name)
        except ConfigError:
            continue
        if config.slug == slug:
            return config
    return None


def available_corpora() -> list[str]:
    """Every configured corpus name, across the whole search path.

    A name found in more than one directory is reported once; the earliest directory
    wins, so a repository config is never silently shadowed by a mounted one.
    """
    seen: list[str] = []
    for directory in corpora_dirs():
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.json")):
            if path.stem not in seen:
                seen.append(path.stem)
    return sorted(seen)


def corpus_path(name: str) -> Path | None:
    """Where ``name``'s config lives, or ``None`` if no searched directory has it."""
    for directory in corpora_dirs():
        candidate = directory / f"{name}.json"
        if candidate.exists():
            return candidate
    return None
