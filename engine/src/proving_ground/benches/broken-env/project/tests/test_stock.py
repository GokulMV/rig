import unittest

from inventory.stock import below, needs_reorder


class Stock(unittest.TestCase):
    def test_at_threshold_reorders(self):
        self.assertTrue(needs_reorder(5, 5))

    def test_above_threshold_doesnt(self):
        self.assertFalse(needs_reorder(6, 5))

    def test_below_lists_skus(self):
        rows = [
            {"sku": "A", "qty": "1", "threshold": "3"},
            {"sku": "B", "qty": "9", "threshold": "3"},
        ]
        self.assertEqual(below(rows), ["A"])


if __name__ == "__main__":
    unittest.main()
