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
