import re
import shutil
from pathlib import Path

doc = Path("/app/brief.md")
assert doc.is_file(), "brief.md was not written"
text = doc.read_text()
for h in ("Answer", "Evidence", "Uncertainties"):
    assert re.search(rf"^##\s+{h}", text, re.M), f"missing section: {h}"
cited = set(re.findall(r"\[S(\d)\]", text))
assert cited, "no citations"
assert cited <= {"1", "2", "3", "4"}, (
    f"cites sources that don't exist: {cited - {'1', '2', '3', '4'}}"
)
evidence = re.split(r"^##\s+", text, flags=re.M)
ev = next(b for b in evidence if b.lower().startswith("evidence"))
paras = [p for p in ev.split("\n") if len(p.strip()) > 40]
assert paras and all(re.search(r"\[S\d\]", p) for p in paras), "an evidence line has no citation"
# The sources disagree on savings (410 vs 650): both figures must be reported.
assert "410" in text and "650" in text, "the conflicting savings figures aren't both reported"
# Numbers that must match the sources if used.
assert "1,400" in text or "1400" in text, (
    "installer capacity (1,400 a year) isn't considered against 2,000 households"
)
Path("/logs/verifier").mkdir(parents=True, exist_ok=True)
shutil.copy(doc, "/logs/verifier/artifact.md")
