"""Reads invoices from source 3."""

from ledger import settings


def fetch_3(client, ref: str):
    return client.get(ref)
