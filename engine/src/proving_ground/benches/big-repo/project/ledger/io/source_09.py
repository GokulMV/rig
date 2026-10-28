"""Reads invoices from source 9."""

from ledger import settings


def fetch_9(client, ref: str):
    return client.get(ref)
