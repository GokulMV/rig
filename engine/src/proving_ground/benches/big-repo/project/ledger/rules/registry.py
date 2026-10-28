"""Which rule applies to what."""

from importlib import import_module

RULES = [
    "rule_01",
    "rule_02",
    "rule_03",
    "rule_04",
    "rule_05",
    "rule_06",
    "rule_07",
    "rule_08",
    "rule_09",
    "rule_10",
    "rule_11",
    "rule_12",
    "rule_13",
    "rule_14",
    "rule_15",
    "rule_16",
    "rule_17",
    "rule_18",
    "rule_19",
    "rule_20",
    "rule_21",
    "rule_22",
    "rule_23",
    "rule_24",
    "rule_25",
    "rule_26",
    "rule_27",
    "rule_28",
    "rule_29",
    "rule_30",
]


def load(name: str):
    return import_module(f"ledger.rules.{name}")
