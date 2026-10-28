"""Rule checks for a PRD; the judge grades the rest."""

import re
import shutil
from pathlib import Path

SECTIONS = ["Problem", "Users", "Requirements", "Success metrics", "Out of scope", "Risks"]


def check(must_not_lead_with: str | None = None) -> str:
    doc = Path("/app/docs/PRD.md")
    assert doc.is_file(), "docs/PRD.md was not written"
    text = doc.read_text()
    heads = [h.strip().lower() for h in re.findall(r"^##\s+(.+)$", text, re.M)]
    for s in SECTIONS:
        assert any(h.startswith(s.lower()) for h in heads), f"missing section: {s}"
    req = re.split(r"^##\s+", text, flags=re.M)
    body = next(b for b in req if b.lower().startswith("requirements"))
    musts = [ln for ln in body.splitlines() if "MUST" in ln]
    assert len(musts) >= 3, f"only {len(musts)} MUST requirements"
    assert (
        sum(
            1
            for ln in musts + [ln for ln in body.splitlines() if "SHOULD" in ln]
            if re.search(r"\bI[1-5]\b", ln)
        )
        >= 3
    ), "requirements don't cite the interviews"
    metrics = next(b for b in req if b.lower().startswith("success metrics"))
    assert "47" in metrics, "the DSO baseline (47 days) isn't in the success metrics"
    assert re.search(r"\b\d+\s*(days|%)", metrics.replace("47", "")), (
        "no target number in the success metrics"
    )
    if must_not_lead_with:
        assert must_not_lead_with not in musts[0].lower(), (
            f"the first MUST requirement is the {must_not_lead_with}"
        )
        assert not any(must_not_lead_with in m.lower() for m in musts), (
            f"the {must_not_lead_with} is a MUST with no customer evidence"
        )
    Path("/logs/verifier").mkdir(parents=True, exist_ok=True)
    shutil.copy(doc, "/logs/verifier/artifact.md")
    return text
