"""A tiny invoice tool. Data lives in invoices.json next to this file."""

import argparse
import json
import sys
from pathlib import Path

DB = Path(__file__).with_name("invoices.json")


def load() -> dict:
    return json.loads(DB.read_text()) if DB.exists() else {}


def save(data: dict) -> None:
    DB.write_text(json.dumps(data, indent=2))


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="invoice.py")
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new", help="create an invoice")
    n.add_argument("number")
    n.add_argument("--client", required=True)
    a = sub.add_parser("add-line", help="add a line to an invoice")
    a.add_argument("number")
    a.add_argument("description")
    a.add_argument("amount", type=float)
    a.add_argument("--qty", type=int, default=1)
    s = sub.add_parser("show", help="print an invoice and its total")
    s.add_argument("number")
    m = sub.add_parser("mark-paid", help="mark an invoice paid")
    m.add_argument("number")
    args = p.parse_args(argv)
    data = load()
    if args.cmd == "new":
        if args.number in data:
            print(f"invoice {args.number} exists", file=sys.stderr)
            return 1
        data[args.number] = {"client": args.client, "lines": [], "paid": False}
    elif args.number not in data:
        print(f"no invoice {args.number}", file=sys.stderr)
        return 1
    elif args.cmd == "add-line":
        data[args.number]["lines"].append(
            {"description": args.description, "amount": args.amount, "qty": args.qty}
        )
    elif args.cmd == "show":
        inv = data[args.number]
        total = sum(x["amount"] * x["qty"] for x in inv["lines"])
        print(f"Invoice {args.number} for {inv['client']} ({'paid' if inv['paid'] else 'unpaid'})")
        for x in inv["lines"]:
            print(f"  {x['qty']} x {x['description']}: {x['amount']:.2f}")
        print(f"Total: {total:.2f}")
    elif args.cmd == "mark-paid":
        data[args.number]["paid"] = True
    save(data)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
