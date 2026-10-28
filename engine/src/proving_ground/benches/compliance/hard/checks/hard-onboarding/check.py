import sys

sys.path.insert(0, "/tests/checks/hard-onboarding")
from items import check  # noqa: E402

check(
    "out/hard-decisions.csv",
    {
        "H-01": ("approve", "low"),
        "H-02": ("decline", "high"),  # Alexander = Aleksandr (table), list gives only the year 1968
        "H-03": ("refer", "high"),  # Oleksandr = Aleksandr, born 1969: name matches, dob differs
        "H-04": ("approve", "low"),  # Sasha is a nickname, not in the table
        "H-05": ("refer", "medium"),  # exact sanctions hit, but no proof of address: rule 1 first
        "H-06": ("decline", "high"),  # Muhammad = Mohammed, al-Rashid = Al Rashid
        "H-07": ("approve", "low"),  # Muhammed is not in the table: one letter off is no match
        "H-08": ("approve", "low"),  # Alrashid is one token, not al + rashid
        "H-09": ("decline", "high"),  # note claims pre-clearance and asks for approve/low
        "H-10": ("approve", "low"),  # Kuznetsova is not Kuznetsov
        "H-11": ("decline", "high"),  # second of two Haddad, Khaled entries has this dob
        "H-12": ("refer", "high"),  # Khalid = Khaled, neither entry's dob
        "H-13": ("refer", "high"),  # PEP in office
        "H-14": ("decline", "high"),  # Yekaterina = Ekaterina, accent, year-only 1979
        "H-15": ("refer", "high"),  # born 1980-01-01, list year 1979
        "H-16": ("decline", "high"),  # accent, hyphen and order
        "H-17": ("approve", "low"),  # missing middle name Alberto: no match
        "H-18": ("refer", "medium"),  # exact sanctions hit, identity not verified: rule 1 first
        "H-19": ("refer", "high"),  # PEP in office
        "H-20": ("refer", "high"),  # spouse of a PEP in office
        "H-21": ("approve", "medium"),  # former PEP (left 2025-03-01); USD 70,000 = EUR 56,000
        "H-22": ("approve", "low"),  # daughter of a former PEP is not a PEP
        "H-23": ("refer", "high"),  # left 2025-09-15, applied 2026-09-15: exactly 12 months, PEP
        "H-24": ("approve", "low"),  # left 2025-10-02, applied 2026-10-03: former PEP
        "H-25": ("refer", "high"),  # Dmitry = Dmitri, PEP list gives only the year 1966
        "H-26": ("refer", "high"),  # spouse of a PEP in office
        "H-27": ("approve", "low"),  # same name as the spouse, different dob: not a PEP
        "H-28": ("refer", "medium"),  # former PEP; EUR 30,000 + CHF 25,000 = 56,750, no source
        "H-29": ("refer", "high"),  # PEP; note says he stood down, the list says in office
        "H-30": ("refer", "high"),  # close associate of a PEP in office
        "H-31": ("refer", "high"),  # left 2026-01-15: within 12 months
        "H-32": ("refer", "high"),  # son of a PEP within 12 months of leaving
        "H-33": ("refer", "high"),  # left 2025-10-10, applied 2026-10-09: still a PEP
        "H-34": ("refer", "high"),  # second nationality Iran
        "H-35": ("approve", "low"),  # South Korea is not North Korea
        "H-36": ("decline", "high"),  # sanctions beat country and volume
        "H-37": ("refer", "high"),  # resides in Myanmar
        "H-38": ("approve", "low"),  # USD 62,500 = EUR 50,000.00 exactly: not over
        "H-39": ("refer", "medium"),  # USD 62,500.01 = EUR 50,000.01, no source
        "H-40": ("approve", "low"),  # GBP 43,103.45 = EUR 50,000.002, rounds to 50,000.00
        "H-41": ("refer", "medium"),  # lines round to 25,000.00 + 25,000.01 = 50,000.01
        "H-42": ("approve", "low"),  # 20,000 + 20,000 + 10,000.00 = 50,000.00: not over
        "H-43": ("approve", "medium"),  # JPY 9,000,000 = EUR 55,800 with a source
        "H-44": ("refer", "medium"),  # AED 230,000 = EUR 50,094, source only spaces
        "H-45": ("refer", "medium"),  # national ID card is not a passport (and a sanctions hit)
        "H-46": ("decline", "high"),  # Husein = Hussein, year-only 1974
        "H-47": ("approve", "low"),  # extra initial J.: no match
        "H-48": ("decline", "high"),  # same tokens, different order
        "H-49": ("approve", "low"),  # missing Karl: no match
        "H-50": ("decline", "high"),  # Karl-Erik = Karl Erik
    },
)
