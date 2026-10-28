import unittest

from instalments import schedule


class InstalmentsTest(unittest.TestCase):
    def test_even_split(self):
        self.assertEqual(schedule("90.00", "USD", 3), [3000, 3000, 3000])

    def test_split_remainder(self):
        self.assertEqual(schedule("10.00", "USD", 3), [334, 333, 333])

    def test_fee_goes_on_the_first_instalment(self):
        self.assertEqual(schedule("100.00", "USD", 4, fee="2.50"), [2750, 2500, 2500, 2500])

    def test_yen(self):
        self.assertEqual(schedule("10000", "JPY", 2), [5000, 5000])

    def test_instalment_count_out_of_range(self):
        for n in (0, 25):
            with self.assertRaises(ValueError):
                schedule("10.00", "USD", n)


if __name__ == "__main__":
    unittest.main()
