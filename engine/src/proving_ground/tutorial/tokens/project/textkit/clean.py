"""Removing what you don't want from text."""

import string


def strip_punct(text: str) -> str:
    """Drop ASCII punctuation: strip_punct("Hi, there!") == "Hi there"."""
    return "".join(c for c in text if c not in string.punctuation)
