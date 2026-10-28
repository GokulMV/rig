"""Reference solutions for the compliance bench's hard tier: POLICY.md plus POLICY-ADDENDUM.md,
implemented once from the data (names, lists, rates, dates), never from the expected answers."""

import csv
import json
import re
import unicodedata
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

H = "data/hard"
REVIEW = date(2026, 10, 20)
MONTHS = {
    m: i
    for i, m in enumerate(
        "january february march april may june july august september october november december".split(),
        1,
    )
}


def _strip(s: str) -> str:
    n = unicodedata.normalize("NFKD", s)
    n = "".join(c for c in n if not unicodedata.combining(c)).lower()
    for ch in "-.,":
        n = n.replace(ch, " ")
    return n


def _equivalents(app: Path) -> dict[str, str]:
    eq: dict[str, str] = {}
    for r in csv.DictReader((app / H / "name-equivalents.csv").read_text().splitlines()):
        canon = _strip(r["canonical"]).strip()
        for s in [r["canonical"], *r["variants"].split(";")]:
            eq[_strip(s).strip()] = canon
    return eq


def _tokens(name: str, eq: dict[str, str]) -> tuple[str, ...]:
    return tuple(sorted(eq.get(t, t) for t in _strip(name).split()))


def _same_dob(listed: str, dob: str) -> bool:
    listed = listed.strip()
    return dob[:4] == listed if len(listed) == 4 else dob == listed


def _sanctions(rows: list[dict], name: tuple, dob: str, eq) -> str | None:
    hits = [r for r in rows if _tokens(r["name"], eq) == name]
    if any(_same_dob(r["dob"], dob) for r in hits):
        return "same"
    return "name" if hits else None


def _year_back(d: date) -> date:
    return d.replace(year=d.year - 1)


def _is_pep(app: Path, name: tuple, dob: str, ref: date, eq) -> bool:
    rows = list(csv.DictReader((app / H / "peps.csv").read_text().splitlines()))
    by_name = {r["name"]: r for r in rows}

    def holder_current(r: dict) -> bool:
        left = r["left_office"].strip()
        return not left or date.fromisoformat(left) >= _year_back(ref)

    def current(r: dict) -> bool:
        rel = r["related_to"].strip()
        return holder_current(by_name[rel]) if rel else holder_current(r)

    return any(
        _tokens(r["name"], eq) == name and _same_dob(r["dob"], dob) and current(r) for r in rows
    )


def _risky(app: Path) -> set[str]:
    return {
        ln.strip().lower()
        for ln in (app / "data/high-risk-countries.txt").read_text().splitlines()
        if ln.strip() and not ln.startswith("#")
    }


def _country_risk(c: dict, risky: set[str]) -> bool:
    return any(x.strip().lower() in risky for x in [c["country"], *c["nationality"]])


def _onboarding(app: Path) -> None:
    eq = _equivalents(app)
    sanc = list(csv.DictReader((app / H / "sanctions.csv").read_text().splitlines()))
    risky = _risky(app)
    rates = {
        r["currency"].strip(): Decimal(r["eur_per_unit"].strip())
        for r in csv.DictReader((app / H / "fx-rates.csv").read_text().splitlines())
    }
    out = ["customer,decision,risk"]
    for c in json.loads((app / H / "applications.json").read_text()):
        name = _tokens(c["name"], eq)
        eur = sum(
            (
                (Decimal(str(line["amount"])) * rates[line["currency"]]).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                for line in c["monthly_volume"]
            ),
            Decimal(0),
        )
        big = eur > Decimal("50000.00")
        docs = {d.strip().lower() for d in c["documents"]}
        hit = _sanctions(sanc, name, c["dob"], eq)
        if not c["id_verified"] or not {"passport", "proof of address"} <= docs:
            d = ("refer", "medium")
        elif hit == "same":
            d = ("decline", "high")
        elif hit == "name":
            d = ("refer", "high")
        elif _is_pep(app, name, c["dob"], date.fromisoformat(c["applied"]), eq):
            d = ("refer", "high")
        elif _country_risk(c, risky):
            d = ("refer", "high")
        elif big and not c["source_of_funds"].strip():
            d = ("refer", "medium")
        else:
            d = ("approve", "medium" if big else "low")
        out.append(f"{c['id']},{d[0]},{d[1]}")
    (app / "out").mkdir(exist_ok=True)
    (app / "out/hard-decisions.csv").write_text("\n".join(out) + "\n")


def _issued(first_line: str) -> date:
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", first_line)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = re.search(r"(\d{1,2}) ([A-Za-z]+) (\d{4})", first_line)
    assert m, first_line
    return date(int(m[3]), MONTHS[m[2].lower()], int(m[1]))


def _rescreen(app: Path) -> None:
    eq = _equivalents(app)
    risky = _risky(app)
    lists = []
    for f in sorted((app / H / "rescreen/lists").glob("*.csv")):
        lines = f.read_text().splitlines()
        lists.append((_issued(lines[0]), list(csv.DictReader(lines[1:]))))
    sanc = max(lists, key=lambda x: x[0])[1]
    updates = sorted(
        (
            r
            for r in csv.DictReader((app / H / "rescreen/updates.csv").read_text().splitlines())
            if date.fromisoformat(r["effective"]) <= REVIEW
        ),
        key=lambda r: r["effective"],
    )
    out = ["customer,decision,risk"]
    for c in json.loads((app / H / "rescreen/customers.json").read_text()):
        for u in updates:
            if u["customer"] == c["id"]:
                c[u["field"]] = u["value"]
        name = _tokens(c["name"], eq)
        hit = _sanctions(sanc, name, c["dob"], eq)
        signoff = c["pep_signoff"].strip()
        if hit == "same":
            d = ("exit", "high")
        elif hit == "name":
            d = ("refer", "high")
        elif _is_pep(app, name, c["dob"], REVIEW, eq):
            ok = signoff and date.fromisoformat(signoff) >= _year_back(REVIEW)
            d = ("keep", "high") if ok else ("refer", "high")
        elif _country_risk(c, risky):
            d = ("keep", "high")
        else:
            d = ("keep", "low")
        out.append(f"{c['id']},{d[0]},{d[1]}")
    (app / "out").mkdir(exist_ok=True)
    (app / "out/hard-rescreen.csv").write_text("\n".join(out) + "\n")


SOLUTIONS = {
    ("compliance", "hard-onboarding"): _onboarding,
    ("compliance", "hard-rescreen"): _rescreen,
}
