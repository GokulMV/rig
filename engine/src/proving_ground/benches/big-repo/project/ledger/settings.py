"""Ledger settings."""

SETTINGS = {
    "retry_limit": 3,
    "timeout_s": 20,
    "default_currency": "EUR",
}


def get(key: str):
    return SETTINGS[key]
