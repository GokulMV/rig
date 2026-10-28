"""The skill matcher measured on real Lab steps and the real starter-skills index
(fixtures/skill_matching.json, 76 steps). At k=1, the number of skills the Lab attaches per step:

                     precision  recall  false attachments
    word overlap        0.217    0.277      21/29 (0.724)
    match-skills        0.756    0.660       6/29 (0.207)

The floors below are those numbers, so a change that makes the word rules worse fails here.

The models (skill_models; `pytest -m models`) on the steps never used to tune them, holdout and
fresh (fixtures/skill_matching_fresh.json), 67 labelled and 34 with no fitting skill:

                     precision  recall  false attachments
    word rules          0.673    0.522       8/34
    models              0.833    0.597       2/34
"""

import os
from pathlib import Path

import pytest
import skill_match_eval as E

from proving_ground import lab, skill_match, skill_models


def test_matcher_stays_above_its_floor_on_real_steps():
    r = E.evaluate(E.lab_match, 1)
    assert r["precision"] >= 0.75, r["misses"]
    assert r["recall"] >= 0.65, r["misses"]
    assert r["false_attach"] <= 0.21, r["misses"]
    r3 = E.evaluate(E.lab_match, 3)
    assert r3["precision"] >= 0.54 and r3["recall"] >= 0.68, r3["misses"]


def _top(ref: str) -> list[dict]:
    return lab.step_skills(E.step(ref), E.library(), 3)


def test_steps_get_skills_for_what_they_do_not_for_shared_words():
    # Implement isn't a review: the words code and review don't bring in receiving-code-review.
    assert all("review" not in s["name"] for s in _top("discipline:development/implement"))
    # A product critique is not a code review.
    assert _top("discipline:product/review") == []
    # Write a failing test: test-driven-development first, not webapp-testing.
    first = _top("discipline:development/test-first")[0]
    assert first["name"] == "test-driven-development" and "failing test" in first["why"]


def test_each_match_says_why_in_the_steps_words():
    review = _top("discipline:development/review")[0]
    assert review["name"] == "review-pr"
    assert review["why"].startswith("matched: ") and "diff" in review["why"]
    assert "name 2/2" in review["why"]


def test_words_reduce_to_one_form():
    t = skill_match.terms
    assert set(t("tests testing tested")) == {"test"}
    assert set(t("reviewer reviewing")) == {"review"}
    assert set(t("planning plans")) == {"plan"}
    assert set(t("a pull request, PRs")) == {"pr"}
    assert set(t("on no off")) == set()  # YAML booleans read as stopwords, not True/False


def test_rare_words_count_more_and_names_gate():
    lib = [
        {"path": "/a", "name": "code-review", "description": "Review code changes"},
        {"path": "/b", "name": "changelog-writer", "description": "Keep a changelog of code"},
        {"path": "/c", "name": "python-lint", "description": "Lint code"},
    ]
    # Implement isn't a review: the review facet rules code-review out.
    assert lab.match_skills("implement code", lib, 3) == []
    got = lab.match_skills("Write the changelog", lib, 3, "for the code")
    assert [s["name"] for s in got] == ["changelog-writer"]
    # python-lint is named for a language the step doesn't mention.
    assert lab.match_skills("lint the code", lib, 3) == []
    assert [s["name"] for s in lab.match_skills("lint python code", lib, 3)] == ["python-lint"]


@pytest.fixture(scope="module")
def held_out():
    """The models on holdout + fresh: fetched first if they aren't on this machine."""
    home = Path(os.environ.get("PG_SKILL_MODELS_DIR") or skill_models.HOME)
    if not skill_models.present(home):
        skill_models.fetch(home)
    ms = skill_models._load(home)
    yield E.evaluate(E.models_match(ms), 1, split="held-out")
    ms.save()


@pytest.mark.models
def test_models_stay_at_what_they_reached_on_steps_never_tuned_on(held_out):
    r = held_out
    assert r["precision"] >= 0.83 and r["recall"] >= 0.59, r["misses"]
    assert int(r["false"].split("/")[0]) <= 2, r["misses"]


@pytest.mark.models
@pytest.mark.xfail(strict=True, reason="not reached: precision 0.833, recall 0.597 (match-skills)")
def test_models_reach_the_target_on_steps_never_tuned_on(held_out):
    # The target: at least 89% precision and recall at one skill per step, at most 7% false.
    r = held_out
    assert r["precision"] >= 0.89 and r["recall"] >= 0.89 and r["false_attach"] <= 0.07
