"""Reads invoices from source 18."""

from ledger import settings


def fetch_18(client, ref: str):
    return client.get(ref)
