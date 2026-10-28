import unittest

from invoice import build_invoice


class InvoiceTest(unittest.TestCase):
    def test_single_line(self):
        inv = build_invoice([("19.99", 3, "0")], "USD")
        self.assertEqual(inv, {"lines": [(5997, 0)], "net": 5997, "tax": 0, "total": 5997})

    def test_yen_has_no_decimals(self):
        inv = build_invoice([("1200", 2, "10")], "JPY")
        self.assertEqual(inv["lines"], [(2400, 240)])
        self.assertEqual(inv["total"], 2640)

    def test_dinar_has_three_decimals(self):
        inv = build_invoice([("1.250", 2, "0")], "KWD")
        self.assertEqual(inv["net"], 2500)

    def test_percent_off_is_shared_by_line_amount(self):
        inv = build_invoice([("10.00", 1, "20"), ("30.00", 1, "20")], "EUR", percent_off="50")
        self.assertEqual(inv["lines"], [(500, 100), (1500, 300)])
        self.assertEqual(inv["total"], 2400)

    def test_amount_off(self):
        inv = build_invoice([("25.00", 2, "0")], "GBP", amount_off="5.00")
        self.assertEqual(inv["net"], 4500)

    def test_line_nets_add_up_to_net(self):
        inv = build_invoice([("3.33", 1, "0"), ("3.33", 1, "0"), ("3.34", 1, "0")], "USD")
        self.assertEqual(sum(n for n, _ in inv["lines"]), inv["net"])
        self.assertEqual(inv["net"], 1000)


if __name__ == "__main__":
    unittest.main()
