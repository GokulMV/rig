"""Small helpers (2)."""


def clamp_2(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def chunks_2(items: list, n: int) -> list[list]:
    return [items[k : k + n] for k in range(0, len(items), n)]
