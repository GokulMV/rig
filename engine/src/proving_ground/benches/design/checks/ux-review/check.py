"""The five planted problems must each be found; the judge grades ranking and fixes."""

import re
import shutil
from pathlib import Path

doc = Path("/app/review.md")
assert doc.is_file(), "review.md was not written"
text = doc.read_text().lower()
heads = re.findall(r"^###\s+", doc.read_text(), re.M)
assert len(heads) >= 4, "fewer than four problems"
assert re.search(r"severity", text), "no severities"
found = {
    "image without alt text": ["alt"],
    "input without a label": ["label"],
    "low-contrast hint text": ["contrast"],
    "pay button is a div (no keyboard, no role)": ["keyboard", "<button", "button element", "role"],
    "error shown only in red, with no detail": [
        "colour",
        "color",
        "only red",
        "red only",
        "vague",
        "aria-live",
        "describ",
    ],
}
missing = [p for p, words in found.items() if not any(w in text for w in words)]
assert not missing, f"not found: {missing}"
Path("/logs/verifier").mkdir(parents=True, exist_ok=True)
shutil.copy(doc, "/logs/verifier/artifact.md")
