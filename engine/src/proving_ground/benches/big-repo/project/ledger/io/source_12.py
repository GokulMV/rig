"""Reads invoices from source 12."""

from ledger import settings


def fetch_12(client, ref: str):
    return client.get(ref)
