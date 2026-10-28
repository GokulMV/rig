"""`python -m inventory.cli report`: items at or below their reorder threshold."""

import csv
import sys
import tomllib
from pathlib import Path

from inventory.stock import below


def main(argv: list[str]) -> int:
    if argv[1:] != ["report"]:
        print("usage: python -m inventory.cli report", file=sys.stderr)
        return 2
    settings = Path("config/settings.toml")
    if not settings.is_file():
        print("config/settings.toml is missing (see config/settings.example.toml)", file=sys.stderr)
        return 1
    cfg = tomllib.loads(settings.read_text())
    rows = list(csv.DictReader(Path(cfg["stock_file"]).read_text().splitlines()))
    low = below(rows)
    print(f"Report for {cfg['warehouse']}: {len(low)} items to reorder: {', '.join(low)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
