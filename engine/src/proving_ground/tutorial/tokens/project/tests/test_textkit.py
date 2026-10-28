import unittest

from textkit.case import camel, title
from textkit.clean import strip_punct
from textkit.count import word_count


class TestTextkit(unittest.TestCase):
    def test_title(self):
        self.assertEqual(title("hello WORLD"), "Hello World")

    def test_camel(self):
        self.assertEqual(camel("hello big world"), "helloBigWorld")
        self.assertEqual(camel(""), "")

    def test_strip_punct(self):
        self.assertEqual(strip_punct("Hi, there!"), "Hi there")

    def test_word_count(self):
        self.assertEqual(word_count("a b  c"), 3)


if __name__ == "__main__":
    unittest.main()
