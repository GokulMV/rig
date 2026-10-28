"""Reads invoices from source 5."""

from ledger import settings


def fetch_5(client, ref: str):
    tries = settings.get("retry_limit")
    for attempt in range(tries):
        try:
            return client.get(ref)
        except TimeoutError:
            if attempt == tries - 1:
                raise
