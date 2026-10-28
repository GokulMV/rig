import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/tests/checks/dedupe")
import reports  # noqa: E402
from golden import CSV, MD, ROWS, TSV  # noqa: E402

assert (reports.to_csv(ROWS), reports.to_tsv(ROWS), reports.to_markdown(ROWS)) == (CSV, TSV, MD)
src = open("/app/reports.py").read()
assert src.count("strftime") == 1, f"date formatting appears {src.count('strftime')} times"
assert src.count("% 100") <= 2, "money formatting is still copied"
assert src.count(".title()") == 1, "name formatting is still copied"
