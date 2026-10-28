"""Measure a code change before and after: the repo's tasks on two snapshots of its code.

A split or merge (improve-architecture) changes the app, not the agent, so it can't be added to
one arm the way a skill is. Instead the base commit is the "without" arm and the after side (a
commit or branch, or the uncommitted working tree) the "with" arm. Both come from git: a commit
is exported with `git archive`, and the working tree is first written as a tree object from a
scratch index (the repo's own index, HEAD and files are never changed). Rules and words: the
measurability skill (`before_after`).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from proving_ground import skills
from proving_ground.files import PG_DIR
from proving_ground.models import Treatment, TreatmentKind

V = skills.value("measurability", "before_after")
NOT_PG = f":(exclude){PG_DIR}"  # .proving-ground/ is Rig's, never part of either arm


class BeforeAfterError(ValueError):
    """A before/after change that can't be measured. The message is meant for the user."""


@dataclass(frozen=True)
class Side:
    """One arm's code: a commit (sha) or the working tree (sha None), as a git tree."""

    tree: str
    label: str  # "split-auth (def5678)", "abc1234", "your uncommitted changes"
    sha: str | None = None
    ref: str | None = None  # as asked for: "HEAD", a branch, a sha
    subject: str = ""

    def json(self) -> dict:
        return {
            "sha": self.sha,
            "short": self.sha[:7] if self.sha else None,
            "ref": self.ref,
            "label": self.label,
            "subject": self.subject,
            "working_tree": self.sha is None,
        }


@dataclass(frozen=True)
class Change:
    base: Side
    after: Side
    files: tuple[str, ...]  # the paths that differ, .proving-ground/ aside

    @property
    def name(self) -> str:
        return V["name"].format(base=self.base.label, after=self.after.label)

    def treatment(self, root: Path) -> Treatment:
        """The run's treatment: the repo itself, hashed on both trees, so a resumed run is the
        same change or refused (service.prepare_experiment)."""
        h = hashlib.sha256(f"{self.base.tree}:{self.after.tree}".encode()).hexdigest()
        return Treatment(
            kind=TreatmentKind.BEFORE_AFTER,
            name=self.name,
            path=str(root.resolve()),
            content_hash=h,
        )

    def meta(self) -> dict:
        """What the run's meta.json keeps, so Results says "before vs after"."""
        return {
            "base": self.base.json(),
            "after": self.after.json(),
            "files": list(self.files[:50]),
            "n_files": len(self.files),
        }

    def json(self) -> dict:
        n = len(self.files)
        return self.meta() | {
            "name": self.name,
            "same": n == 0,
            "says": V["same"].format(after=self.after.label, base=self.base.label)
            if n == 0
            else V["compare"].format(base=self.base.label, after=self.after.label),
            "files_text": V["file"] if n == 1 else V["files"].format(n=n),
        }


def _git(root: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False, env=env
    )


def is_git(root: Path) -> bool:
    return _git(root, "rev-parse", "--verify", "--quiet", "HEAD").returncode == 0


def _commit(root: Path, ref: str) -> str:
    ref = ref.strip()
    # Never an option to git; a ref is a name or a sha.
    if not ref or ref.startswith("-") or any(c.isspace() for c in ref):
        raise BeforeAfterError(V["unknown_ref"].format(ref=ref or "(empty)"))
    got = _git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    if got.returncode != 0:
        raise BeforeAfterError(V["unknown_ref"].format(ref=ref))
    return got.stdout.strip()


def _subject(root: Path, sha: str) -> str:
    return _git(root, "log", "-1", "--format=%s", sha).stdout.strip()


def _branches(root: Path) -> set[str]:
    out = _git(root, "for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/tags")
    return set(out.stdout.split())


def _side(root: Path, ref: str) -> Side:
    sha = _commit(root, ref)
    tree = _git(root, "rev-parse", f"{sha}^{{tree}}").stdout.strip()
    named = ref.strip() in _branches(root) or ref.strip() == "HEAD"
    label = f"{ref.strip()} ({sha[:7]})" if named else sha[:7]
    return Side(tree=tree, label=label, sha=sha, ref=ref.strip(), subject=_subject(root, sha))


def working_tree(root: Path) -> str:
    """The working tree as a git tree object: tracked and untracked files git doesn't ignore,
    .proving-ground/ left out. Written through a scratch copy of the index, so the repo's own
    index, HEAD and files stay as they are (only new objects are added to its object store)."""
    index = _git(root, "rev-parse", "--git-path", "index").stdout.strip()
    index_path = Path(index) if os.path.isabs(index) else root / index
    with tempfile.TemporaryDirectory(prefix="rig-index-") as tmp:
        scratch = Path(tmp) / "index"
        if index_path.is_file():
            shutil.copyfile(index_path, scratch)  # its stat cache: unchanged files aren't re-read
        env = os.environ | {"GIT_INDEX_FILE": str(scratch)}
        added = _git(root, "add", "-A", "--", ".", NOT_PG, env=env)
        if added.returncode != 0:
            raise BeforeAfterError(f"git couldn't read the working tree: {added.stderr.strip()}")
        tree = _git(root, "write-tree", env=env)
        if tree.returncode != 0:
            raise BeforeAfterError(f"git couldn't read the working tree: {tree.stderr.strip()}")
        return tree.stdout.strip()


def _change(root: Path, base: str, after: str | None) -> Change:
    if not is_git(root):
        raise BeforeAfterError(V["not_git"])
    b = _side(root, base or "HEAD")
    if after is None or not after.strip():
        a = Side(tree=working_tree(root), label=V["working_tree"])
    else:
        a = _side(root, after)
    diff = _git(root, "diff", "--name-only", "--relative", b.tree, a.tree, "--", ".", NOT_PG)
    return Change(b, a, tuple(f for f in diff.stdout.splitlines() if f))


def resolve(root: Path, base: str = "HEAD", after: str | None = None) -> Change:
    """The change from `base` (a commit or branch) to `after` (one too, or None: the uncommitted
    working tree). Raises BeforeAfterError when the repo has no commit, a ref is unknown, or the
    two have the same code (`same`: it would measure nothing)."""
    change = _change(root.resolve(), base, after)
    if not change.files:
        raise BeforeAfterError(V["same"].format(after=change.after.label, base=change.base.label))
    return change


def compare(root: Path, base: str = "HEAD", after: str | None = None) -> dict:
    """What a before/after run would compare, for Measure: both sides, the files that differ,
    and whether it would measure nothing (`same`, with the line why). Raises BeforeAfterError
    for a repo with no commit or an unknown ref."""
    return _change(root.resolve(), base, after).json()


def refs(root: Path, commits: int = 15, branches: int = 30) -> dict:
    """What Measure offers to pick from: HEAD, the branches (newest first), recent commits, and
    whether there are uncommitted changes. {"git": False, "says": ...} for a repo with no commit."""
    root = root.resolve()
    if not is_git(root):
        return {"git": False, "says": V["not_git"]}
    head = _git(root, "rev-parse", "HEAD").stdout.strip()
    current = _git(root, "symbolic-ref", "--short", "-q", "HEAD").stdout.strip() or None
    got = _git(
        root,
        "for-each-ref",
        "--sort=-committerdate",
        f"--count={branches}",
        "--format=%(refname:short)%00%(objectname)%00%(subject)",
        "refs/heads",
    )
    heads = []
    for line in got.stdout.splitlines():
        name, sha, subject = (line.split("\0") + ["", ""])[:3]
        heads.append(
            {
                "name": name,
                "sha": sha,
                "short": sha[:7],
                "subject": subject,
                "current": name == current,
            }
        )
    log = _git(root, "log", f"-n{commits}", "--format=%H%x00%s", "HEAD")
    recent = []
    for line in log.stdout.splitlines():
        sha, subject = (line.split("\0") + [""])[:2]
        recent.append({"sha": sha, "short": sha[:7], "subject": subject})
    status = _git(root, "status", "--porcelain", "--", ".", NOT_PG)
    return {
        "git": True,
        "head": {
            "sha": head,
            "short": head[:7],
            "branch": current,
            "subject": _subject(root, head),
        },
        "branches": heads,
        "commits": recent,
        "dirty": bool(status.stdout.strip()),
    }
