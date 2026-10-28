"""Runs the hidden cases against the agent's code in a child process (check.py's), so a crash
or a hang in that code costs items, never the RIG_ITEMS line. One line per case to argv[1]."""

import copy
import signal
import sys

sys.path.insert(0, "/tests/checks/hard-stale-test")
from cases import CASES, FUNC, MODULE  # noqa: E402

out = open(sys.argv[1], "w", buffering=1)


def timeout(*_):
    raise TimeoutError("took more than 5 seconds")


def normalise(got):
    if isinstance(got, dict):  # an invoice: compare its four amounts, lines as tuples
        return {
            "lines": [tuple(line) for line in got["lines"]],
            "net": got["net"],
            "tax": got["tax"],
            "total": got["total"],
        }
    return list(got)


signal.signal(signal.SIGALRM, timeout)
sys.path.insert(0, "/app/invoicing")
try:
    signal.alarm(10)
    func = getattr(__import__(MODULE), FUNC)
    signal.alarm(0)
except BaseException as e:  # noqa: BLE001 - any failure to import costs every case
    print(f"cannot import {FUNC} from invoicing/{MODULE}.py: {e!r}", file=sys.stderr)
    sys.exit(0)

for i, (args, kwargs, expected) in enumerate(CASES):
    call = f"{FUNC}{tuple(args)!r} {kwargs!r}"
    try:
        signal.alarm(5)
        try:
            got = normalise(func(*copy.deepcopy(args), **copy.deepcopy(kwargs)))
        except ValueError as e:
            got = "ValueError" if expected == "ValueError" else f"ValueError({e})"
        finally:
            signal.alarm(0)
    except BaseException as e:  # noqa: BLE001 - one bad case must not stop the rest
        got = f"raised {e!r}"
    if got == expected:
        out.write(f"ok {i}\n")
    else:
        out.write(f"fail {i} {call}: expected {expected!r}, got {got!r}\n")
