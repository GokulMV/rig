"""Small helpers (9)."""


def clamp_9(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def chunks_9(items: list, n: int) -> list[list]:
    return [items[k : k + n] for k in range(0, len(items), n)]
