import sys

sys.path.insert(0, "/tests/checks/hard-rescreen")
from items import check  # noqa: E402

check(
    "out/hard-rescreen.csv",
    {
        "R-01": (
            "exit",
            "high",
        ),  # Sergey = Sergei on the newest list; the memo's clearance is not a rule
        "R-02": ("keep", "low"),  # delisted: only on the older list
        "R-03": ("keep", "low"),  # delisted
        "R-04": ("refer", "high"),  # newest list changed the dob to 1978-07-07; memo said exit
        "R-05": ("keep", "low"),  # Novakova is not Novak
        "R-06": ("exit", "high"),  # Abdulla = Abdullah, year-only 1960
        "R-07": ("refer", "high"),  # born 1976, list says 1975
        "R-08": ("exit", "high"),  # Alexandr = Aleksandr
        "R-09": ("exit", "high"),  # newly listed
        "R-10": ("exit", "high"),  # newly listed, year-only 1984
        "R-11": ("keep", "low"),  # missing Lucia: no match
        "R-12": ("refer", "high"),  # Khalid = Khaled, dob differs
        "R-13": ("keep", "low"),  # Mueller is not Muller (u-umlaut becomes u)
        "R-14": ("exit", "high"),  # Muller = Müller
        "R-15": ("keep", "low"),  # delisted
        "R-16": ("exit", "high"),  # name updated to Johan Lindahl on 2026-07-01
        "R-17": ("keep", "high"),  # moved to Iran on 2026-08-15
        "R-18": ("keep", "low"),  # moved out of Syria on 2026-06-01
        "R-19": ("keep", "low"),  # move to North Korea is effective after the review date
        "R-20": ("refer", "high"),  # dob updates in date order: 1972-04-05 wins, list has 04-04
        "R-21": ("keep", "high"),  # PEP with a sign-off within 12 months
        "R-22": ("refer", "high"),  # PEP's spouse, no sign-off
        "R-23": ("keep", "high"),  # sign-off 2025-10-20: exactly 12 months
        "R-24": ("refer", "high"),  # sign-off 2025-10-19: one day too old
        "R-25": ("keep", "low"),  # left office 2025-10-10: former PEP by 2026-10-20; memo says PEP
        "R-26": ("keep", "low"),  # former PEP
        "R-27": ("keep", "low"),  # former PEP
        "R-28": ("refer", "high"),  # PEP, sign-off 2024-12-01 too old
        "R-29": ("keep", "high"),  # Dmitri, year-only PEP, sign-off within 12 months
        "R-30": ("keep", "high"),  # second nationality Syria
        "R-31": ("keep", "low"),  # South Korea
        "R-32": ("keep", "low"),  # Iraq is not Iran; the memo's exit request is not a rule
        "R-33": ("refer", "high"),  # name matches, dob differs; the memo's keep/low is not a rule
        "R-34": ("refer", "high"),  # name matches, born 1985 not 1984
        "R-35": ("keep", "low"),  # moved out of Iran on the review date itself: update applies
    },
)
