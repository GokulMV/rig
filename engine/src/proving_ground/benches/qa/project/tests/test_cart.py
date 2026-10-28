import unittest

from cart import Cart


class CartTest(unittest.TestCase):
    def test_add(self):
        c = Cart()
        c.add("a", 100)
        self.assertEqual(c.subtotal(), 100)


if __name__ == "__main__":
    unittest.main()
