// GET /api/tutorial as the engine returned it (this branch): the words, the example and the recorded
// run. Regenerate with: curl -s 127.0.0.1:<port>/api/tutorial
import type { Tutorial } from "../lib/types";

export const TUTORIAL = {
    "text": {
        "home": {
            "title": "New Here? See One Real Run, Start to Finish",
            "title_done": "The Tutorial: One Real Run, Start to Finish",
            "lead": "10 tiny coding tasks, run with and without one skill on a free local model. Five steps, about two minutes to read. Nothing in it touches your repos or runs.",
            "start": "Start the Tutorial",
            "replay": "Replay the Tutorial"
        },
        "proof": {
            "pill": "Real Run",
            "caption": "pricetags: 10 tasks with and without the skill price-tags-style, on Qwen3.5 9B (Q4_0), local and free",
            "without": "Without the skill",
            "with": "With the skill"
        },
        "eyebrow": "Tutorial · step {step} of 5",
        "leave": "Leave the Tutorial",
        "stepper": "Tutorial steps",
        "steps": [
            {
                "id": "describe",
                "title": "Describe: What Should the Agent Get Better At?",
                "lead": "Every Rig run starts from a goal and the place the work lives. Here the goal is plain: write the labels on a corner shop's shelves in the shop's house style. The work lives in a tiny Python repo, pricetags.",
                "goal_title": "Goal",
                "goal": "Shelf labels for a corner shop, written in the shop's house style.",
                "repo": "Where it lives: the repo pricetags",
                "tasks_line": ".proving-ground/scenarios/ (10 tasks)",
                "note": "In your own run, this is your repo (Rig a Repo) or a workflow you describe (Rig a Workflow)."
            },
            {
                "id": "design",
                "title": "Design: The Agent, and One Part to Test",
                "lead": "Your architecture is the car; the change you want to judge is a part. Here the car is Claude Code running on Qwen3.5 9B (Q4_0), a free local model, and the part is one skill, price-tags-style: the house rules, written down. The code alone doesn't say them.",
                "car": "The Car",
                "car_text": "Claude Code, on Qwen3.5 9B (Q4_0) served by llama.cpp on this Mac. Nothing leaves the machine, and it costs nothing.",
                "part": "The Part Being Tested",
                "part_text": "The skill price-tags-style. The \"with\" arm is told to open it; the \"without\" arm never sees it.",
                "note": "In your own run, Design ranks whole architectures for your goal; you can also keep the one you have."
            },
            {
                "id": "build",
                "title": "Build: Tasks, Each with a Check",
                "lead": "Rig judges a change on tasks, never on a feeling. Each of these 10 tasks asks for one new label, and each has a check: a command that passes or fails by calling the new function and comparing its text. Nothing is graded by eye.",
                "tasks_title": "Tasks",
                "check_title": "One Task's Check",
                "note": "In your own run, Rig writes tasks like these for your repo, and you approve each check before anything runs."
            },
            {
                "id": "measure",
                "title": "Measure: The Same Tasks, with and without the Skill",
                "lead": "Each task ran twice, each time in its own Docker sandbox: once with the skill and once without. With it, 9 of 10 passed; without it, 2 of 10. The Rig score turns that into one number, and shows how it was made.",
                "task": "Task",
                "without": "Without",
                "with": "With",
                "passed": "passed",
                "failed": "failed",
                "timed_out": "timed out",
                "errored": "errored",
                "total": "Passed",
                "rows": "Task by task, with the skill: 8 went from fail to pass, 1 from pass to fail, and 1 came out the same both ways.",
                "interval_title": "What the Skill Changed",
                "interval": "+70 pts, 95% interval +14 to +91",
                "score_title": "The Rig Score",
                "note": "In your own run, you pick the tasks and the size, see the price first, and watch it live."
            },
            {
                "id": "ship",
                "title": "Ship: Keep What Earned Its Place",
                "lead": "The skill scored 78 out of 100: Works, but the lift needs work. Ship turns what you measured into a build brief any coding agent can follow, with the evidence beside each change.",
                "result_title": "What It Rests On",
                "brief_title": "The Build Brief, for This Example",
                "brief": [
                    "Add the skill price-tags-style to the agent's skills (.claude/skills/price-tags-style/).",
                    "Measured on 10 pairs with Qwen3.5 9B (Q4_0): 9 of 10 passed with it, 2 of 10 without.",
                    "Rig score 78/100: Works, but the lift needs work.",
                    "Measure again when the model or the tasks change."
                ],
                "note": "In your own run, Ship writes BUILD.md and rig.json for the changes you accepted."
            }
        ],
        "finish": {
            "eyebrow": "Tutorial · Done",
            "title": "That's Rig, End to End",
            "lead": "Describe, design, build, measure, ship, on one real run. Now try it on something of yours.",
            "options": [
                {
                    "id": "repo",
                    "label": "Rig Your Own Repo",
                    "text": "Attach a repo: Rig maps it, suggests parts, writes tasks and measures each change.",
                    "to": "repo"
                },
                {
                    "id": "lab",
                    "label": "Rig a Workflow",
                    "text": "No repo needed: build or pick a workflow and measure it on a bench.",
                    "to": "lab"
                },
                {
                    "id": "home",
                    "label": "Back to Home",
                    "text": "The start page, with your runs.",
                    "to": "home"
                }
            ]
        },
        "stale": "The example changed after this run was recorded, so these numbers are from the earlier version.",
        "recorded_note": "Recorded on 2026-10-27 with Qwen3.5 9B (Q4_0). This page only reads that record; it runs nothing.",
        "settings_title": "How It Was Run",
        "settings": [
            "Model: Qwen3.5-9B-Q4_0.gguf, served by llama.cpp 0.7.0 (build 11669): -c 65536 -np 1 --jinja, Qwen 3.5's own chat template with its system-message check turned into a system turn; thinking on (Claude Code asks for it)",
            "Agent: Claude Code in a Docker sandbox, pointed at the local server; the \"with\" arm told to open the skill",
            "Time limit: 3× each task's own, as for any local model"
        ]
    },
    "example": {
        "name": "pricetags",
        "files": [
            {
                "path": "README.md",
                "text": "# pricetags\n\nThe labels on the shelves of a small corner shop, made in Python. Prices are kept in whole\ncents (an `int`); the functions in `pricetags/tags.py` turn them into the text printed on the\nlabels.\n\nRun the tests with `python3 -m unittest`.\n"
            },
            {
                "path": "pricetags/tags.py",
                "text": "\"\"\"The text printed on shelf labels. Prices are whole cents (int).\"\"\"\n\n\ndef price(cents: int) -> str:\n    \"\"\"The label for one price: price(123456) == \"€1.234,56\".\"\"\"\n    euros, rest = divmod(cents, 100)\n    return f\"€{euros:,}\".replace(\",\", \".\") + f\",{rest:02d}\"\n"
            },
            {
                "path": "tests/test_tags.py",
                "text": "import unittest\n\nfrom pricetags.tags import price\n\n\nclass PriceTest(unittest.TestCase):\n    def test_price(self):\n        self.assertEqual(price(1999), \"€19,99\")\n        self.assertEqual(price(5), \"€0,05\")\n        self.assertEqual(price(123456), \"€1.234,56\")\n\n\nif __name__ == \"__main__\":\n    unittest.main()\n"
            }
        ],
        "skill": {
            "name": "price-tags-style",
            "description": "The shop's house style for shelf labels in pricetags/tags.py: how prices, units, refunds, discounts, ranges, sales and free items are written. Use it for any change to a label.",
            "path": ".claude/skills/price-tags-style/SKILL.md",
            "text": "---\nname: price-tags-style\ndescription: \"The shop's house style for shelf labels in pricetags/tags.py: how prices, units, refunds, discounts, ranges, sales and free items are written. Use it for any change to a label.\"\n---\n\n# Price tag house style\n\nEvery label is built from `price(cents)` in `pricetags/tags.py`, which already writes one\nprice the house way: euro sign first, dot between thousands, comma before the cents\n(`price(123456) == \"€1.234,56\"`). Reuse it; never format a price by hand.\n\n## Rules\n\n- **Per unit:** the price, a space, a slash, a space, the unit: `€2,50 / kg`.\n- **Per 100 g** (from a price per kg): divide by 10, round half up to a whole cent, then\n  `€1,25 / 100 g`.\n- **Refunds:** a minus sign straight before the euro sign: `-€3,00`. Takes the refund as a\n  positive number of cents.\n- **Discounts:** a minus sign, the whole percent, a percent sign, no spaces: `-15%`.\n- **Ranges:** the low price, the word `to`, the high price: `€5,00 to €9,00`.\n- **Sales:** the new price, then the old one in brackets after `was`: `€7,99 (was €9,99)`.\n- **Free items:** zero cents is the word `free`, lowercase. Any other amount is `price()`.\n- **Rounding:** always half up to a whole cent (`282.5` cents is `283`). Never Python's\n  `round()`, which rounds halves to even.\n- **Tax:** a price with tax added is net × (100 + rate) ÷ 100, rounded half up, then `price()`.\n\n## Check your work\n\nRun `python3 -m unittest` from the project root, and add a test for the new label in\n`tests/test_tags.py`.\n",
            "body": "# Price tag house style\n\nEvery label is built from `price(cents)` in `pricetags/tags.py`, which already writes one\nprice the house way: euro sign first, dot between thousands, comma before the cents\n(`price(123456) == \"€1.234,56\"`). Reuse it; never format a price by hand.\n\n## Rules\n\n- **Per unit:** the price, a space, a slash, a space, the unit: `€2,50 / kg`.\n- **Per 100 g** (from a price per kg): divide by 10, round half up to a whole cent, then\n  `€1,25 / 100 g`.\n- **Refunds:** a minus sign straight before the euro sign: `-€3,00`. Takes the refund as a\n  positive number of cents.\n- **Discounts:** a minus sign, the whole percent, a percent sign, no spaces: `-15%`.\n- **Ranges:** the low price, the word `to`, the high price: `€5,00 to €9,00`.\n- **Sales:** the new price, then the old one in brackets after `was`: `€7,99 (was €9,99)`.\n- **Free items:** zero cents is the word `free`, lowercase. Any other amount is `price()`.\n- **Rounding:** always half up to a whole cent (`282.5` cents is `283`). Never Python's\n  `round()`, which rounds halves to even.\n- **Tax:** a price with tax added is net × (100 + rate) ÷ 100, rounded half up, then `price()`.\n\n## Check your work\n\nRun `python3 -m unittest` from the project root, and add a test for the new label in\n`tests/test_tags.py`."
        },
        "tasks": [
            {
                "id": "discount",
                "title": "Discount label",
                "kind": "typical",
                "instruction": "Add `discount(percent)` to pricetags/tags.py: the label for a percentage off, such as 15 percent off.",
                "check": "python3 -m unittest -q && python3 - <<'PY'\nfrom pricetags.tags import discount\ngot = discount(15)\nassert got == \"-15%\", f'discount(15) gave {got!r}'\ngot = discount(50)\nassert got == \"-50%\", f'discount(50) gave {got!r}'\nprint('ok')\nPY\n"
            },
            {
                "id": "free-item",
                "title": "Free items",
                "kind": "edge",
                "instruction": "Add `tag(cents)` to pricetags/tags.py: the label for an item on the shelf, which may be given away at no charge.",
                "check": "python3 -m unittest -q && python3 - <<'PY'\nfrom pricetags.tags import tag\ngot = tag(0)\nassert got == \"free\", f'tag(0) gave {got!r}'\ngot = tag(150)\nassert got == \"€1,50\", f'tag(150) gave {got!r}'\nprint('ok')\nPY\n"
            },
            {
                "id": "parse-price",
                "title": "Read a label back",
                "kind": "typical",
                "instruction": "Add `parse_price(text)` to pricetags/tags.py: the reverse of `price()`, turning a price label back into whole cents (an int).",
                "check": "python3 -m unittest -q && python3 - <<'PY'\nfrom pricetags.tags import parse_price\ngot = parse_price(\"€1.234,56\")\nassert got == 123456, f'parse_price(\"€1.234,56\") gave {got!r}'\ngot = parse_price(\"€0,05\")\nassert got == 5, f'parse_price(\"€0,05\") gave {got!r}'\ngot = parse_price(\"€19,99\")\nassert got == 1999, f'parse_price(\"€19,99\") gave {got!r}'\nprint('ok')\nPY\n"
            },
            {
                "id": "per-100g",
                "title": "Price per 100 g",
                "kind": "edge",
                "instruction": "Add `per_100g(cents_per_kg)` to pricetags/tags.py: the label for the price per 100 g of a product priced per kg.",
                "check": "python3 -m unittest -q && python3 - <<'PY'\nfrom pricetags.tags import per_100g\ngot = per_100g(1250)\nassert got == \"€1,25 / 100 g\", f'per_100g(1250) gave {got!r}'\ngot = per_100g(1245)\nassert got == \"€1,25 / 100 g\", f'per_100g(1245) gave {got!r}'\nprint('ok')\nPY\n"
            },
            {
                "id": "price-range",
                "title": "Price range",
                "kind": "typical",
                "instruction": "Add `price_range(low, high)` to pricetags/tags.py: the label for a product sold in several sizes, from the cheapest price to the dearest (both in cents).",
                "check": "python3 -m unittest -q && python3 - <<'PY'\nfrom pricetags.tags import price_range\ngot = price_range(500, 900)\nassert got == \"€5,00 to €9,00\", f'price_range(500, 900) gave {got!r}'\ngot = price_range(99, 120000)\nassert got == \"€0,99 to €1.200,00\", f'price_range(99, 120000) gave {got!r}'\nprint('ok')\nPY\n"
            },
            {
                "id": "refund",
                "title": "Refund label",
                "kind": "typical",
                "instruction": "Add `refund(cents)` to pricetags/tags.py: the label for money given back to a customer. It takes the amount refunded in cents.",
                "check": "python3 -m unittest -q && python3 - <<'PY'\nfrom pricetags.tags import refund\ngot = refund(300)\nassert got == \"-€3,00\", f'refund(300) gave {got!r}'\ngot = refund(123456)\nassert got == \"-€1.234,56\", f'refund(123456) gave {got!r}'\nprint('ok')\nPY\n"
            },
            {
                "id": "sale",
                "title": "Sale label",
                "kind": "typical",
                "instruction": "Add `sale(was, now)` to pricetags/tags.py: the label for a product on sale, showing its new price and its old one (both in cents).",
                "check": "python3 -m unittest -q && python3 - <<'PY'\nfrom pricetags.tags import sale\ngot = sale(999, 799)\nassert got == \"€7,99 (was €9,99)\", f'sale(999, 799) gave {got!r}'\ngot = sale(150000, 99900)\nassert got == \"€999,00 (was €1.500,00)\", f'sale(150000, 99900) gave {got!r}'\nprint('ok')\nPY\n"
            },
            {
                "id": "total",
                "title": "Basket total",
                "kind": "typical",
                "instruction": "Add `total(prices)` to pricetags/tags.py: the label for the sum of a list of prices in cents.",
                "check": "python3 -m unittest -q && python3 - <<'PY'\nfrom pricetags.tags import total\ngot = total([1000, 240, 5])\nassert got == \"€12,45\", f'total([1000, 240, 5]) gave {got!r}'\ngot = total([99999, 1])\nassert got == \"€1.000,00\", f'total([99999, 1]) gave {got!r}'\nprint('ok')\nPY\n"
            },
            {
                "id": "unit-price",
                "title": "Price per unit",
                "kind": "typical",
                "instruction": "Add `unit_price(cents, unit)` to pricetags/tags.py: the label for a price per unit, such as a price per kg.",
                "check": "python3 -m unittest -q && python3 - <<'PY'\nfrom pricetags.tags import unit_price\ngot = unit_price(250, \"kg\")\nassert got == \"€2,50 / kg\", f'unit_price(250, \"kg\") gave {got!r}'\ngot = unit_price(1999, \"l\")\nassert got == \"€19,99 / l\", f'unit_price(1999, \"l\") gave {got!r}'\nprint('ok')\nPY\n"
            },
            {
                "id": "with-tax",
                "title": "Price with tax",
                "kind": "edge",
                "instruction": "Add `with_tax(net_cents, rate)` to pricetags/tags.py: the label for a net price in cents with a tax rate in percent added, such as 23 for 23%.",
                "check": "python3 -m unittest -q && python3 - <<'PY'\nfrom pricetags.tags import with_tax\ngot = with_tax(1000, 23)\nassert got == \"€12,30\", f'with_tax(1000, 23) gave {got!r}'\ngot = with_tax(250, 13)\nassert got == \"€2,83\", f'with_tax(250, 13) gave {got!r}'\nprint('ok')\nPY\n"
            }
        ]
    },
    "run": {
        "recorded": "2026-10-27",
        "model": {
            "file": "Qwen3.5-9B-Q4_0.gguf",
            "id": "qwen3.5-9b",
            "server": "llama.cpp 0.7.0 (build 11669): -c 65536 -np 1 --jinja, Qwen 3.5's own chat template with its system-message check turned into a system turn; thinking on (Claude Code asks for it)",
            "agent": "claude-code",
            "nudge": true,
            "timeout_factor": 3,
            "label": "Qwen3.5 9B (Q4_0)"
        },
        "skill": "price-tags-style",
        "tasks": [
            {
                "id": "discount",
                "title": "Discount label",
                "with": {
                    "passed": 1,
                    "trials": 1,
                    "outcomes": [
                        "pass"
                    ],
                    "seconds": [
                        220.4
                    ],
                    "details": [
                        ""
                    ]
                },
                "without": {
                    "passed": 0,
                    "trials": 1,
                    "outcomes": [
                        "fail"
                    ],
                    "seconds": [
                        61.0
                    ],
                    "details": [
                        ""
                    ]
                }
            },
            {
                "id": "free-item",
                "title": "Free items",
                "with": {
                    "passed": 1,
                    "trials": 1,
                    "outcomes": [
                        "pass"
                    ],
                    "seconds": [
                        244.1
                    ],
                    "details": [
                        ""
                    ]
                },
                "without": {
                    "passed": 0,
                    "trials": 1,
                    "outcomes": [
                        "fail"
                    ],
                    "seconds": [
                        51.5
                    ],
                    "details": [
                        ""
                    ]
                }
            },
            {
                "id": "parse-price",
                "title": "Read a label back",
                "with": {
                    "passed": 0,
                    "trials": 1,
                    "outcomes": [
                        "fail"
                    ],
                    "seconds": [
                        921.4
                    ],
                    "details": [
                        "timed out after 900 s"
                    ]
                },
                "without": {
                    "passed": 1,
                    "trials": 1,
                    "outcomes": [
                        "pass"
                    ],
                    "seconds": [
                        102.9
                    ],
                    "details": [
                        ""
                    ]
                }
            },
            {
                "id": "per-100g",
                "title": "Price per 100 g",
                "with": {
                    "passed": 1,
                    "trials": 1,
                    "outcomes": [
                        "pass"
                    ],
                    "seconds": [
                        360.7
                    ],
                    "details": [
                        ""
                    ]
                },
                "without": {
                    "passed": 0,
                    "trials": 1,
                    "outcomes": [
                        "fail"
                    ],
                    "seconds": [
                        146.8
                    ],
                    "details": [
                        ""
                    ]
                }
            },
            {
                "id": "price-range",
                "title": "Price range",
                "with": {
                    "passed": 1,
                    "trials": 1,
                    "outcomes": [
                        "pass"
                    ],
                    "seconds": [
                        187.6
                    ],
                    "details": [
                        ""
                    ]
                },
                "without": {
                    "passed": 0,
                    "trials": 1,
                    "outcomes": [
                        "fail"
                    ],
                    "seconds": [
                        67.6
                    ],
                    "details": [
                        ""
                    ]
                }
            },
            {
                "id": "refund",
                "title": "Refund label",
                "with": {
                    "passed": 1,
                    "trials": 1,
                    "outcomes": [
                        "pass"
                    ],
                    "seconds": [
                        163.6
                    ],
                    "details": [
                        ""
                    ]
                },
                "without": {
                    "passed": 0,
                    "trials": 1,
                    "outcomes": [
                        "fail"
                    ],
                    "seconds": [
                        921.2
                    ],
                    "details": [
                        "timed out after 900 s"
                    ]
                }
            },
            {
                "id": "sale",
                "title": "Sale label",
                "with": {
                    "passed": 1,
                    "trials": 1,
                    "outcomes": [
                        "pass"
                    ],
                    "seconds": [
                        248.4
                    ],
                    "details": [
                        ""
                    ]
                },
                "without": {
                    "passed": 0,
                    "trials": 1,
                    "outcomes": [
                        "fail"
                    ],
                    "seconds": [
                        66.2
                    ],
                    "details": [
                        ""
                    ]
                }
            },
            {
                "id": "total",
                "title": "Basket total",
                "with": {
                    "passed": 1,
                    "trials": 1,
                    "outcomes": [
                        "pass"
                    ],
                    "seconds": [
                        308.9
                    ],
                    "details": [
                        ""
                    ]
                },
                "without": {
                    "passed": 1,
                    "trials": 1,
                    "outcomes": [
                        "pass"
                    ],
                    "seconds": [
                        69.6
                    ],
                    "details": [
                        ""
                    ]
                }
            },
            {
                "id": "unit-price",
                "title": "Price per unit",
                "with": {
                    "passed": 1,
                    "trials": 1,
                    "outcomes": [
                        "pass"
                    ],
                    "seconds": [
                        173.5
                    ],
                    "details": [
                        ""
                    ]
                },
                "without": {
                    "passed": 0,
                    "trials": 1,
                    "outcomes": [
                        "fail"
                    ],
                    "seconds": [
                        68.1
                    ],
                    "details": [
                        ""
                    ]
                }
            },
            {
                "id": "with-tax",
                "title": "Price with tax",
                "with": {
                    "passed": 1,
                    "trials": 1,
                    "outcomes": [
                        "pass"
                    ],
                    "seconds": [
                        253.7
                    ],
                    "details": [
                        ""
                    ]
                },
                "without": {
                    "passed": 0,
                    "trials": 1,
                    "outcomes": [
                        "fail"
                    ],
                    "seconds": [
                        148.7
                    ],
                    "details": [
                        ""
                    ]
                }
            }
        ],
        "n": 10,
        "with": 9,
        "without": 2,
        "diff": 0.7,
        "ci_low": 0.13950380052769806,
        "ci_high": 0.9073099001306912,
        "verdict": "helps",
        "ledger": {
            "total": 20,
            "with": 10,
            "without": 10,
            "pairs": 10,
            "logs_read": 10,
            "clean": 18,
            "timed_out": 2,
            "errored": 0,
            "broken": 0
        },
        "rig": {
            "score": 78,
            "band": "works_but",
            "tone": "neutral",
            "label": "Works, but the lift needs work",
            "reason": "Lift could be as small as +14 pts",
            "provisional": false,
            "pairs": 10,
            "parts": [
                {
                    "id": "lift",
                    "name": "Lift",
                    "weight": 0.4,
                    "score": 55.8,
                    "detail": "lower bound +14 pts (target +25)",
                    "counted": true,
                    "weight_used": 0.4706
                },
                {
                    "id": "cost",
                    "name": "Cost",
                    "weight": 0.2,
                    "score": 100.0,
                    "detail": "costs nothing (a local model)",
                    "counted": true,
                    "weight_used": 0.2353
                },
                {
                    "id": "followed",
                    "name": "Followed",
                    "weight": 0.15,
                    "score": 100.0,
                    "detail": "opened the skill in 10 of the 10 \"with\" trials whose logs could be read",
                    "counted": true,
                    "weight_used": 0.1765
                },
                {
                    "id": "holds_up",
                    "name": "Holds Up",
                    "weight": 0.15,
                    "score": null,
                    "detail": "This bench has no held-out tasks, so it's unknown whether this holds on unseen tasks",
                    "counted": false,
                    "weight_used": 0.0
                },
                {
                    "id": "reliable",
                    "name": "Reliable",
                    "weight": 0.1,
                    "score": 90.0,
                    "detail": "18 of 20 trials ran cleanly (10 with, 10 without)",
                    "counted": true,
                    "weight_used": 0.1176
                }
            ],
            "gates": [],
            "formula": {
                "text": "40% × 55.8 + 20% × 100 + 15% × 100 + 10% × 90 = 66.3; ÷ 85% (weights rescaled to the measured parts; holds up not measured) = 78.0; rounded: 78",
                "measured_weight": 0.85,
                "raw": 78.02,
                "not_measured": [
                    "holds up"
                ]
            },
            "ledger": {
                "total": 20,
                "with": 10,
                "without": 10,
                "pairs": 10,
                "logs_read": 10,
                "clean": 18,
                "timed_out": 2,
                "errored": 0,
                "broken": 0
            },
            "ledger_text": "20 trials (10 with, 10 without) · 10 complete pairs · 18 ran cleanly, 2 timed out · logs read for 10 of the 10 \"with\" trials",
            "verdict": {
                "id": "helps",
                "word": "Helps",
                "tone": "positive",
                "reason": "9 of 10 passed with vs 2 of 10 passed without (+70 pts, 95% interval +14 to +91); takes 1.8× as long and timed out on 1 of 10.",
                "next": "Next: use it, and measure again when the model or the tasks change.",
                "facts": [
                    "Quality: 9 of 10 passed with, 2 of 10 passed without (+70 pts, 95% interval +14 to +91)",
                    "Cost: nothing (a local model)",
                    "Time: 5.1 min vs 2.8 min per trial (1.8×)",
                    "Reliability: with, 1 of 10 timed out; without, 1 of 10 timed out"
                ]
            },
            "quality": "pass_rate"
        },
        "stale": false
    }
} as unknown as Tutorial;
