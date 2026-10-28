import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/tests/checks/behaviour")
import reports  # noqa: E402
from golden import CSV, MD, ROWS, TSV  # noqa: E402

assert reports.to_csv(ROWS) == CSV, reports.to_csv(ROWS)
assert reports.to_tsv(ROWS) == TSV, reports.to_tsv(ROWS)
assert reports.to_markdown(ROWS) == MD, reports.to_markdown(ROWS)
src = open("/app/reports.py").read()
# The task is a refactor: three copies of the loop must not survive.
assert src.count("for row in rows") <= 1, "the row loop is still copied into each exporter"
