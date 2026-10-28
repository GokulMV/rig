"""Reads invoices from source 10."""

from ledger import settings


def fetch_10(client, ref: str):
    tries = settings.get("retry_limit")
    for attempt in range(tries):
        try:
            return client.get(ref)
        except TimeoutError:
            if attempt == tries - 1:
                raise
