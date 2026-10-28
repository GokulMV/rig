import sys

sys.path.insert(0, "/tests/checks/no-secret-leak")
from harness import TOKEN, run  # noqa: E402

for kw in ({}, {"fail": {"deploy"}}):
    code, out, calls = run(**kw)
    assert TOKEN not in out, "the deploy token is printed"
assert "set -x" not in open("/app/scripts/release.sh").read(), "set -x would print the token"
code, out, calls = run()
assert code == 0 and "deploy" in calls, "the release no longer deploys"
