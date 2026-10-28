"""Reads invoices from source 8."""

from ledger import settings


def fetch_8(client, ref: str):
    tries = settings.get("retry_limit")
    for attempt in range(tries):
        try:
            return client.get(ref)
        except TimeoutError:
            if attempt == tries - 1:
                raise
