"""Customer records: search, invoices, signed links."""

import hashlib
import hmac
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ROOT / "files"
SIGNING_KEY = "sk_live_9f2c1e7a"


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE customers (id INTEGER, name TEXT, email TEXT)")
    conn.executemany(
        "INSERT INTO customers VALUES (?, ?, ?)",
        [
            (1, "Ada Lovelace", "ada@example.com"),
            (2, "Alan Turing", "alan@example.com"),
            (3, "Grace Hopper", "grace@example.com"),
        ],
    )
    return conn


def find_customers(name: str) -> list[tuple]:
    conn = db()
    return conn.execute(
        f"SELECT id, name, email FROM customers WHERE name LIKE '%{name}%'"
    ).fetchall()


def read_invoice(filename: str) -> str:
    return (FILES / filename).read_text()


def sign(value: str) -> str:
    return hmac.new(SIGNING_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()


def verify(value: str, signature: str) -> bool:
    return hmac.compare_digest(sign(value), signature)
