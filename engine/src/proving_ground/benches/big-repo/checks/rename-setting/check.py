import subprocess
import sys
from pathlib import Path

app = Path("/app")
left = [
    str(p.relative_to(app))
    for p in app.rglob("*")
    if p.is_file()
    and p.suffix in (".py", ".md", ".toml", ".txt")
    and "retry_limit" in p.read_text(errors="replace")
]
assert not left, f"retry_limit is still used in: {left}"
sys.path.insert(0, "/app")
from ledger import settings  # noqa: E402

assert settings.get("max_retries") == 3
uses = [
    p
    for p in (app / "ledger" / "io").glob("*.py")
    if 'settings.get("max_retries")' in p.read_text()
]
assert len(uses) >= 13, f"only {len(uses)} I/O sources read max_retries"
assert "max_retries" in (app / "docs" / "configuration.md").read_text()
r = subprocess.run(
    [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
    cwd="/app",
    capture_output=True,
    text=True,
)
assert r.returncode == 0, r.stderr[-1500:]
