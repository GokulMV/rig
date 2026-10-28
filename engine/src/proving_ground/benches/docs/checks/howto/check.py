"""Run every command in the how-to, in order, in a fresh copy; check every subcommand is shown."""

import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

doc = Path("/app/docs/HOWTO.md")
assert doc.is_file(), "docs/HOWTO.md was not written"
text = doc.read_text()
blocks = re.findall(r"```(?:bash|sh|shell)\n(.*?)```", text, re.S)
cmds = [
    ln.strip().removeprefix("$ ").strip()
    for b in blocks
    for ln in b.splitlines()
    if ln.strip() and not ln.strip().startswith("#")
]
cmds = [c for c in cmds if c.startswith("python3 invoice.py")]
assert cmds, "no runnable python3 invoice.py commands in ```bash blocks"
for sub in ("new", "add-line", "show", "mark-paid"):
    assert any(shlex.split(c)[2:3] == [sub] for c in cmds), f"no example of '{sub}'"
with tempfile.TemporaryDirectory() as d:
    shutil.copy("/app/invoice.py", d)
    for c in cmds:
        r = subprocess.run(shlex.split(c), cwd=d, capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, f"this example fails: {c}\n{r.stderr}"
Path("/logs/verifier").mkdir(parents=True, exist_ok=True)
shutil.copy(doc, "/logs/verifier/artifact.md")
