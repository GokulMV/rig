"""Reference solutions for the finance bench's hard tier: POLICY.md plus POLICY-ADDENDUM.md,
implemented once from the data, so the checks' expected answers are derived, not copied."""

import csv
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

HARD = "data/hard"
SUFFIXES = {"ltd", "limited", "plc", "inc", "gmbh"}
CAP = Decimal("1.01")
TOL = Decimal("0.02")


def _rows(app: Path, rel: str) -> list[dict]:
    return list(csv.DictReader((app / rel).read_text().splitlines()))


def supplier_key(name: str) -> str:
    """Addendum: lower case, delete punctuation, collapse spaces, drop one legal suffix word."""
    s = re.sub(r"[^a-z0-9 ]", "", name.lower())
    words = s.split()
    if len(words) > 1 and words[-1] in SUFFIXES:
        words = words[:-1]
    return " ".join(words)


def _cents(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _usd_price(rates: list[dict], ccy: str, on: str, price: Decimal) -> Decimal:
    if ccy == "USD":
        return price
    rate = max(
        (r for r in rates if r["currency"] == ccy and r["date"] <= on), key=lambda r: r["date"]
    )
    return _cents(price * Decimal(rate["usd_per_1"]))


def _sig(r: dict) -> tuple:
    return (
        supplier_key(r["supplier"]),
        r["po"],
        r["line"],
        int(r["qty"]),
        Decimal(r["unit_price"]),
        r["currency"],
    )


def hard_batch(app: Path) -> None:
    pos = {(r["po"], r["line"]): r for r in _rows(app, f"{HARD}/pos.csv")}
    receipts = _rows(app, f"{HARD}/receipts.csv")
    rates = _rows(app, f"{HARD}/fx-rates.csv")
    paid = _rows(app, f"{HARD}/paid-history.csv")
    qty_billed: dict = {}
    value_billed: dict = {}
    for p in paid:
        key = (p["po"], p["line"])
        qty_billed[key] = qty_billed.get(key, 0) + int(p["qty"])
        value_billed[key] = value_billed.get(key, Decimal(0)) + Decimal(p["usd_value"])
    seen = {_sig(p) for p in paid}  # earlier invoices: paid history, then earlier invoices here
    invoices: dict[str, list[dict]] = {}
    for r in _rows(app, f"{HARD}/invoices.csv"):
        invoices.setdefault(r["invoice"], []).append(r)
    out = ["invoice,decision,route"]
    for inv, lines in invoices.items():
        route, take = None, []
        for r in lines:
            key = (r["po"], r["line"])
            qty = int(r["qty"])
            po = pos.get(key)
            if _sig(r) in seen:
                hit = "ap-lead"
            elif po is None or po["status"] == "closed":
                hit = "procurement"
            else:
                received = sum(
                    int(x["qty_received"])
                    for x in receipts
                    if (x["po"], x["line"]) == key and x["date"] <= r["date"]
                )
                po_price = Decimal(po["unit_price"])
                usd = _usd_price(rates, r["currency"], r["date"], Decimal(r["unit_price"]))
                value = usd * qty
                if qty + qty_billed.get(key, 0) > received:
                    hit = "receiving"
                elif abs(usd - po_price) > po_price * TOL:
                    hit = "buyer"
                elif value + value_billed.get(key, Decimal(0)) > (int(po["qty"]) * po_price * CAP):
                    hit = "buyer"
                else:
                    hit = None
                take.append((key, qty, value))
            route = route or hit
        seen |= {_sig(r) for r in lines}
        if route is None:
            for key, qty, value in take:
                qty_billed[key] = qty_billed.get(key, 0) + qty
                value_billed[key] = value_billed.get(key, Decimal(0)) + value
        out.append(f"{inv},{'hold' if route else 'approve'},{route or 'none'}")
    (app / "out" / "hard-decisions.csv").write_text("\n".join(out) + "\n")


def recon_result(app: Path) -> tuple[list[str], list[str], Decimal]:
    bank = _rows(app, f"{HARD}/bank.csv")
    ledger = _rows(app, f"{HARD}/ledger.csv")
    # Date order, ties in file order (sorted() is stable).
    led = sorted(ledger, key=lambda r: r["date"])
    used: set[str] = set()
    unmatched_bank = []
    for b in sorted(bank, key=lambda r: r["date"]):
        hit = next(
            (
                x
                for x in led
                if x["id"] not in used
                and Decimal(x["amount"]) == Decimal(b["amount"])
                and abs((date.fromisoformat(x["date"]) - date.fromisoformat(b["date"])).days) <= 3
            ),
            None,
        )
        if hit:
            used.add(hit["id"])
        else:
            unmatched_bank.append(b["id"])
    unmatched_ledger = [r["id"] for r in ledger if r["id"] not in used]
    diff = sum(Decimal(r["amount"]) for r in bank) - sum(Decimal(r["amount"]) for r in ledger)
    return sorted(unmatched_bank), sorted(unmatched_ledger), diff


def hard_recon(app: Path) -> None:
    ub, ul, diff = recon_result(app)
    (app / "out" / "hard-recon.md").write_text(
        "Bank lines in date order, each matched to the earliest unused ledger line with the same\n"
        "amount within 3 days.\n\n"
        f"UNMATCHED BANK: {', '.join(ub) or 'none'}\n"
        f"UNMATCHED LEDGER: {', '.join(ul) or 'none'}\n"
        f"DIFFERENCE: {diff:.2f}\n"
    )


SOLUTIONS = {
    ("finance", "hard-batch"): hard_batch,
    ("finance", "hard-recon"): hard_recon,
}
