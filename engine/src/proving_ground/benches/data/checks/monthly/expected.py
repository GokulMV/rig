CLEAN = [
    ("1001", "2026-01-05", "Ada Lovelace", 1250),
    ("1002", "2026-01-05", "Alan Turing", 4000),
    ("1003", "2026-01-07", "Grace Hopper", 725),
    ("1004", "2026-01-20", "Ada Lovelace", -300),
    ("1006", "2026-02-03", "Grace Hopper", 10000),
    ("1008", "2026-02-28", "Alan Turing", 999),
    ("1009", "2026-03-01", "Margaret Hamilton", 125000),
    ("1010", "2026-03-03", "Ada Lovelace", 2000),
    ("1011", "2026-03-15", "Margaret Hamilton", -25000),
]
# Orders in data/orders.csv the rules drop (no customer; no amount).
DROPPED = ["1005", "1007"]
MONTHLY = {"2026-01": 5675, "2026-02": 10999, "2026-03": 102000}
TOP = {"customer": "Margaret Hamilton", "cents": 100000}
