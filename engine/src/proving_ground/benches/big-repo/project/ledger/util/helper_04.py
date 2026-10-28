"""Small helpers (4)."""


def clamp_4(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def chunks_4(items: list, n: int) -> list[list]:
    return [items[k : k + n] for k in range(0, len(items), n)]
