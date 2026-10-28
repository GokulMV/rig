"""Counting things in text."""


def word_count(text: str) -> int:
    """How many words, split on whitespace: word_count("a b  c") == 3."""
    return len(text.split())
