import hashlib
import subprocess
from pathlib import Path

APP = Path("/app")
CODE = "d57fdbc04c28b987d5b9893ac91844f6781379af6832c670b662e8ff9f7e0a15"


def unchanged() -> None:
    """The fix is in the environment: src/ and tests/ stay as they were."""
    paths = [
        p.relative_to(APP)
        for top in ("src", "tests")
        for p in (APP / top).rglob("*.py")
        if p.name != "_build.py"
    ]
    m = hashlib.sha256()
    for p in sorted(paths):
        m.update(p.as_posix().encode())
        m.update((APP / p).read_bytes())
    assert m.hexdigest() == CODE, "src/ or tests/ were changed: fix the environment, not the code"


def run(script: str) -> str:
    r = subprocess.run(["bash", script], cwd=APP, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"{script} still fails:\n{r.stdout[-800:]}\n{r.stderr[-800:]}"
    return r.stdout + r.stderr
