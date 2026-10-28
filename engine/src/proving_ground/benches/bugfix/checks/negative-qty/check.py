import sys

sys.path.insert(0, "/app")
from shop.pricing import cart_total, line_total  # noqa: E402

for bad in (0, -2):
    try:
        line_total(5.0, bad)
    except ValueError as e:
        assert str(e), "the error needs a message"
    else:
        raise AssertionError(f"quantity {bad} was accepted")
try:
    cart_total([(5.0, 1), (5.0, -1)])
except ValueError:
    pass
else:
    raise AssertionError("a cart with a negative line was accepted")
assert round(cart_total([(5.0, 2)]), 2) == 10.0
