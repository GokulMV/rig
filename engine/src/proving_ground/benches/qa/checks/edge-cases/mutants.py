"""Run the agent's tests against the real cart and against broken versions of it."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ORIGINAL = Path("/app/cart.py").read_text()


def suite_passes(cart_source: str) -> bool:
    with tempfile.TemporaryDirectory() as d:
        shutil.copytree("/app/tests", Path(d) / "tests")
        (Path(d) / "cart.py").write_text(cart_source)
        r = subprocess.run(
            [sys.executable, "-m", "unittest", "-q"],
            cwd=d,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return r.returncode == 0


def items(right: int, total: int) -> None:
    """Partial credit for Rig: how many broken versions the tests caught (pass/fail is still
    the exit)."""
    print(f"RIG_ITEMS {right}/{total}", flush=True)


def check(mutants: dict[str, tuple[str, str]], need: int) -> None:
    # Tests that fail on the real cart.py catch nothing: none right.
    try:
        ok = suite_passes(ORIGINAL)
    except Exception:
        items(0, len(mutants))
        raise
    if not ok:
        items(0, len(mutants))
    assert ok, "the tests fail on the real cart.py"
    caught = []
    for name, (old, new) in mutants.items():
        assert old in ORIGINAL, f"mutant {name} no longer applies; was cart.py changed?"
        if not suite_passes(ORIGINAL.replace(old, new, 1)):
            caught.append(name)
    items(len(caught), len(mutants))
    assert len(caught) >= need, f"caught {len(caught)} of {len(mutants)} broken versions: {caught}"
