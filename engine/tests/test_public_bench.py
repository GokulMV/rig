"""Public benchmarks: the registry cached and tolerant of being offline, a seeded sample, only
the sampled task folders fetched at the pinned commit, unsafe entries refused. No network:
a fake registry and a local bare git repo."""

import functools
import json
import os
import subprocess
from pathlib import Path

import pytest

from proving_ground import bench as bench_mod
from proving_ground import public_bench as pb

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]


def _git(*args, cwd):
    return subprocess.run(
        [*GIT, *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _task(root: Path, name: str, text: str, valid: bool = True):
    t = root / "datasets" / "demo" / name
    (t / "environment").mkdir(parents=True)
    (t / "task.toml").write_text('schema_version = "1.4"\n')
    (t / "instruction.md").write_text(text)
    (t / "environment" / "Dockerfile").write_text("FROM ubuntu:24.04\n")
    if valid:
        (t / "tests").mkdir()
        (t / "tests" / "test.sh").write_text("echo 1 > /logs/verifier/reward.txt\n")


@pytest.fixture
def repo(tmp_path: Path):
    """A bare repo of six tasks (one not a Harbor task), with two commits: the registry pins
    the first, so the second's change must not come down."""
    work = tmp_path / "work"
    work.mkdir()
    _git("init", "-q", "-b", "main", cwd=work)
    for i in range(5):
        _task(work, f"task-{i}", f"Do task {i}, first version.")
    _task(work, "no-tests", "Not a Harbor task.", valid=False)
    (work / "README.md").write_text("Not a task.\n")
    _git("add", "-A", cwd=work)
    _git("commit", "-qm", "one", cwd=work)
    first = _git("rev-parse", "HEAD", cwd=work)
    for i in range(5):
        (work / "datasets" / "demo" / f"task-{i}" / "instruction.md").write_text("Changed later.")
    _git("commit", "-qam", "two", cwd=work)
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(work), str(bare)], check=True)
    for k in ("uploadpack.allowFilter", "uploadpack.allowAnySHA1InWant"):
        _git("config", k, "true", cwd=bare)
    return f"file://{bare}", first


def _registry(url: str, commit: str, extra: list | None = None) -> list:
    names = [f"task-{i}" for i in range(5)] + ["no-tests"]
    tasks = [
        {"name": n, "git_url": url, "git_commit_id": commit, "path": f"datasets/demo/{n}"}
        for n in names
    ]
    return [
        {
            "name": "terminal-bench",
            "version": "2.0",
            "description": "Terminal tasks.",
            "tasks": tasks,
        },
        {
            "name": "swebench-verified",
            "version": "1.0",
            "description": "Repos.",
            "tasks": tasks[:2],
        },
        {
            "name": "featurebench-modal",
            "version": "1.0",
            "description": "Modal only.",
            "tasks": tasks,
        },
        {"name": "seta-env", "version": "1.0", "description": "RL training.", "tasks": tasks},
        *(extra or []),
    ]


class Fetch:
    def __init__(self, data):
        self.data, self.calls, self.offline = data, 0, False

    def __call__(self, url: str) -> bytes:
        self.calls += 1
        if self.offline:
            raise OSError("no network")
        return json.dumps(self.data).encode()


@pytest.fixture
def home(tmp_path: Path, monkeypatch):
    h = tmp_path / "home"
    monkeypatch.setattr(bench_mod, "IMPORTS", h / "imported-benches.json")
    return h


def test_the_registry_is_listed_cached_and_kept_when_offline(home, repo):
    url, first = repo
    f = Fetch(_registry(url, first))
    p = pb.PublicBenches(home, fetch=f, schemes=["https", "file"])
    got = p.listing()
    assert got["note"] is None and got["default_sample"] == pb.P["default_sample"]
    rows = {r["key"]: r for r in got["datasets"]}
    # Not agent tasks or not runnable here: left out.
    assert set(rows) == {"terminal-bench@2.0", "swebench-verified@1.0"}
    tb = rows["terminal-bench@2.0"]
    assert tb["tasks"] == 6 and tb["disciplines"] == ["devops", "development"]
    assert not tb["heavy"] and rows["swebench-verified@1.0"]["heavy"]
    assert (home / "public-registry.json").is_file()
    p.listing()
    assert f.calls == 1  # cached
    f.offline = True
    stale = p.listing(refresh=True)
    assert "showing the copy from" in stale["note"] and len(stale["datasets"]) == 2
    os.utime(home / "public-registry.json", (1, 1))  # a day old, and still offline
    calls = f.calls
    again = p.listing()
    assert f.calls == calls  # not retried yet: no wait on the network for every listing
    assert "showing the copy from 1970" in again["note"] and len(again["datasets"]) == 2
    empty = pb.PublicBenches(home / "fresh", fetch=f).listing()
    assert empty["datasets"] == [] and "no saved copy" in empty["note"]


def test_the_sample_is_deterministic_and_deduplicated():
    tasks = [
        {
            "name": f"t{i}",
            "git_url": "https://x/r.git",
            "git_commit_id": "a" * 40,
            "path": f"d/t{i}",
        }
        for i in range(30)
    ]
    d = {"name": "demo", "version": "1.0", "tasks": tasks + tasks[:5]}  # five listed twice
    one = pb.sample(d, 5, ["https"])
    assert one == pb.sample(d, 5, ["https"]) and len(one) == 5
    assert [t.path for t in one] == sorted(t.path for t in one)
    assert len({t.path for t in pb.sample(d, 100, ["https"])}) == 30  # all, once each
    other = {"name": "demo", "version": "2.0", "tasks": tasks}
    assert pb.sample(other, 5, ["https"]) != one  # seeded by benchmark and version


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("path", "datasets/../../etc"),
        ("path", "../outside"),
        ("path", "/etc/passwd"),
        ("path", "datasets/./x"),
        ("path", "datasets//x"),
        ("path", "datasets/*"),
        ("path", "datasets\\x"),
        ("path", "-x"),
        ("git_url", "http://example.com/r.git"),
        ("git_url", "ssh://git@example.com/r.git"),
        ("git_url", "--upload-pack=touch /tmp/x"),
        ("git_url", "https://user:pw@example.com/r.git"),
        ("git_commit_id", "abc123"),
    ],
)
def test_an_unsafe_entry_refuses_the_whole_benchmark(home, field, value):
    good = {
        "name": "ok",
        "git_url": "https://example.com/r.git",
        "git_commit_id": "a" * 40,
        "path": "d/ok",
    }
    bad = {**good, "name": "bad", field: value}
    reg = [{"name": "terminal-bench", "version": "2.0", "tasks": [good, bad]}]
    calls = []
    p = pb.PublicBenches(home, fetch=Fetch(reg), download=lambda *a: calls.append(a) or {})
    with pytest.raises(pb.PublicBenchError, match="Refused"):
        p.add("terminal-bench@2.0", 2)
    assert calls == []  # git never ran
    assert not (home / "public-benches" / "terminal-bench@2.0").exists()


def test_head_means_unpinned():
    t = pb.checked(
        {"git_url": "https://x/r.git", "git_commit_id": "HEAD", "path": "a/b"}, ["https"]
    )
    assert t.commit is None and t.folder == "b"


def test_only_the_sampled_folders_come_down_at_the_pinned_commit(home, repo):
    url, first = repo
    p = pb.PublicBenches(home, fetch=Fetch(_registry(url, first)), schemes=["https", "file"])
    picked = pb.sample(p.dataset("terminal-bench@2.0"), 3, p.schemes)
    b, dropped = p.add("terminal-bench@2.0", 3)
    folder = home / "public-benches" / "terminal-bench@2.0"
    on_disk = sorted(x.name for x in folder.iterdir() if x.is_dir())
    valid = [t.folder for t in picked if t.folder != "no-tests"]
    assert on_disk == valid  # the sample, nothing else from the repo
    assert dropped == (["no-tests"] if "no-tests" in {t.folder for t in picked} else [])
    assert not (folder / "README.md").exists()
    for name in valid:  # the pinned commit, not the later one
        assert (folder / name / "instruction.md").read_text().endswith("first version.")
    # A normal imported bench, marked public, with where it came from.
    assert b.id == "imp-terminal-bench-2-0" and b.name == "terminal-bench 2.0"
    assert b.tasks == folder.resolve() and len(b.scenarios) == len(valid)
    assert b.public["total"] == 6 and b.public["key"] == "terminal-bench@2.0"
    assert all(t["commit"] == first and t["pinned"] for t in b.public["tasks"])
    assert bench_mod.bench(b.id).disciplines == ["devops", "development"]
    assert not list((home / "public-benches").glob(".staging-*"))
    # The same size again gives the same tasks.
    b2, _ = p.add("terminal-bench@2.0", 3)
    assert [s["title"] for s in b2.scenarios] == [s["title"] for s in b.scenarios]


def test_sample_size_is_bounded(home, repo):
    url, first = repo
    p = pb.PublicBenches(home, fetch=Fetch(_registry(url, first)), schemes=["https", "file"])
    for n in (0, pb.P["max_sample"] + 1):
        with pytest.raises(pb.PublicBenchError, match="A sample is"):
            p.add("terminal-bench@2.0", n)
    with pytest.raises(KeyError):
        p.add("seta-env@1.0", 2)  # excluded: not offered, not addable


def test_api_lists_adds_and_removes_a_public_benchmark(tmp_path: Path, repo, monkeypatch):
    from fastapi.testclient import TestClient
    from test_api_workspace import BASE, ORIGIN
    from test_catalog import FakeGitHub

    from proving_ground.agents import Credentials
    from proving_ground.api.app import create_app
    from proving_ground.workspace import Workspace

    url, first = repo
    home = tmp_path / "home"
    monkeypatch.setattr(bench_mod, "IMPORTS", None)
    pub = pb.PublicBenches(home, fetch=Fetch(_registry(url, first)), schemes=["https", "file"])
    c = TestClient(
        create_app(
            workspace=Workspace(tmp_path / "ws.json"),
            credentials=Credentials(env={"ANTHROPIC_API_KEY": "k"}, home=tmp_path / "h"),
            github=FakeGitHub(),
            home=home,
            user_skills_dir=tmp_path / "none",
            web_dist=tmp_path / "nodist",
            host_login=lambda: None,
            public_benches=pub,
        ),
        base_url=BASE,
    )
    rows = c.get("/api/lab/public-benches").json()["datasets"]
    assert [r["key"] for r in rows] == ["terminal-bench@2.0", "swebench-verified@1.0"]
    assert (
        c.post(
            "/api/lab/public-benches", json={"key": "nope@1", "sample": 2}, headers=ORIGIN
        ).status_code
        == 404
    )
    r = c.post(
        "/api/lab/public-benches", json={"key": "terminal-bench@2.0", "sample": 2}, headers=ORIGIN
    )
    assert r.status_code == 200, r.text
    got = r.json()["bench"]
    assert (
        got["imported"]
        and got["public"]["total"] == 6
        and got["public"]["key"] == "terminal-bench@2.0"
    )
    assert "sampled from its 6" in got["summary"]
    listed = c.get("/api/lab/public-benches").json()["datasets"][0]
    assert listed["added"] == got["id"]
    assert any(b["id"] == got["id"] for b in c.get("/api/lab/benches").json())
    folder = home / "public-benches" / "terminal-bench@2.0"
    assert folder.is_dir()
    assert c.delete(f"/api/lab/benches/{got['id']}", headers=ORIGIN).status_code == 200
    assert not folder.exists()
    assert all(b["id"] != got["id"] for b in c.get("/api/lab/benches").json())


# ---------- Hugging Face: only the sampled folders, over HTTP, at the commit ----------

HF_URL = "https://huggingface.co/datasets/harborframework/harbor-datasets"
PIN, LATER = "1" * 40, "2" * 40


class Item:
    def __init__(self, path, size=None):
        self.path = path
        if size is not None:
            self.size = size


class FakeHf:
    """A Hub with one dataset repo at two commits. Records every call; no network."""

    def __init__(self):
        self.repos = {PIN: self._files("first"), LATER: self._files("later")}
        self.listed, self.fetched, self.extra, self.lie = [], [], {}, {}

    @staticmethod
    def _files(word):
        out = {"README.md": b"not a task\n"}
        for i in range(6):
            base = f"datasets/demo/hf-{i}"
            out[f"{base}/task.toml"] = b'schema_version = "1.4"\n'
            out[f"{base}/instruction.md"] = f"Task {i}, {word} version.".encode()
            out[f"{base}/environment/Dockerfile"] = b"FROM ubuntu:24.04\n"
            out[f"{base}/environment/data.sqlite"] = b"\0" * 1000  # an LFS file on the Hub
            out[f"{base}/environment/run.sh"] = b"#!/bin/sh\necho hi\n"
            out[f"{base}/tests/test.sh"] = b"#!/bin/bash\necho 1 > /logs/verifier/reward.txt\n"
        return out

    def repo_info(self, repo_id, repo_type=None, **k):
        assert (repo_id, repo_type) == ("harborframework/harbor-datasets", "dataset")
        return type("Info", (), {"sha": LATER})()

    def list_repo_tree(self, repo_id, path_in_repo, recursive, repo_type, revision, **k):
        assert recursive and repo_type == "dataset"
        self.listed.append((path_in_repo, revision))
        files = {**self.repos[revision], **self.extra}
        yield Item(path_in_repo)  # a folder entry
        for p, b in sorted(files.items()):
            if p.startswith(path_in_repo + "/") or p in self.extra:
                yield Item(p, len(b))

    def hf_hub_download(self, repo_id, filename, repo_type, revision, local_dir, **k):
        self.fetched.append((filename, revision))
        data = self.lie.get(filename, self.repos[revision].get(filename, b""))
        out = Path(local_dir) / filename
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        return str(out)


def _hf_registry(commit=PIN, url=HF_URL):
    tasks = [
        {
            "name": f"hf-{i}",
            "git_url": url,
            "git_commit_id": commit,
            "path": f"datasets/demo/hf-{i}",
        }
        for i in range(6)
    ]
    return [{"name": "spider2-dbt", "version": "1.0", "description": "dbt.", "tasks": tasks}]


def _hf(home, hub, commit=PIN, url=HF_URL, git=None):
    dl = functools.partial(pb.download_tasks, hf_api=hub, git=git)
    return pb.PublicBenches(home, fetch=Fetch(_hf_registry(commit, url)), download=dl)


def test_hugging_face_brings_only_the_sampled_folders_at_the_pinned_commit(home):
    hub = FakeHf()
    p = _hf(home, hub)
    row = p.listing()["datasets"][0]
    assert "whole_repo" not in row and row["disciplines"] == ["data"]
    picked = [t.path for t in pb.sample(p.dataset("spider2-dbt@1.0"), 3, p.schemes)]
    b, dropped = p.add("spider2-dbt@1.0", 3)
    assert dropped == []
    assert sorted(x for x, _ in hub.listed) == picked and {r for _, r in hub.listed} == {PIN}
    # Every file of the sampled folders, and nothing else (no README, no other task).
    assert sorted(f for f, _ in hub.fetched) == sorted(
        f for f in hub.repos[PIN] if any(f.startswith(x + "/") for x in picked)
    )
    assert {r for _, r in hub.fetched} == {PIN}
    folder = home / "public-benches" / "spider2-dbt@1.0"
    assert sorted(x.name for x in folder.iterdir() if x.is_dir()) == [Path(x).name for x in picked]
    assert not (folder / ".hf").exists() and not list(folder.rglob(".cache"))
    t = folder / Path(picked[0]).name
    assert (t / "instruction.md").read_text().endswith("first version.")
    assert (t / "environment" / "data.sqlite").stat().st_size == 1000
    for f in ("tests/test.sh", "environment/run.sh"):  # a #! line: executable, as git keeps it
        assert os.access(t / f, os.X_OK)
    assert not os.access(t / "instruction.md", os.X_OK)
    assert len(b.scenarios) == 3 and b.public["source"] == HF_URL
    assert all(x["commit"] == PIN and x["pinned"] for x in b.public["tasks"])
    assert not list((home / "public-benches").glob(".staging-*"))


def test_hugging_face_head_is_resolved_once_and_recorded_unpinned(home):
    hub = FakeHf()
    b, _ = _hf(home, hub, commit="HEAD").add("spider2-dbt@1.0", 2)
    assert {r for _, r in hub.listed} == {LATER} and {r for _, r in hub.fetched} == {LATER}
    assert all(x["commit"] == LATER and not x["pinned"] for x in b.public["tasks"])


@pytest.mark.parametrize(
    ("value", "budget"), [(2000, "download_max_bytes"), (5, "download_max_files")]
)
def test_a_sample_over_the_budget_is_refused_before_anything_downloads(
    home, monkeypatch, value, budget
):
    monkeypatch.setitem(pb.P, budget, value)
    hub = FakeHf()
    with pytest.raises(pb.PublicBenchError, match="Pick a smaller sample") as e:
        _hf(home, hub).add("spider2-dbt@1.0", 2)
    assert ("2,000 bytes" if value == 2000 else "over the 5 one download") in str(e.value)
    assert hub.fetched == []
    assert not list((home / "public-benches").iterdir())  # no folder, no staging left


@pytest.mark.parametrize(
    "bad", ["datasets/demo/hf-0/../../../etc/x", "datasets/other/x", "datasets/demo/hf-0//x"]
)
def test_a_listed_file_outside_its_task_is_refused(home, bad):
    hub = FakeHf()
    hub.extra = {bad: b"x"}
    with pytest.raises(pb.PublicBenchError, match="Refused file"):
        _hf(home, hub).add("spider2-dbt@1.0", 2)
    assert hub.fetched == []


def test_a_file_that_comes_down_at_another_size_refuses_the_sample(home):
    hub = FakeHf()
    hub.lie = {f"datasets/demo/hf-{i}/task.toml": b"short" for i in range(6)}
    with pytest.raises(pb.PublicBenchError, match="different size"):
        _hf(home, hub).add("spider2-dbt@1.0", 2)
    assert not list((home / "public-benches").iterdir())


def test_hugging_face_stops_at_the_time_budget(home, monkeypatch):
    monkeypatch.setitem(pb.P, "download_timeout_s", 0)
    hub = FakeHf()
    with pytest.raises(pb.PublicBenchError, match="took longer than 0 s"):
        _hf(home, hub).add("spider2-dbt@1.0", 2)
    assert hub.fetched == [] and not list((home / "public-benches").iterdir())


@pytest.mark.parametrize(
    "url",
    [
        "https://huggingface.co/datasets/harborframework",
        "https://huggingface.co/datasets/a/b/tree/main",
        "https://huggingface.co/datasets/a/b?x=1",
        "https://huggingface.co/datasets/a/../b",
        "https://huggingface.co/",
        "https://huggingface.co/spaces/x",
    ],
)
def test_a_hugging_face_url_must_name_one_repo(home, url):
    hub = FakeHf()
    with pytest.raises(pb.PublicBenchError, match="Refused repository"):
        _hf(home, hub, url=url).add("spider2-dbt@1.0", 2)
    assert hub.listed == []


def test_hugging_face_repo_ids():
    assert pb.hf_repo(HF_URL + ".git") == ("harborframework/harbor-datasets", "dataset")
    assert pb.hf_repo("https://hf.co/spaces/a/b") == ("a/b", "space")
    assert pb.hf_repo("https://huggingface.co/a/b") == ("a/b", "model")
    assert pb.hf_repo("https://github.com/a/b.git") is None


def test_other_hosts_still_go_through_git(home, monkeypatch):
    mixed = [
        {
            "name": "g",
            "git_url": "https://github.com/x/r.git",
            "git_commit_id": "a" * 40,
            "path": "d/g",
        },
        {"name": "hf-0", "git_url": HF_URL, "git_commit_id": PIN, "path": "datasets/demo/hf-0"},
    ]
    seen = []

    def git(tasks, dest, left):
        seen.append(([t.name for t in tasks], left))
        _task(dest.parent / "g-src", "g", "From git.")
        (dest / "g").parent.mkdir(parents=True, exist_ok=True)
        (dest.parent / "g-src" / "datasets" / "demo" / "g").replace(dest / "g")
        return {"g": "a" * 40}

    hub = FakeHf()
    reg = [{"name": "mix", "version": "1", "tasks": mixed}]
    dl = functools.partial(pb.download_tasks, hf_api=hub, git=git)
    b, _ = pb.PublicBenches(home, fetch=Fetch(reg), download=dl).add("mix@1", 2)
    assert seen[0][0] == ["g"] and 0 < seen[0][1] <= pb.P["download_timeout_s"]
    assert [x for x, _ in hub.listed] == ["datasets/demo/hf-0"]
    assert sorted(t["name"] for t in b.public["tasks"]) == ["g", "hf-0"]
    assert {t["name"]: t["commit"] for t in b.public["tasks"]} == {"g": "a" * 40, "hf-0": PIN}
    assert len(b.scenarios) == 2
