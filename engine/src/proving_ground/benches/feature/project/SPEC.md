# Durations

## parse_duration(text) -> int seconds

- Units: `d` (86400), `h` (3600), `m` (60), `s` (1). Each is a whole number followed by its unit.
- Parts can be combined in any order and repeated units add up: `1h30m` = 5400, `30m1h` = 5400,
  `1m1m` = 120.
- Spaces between parts are allowed and ignored: `1h 30m` = 5400. Units are case-insensitive:
  `2H` = 7200.
- A bare number is seconds: `90` = 90.
- Raise `ValueError` for an empty string, a unit with no number (`h`), an unknown unit (`5y`),
  a negative or fractional number (`-5m`, `1.5h`), or anything else left over (`1h x`).

Examples: `"1h30m"` → 5400, `"90s"` → 90, `"2d"` → 172800.

## format_duration(seconds) -> str

- The largest units first, each with its letter, no spaces, zero parts left out:
  5400 → `1h30m`, 90 → `1m30s`, 172800 → `2d`, 0 → `0s`.
- Raise `ValueError` for a negative number.
