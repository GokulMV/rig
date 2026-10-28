"""GET /api/rig-score: the explainer page's data, straight from the rig-score skill, and a worked
example scored by the real rig_score()."""

import math
from pathlib import Path

from fastapi.testclient import TestClient

from proving_ground import skills
from proving_ground.api.app import create_app
from proving_ground.rig_score import rig_score

BASE = "http://127.0.0.1:7357"
V = skills.load("rig-score").values


def body(tmp_path: Path) -> dict:
    c = TestClient(create_app(tmp_path, home=tmp_path / "home"), base_url=BASE)
    r = c.get("/api/rig-score")
    assert r.status_code == 200
    return r.json()


def test_the_five_parts_and_their_weights_come_from_the_skill(tmp_path: Path):
    b = body(tmp_path)
    assert [p["id"] for p in b["parts"]] == ["lift", "cost", "followed", "holds_up", "reliable"]
    assert [p["weight"] for p in b["parts"]] == [V["parts"][p]["weight"] for p in V["parts"]]
    assert math.isclose(sum(p["weight"] for p in b["parts"]), 1.0)
    lift = b["parts"][0]
    assert f"+{V['parts']['lift']['target_pts']} pts" in lift["scale"]
    cost = b["parts"][1]
    assert f"{V['parts']['cost']['full']}×" in cost["scale"] and f"{V['parts']['cost']['zero']}×" in cost["scale"]
    assert cost["needs_lift"] and not lift["needs_lift"]
    # Every placeholder was filled.
    for p in b["parts"]:
        assert "{" not in p["scale"] + p["measures"]
    assert "Cost and Reliable" in b["no_credit"]


def test_gates_and_bands_carry_the_skills_caps_and_thresholds(tmp_path: Path):
    b = body(tmp_path)
    caps = {g["id"]: g["cap"] for g in b["gates"]}
    G = V["gates"]
    assert caps == {
        "hurts": G["hurts_cap"],
        "not_shown": G["not_shown_cap"],
        "provisional": G["provisional_cap"],
        "ceiling_worse": G["ceiling_worse_cap"],
    }
    assert f"Fewer than {G['min_pairs']} pairs" in next(g for g in b["gates"] if g["id"] == "provisional")["text"]
    assert [x["id"] for x in b["bands"]] == [x["id"] for x in V["bands"]]
    works = next(x for x in b["bands"] if x["id"] == "works")
    assert works["min"] == 80 and works["label"] == "Works — use it"
    assert next(x for x in b["bands"] if x["id"] == "works_but")["when"].startswith("60 to 79")
    assert "{" not in "".join(x["label"] + x["when"] for x in b["bands"])
    assert [v["word"] for v in b["verdict"]] == ["Helps", "Doesn't Help", "Can't Tell Yet"]


def test_the_worked_example_is_the_real_formula(tmp_path: Path):
    ex = body(tmp_path)["example"]
    assert ex["result"] == rig_score(V["explain"]["example"]["evidence"])
    r = ex["result"]
    assert r["score"] == 67 and r["band"] == "works_but"
    assert "÷ 85%" in r["formula"]["text"]
    assert "share its 15%" in ex["note"]


def test_the_metric_choice_and_its_rule_come_from_the_skill(tmp_path: Path):
    m = body(tmp_path)["metric"]
    M = V["metric"]
    assert m["default"] == "pass_rate" and m["margin_pts"] == M["margin_pts"]
    assert [o["id"] for o in m["options"]] == ["pass_rate", "tokens", "cost", "time"]
    assert m["options"][1]["name"] == "Tokens per Solved Task"
    assert f"-{M['margin_pts']} pts" in m["text"] and "Cost's 20%" in m["text"]
    assert "{" not in m["text"] + m["guard_note"]
    assert m["guard_note"].startswith("The pass rate is the guard: until its 95% interval shows")
    # How many pairs the guard needs is said once on Measure, by the estimate (metric_plan).
    assert "pairs" not in m["guard_note"]
