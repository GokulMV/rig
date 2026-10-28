import sys
from pathlib import Path

sys.path.insert(0, "/tests/checks/missing-config")
from env import run, unchanged  # noqa: E402

out = run("scripts/smoke.sh")
assert "Report for main: 3 items to reorder: NUT-M6, WASHER-6, GASKET-2" in out, out[-500:]
settings = Path("/app/config/settings.toml").read_text()
assert "CHANGE_ME" not in settings, "settings.toml still has the placeholder"
assert Path("/app/config/settings.example.toml").read_text().count("CHANGE_ME") == 1, (
    "the example was edited"
)
unchanged()
