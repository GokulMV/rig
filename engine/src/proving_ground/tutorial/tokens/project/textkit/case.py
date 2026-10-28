"""Changing the case of words."""


def title(text: str) -> str:
    """Each word starts with a capital: title("hello world") == "Hello World"."""
    return " ".join(w[:1].upper() + w[1:].lower() for w in text.split())


def camel(text: str) -> str:
    """Words joined, each after the first capitalised: camel("hello big world") == "helloBigWorld"."""
    words = text.split()
    if not words:
        return ""
    return words[0].lower() + "".join(w[:1].upper() + w[1:].lower() for w in words[1:])
