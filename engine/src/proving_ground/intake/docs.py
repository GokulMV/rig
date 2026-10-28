"""Read PDFs and text-like documents into plain text."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

TEXT_SUFFIXES = {
    ".md",
    ".markdown",
    ".txt",
    ".yaml",
    ".yml",
    ".json",
    ".mmd",
    ".mermaid",
    ".toml",
    ".csv",
    ".puml",
    ".dot",
    ".sql",
    ".tf",
    ".xml",
}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def read_pdf(path: Path, max_pages: int = 30, max_chars: int = 60_000) -> tuple[str, int]:
    reader = PdfReader(str(path))
    total = len(reader.pages)
    out: list[str] = []
    size = 0
    for page in reader.pages[:max_pages]:
        chunk = page.extract_text() or ""
        out.append(chunk)
        size += len(chunk)
        if size >= max_chars:
            break
    return "\n\n".join(out)[:max_chars], total


def read_text_file(path: Path, max_chars: int = 60_000) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    return text if len(text) <= max_chars else text[:max_chars] + "\n[cut]"
