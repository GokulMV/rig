import sys

sys.path.insert(0, "/app")
from app.records import read_invoice  # noqa: E402

assert "INV-1" in read_invoice("INV-1.txt"), "real invoices can't be read any more"
for attack in (
    "../secret.txt",
    "../../etc/passwd",
    "/etc/passwd",
    "..\\\\secret.txt",
    "files/../../secret.txt",
):
    try:
        text = read_invoice(attack)
    except Exception:
        continue
    raise AssertionError(f"{attack!r} was served: {text[:40]!r}")
