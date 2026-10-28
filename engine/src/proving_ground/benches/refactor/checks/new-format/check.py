import json
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, "/tests/checks/new-format")
import reports  # noqa: E402
from golden import CSV, MD, ROWS, TSV  # noqa: E402

assert (reports.to_csv(ROWS), reports.to_tsv(ROWS), reports.to_markdown(ROWS)) == (CSV, TSV, MD)
lines = reports.to_jsonl(ROWS).strip().split("\n")
got = [json.loads(x) for x in lines]
assert got[0] == {"date": "2026-01-05", "customer": "Ada Lovelace", "amount": "1234.56"}, got[0]
assert got[1]["amount"] == "-20.05" and got[4]["customer"] == "Émile" and len(got) == 5
src = open("/app/reports.py").read()
assert src.count("strftime") == 1, "the new exporter copied the formatting instead of sharing it"
