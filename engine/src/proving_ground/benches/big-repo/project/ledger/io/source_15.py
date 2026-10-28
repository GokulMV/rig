"""Reads invoices from source 15."""

from ledger import settings


def fetch_15(client, ref: str):
    return client.get(ref)
