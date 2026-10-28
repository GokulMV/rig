import shutil
import subprocess
from pathlib import Path

APP = Path("/app")


def run_tests(hidden: Path) -> None:
    """The repo's own tests and this check's hidden ones, on Node's built-in runner."""
    dest = APP / ".pg-hidden"
    dest.mkdir(exist_ok=True)
    shutil.copy(hidden, dest / hidden.name)
    files = sorted(str(p) for p in (APP / "tests").glob("*.test.ts")) + [str(dest / hidden.name)]
    r = subprocess.run(
        ["node", "--test", *files], cwd=APP, capture_output=True, text=True, timeout=120
    )
    assert r.returncode == 0, f"tests fail:\n{r.stdout[-2500:]}\n{r.stderr[-800:]}"
