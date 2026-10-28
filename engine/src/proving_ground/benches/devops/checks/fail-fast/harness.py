"""Run release.sh in a copy, with fake bin/ tools that record calls and can fail on demand."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

TOKEN = "tok-SECRET-1234"


def run(fail: set[str] = frozenset(), healthy_after: int | None = 1) -> tuple[int, str, list[str]]:
    d = Path(tempfile.mkdtemp())
    shutil.copytree("/app/scripts", d / "scripts")
    b = d / "bin"
    b.mkdir()
    log = d / "calls.log"
    for tool in ("test", "build", "deploy", "rollback"):
        code = 1 if tool in fail else 0
        (b / tool).write_text(
            f"#!/usr/bin/env bash\necho {tool} >> {log}\necho '{tool} output'\nexit {code}\n"
        )
    count = d / "health.count"
    ok = "true" if healthy_after is not None else "false"
    (b / "health").write_text(
        "#!/usr/bin/env bash\n"
        f"echo health >> {log}\nn=$(( $(cat {count} 2>/dev/null || echo 0) + 1 )); echo $n > {count}\n"
        f"if {ok} && [ $n -ge {healthy_after or 1} ]; then echo ok; else echo down; exit 1; fi\n"
    )
    for f in b.iterdir():
        f.chmod(0o755)
    env = dict(os.environ, DEPLOY_TOKEN=TOKEN, PATH=f"{b}:{os.environ['PATH']}")
    r = subprocess.run(
        ["bash", "scripts/release.sh"], cwd=d, env=env, capture_output=True, text=True, timeout=60
    )
    calls = log.read_text().split() if log.exists() else []
    return r.returncode, r.stdout + r.stderr, calls
