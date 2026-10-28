"""A reference solution for the tutorial's price-tags tasks: every label in the house style
(the price-tags-style skill). Appended to pricetags/tags.py, it passes every task's check."""

SOLUTION = '''

def _half_up(num, den):
    return (2 * num + den) // (2 * den)


def unit_price(cents, unit):
    return f"{price(cents)} / {unit}"


def refund(cents):
    return f"-{price(cents)}"


def discount(percent):
    return f"-{percent}%"


def price_range(low, high):
    return f"{price(low)} to {price(high)}"


def sale(was, now):
    return f"{price(now)} (was {price(was)})"


def total(prices):
    return price(sum(prices))


def tag(cents):
    return "free" if cents == 0 else price(cents)


def per_100g(cents_per_kg):
    return f"{price(_half_up(cents_per_kg, 10))} / 100 g"


def parse_price(text):
    return int(text.lstrip("€").replace(".", "").replace(",", ""))


def with_tax(net_cents, rate):
    return price(_half_up(net_cents * (100 + rate), 100))
'''

# A plausible guess without the house rules: right where the code shows the way (a total, reading
# a label back), wrong where only the skill says how.
GUESS = '''

def unit_price(cents, unit):
    return f"{price(cents)}/{unit}"


def refund(cents):
    return f"Refund: {price(cents)}"


def discount(percent):
    return f"{percent}% off"


def price_range(low, high):
    return f"{price(low)} - {price(high)}"


def sale(was, now):
    return f"Was {price(was)}, now {price(now)}"


def total(prices):
    return price(sum(prices))


def tag(cents):
    return "Free" if cents == 0 else price(cents)


def per_100g(cents_per_kg):
    return f"{price(round(cents_per_kg / 10))} per 100g"


def parse_price(text):
    return int(text.lstrip("€").replace(".", "").replace(",", ""))


def with_tax(net_cents, rate):
    return price(round(net_cents * (1 + rate / 100)))
'''
