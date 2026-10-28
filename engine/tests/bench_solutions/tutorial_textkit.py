"""A reference solution for the repo tutorial's textkit tasks (tutorial-tokens skill): one helper
per module, appended to that module, passes every task's check."""

SOLUTION = {
    "case": """

def snake(text):
    return "_".join(w.lower() for w in text.split())


def kebab(text):
    return "-".join(w.lower() for w in text.split())


def initials(name):
    return "".join(w[0].upper() for w in name.split())


def swap(text):
    return text.swapcase()
""",
    "clean": """

def squeeze(text):
    return " ".join(text.split())


def strip_digits(text):
    return "".join(c for c in text if not c.isdigit())


def only_ascii(text):
    return "".join(c for c in text if c.isascii())
""",
    "count": """

def char_count(text):
    return sum(not c.isspace() for c in text)


def line_count(text):
    return len(text.splitlines())


def vowel_count(text):
    return sum(c in "aeiouAEIOU" for c in text)
""",
}
