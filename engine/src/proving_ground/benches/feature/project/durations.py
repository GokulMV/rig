"""Durations as text: "1h30m" <-> 5400 seconds. See SPEC.md."""


def parse_duration(text: str) -> int:
    raise NotImplementedError


def format_duration(seconds: int) -> str:
    raise NotImplementedError
