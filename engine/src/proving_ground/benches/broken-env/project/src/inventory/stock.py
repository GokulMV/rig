"""Reorder rules."""


def needs_reorder(qty: int, threshold: int) -> bool:
    return qty <= threshold


def below(rows: list[dict]) -> list[str]:
    return [r["sku"] for r in rows if needs_reorder(int(r["qty"]), int(r["threshold"]))]
