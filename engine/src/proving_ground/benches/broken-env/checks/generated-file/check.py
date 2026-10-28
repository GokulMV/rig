import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/tests/checks/generated-file")
from env import run, unchanged  # noqa: E402

out = run("scripts/version.sh")
assert out.strip().splitlines()[-1] == "2.4.1", out[-300:]
built = Path("/app/src/inventory/_build.py").read_text()
# Made by the generator, not written by hand: running it again changes nothing.
subprocess.run(["python3", "scripts/gen_build.py"], cwd="/app", check=True)
assert Path("/app/src/inventory/_build.py").read_text() == built, (
    "_build.py differs from what gen_build.py writes"
)
unchanged()
