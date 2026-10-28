"""Reads invoices from source 6."""

from ledger import settings


def fetch_6(client, ref: str):
    return client.get(ref)
