"""Generate the big-repo bench project: a ledger package of ~120 modules with three needles.

Deterministic (seeded); run once, output committed. Usage: gen_bigrepo.py <project dir>
"""

import random
import sys
from pathlib import Path

rng = random.Random(4127)
root = Path(sys.argv[1])
pkg = root / "ledger"

CURRENCIES = [
    "EUR",
    "USD",
    "GBP",
    "JPY",
    "CHF",
    "SEK",
    "NOK",
    "DKK",
    "PLN",
    "CZK",
    "HUF",
    "AUD",
    "NZD",
    "CAD",
    "SGD",
    "HKD",
    "INR",
    "BRL",
    "MXN",
    "ZAR",
    "TRY",
    "KRW",
    "CNY",
    "THB",
    "IDR",
    "MYR",
    "PHP",
    "ILS",
    "AED",
    "SAR",
]
REGIONS = ["EMEA", "NA", "LATAM", "APAC", "ANZ"]
DECIMALS = {"JPY": 0, "KRW": 0, "IDR": 0}


def w(rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.lstrip("\n"))


w(
    "README.md",
    """
# ledger

Invoicing and month-end reports for a multi-currency business: currencies, rules (fees,
discounts, taxes), reports and I/O. About 120 modules.

- Run the tests: `python3 -m unittest discover -s tests -q`
- Settings: `ledger/settings.py` (the client's retry settings are read from there too).
""",
)

w("ledger/__init__.py", '"""Multi-currency ledger."""\n')
w("ledger/util/__init__.py", "")
w(
    "ledger/util/rounding.py",
    '''
"""Rounding to a currency's minor unit."""

from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

from ledger.currencies.registry import decimals


def to_minor(amount: Decimal, currency: str) -> Decimal:
    """Round half up to the currency's minor unit (cents, or whole yen)."""
    q = Decimal(1).scaleb(-decimals(currency))
    return amount.quantize(q, rounding=ROUND_HALF_UP)


def bankers(amount: Decimal, currency: str) -> Decimal:
    """Round half to even. Only for statistical reports, never for invoices."""
    q = Decimal(1).scaleb(-decimals(currency))
    return amount.quantize(q, rounding=ROUND_HALF_EVEN)
''',
)
for i in range(2, 11):
    w(
        f"ledger/util/helper_{i:02d}.py",
        f'''
"""Small helpers ({i})."""


def clamp_{i}(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def chunks_{i}(items: list, n: int) -> list[list]:
    return [items[k : k + n] for k in range(0, len(items), n)]
''',
    )

# Currencies: one module each, plus a registry.
w("ledger/currencies/__init__.py", "")
reg = [
    '"""Every currency the ledger knows."""',
    "",
    "from importlib import import_module",
    "",
    f"CODES = {CURRENCIES!r}",
    "",
    "",
    "def info(code: str):",
    '    return import_module(f"ledger.currencies.{code.lower()}")',
    "",
    "",
    "def decimals(code: str) -> int:",
    "    return info(code).DECIMALS",
    "",
]
w("ledger/currencies/registry.py", "\n".join(reg))
for c in CURRENCIES:
    d = DECIMALS.get(c, 2)
    w(
        f"ledger/currencies/{c.lower()}.py",
        f'''
"""{c}."""

CODE = "{c}"
DECIMALS = {d}
SYMBOL = "{c[:2]}"
''',
    )

# Settings, with the retry setting the rename needle is about.
w(
    "ledger/settings.py",
    '''
"""Ledger settings."""

SETTINGS = {
    "retry_limit": 3,
    "timeout_s": 20,
    "default_currency": "EUR",
}


def get(key: str):
    return SETTINGS[key]
''',
)

# I/O modules: many read the retry setting.
w("ledger/io/__init__.py", "")
io_names = [f"source_{i:02d}" for i in range(1, 21)]
for i, n in enumerate(io_names, 1):
    uses = i % 3 != 0
    body = f'''
"""Reads invoices from source {i}."""

from ledger import settings


def fetch_{i}(client, ref: str):
'''
    if uses:
        body += """    tries = settings.get("retry_limit")
    for attempt in range(tries):
        try:
            return client.get(ref)
        except TimeoutError:
            if attempt == tries - 1:
                raise
"""
    else:
        body += "    return client.get(ref)\n"
    w(f"ledger/io/{n}.py", body)

# Rules: fees per region, discounts, taxes. Needles live here.
w("ledger/rules/__init__.py", "")
rule_lines = [
    '"""Which rule applies to what."""',
    "",
    "from importlib import import_module",
    "",
    "RULES = [",
]
for i in range(1, 31):
    rule_lines.append(f'    "rule_{i:02d}",')
rule_lines += [
    "]",
    "",
    "",
    "def load(name: str):",
    '    return import_module(f"ledger.rules.{name}")',
    "",
]
w("ledger/rules/registry.py", "\n".join(rule_lines))
late_fee_region = {}
for i in range(1, 31):
    kind = ["late_fee", "discount", "tax"][i % 3]
    region = REGIONS[i % len(REGIONS)]
    if i == 23:
        # The real APAC late fee.
        w(
            f"ledger/rules/rule_{i:02d}.py",
            '''
"""Late fee for APAC accounts (from the 2026 price list)."""

from decimal import Decimal

KIND = "late_fee"
REGION = "APAC"
PERCENT = Decimal("1.75")


def apply(amount: Decimal) -> Decimal:
    return amount * PERCENT / 100
''',
        )
        late_fee_region[i] = "APAC"
        continue
    if i == 8:
        # A decoy: the old APAC fee, deprecated and not in use.
        w(
            f"ledger/rules/rule_{i:02d}.py",
            '''
"""DEPRECATED: the 2024 APAC late fee. Replaced by rule_23; kept for old reports only.
Not loaded by invoices (see ledger/reports/invoice.py)."""

from decimal import Decimal

KIND = "late_fee_2024"
REGION = "APAC"
PERCENT = Decimal("1.5")


def apply(amount: Decimal) -> Decimal:
    return amount * PERCENT / 100
''',
        )
        continue
    if i == 17:
        # The drift needle: an EUR fee rounded with banker's rounding.
        w(
            f"ledger/rules/rule_{i:02d}.py",
            '''
"""Processing fee for EUR invoices."""

from decimal import Decimal

from ledger.util.rounding import bankers

KIND = "fee"
REGION = "EMEA"
CURRENCY = "EUR"
PERCENT = Decimal("2.5")


def apply(amount: Decimal) -> Decimal:
    return bankers(amount * PERCENT / 100, CURRENCY)
''',
        )
        continue

    pct = f"{rng.choice([0.5, 1, 1.25, 2, 3, 4.5])}"
    w(
        f"ledger/rules/rule_{i:02d}.py",
        f'''
"""{kind.replace("_", " ").title()} for {region} accounts."""

from decimal import Decimal

from ledger.util.rounding import to_minor

KIND = "{kind}"
REGION = "{region}"
PERCENT = Decimal("{pct}")


def apply(amount: Decimal, currency: str = "EUR") -> Decimal:
    return to_minor(amount * PERCENT / 100, currency)
''',
    )

# Reports.
w("ledger/reports/__init__.py", "")
w(
    "ledger/reports/invoice.py",
    '''
"""Invoice totals: lines, then the EUR processing fee (rule_17), rounded to the minor unit."""

from decimal import Decimal

from ledger.rules.registry import load
from ledger.util.rounding import to_minor


def invoice_total(lines: list[tuple[str, str]], currency: str) -> Decimal:
    """lines: (description, amount as text). Returns the total in `currency`."""
    subtotal = sum((Decimal(a) for _, a in lines), Decimal(0))
    total = to_minor(subtotal, currency)
    if currency == "EUR":
        total += load("rule_17").apply(subtotal)
    return total
''',
)
for i in range(1, 29):
    w(
        f"ledger/reports/report_{i:02d}.py",
        f'''
"""Report {i}: totals by {rng.choice(["customer", "region", "month", "product", "channel"])}."""

from collections import defaultdict
from decimal import Decimal


def build_{i}(rows: list[dict]) -> dict[str, Decimal]:
    out: dict[str, Decimal] = defaultdict(Decimal)
    for r in rows:
        out[r["key"]] += Decimal(r["amount"])
    return dict(out)
''',
    )

# Docs that mention the retry setting.
w(
    "docs/configuration.md",
    """
# Configuration

`retry_limit` (default 3): how many times an I/O source retries a timed-out fetch.
`timeout_s` (default 20): seconds before a fetch times out.
`default_currency`: the ledger's home currency.
""",
)
w(
    "docs/operations.md",
    """
# Operations

If a source keeps timing out, raise `retry_limit` in ledger/settings.py before raising
`timeout_s`.
""",
)

# Tests that pass on the untouched repo.
w("tests/__init__.py", "")
w(
    "tests/test_rules.py",
    """
import unittest
from decimal import Decimal

from ledger.reports.invoice import invoice_total
from ledger.rules.registry import RULES, load


class Rules(unittest.TestCase):
    def test_every_rule_loads(self):
        for name in RULES:
            self.assertTrue(hasattr(load(name), "apply"))

    def test_usd_invoice(self):
        self.assertEqual(invoice_total([("a", "10.005")], "USD"), Decimal("10.01"))

    def test_yen_has_no_minor_unit(self):
        self.assertEqual(invoice_total([("a", "100.5")], "JPY"), Decimal("101"))


if __name__ == "__main__":
    unittest.main()
""",
)
w(
    "tests/test_io.py",
    """
import unittest

from ledger.io import source_01


class Flaky:
    def __init__(self, fails):
        self.fails = fails

    def get(self, ref):
        if self.fails:
            self.fails -= 1
            raise TimeoutError
        return ref


class IO(unittest.TestCase):
    def test_retries_then_succeeds(self):
        self.assertEqual(source_01.fetch_1(Flaky(2), "x"), "x")

    def test_gives_up(self):
        with self.assertRaises(TimeoutError):
            source_01.fetch_1(Flaky(5), "x")


if __name__ == "__main__":
    unittest.main()
""",
)
print(sum(1 for _ in root.rglob("*.py")), "py files")
