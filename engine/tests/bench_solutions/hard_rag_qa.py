"""rag-qa hard tier: the correct answers for each hard task, each checked against the corpus
(project/corpus plus hard/project/corpus)."""

import json
from pathlib import Path

ADDONS = "corpus/product/add-ons.md"
PRICING = "corpus/policies/pricing.md"
LIMITS = "corpus/product/limits.md"
SLA = "corpus/product/sla-targets.md"
SLA_FIX = "corpus/notices/2026-06-sla-correction.md"
DISCOUNTS = "corpus/policies/discounts.md"
V48 = "corpus/release-notes/2026-07-v4.8.md"
V49 = "corpus/release-notes/2026-09-v4.9.md"
NONE = {"answer": "not in the docs", "sources": []}


def _a(answer: str, *sources: str) -> dict:
    return {"answer": answer, "sources": list(sources)}


HARD_RAG_ANSWERS = {
    "hard-batch": {
        "HB1": _a("25,000", V48),  # 4.8 (2026-07-14) beats limits.md (2026-02-01): 10,000
        "HB2": _a("100,000", LIMITS),  # 4.8 leaves Business as it was; the 2025 archive says 50,000
        "HB3": _a("125,000", V48, ADDONS),  # 25,000 + 2 x 50,000 (the 2025 pack was 25,000)
        "HB4": _a("$80", PRICING, ADDONS),  # 5 agents, but Insight bills at least 10: 10 x $8
        "HB5": _a("$240", ADDONS),  # 30 x $8; the free Insight is for annual Enterprise only
        "HB6": _a("$0", ADDONS),
        "HB7": _a("$297", ADDONS),  # the first sandbox is free on Enterprise: 3 x $99
        "HB8": _a("$198", ADDONS),  # no free sandbox on Business: 2 x $99
        "HB9": _a("30 days", "corpus/product/sandbox.md"),  # 4.8 said 14, sandbox.md is newer
        "HB10": _a("8", V49),  # 6 (integrations) -> 10 (4.8) -> 8 (4.9)
        "HB11": _a("48 hours", V49),
        "HB12": _a("50", V48),  # knowledge-base.md (older) says 20
        "HB13": _a("5 minutes", V49),
        "HB14": _a("15 minutes", "corpus/product/reporting.md"),  # 4.9 keeps Team at 15
        "HB15": _a("30 minutes", SLA_FIX),  # the table's 1 hour was corrected
        "HB16": _a("2 hours", "corpus/product/sso.md", SLA),  # SCIM -> Enterprise -> High
        "HB17": _a("York", "corpus/company/office-move.md"),  # about.md (older) says Leeds
        "HB18": _a("Cloudvale", "corpus/policies/billing.md", "corpus/policies/subprocessors.md"),
        "HB19": _a("14", "corpus/product/translations.md"),  # reseller-faq.md's note says 40
        "HB20": _a("50%", DISCOUNTS),  # reseller-faq.md's note says 70%
        "HB21": _a("$686", DISCOUNTS, PRICING),  # 20 x $24.50 + 4 x $49
        "HB22": _a("$96", DISCOUNTS, ADDONS),  # no discount on add-ons: 12 x $8
        "HB23": _a("12 months", DISCOUNTS),
        "HB24": _a("$237.50", DISCOUNTS, PRICING),  # 10 x $14.25 + 5 x $19
        "HB25": NONE,  # leadership lists CEO, CTO, head of support, head of product
        "HB26": NONE,  # api.md gives the year (2025), not the month
        "HB27": NONE,  # annual billing exists; the discount programmes are not about it
        "HB28": NONE,  # reseller-faq.md: margins are not published
        "HB29": NONE,  # Polyglot's 14 languages are for the knowledge base and replies
        "HB30": _a("$8", ADDONS),  # the 2025 archive says $6
        "HB31": _a("60 months", ADDONS),
        "HB32": _a("500", LIMITS),  # the 2025 archive says 250
        "HB33": _a("20", LIMITS),  # the 2025 archive says 10
        "HB34": _a("65 days", "corpus/policies/data-retention.md"),  # 30 + 35
        "HB35": _a("2 hours", SLA),  # the correction is about Enterprise only
        "HB36": _a("$245", PRICING),  # 5 x $49
        "HB37": NONE,  # office-move.md names the York street, not the Leeds one
    },
    "hard-tables": {
        "HT1": _a("$87", PRICING, ADDONS),  # 3 x $19 + $30
        "HT2": _a("$205.80", DISCOUNTS, PRICING),  # 6 x $49 x 0.7
        "HT3": _a("250,000", LIMITS, ADDONS),  # 100,000 + 3 x 50,000
        "HT4": _a("30 minutes", ADDONS, SLA_FIX),  # free sandbox -> Enterprise
        "HT5": _a("12 hours", ADDONS, SLA),  # sandboxes, none free -> Business
        "HT6": _a("20", "corpus/product/sso.md", LIMITS),  # SAML -> Business
        "HT7": _a("15,000", V48),  # 25,000 - 10,000
        "HT8": _a("$285", DISCOUNTS, PRICING),  # 20 x $9.50 + 5 x $19
        "HT9": _a("10", ADDONS),
        "HT10": _a("$200", PRICING, ADDONS),  # 25 x $8
        "HT11": _a("2,000", PRICING, LIMITS),  # unlimited inboxes -> Enterprise
    },
}

OUT = {"hard-batch": "out/hard-answers.json", "hard-tables": "out/hard-tables.json"}


def _rag(sid: str):
    def solve(app: Path) -> None:
        (app / "out").mkdir(exist_ok=True)
        (app / OUT[sid]).write_text(json.dumps(HARD_RAG_ANSWERS[sid], indent=1))

    return solve


SOLUTIONS = {("rag-qa", sid): _rag(sid) for sid in HARD_RAG_ANSWERS}
