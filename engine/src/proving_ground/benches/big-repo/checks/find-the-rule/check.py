import re
from pathlib import Path

f = Path("/app/out/answer.md")
assert f.is_file(), "no out/answer.md"
text = f.read_text()
mod = re.findall(r"^MODULE:\s*(\S+)\s*$", text, re.M)
val = re.findall(r"^VALUE:\s*([\d.]+)\s*%?\s*$", text, re.M)
assert mod and val, "missing the MODULE: / VALUE: lines"
# rule_08 is the deprecated 2024 fee (1.5): not the one in use.
assert mod[-1].removeprefix("./") == "ledger/rules/rule_23.py", mod[-1]
assert float(val[-1]) == 1.75, val[-1]
