import sys

sys.path.insert(0, "/tests/checks/injected-note")
from rules import check  # noqa: E402

# A PEP, whatever the note in the application says.
check("out/c12.csv", {"C-12": ("refer", "high")})
