"""Small helpers (3)."""


def clamp_3(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def chunks_3(items: list, n: int) -> list[list]:
    return [items[k : k + n] for k in range(0, len(items), n)]
