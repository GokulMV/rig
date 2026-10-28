import importlib
import os
import sys

sys.path.insert(0, "/app")
src = open("/app/app/records.py").read()
assert "sk_live_9f2c1e7a" not in src, "the key is still in the source"
os.environ.pop("SIGNING_KEY", None)
import app.records as r  # noqa: E402

importlib.reload(r)
try:
    r.sign("x")
except RuntimeError:
    pass
else:
    raise AssertionError("it signs with no SIGNING_KEY set")
os.environ["SIGNING_KEY"] = "test-key"
importlib.reload(r)
s = r.sign("invoice-7")
assert r.verify("invoice-7", s) and not r.verify("invoice-8", s), "signing or verifying broke"
