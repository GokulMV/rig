import unittest

from pricetags.tags import price


class PriceTest(unittest.TestCase):
    def test_price(self):
        self.assertEqual(price(1999), "€19,99")
        self.assertEqual(price(5), "€0,05")
        self.assertEqual(price(123456), "€1.234,56")


if __name__ == "__main__":
    unittest.main()
