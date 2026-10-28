import subprocess
import sys
from decimal import Decimal

sys.path.insert(0, "/app")
from ledger.reports.invoice import invoice_total  # noqa: E402

# The fee is 2.5% rounded half up to the cent: 9.80 -> 0.245 -> 0.25.
assert invoice_total([("a", "9.80")], "EUR") == Decimal("10.05"), invoice_total(
    [("a", "9.80")], "EUR"
)
assert invoice_total([("a", "10.20")], "EUR") == Decimal("10.46")
assert invoice_total([("a", "10.005")], "USD") == Decimal("10.01")
r = subprocess.run(
    [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"],
    cwd="/app",
    capture_output=True,
    text=True,
)
assert r.returncode == 0, r.stderr[-1500:]
