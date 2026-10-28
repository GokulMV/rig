"""Small helpers (5)."""


def clamp_5(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def chunks_5(items: list, n: int) -> list[list]:
    return [items[k : k + n] for k in range(0, len(items), n)]
