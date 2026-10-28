"""Every currency the ledger knows."""

from importlib import import_module

CODES = ['EUR', 'USD', 'GBP', 'JPY', 'CHF', 'SEK', 'NOK', 'DKK', 'PLN', 'CZK', 'HUF', 'AUD', 'NZD', 'CAD', 'SGD', 'HKD', 'INR', 'BRL', 'MXN', 'ZAR', 'TRY', 'KRW', 'CNY', 'THB', 'IDR', 'MYR', 'PHP', 'ILS', 'AED', 'SAR']


def info(code: str):
    return import_module(f"ledger.currencies.{code.lower()}")


def decimals(code: str) -> int:
    return info(code).DECIMALS
