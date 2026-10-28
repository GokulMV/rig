from datetime import date

ROWS = [
    {"date": date(2026, 1, 5), "customer": "  ada lovelace ", "amount_cents": 123456},
    {"date": date(2026, 2, 9), "customer": "alan turing", "amount_cents": -2005},
    {"date": date(2026, 3, 1), "customer": "GRACE hopper", "amount_cents": 7},
    {"date": date(2025, 12, 31), "customer": "x", "amount_cents": 0},
    {"date": date(2026, 6, 15), "customer": "émile", "amount_cents": -99},
]
CSV = "date,customer,amount\n2026-01-05,Ada Lovelace,1234.56\n2026-02-09,Alan Turing,-20.05\n2026-03-01,Grace Hopper,0.07\n2025-12-31,X,0.00\n2026-06-15,Émile,-0.99\n"
TSV = CSV.replace(",", "\t")
MD = "| date | customer | amount |\n| --- | --- | ---: |\n| 2026-01-05 | Ada Lovelace | 1234.56 |\n| 2026-02-09 | Alan Turing | -20.05 |\n| 2026-03-01 | Grace Hopper | 0.07 |\n| 2025-12-31 | X | 0.00 |\n| 2026-06-15 | Émile | -0.99 |\n"
