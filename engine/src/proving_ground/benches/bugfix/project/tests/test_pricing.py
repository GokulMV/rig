import unittest

from shop.pricing import cart_total, line_total


class PricingTest(unittest.TestCase):
    def test_line_total(self):
        self.assertEqual(line_total(2.5, 2), 5.0)

    def test_coupon(self):
        self.assertEqual(cart_total([(10.0, 1)], "SAVE10"), 9.0)

    def test_bulk_discount(self):
        self.assertEqual(line_total(1.0, 10), 9.5)


if __name__ == "__main__":
    unittest.main()
