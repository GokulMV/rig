"""Instalment plans: a total split into n payments, plus a fee. The rules are in README.md."""

from money import minor_units, to_minor

MAX_INSTALMENTS = 24


def schedule(total: str, currency: str, n: int, fee: str = "0") -> list[int]:
    if not 1 <= n < MAX_INSTALMENTS:
        raise ValueError(f"instalments must be between 1 and {MAX_INSTALMENTS}, got {n}")
    amount = round(float(total) * 10 ** minor_units(currency))
    base = amount // n
    parts = [base] * n
    parts[-1] += amount - base * n
    parts[0] += to_minor(fee, currency)
    return parts
