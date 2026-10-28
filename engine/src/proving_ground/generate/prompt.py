"""Build the generator prompt from project sources. Source text is framed as data."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from proving_ground import skills
from proving_ground.models import ScenarioKind
from proving_ground.store import SourceRow

G = skills.load("generate-scenarios").values
MAX_SOURCE_CHARS = G["max_source_chars"]
MAX_TOTAL_CHARS = G["max_total_chars"]
MAX_IMAGES = G["max_images"]
MAX_IMAGE_BYTES = G["max_image_bytes"]
MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
SOURCE_ORDER = {"repo": 0, "graph": 1, "md": 2, "pdf": 3}

SYSTEM = skills.section("generate-scenarios", "System prompt")


@dataclass
class Prompt:
    system: str
    content: list[dict[str, Any]]
    included: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)

    @property
    def chars(self) -> int:
        return len(self.system) + sum(len(b.get("text", "")) for b in self.content)


def _escape(text: str) -> str:
    return text.replace("</source", "<\\/source").replace("</use_case", "<\\/use_case")


def _trim(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "\n[cut]"


def _image_block(row: SourceRow) -> dict[str, Any] | None:
    path = Path(row.meta.get("path", ""))
    media = MEDIA_TYPES.get(path.suffix.lower())
    if media is None or not path.is_file() or path.stat().st_size > MAX_IMAGE_BYTES:
        return None
    data = base64.standard_b64encode(path.read_bytes()).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}}


def build_prompt(
    sources: list[SourceRow],
    mix: dict[ScenarioKind, int],
    existing_ids: set[str],
    max_source_chars: int = MAX_SOURCE_CHARS,
    max_total_chars: int = MAX_TOTAL_CHARS,
) -> Prompt:
    prompt = Prompt(system=SYSTEM, content=[])
    use_cases = [s for s in sources if s.kind == "usecase"]
    images = [s for s in sources if s.kind == "image"]
    texts = sorted(
        (s for s in sources if s.kind not in {"usecase", "image"}),
        key=lambda s: (SOURCE_ORDER.get(s.kind, 9), s.id),
    )
    budget = max_total_chars
    parts: list[str] = []
    for s in texts:
        body = _escape(_trim(s.text, max_source_chars))
        if len(body) > budget:
            prompt.dropped.append(f"{s.kind}:{s.name}")
            continue
        budget -= len(body)
        parts.append(f'<source kind="{s.kind}" name="{_escape(s.name)}">\n{body}\n</source>')
        prompt.included.append(f"{s.kind}:{s.name}")
    for s in use_cases:
        parts.append(f"<use_case>\n{_escape(_trim(s.text, max_source_chars))}\n</use_case>")
        prompt.included.append(f"usecase:{s.name}")
    if parts:
        prompt.content.append({"type": "text", "text": "\n\n".join(parts)})
    for s in images:
        shown = sum(b["type"] == "image" for b in prompt.content)
        block = _image_block(s) if shown < MAX_IMAGES else None
        if block is None:
            prompt.dropped.append(f"image:{s.name}")
            continue
        prompt.content.append({"type": "text", "text": f"Image: {_escape(s.name)}"})
        prompt.content.append(block)
        prompt.included.append(f"image:{s.name}")
    wanted = ", ".join(f"{n} {k.value}" for k, n in mix.items())
    taken = ", ".join(sorted(existing_ids)) or "none"
    prompt.content.append(
        {
            "type": "text",
            "text": (
                f"Create scenarios for this project: {wanted}.\n"
                f"Existing scenario ids (do not reuse): {taken}.\n"
                "Return the result by calling the emit_plan tool once."
            ),
        }
    )
    return prompt
