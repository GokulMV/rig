import re
import shutil
from pathlib import Path

doc = Path("/app/post.md")
assert doc.is_file(), "post.md was not written"
text = doc.read_text()
words = len(re.findall(r"\b\w[\w'-]*\b", text))
assert 150 <= words <= 300, f"{words} words; the brief says 150-300"
low = text.lower()
for banned in ("free forever", "#1", "best in class", "guaranteed", "100%"):
    assert banned not in low, f"banned claim: {banned}"
assert "$29" in text, "the price ($29 per practitioner per month) isn't stated"
assert "50" in text and "beta" in low, "the beta limit (50 clinics) isn't stated"
for n in re.findall(r"(\d+)%", text):
    assert n in ("18", "11"), f"a percentage that isn't in the facts: {n}%"
Path("/logs/verifier").mkdir(parents=True, exist_ok=True)
shutil.copy(doc, "/logs/verifier/artifact.md")
