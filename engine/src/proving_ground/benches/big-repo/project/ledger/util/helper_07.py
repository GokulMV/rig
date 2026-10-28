"""Small helpers (7)."""


def clamp_7(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def chunks_7(items: list, n: int) -> list[list]:
    return [items[k : k + n] for k in range(0, len(items), n)]
