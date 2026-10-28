"""Record a tutorial track's example run, on a local model, through the same engine a repo run
uses. Free: nothing leaves this machine. `--track skill` (the default): the price-tags tasks with
and without the house-style skill, scored on the pass rate. `--track tokens`: the textkit tasks
with and without the lean-context skill, scored on tokens per solved task (rig-score: Metric),
so it needs about `metric_guard_pairs()` pairs (`--repeats 4` on its ten tasks gives 40).

    uv run python -m proving_ground.tutorial.record --base http://127.0.0.1:8096 \
        --model qwen3.5-9b --model-file Qwen3.5-9B-Q4_0.gguf --server "llama.cpp 0.7.0 ..." \
        --work /some/empty/dir/outside/any/git/repo

It needs Docker and a llama.cpp (or Ollama) server that speaks Anthropic's Messages API. The
work folder must not sit inside a git repo (the snapshot would export that repo instead). It
writes `recorded.json` next to this file: every trial's outcome, and the Rig score the app
computes for the run (GET /api/experiments/{id}). Nothing here is ever run by the tests.
`--track tokens` writes `tokens/recorded.json`, with each trial's tokens as well.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
# Per track: the example repo, its folder name in the work dir, the skill, the metric and the
# record it writes.
TRACKS = {
    "skill": (HERE / "project", "pricetags", HERE / "skill" / "price-tags-style", None),
    "tokens": (
        HERE / "tokens" / "project",
        "textkit",
        HERE / "tokens" / "skill" / "lean-context",
        "tokens",
    ),
}
OUT = {"skill": HERE / "recorded.json", "tokens": HERE / "tokens" / "recorded.json"}


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=rig", "-c", "user.email=rig@localhost", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def setup(work: Path, track: str = "skill") -> tuple[Path, Path]:
    """A fresh git repo of the track's example project, and a copy of its skill beside it."""
    project, name, src, _ = TRACKS[track]
    repo, skill = work / name, work / "skills" / src.name
    for d in (repo, skill):
        if d.exists():
            shutil.rmtree(d)
    shutil.copytree(project, repo, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(src, skill)
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", name)
    return repo, skill


def main() -> None:
    from fastapi.testclient import TestClient

    from proving_ground import local_models as local_mod
    from proving_ground.agents import Credentials
    from proving_ground.api.app import create_app
    from proving_ground.report import format_event
    from proving_ground.service import execute, prepare_experiment
    from proving_ground.tutorial import fingerprint
    from proving_ground.workspace import Workspace

    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="The local server, e.g. http://127.0.0.1:8096")
    ap.add_argument("--model", required=True, help="The model id the server lists")
    ap.add_argument("--model-file", required=True, help="The weights it serves, for the record")
    ap.add_argument("--server", required=True, help="The server and its flags, for the record")
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--only", nargs="*", default=[], help="Only these task ids (a smoke test)")
    ap.add_argument("--track", choices=sorted(TRACKS), default="skill")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()
    project, _, src, metric = TRACKS[a.track]
    out = a.out or OUT[a.track]

    work = a.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    made_on = fingerprint(project, src)  # the example as it is now, copied by setup() below
    repo, skill = setup(work, a.track)
    lm = local_mod.make(a.base, a.model, "llamacpp")
    harbor_model, env = local_mod.agent_env(lm)
    from proving_ground.files import load_scenarios

    ids = a.only or [s.id for s in load_scenarios(repo)]
    prep = prepare_experiment(
        repo,
        skill,
        budget=1.0,  # a local model: trials cost nothing
        n=a.repeats * len(ids),
        model=lm.id,
        scenario_ids=ids,
        agent="claude-code",
        env=env,
        extra_meta={"local_model": lm.id} | ({"metric": metric} if metric else {}),
        harbor_model=harbor_model,
        free=True,
        timeout_factor=local_mod.L["timeout_factor"],
        nudge=True,  # a small model never opens a skill it is only offered (judge-experiment)
        reuse_baseline=False,
    )
    started = dt.datetime.now(dt.UTC)
    execute(prep, lambda ev: print(format_event(ev), flush=True))

    # The score as the app shows it: the run read back through the API, not recomputed here.
    app = create_app(
        repo,
        home=work / "home",
        user_skills_dir=work / "user-skills",
        workspace=Workspace(None),
        credentials=Credentials(env={}, home=work / "h"),
    )
    c = TestClient(app, base_url="http://localhost:7357")
    rid = c.get("/api/repos").json()[0]["id"]
    got = c.get(f"/api/experiments/{prep.eid}", params={"repo": rid}).json()
    tasks = []
    for s in prep.scenarios:
        row = {"id": s.id, "title": s.title, "instruction": s.instruction}
        for t in got["trials"]:
            if t["scenario_id"] == s.id:
                row.setdefault(t["arm"], []).append(
                    {
                        "outcome": t["outcome"],
                        "seconds": round(t["duration_s"] or 0, 1),
                        "detail": t.get("detail"),
                    }
                    | ({"tokens": t["tokens_in"] + t["tokens_out"]} if metric else {})
                )
        tasks.append(row)
    record = {
        "recorded": started.date().isoformat(),
        "model": {
            "file": a.model_file,
            "id": a.model,
            "server": a.server,
            "agent": "claude-code",
            "nudge": True,
            "timeout_factor": local_mod.L["timeout_factor"],
        },
        "skill": src.name,
        # The files the run was made on: the tutorial says if they changed since.
        "fingerprint": made_on,
        "repeats": a.repeats,
        "tasks": tasks,
        "summary": got["summary"],
        "ledger": got["ledger"],
        "rig": got["rig"],
    }
    if metric:
        record["metric"] = metric
        record["took_s"] = round((dt.datetime.now(dt.UTC) - started).total_seconds())
    out.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out}: Rig score {got['rig'].get('score')} ({got['rig'].get('label')})")


if __name__ == "__main__":
    main()
