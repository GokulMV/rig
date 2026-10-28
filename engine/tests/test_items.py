"""Partial credit: a check's `RIG_ITEMS <right>/<total>` line, from the bench checks through the
runner, the store and the statistics."""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from test_harbor_runner import Recorder, result, runner, spec

from proving_ground.bench import bench, materialize, run_check_locally
from proving_ground.models import Scenario, ScenarioKind, Treatment, TreatmentKind
from proving_ground.runner.base import TrialSpec
from proving_ground.runner.fake import FakeRunner
from proving_ground.runner.harbor import items_in
from proving_ground.stats import item_stats, summarize, t975
from proving_ground.store import Store
from proving_ground.trial import TrialOutcome

# ---- the bench checks: partial output scores part, and keeps its failure message ----


def _check(tmp_path: Path, bid: str, sid: str, files: dict[str, str]):
    project = materialize(bench(bid), tmp_path / "project")
    work = tmp_path / "work"
    run_check_locally(project, sid, work)
    for rel, text in files.items():
        (work / "app" / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / "app" / rel).write_text(text)
    r = subprocess.run(
        [sys.executable, str(work / "tests" / "checks" / sid / "check.py")],
        cwd=work / "app",
        capture_output=True,
        text=True,
    )
    return r, items_in(r.stdout + r.stderr)


THREE_WAY = """invoice,decision,route
INV-1001,approve,none
INV-1002,hold,receiving
INV-1003,hold,buyer
INV-1004,approve,none
INV-1005,hold,procurement
INV-1006,approve,none
INV-1007,hold,procurement
INV-1008,hold,receiving
INV-1009,approve,none
"""


def test_finance_counts_invoices_and_still_says_which_is_wrong(tmp_path: Path):
    r, got = _check(tmp_path, "finance", "three-way-match", {"out/decisions.csv": THREE_WAY})
    assert r.returncode != 0 and got == (8, 9)
    assert "INV-1009: ('approve', 'none') but the policy gives ('hold', 'ap-lead')" in r.stderr


def test_finance_an_extra_invoice_costs_one_so_only_a_pass_scores_all(tmp_path: Path):
    right = THREE_WAY.replace("INV-1009,approve,none", "INV-1009,hold,ap-lead")
    r, got = _check(tmp_path, "finance", "three-way-match", {"out/decisions.csv": right})
    assert r.returncode == 0 and got == (9, 9)
    r, got = _check(
        tmp_path / "x",
        "finance",
        "three-way-match",
        {"out/decisions.csv": right + "INV-9,approve,none\n"},
    )
    assert r.returncode != 0 and got == (8, 9) and "but expected" in r.stderr


def test_finance_missing_file_scores_none(tmp_path: Path):
    r, got = _check(tmp_path, "finance", "q4-batch", {})
    assert r.returncode != 0 and got == (0, 6) and "no out/q4.csv" in r.stderr


def test_finance_bank_recon_counts_its_three_lines(tmp_path: Path):
    text = (
        "working\nUNMATCHED BANK: B-05, B-07, B-08\nUNMATCHED LEDGER: L-05\nDIFFERENCE: 1019.12\n"
    )
    r, got = _check(tmp_path, "finance", "bank-recon", {"out/recon.md": text})
    assert r.returncode != 0 and got == (2, 3)


def test_compliance_counts_customers(tmp_path: Path):
    text = "customer,decision,risk\nC-09,decline,high\nC-10,approve,low\nC-11,approve,low\n"
    r, got = _check(tmp_path, "compliance", "fuzzy-names", {"out/fuzzy.csv": text})
    assert r.returncode != 0 and got == (2, 3)
    assert "C-10: ('approve', 'low') but the policy gives ('refer', 'high')" in r.stderr


def test_rag_counts_questions(tmp_path: Path):
    from bench_solutions.solutions import RAG_ANSWERS

    answers = json.loads(json.dumps(RAG_ANSWERS["lookup"]))
    answers["L2"]["answer"] = "12"  # wrong
    answers["L6"]["sources"] = ["corpus/onboarding.md"]  # right answer, wrong evidence
    del answers["L4"]
    r, got = _check(tmp_path, "rag-qa", "lookup", {"out/answers.json": json.dumps(answers)})
    assert r.returncode != 0 and got == (3, 6)
    assert "L2: wrong answer '12'" in r.stderr and "L4: missing" in r.stderr
    r, got = _check(tmp_path / "x", "rag-qa", "lookup", {"out/answers.json": "not json"})
    assert r.returncode != 0 and got == (0, 6)


def test_support_counts_tickets(tmp_path: Path):
    reply = "Hi.\nDECISION: refund\nAMOUNT: $20.00\n"
    r, got = _check(tmp_path, "support", "tickets", {"replies/T-301.md": reply})
    assert r.returncode != 0 and got == (1, 4) and "no reply for T-302" in r.stderr


def test_data_clean_counts_orders(tmp_path: Path):
    rows = [
        "order_id,date,customer,amount_cents",
        "1001,2026-01-05,Ada Lovelace,1250",
        "1002,2026-01-05,Alan Turing,4000",
        "1003,2026-01-07,Grace Hopper,725",
        "1004,2026-01-20,Ada Lovelace,-300",
        "1006,2026-02-03,Grace Hopper,10000",
        "1007,2026-02-14,Linus,0",  # should be dropped: no amount
        "1008,2026-02-28,Alan Turing,999",
        "1009,2026-03-01,Margaret Hamilton,125000",
        "1010,2026-03-03,Ada Lovelace,2000",
        "1011,2026-03-15,Margaret Hamilton,-2500",  # wrong amount
    ]
    r, got = _check(tmp_path, "data", "clean", {"out/orders_clean.csv": "\n".join(rows) + "\n"})
    # 9 kept orders less the wrong one, 2 dropped less 1007, and not the whole file: 8 + 1 + 0.
    assert r.returncode != 0 and got == (9, 12)


def test_feature_counts_cases_after_the_agents_code_last_runs(tmp_path: Path):
    # A parser that only knows hours, and prints a fake count of its own.
    code = (
        "def parse_duration(t):\n"
        "    print('RIG_ITEMS 9/9')\n"
        "    if t.endswith('h') and t[:-1].isdigit():\n"
        "        return int(t[:-1]) * 3600\n"
        "    raise ValueError(t)\n"
    )
    r, got = _check(tmp_path, "feature", "parse", {"durations.py": code})
    assert r.returncode != 0 and got == (1, 9)


def test_a_check_that_counts_nothing_prints_nothing(tmp_path: Path):
    r, got = _check(tmp_path, "bugfix", "rounding", {})
    assert r.returncode != 0 and got is None


# ---- the runner reads the last line ----


def test_items_in_takes_the_last_well_formed_line():
    assert items_in("RIG_ITEMS 3/12\nnoise\nRIG_ITEMS 11/12\n") == (11, 12)
    assert items_in("  RIG_ITEMS 4 / 5  \n") == (4, 5)
    assert items_in("no count\n") is None
    assert items_in("RIG_ITEMS 13/12\n") is None and items_in("RIG_ITEMS 0/0\n") is None
    assert items_in("say RIG_ITEMS 1/2 inline\n") is None


def test_harbor_runner_reads_the_trials_check_log(tmp_path: Path):
    log = tmp_path / "trials" / "fix__abc" / "verifier" / "check.log"
    log.parent.mkdir(parents=True)
    log.write_text("AssertionError: INV-1009\nRIG_ITEMS 11/12\n")
    t = runner(tmp_path, Recorder(result(0.0))).run_trial(spec("with"))
    assert (t.outcome, t.items_right, t.items_total) == ("fail", 11, 12)
    log.write_text("nothing counted\n")
    t = runner(tmp_path, Recorder(result(1.0))).run_trial(spec("with"))
    assert (t.outcome, t.items_right, t.items_total) == ("pass", None, None)
    # An errored trial measures nothing, counts included.
    log.write_text("RIG_ITEMS 1/2\n")
    t = runner(tmp_path, Recorder(result(None))).run_trial(spec("with"))
    assert t.outcome == "errored" and t.items_right is None


def test_fake_runner_produces_counts():
    sc = Scenario(id="fix", instruction="x", check="true", check_status="approved")
    tr = Treatment(kind=TreatmentKind.SKILL, name="t", path="/t", content_hash="d" * 64)
    fr = FakeRunner(lambda s: ("fail", 11, 12) if s.arm == "without" else "pass")
    out = [
        fr.run_trial(TrialSpec(1, sc, arm, 0, tr, "m", 0, Path("/r")))
        for arm in ("with", "without")
    ]
    assert [(t.outcome, t.items_right, t.items_total) for t in out] == [
        ("pass", None, None),
        ("fail", 11, 12),
    ]


# ---- the store keeps them, and adds the columns to an older database ----


def _t(arm, outcome, right=None, total=None, sid="a", rep=0, kind=ScenarioKind.TYPICAL):
    return TrialOutcome(sid, kind, arm, rep, outcome, items_right=right, items_total=total)


def test_store_round_trips_counts_and_migrates(tmp_path: Path):
    db = tmp_path / "old.db"
    s = Store(f"sqlite:///{db}")
    treat = Treatment(kind=TreatmentKind.SKILL, name="t", path="/t", content_hash="a" * 64)
    eid = s.create_experiment(s.ensure_project("/r"), treat, "m", 1, 1.0, 0)
    s.record_trial(eid, _t("with", "fail", 11, 12))
    s.record_trial(eid, _t("without", "pass"))
    assert [(t.items_right, t.items_total) for t in s.trials(eid)] == [(11, 12), (None, None)]
    # A database from before partial credit: drop the columns, reopen, and it works again.
    with sqlite3.connect(db) as conn:
        conn.execute("ALTER TABLE trials DROP COLUMN items_right")
        conn.execute("ALTER TABLE trials DROP COLUMN items_total")
    s2 = Store(f"sqlite:///{db}")
    assert [(t.items_right, t.items_total) for t in s2.trials(eid)] == [(None, None)] * 2
    s2.record_trial(eid, _t("with", "pass", 12, 12, rep=1))
    assert (s2.trials(eid)[-1].items_right, s2.trials(eid)[-1].items_total) == (12, 12)


# ---- the statistics: a paired t interval, only when every pair counted ----


def _pairs(rows):
    """rows: (with right, without right, total) per pair."""
    out = []
    for i, (w, wo, n) in enumerate(rows):
        out += [
            _t("with", "pass" if w == n else "fail", w, n, sid=f"s{i}"),
            _t("without", "pass" if wo == n else "fail", wo, n, sid=f"s{i}"),
        ]
    return out


def test_t_quantiles():
    assert t975(1) == 12.706 and t975(30) == 2.042
    assert abs(t975(40) - 2.021) < 0.001 and abs(t975(120) - 1.980) < 0.001
    assert abs(t975(10_000) - 1.960) < 0.001
    with pytest.raises(ValueError):
        t975(0)


def test_item_interval_is_a_paired_t_on_the_per_pair_differences():
    rows = [(12, 11, 12), (12, 12, 12), (11, 10, 12), (12, 9, 12), (10, 10, 12)]
    st = summarize(_pairs(rows)).items
    assert st is not None and st.n_pairs == 5
    d = [(w - wo) / 12 for w, wo, _ in rows]
    mean = sum(d) / 5
    sd = (sum((x - mean) ** 2 for x in d) / 4) ** 0.5
    assert abs(st.diff - mean) < 1e-12
    assert abs(st.ci_low - (mean - 2.776 * sd / 5**0.5)) < 1e-12
    assert abs(st.ci_high - (mean + 2.776 * sd / 5**0.5)) < 1e-12
    assert st.ci_low < 0 < mean < st.ci_high  # five pairs this mixed don't settle it
    assert (st.right_with, st.total_with, st.right_without, st.total_without) == (57, 60, 52, 60)
    assert abs(st.score_with - 57 / 60) < 1e-12 and abs(st.score_without - 52 / 60) < 1e-12
    # The pass rate sees 2 of 5 vs 1 of 5; the items see the near-misses.
    h = summarize(_pairs(rows)).headline
    assert (h.pass_with, h.pass_without) == (0.6, 0.2)


def test_item_interval_clears_zero_where_the_pass_rate_cannot_tell():
    # Near the ceiling both arms fail almost every task, but "with" gets one more item right.
    rows = [(11, 10, 12)] * 18 + [(12, 12, 12), (11, 11, 12)]
    s = summarize(_pairs(rows))
    assert s.headline.diff == 0 and s.headline.ci_low < 0 < s.headline.ci_high
    assert s.items is not None and s.items.ci_low > 0 and abs(s.items.diff - 0.075) < 1e-12


def test_item_interval_guards():
    one = item_stats(
        [{"with": _t("with", "pass", 12, 12), "without": _t("without", "fail", 1, 12)}]
    )
    assert one is not None and (one.ci_low, one.ci_high) == (-1.0, 1.0)
    # Identical pairs: the spread is floored at half an item, not zero.
    same = summarize(_pairs([(12, 12, 12)] * 10)).items
    assert same is not None and same.diff == 0 and same.ci_low < 0 < same.ci_high
    assert abs(same.ci_high - 2.262 * (0.5 / 12) / 10**0.5) < 1e-12
    # Clipped to [-1, 1].
    wild = summarize(_pairs([(12, 0, 12), (0, 12, 12)])).items
    assert wild is not None and (wild.ci_low, wild.ci_high) == (-1.0, 1.0)


def test_a_trial_without_a_count_on_an_item_based_task_is_filled_in():
    rows = _pairs([(12, 11, 12), (12, 12, 12)])
    assert summarize(rows).items is not None
    # A fail that printed nothing produced nothing gradable: 0 of the task's 12.
    failed = [*rows[:-1], _t("without", "fail", sid="s1")]
    st = summarize(failed).items
    assert st is not None and st.n_pairs == 2
    assert (st.right_without, st.total_without) == (11, 24)
    assert abs(st.diff - ((12 - 11) / 12 + (12 - 0) / 12) / 2) < 1e-12
    # A pass is never made a failure: all 12.
    passed = [*rows[:-1], _t("without", "pass", sid="s1")]
    st = summarize(passed).items
    assert st is not None and (st.right_without, st.total_without) == (23, 24)
    # The total can come from a trial outside the headline (here, an errored pair's partner).
    lone = [
        _t("with", "fail", sid="x"),
        _t("without", "fail", sid="x"),
        _t("with", "fail", 3, 10, sid="x", rep=1),
        _t("without", "errored", sid="x", rep=1),
    ]
    st = summarize(lone).items
    assert st is not None and st.n_pairs == 1 and (st.total_with, st.right_with) == (10, 0)


def test_no_items_when_a_task_never_counted():
    rows = _pairs([(12, 11, 12)])
    other = [_t("with", "pass", sid="plain"), _t("without", "fail", sid="plain")]
    assert summarize([*rows, *other]).items is None
    assert summarize(other).items is None
    # An errored trial leaves its pair out of the headline, and so out of the items.
    half = [*rows, _t("with", "errored", sid="s9")]
    half += [_t("without", "fail", sid="s9")]
    st = summarize(half).items
    assert st is not None and st.n_pairs == 1
    # Imaginary tasks are not in the headline either.
    imag = [*rows, _t("with", "pass", sid="im", kind=ScenarioKind.IMAGINARY)]
    imag += [_t("without", "fail", sid="im", kind=ScenarioKind.IMAGINARY)]
    assert summarize(imag).items is not None
    assert summarize([]).items is None


def test_summary_json_has_items_only_when_measured():
    from proving_ground.api.views import summary_json

    assert "items" not in summary_json(summarize(_pairs([(12, 11, 12)])[:1]))
    plain = [_t("with", "pass", sid="p"), _t("without", "fail", sid="p")]
    assert "items" not in summary_json(summarize(plain))
    got = summary_json(summarize(_pairs([(12, 11, 12), (11, 11, 12)])))["items"]
    assert set(got) == {
        "with",
        "without",
        "diff",
        "ci_low",
        "ci_high",
        "n",
        "right_with",
        "total_with",
        "right_without",
        "total_without",
    }
    assert got["n"] == 2 and got["right_with"] == 23 and got["total_without"] == 24
