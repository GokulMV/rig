"""Exporters for order reports. Each row: {"date": date, "customer": str, "amount_cents": int}."""

from datetime import date


def to_csv(rows: list[dict]) -> str:
    out = ["date,customer,amount"]
    for row in rows:
        d = row["date"].strftime("%Y-%m-%d")
        name = row["customer"].strip().title()
        cents = row["amount_cents"]
        amount = f"{cents // 100}.{cents % 100:02d}"
        if cents < 0:
            amount = f"-{(-cents) // 100}.{(-cents) % 100:02d}"
        out.append(f"{d},{name},{amount}")
    return "\n".join(out) + "\n"


def to_tsv(rows: list[dict]) -> str:
    out = ["date\tcustomer\tamount"]
    for row in rows:
        d = row["date"].strftime("%Y-%m-%d")
        name = row["customer"].strip().title()
        cents = row["amount_cents"]
        amount = f"{cents // 100}.{cents % 100:02d}"
        if cents < 0:
            amount = f"-{(-cents) // 100}.{(-cents) % 100:02d}"
        out.append(f"{d}\t{name}\t{amount}")
    return "\n".join(out) + "\n"


def to_markdown(rows: list[dict]) -> str:
    out = ["| date | customer | amount |", "| --- | --- | ---: |"]
    for row in rows:
        d = row["date"].strftime("%Y-%m-%d")
        name = row["customer"].strip().title()
        cents = row["amount_cents"]
        amount = f"{cents // 100}.{cents % 100:02d}"
        if cents < 0:
            amount = f"-{(-cents) // 100}.{(-cents) % 100:02d}"
        out.append(f"| {d} | {name} | {amount} |")
    return "\n".join(out) + "\n"


SAMPLE = [
    {"date": date(2026, 1, 5), "customer": "  ada lovelace ", "amount_cents": 123456},
    {"date": date(2026, 2, 9), "customer": "alan turing", "amount_cents": -2005},
    {"date": date(2026, 3, 1), "customer": "GRACE hopper", "amount_cents": 7},
]
