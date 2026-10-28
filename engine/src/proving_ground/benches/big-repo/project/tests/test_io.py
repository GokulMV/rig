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
