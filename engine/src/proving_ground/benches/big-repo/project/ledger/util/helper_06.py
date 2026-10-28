"""Small helpers (6)."""


def clamp_6(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def chunks_6(items: list, n: int) -> list[list]:
    return [items[k : k + n] for k in range(0, len(items), n)]
