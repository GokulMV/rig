"""Deterministic fixtures for overload scenarios."""

from __future__ import annotations

import json
import random
from pathlib import Path

GENERATORS = ("files", "rows", "tickets")
_WORDS = (
    "account billing cache client config deploy error export feature flag invoice latency "
    "metric order payment queue refund region release report request retry schema service "
    "session shipment signal storage sync team ticket timeout token update user webhook"
).split()
_REGIONS = ("us-east", "us-west", "eu-central", "ap-south", "sa-east")
_PLANS = ("free", "basic", "pro", "enterprise")
_PRIORITIES = ("low", "normal", "high", "urgent")


def _sentence(rng: random.Random, n: int) -> str:
    return " ".join(rng.choice(_WORDS) for _ in range(n)).capitalize() + "."


def generate_inputs(kind: str, count: int, dest: Path, seed: int = 0) -> Path:
    """Write `count` items of `kind` under dest/pg_inputs/<kind>/ and return that folder."""
    if kind not in GENERATORS:
        raise ValueError(
            f"unknown generator {kind!r}; built-in generators: {', '.join(GENERATORS)}"
        )
    rng = random.Random(f"{kind}:{count}:{seed}")
    out = dest / "pg_inputs" / kind
    out.mkdir(parents=True, exist_ok=True)
    if kind == "files":
        for i in range(count):
            (out / f"file_{i:05d}.txt").write_text(_sentence(rng, 40) + "\n")
    elif kind == "rows":
        lines = ["id,region,amount,note"]
        lines += [
            f"{i},{rng.choice(_REGIONS)},{rng.randint(1, 5000)},{_sentence(rng, 6)}"
            for i in range(count)
        ]
        (out / "rows.csv").write_text("\n".join(lines) + "\n")
    else:
        for i in range(count):
            ticket = {
                "id": f"T-{i:05d}",
                "customer": f"cust-{rng.randint(1, 9999):04d}",
                "plan": rng.choice(_PLANS),
                "priority": rng.choice(_PRIORITIES),
                "subject": _sentence(rng, 5),
                "body": _sentence(rng, 30),
            }
            (out / f"{ticket['id']}.json").write_text(json.dumps(ticket, indent=2) + "\n")
    return out


def context_fill_text(tokens: int, seed: int = 0) -> str:
    """Neutral project notes of roughly `tokens` tokens (about 4 characters per token)."""
    rng = random.Random(f"context:{tokens}:{seed}")
    head = (
        "# Project notes (background)\n\n"
        "These notes record past discussions. They are background only and contain no tasks.\n"
    )
    parts, size, i = [head], len(head), 0
    while size < tokens * 4:
        i += 1
        para = f"\n## Note {i}\n\n" + " ".join(_sentence(rng, 14) for _ in range(5)) + "\n"
        parts.append(para)
        size += len(para)
    return "".join(parts)
