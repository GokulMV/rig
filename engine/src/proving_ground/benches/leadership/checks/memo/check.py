import re
import shutil
from pathlib import Path

doc = Path("/app/memo.md")
assert doc.is_file(), "memo.md was not written"
text = doc.read_text()
words = len(re.findall(r"\b\w[\w'-]*\b", text))
assert words <= 600, f"{words} words; the limit is 600"
for h in ("Options", "Recommendation", "What would change my mind"):
    assert re.search(rf"^##\s+{h}", text, re.M), f"missing section: {h}"
opts = re.split(r"^##\s+", text, flags=re.M)
options = next(b for b in opts if b.startswith("Options"))
items = re.findall(r"^\s*(?:[-*]|\d+\.|###)\s+", options, re.M)
assert len(items) >= 3, "fewer than three options"
assert "180,000" in text or "180k" in text.lower(), "platform A's cost (180,000 a year) isn't used"
assert "240,000" in text or "240k" in text.lower(), "platform B's cost (240,000 a year) isn't used"
Path("/logs/verifier").mkdir(parents=True, exist_ok=True)
shutil.copy(doc, "/logs/verifier/artifact.md")
