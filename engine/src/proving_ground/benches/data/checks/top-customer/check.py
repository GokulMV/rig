import json
import sys

sys.path.insert(0, "/tests/checks/top-customer")
from expected import TOP  # noqa: E402

got = json.load(open("/app/out/top_customer.json"))
assert got == TOP, got
