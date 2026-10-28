import json
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_catalog import FakeGitHub

from proving_ground.agents import Credentials
from proving_ground.api.app import create_app
from proving_ground.remotes import RemoteError, Remotes, parse_remote, redact
from proving_ground.workspace import Workspace

BASE = "http://127.0.0.1:7357"
ORIGIN = {"origin": BASE}
TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2"


@pytest.mark.parametrize(
    "text,host,owner,name,provider",
    [
        ("https://github.com/acme/shop", "github.com", "acme", "shop", "github"),
        ("https://github.com/acme/shop.git", "github.com", "acme", "shop", "github"),
        ("https://github.com/acme/shop/tree/main/src", "github.com", "acme", "shop", "github"),
        ("git@github.com:acme/shop.git", "github.com", "acme", "shop", "github"),
        ("ssh://git@github.com/acme/shop.git", "github.com", "acme", "shop", "github"),
        ("acme/shop", "github.com", "acme", "shop", "github"),
        ("github.com/acme/shop", "github.com", "acme", "shop", "github"),
        ("https://gitlab.com/grp/sub/deep/app", "gitlab.com", "grp/sub/deep", "app", "gitlab"),
        ("https://gitlab.com/grp/app/-/issues/3", "gitlab.com", "grp", "app", "gitlab"),
        ("git@gitlab.com:grp/sub/app.git", "gitlab.com", "grp/sub", "app", "gitlab"),
        ("https://git.corp.example/team/app.git", "git.corp.example", "team", "app", "gitlab"),
        ("https://me:secret@github.com/acme/shop", "github.com", "acme", "shop", "github"),
    ],
)
def test_parse(text, host, owner, name, provider):
    r = parse_remote(text)
    assert (r.host, r.owner, r.name, r.provider) == (host, owner, name, provider)
    assert "secret" not in r.url and "@" not in r.url


@pytest.mark.parametrize(
    "text",
    ["", "shop", "https://github.com/acme", "https://github.com/../x", "a/..", "ftp://x/a/b"],
)
def test_parse_rejects(text):
    with pytest.raises(RemoteError):
        parse_remote(text)


def test_redact():
    assert TOKEN not in redact(f"fatal: {TOKEN} bad", None)
    assert "hunter2" not in redact("https://bob:hunter2@host/x", "hunter2")
    assert "customtoken" not in redact("oops customtoken", "customtoken")


class Fake:
    """Stands in for subprocess: records every call; understands gh, glab and git."""

    def __init__(self, gh_ok=True, glab_ok=False, clone_fail=None):
        self.calls: list[tuple[list[str], dict]] = []
        self.gh_ok, self.glab_ok, self.clone_fail = gh_ok, glab_ok, clone_fail
        self.upstream: Path | None = None

    def __call__(self, cmd, *, env=None, cwd=None, timeout=0):
        self.calls.append((list(cmd), dict(env or {})))

        def out(stdout="", stderr="", code=0):
            return subprocess.CompletedProcess(cmd, code, stdout, stderr)

        if cmd[0] == "gh":
            if cmd[1:3] == ["auth", "status"]:
                if not self.gh_ok:
                    return out(stderr="You are not logged into any GitHub hosts.", code=1)
                return out(
                    stdout="github.com\n  ✓ Logged in to github.com account octocat (keyring)\n"
                )
            if cmd[1:3] == ["auth", "token"]:
                return out(stdout=TOKEN + "\n")
            if cmd[1:3] == ["repo", "list"]:
                return out(
                    stdout=json.dumps(
                        [
                            {
                                "name": "shop",
                                "owner": {"login": "octocat"},
                                "description": "A shop",
                                "isPrivate": True,
                                "updatedAt": "2026-10-01T00:00:00Z",
                            },
                            {
                                "name": "blog",
                                "owner": {"login": "octocat"},
                                "description": None,
                                "isPrivate": False,
                                "updatedAt": "2026-09-01T00:00:00Z",
                            },
                        ]
                    )
                )
        if cmd[0] == "glab":
            if not self.glab_ok:
                return out(stderr="not logged in", code=1)
            if cmd[1:3] == ["auth", "status"]:
                return out(stderr="gitlab.com\n  ✓ Logged in to gitlab.com as tanuki (config)\n")
            return out(stdout="glpat-" + "x" * 20 + "\n")
        if cmd[0] == "git":
            args = cmd[cmd.index("clone") :] if "clone" in cmd else None
            if args:
                if self.clone_fail:
                    (Path(args[-1])).mkdir(parents=True)
                    return out(stderr=self.clone_fail, code=128)
                dest = Path(args[-1])
                dest.mkdir(parents=True)
                (dest / "README.md").write_text("hello\n")
                (dest / "pyproject.toml").write_text("[project]\nname='x'\n")
                subprocess.run(["git", "init", "-q", str(dest)], check=True)
                (dest / ".git" / "shallow").write_text("x\n")
                return out()
            if "pull" in cmd:
                return out()
            if "rev-parse" in cmd:
                return out(stdout="abc1234\n")
        raise AssertionError(f"unexpected {cmd}")


def hub(tmp_path, fake=None, http=None, which=lambda c: f"/bin/{c}"):
    return Remotes(tmp_path / "home", run=fake or Fake(), http=http, which=which)


def clone_calls(fake):
    return [(c, e) for c, e in fake.calls if c[0] == "git" and "clone" in c]


def test_clone_keeps_token_out_of_argv_and_url(tmp_path):
    fake = Fake()
    r = hub(tmp_path, fake)
    remote = parse_remote("acme/shop")
    dest = r.dest_for(remote)
    assert dest == tmp_path / "home" / "repos" / "github.com" / "acme" / "shop"
    r.clone(remote.url, dest, TOKEN)
    [(cmd, env)] = clone_calls(fake)
    assert TOKEN not in " ".join(cmd)
    assert "--depth" in cmd and "1" in cmd
    assert env["PG_GIT_TOKEN"] == TOKEN
    assert cmd[-2] == "https://github.com/acme/shop"
    # The token is in no other call, and the askpass script is gone, holding no secret.
    assert all(TOKEN not in json.dumps(e) for c, e in fake.calls if c is not cmd)
    assert not Path(env["GIT_ASKPASS"]).exists()


def test_clone_without_token_sets_no_secret(tmp_path):
    fake = Fake()
    r = hub(tmp_path, fake)
    remote = parse_remote("acme/shop")
    r.clone(remote.url, r.dest_for(remote))
    [(cmd, env)] = clone_calls(fake)
    assert "PG_GIT_TOKEN" not in env and "GIT_ASKPASS" not in env
    assert env["GIT_TERMINAL_PROMPT"] == "0"


def test_clone_error_is_redacted_and_cleaned(tmp_path):
    fake = Fake(clone_fail=f"fatal: Authentication failed for 'https://x:{TOKEN}@github.com/a/b'")
    r = hub(tmp_path, fake)
    remote = parse_remote("acme/shop")
    with pytest.raises(RemoteError) as e:
        r.clone(remote.url, r.dest_for(remote), TOKEN)
    assert TOKEN not in str(e.value)
    assert "sign in" in str(e.value)
    assert not r.dest_for(remote).exists()


def test_status_with_cli_login(tmp_path):
    r = hub(tmp_path, Fake(gh_ok=True, glab_ok=False))
    gh, gl = r.status()
    assert gh["signed_in"] and gh["via"] == "cli" and gh["cli_account"] == "octocat"
    assert not gl["signed_in"] and gl["installed"]
    assert TOKEN not in json.dumps(r.status())


def test_status_cli_missing_and_typed_token(tmp_path):
    r = hub(tmp_path, Fake(), which=lambda c: None)
    r.tokens.set("gitlab", "glpat-secretsecret")
    gh, gl = r.status()
    assert not gh["installed"] and not gh["signed_in"]
    assert gl["via"] == "token" and "secretsecret" not in json.dumps(r.status())


def test_list_mine_gh_and_rest(tmp_path):
    r = hub(tmp_path)
    rows = r.list_mine("github")
    assert [x["full_name"] for x in rows] == ["octocat/shop", "octocat/blog"]
    assert rows[0]["private"] and rows[1]["description"] == ""
    assert [x["name"] for x in r.list_mine("github", "BLO")] == ["blog"]

    class Http:
        def get(self, url, headers=None):
            assert headers["PRIVATE-TOKEN"] == "glpat-secretsecret"
            return type(
                "R",
                (),
                {
                    "status_code": 200,
                    "json": lambda s: [
                        {
                            "path_with_namespace": "grp/sub/app",
                            "description": "d",
                            "visibility": "private",
                            "last_activity_at": "2026-10-02",
                        }
                    ],
                },
            )()

    g = hub(tmp_path, http=Http())
    g.tokens.set("gitlab", "glpat-secretsecret")
    [row] = g.list_mine("gitlab")
    assert row["owner"] == "grp/sub" and row["url"] == "https://gitlab.com/grp/sub/app"


def test_list_mine_needs_sign_in(tmp_path):
    with pytest.raises(RemoteError, match="Sign in"):
        hub(tmp_path, Fake(glab_ok=False)).list_mine("gitlab")


# ---------- API ----------


class FakeHttp:
    """The provider's user endpoint: GitHub knows the token, GitLab refuses it."""

    def get(self, url, headers=None):
        ok = "github" in url
        return type(
            "R", (), {"status_code": 200 if ok else 401, "json": lambda s: {"login": "me"}}
        )()


@pytest.fixture
def api(tmp_path):
    fake = Fake()
    home = tmp_path / "home"
    r = Remotes(home, run=fake, http=FakeHttp(), which=lambda c: f"/bin/{c}")
    app = create_app(
        workspace=Workspace(home / "workspace.json"),
        credentials=Credentials(env={}, home=tmp_path / "u"),
        github=FakeGitHub(),
        home=home,
        user_skills_dir=tmp_path / "none",
        remotes=r,
    )
    return TestClient(app, base_url=BASE, headers=ORIGIN), fake, home


def wait(c, job):
    for _ in range(100):
        j = c.get(f"/api/repos/remote/{job}").json()
        if j["state"] != "running":
            return j
        time.sleep(0.05)
    raise AssertionError("clone job never finished")


def test_api_clone_end_to_end_and_pull(api):
    c, fake, home = api
    assert c.get("/api/remotes/status").json()[0]["cli_account"] == "octocat"
    job = c.post("/api/repos/remote", json={"url": "https://github.com/acme/shop.git"}).json()[
        "job"
    ]
    j = wait(c, job)
    assert j["state"] == "done", j
    repo = j["repo"]
    assert repo["remote"] == "https://github.com/acme/shop" and repo["provider"] == "github"
    assert repo["root"] == str((home / "repos/github.com/acme/shop").resolve())
    assert c.get("/api/repos").json()[0]["id"] == repo["id"]
    # The signed-in gh login supplied the token, but only through the clone call's env.
    [(cmd, env)] = clone_calls(fake)
    assert env["PG_GIT_TOKEN"] == TOKEN and TOKEN not in " ".join(cmd)
    assert TOKEN not in (home / "workspace.json").read_text()
    # The clone is a real project: intake ran.
    assert c.get("/api/project", params={"repo": repo["id"]}).status_code == 200

    p = c.post(f"/api/repos/{repo['id']}/pull").json()
    assert p["head"] == "abc1234"
    pull = next(x for x in fake.calls if "pull" in x[0])
    assert "--depth" in pull[0] and pull[1]["PG_GIT_TOKEN"] == TOKEN

    # Attaching the same address again reuses the clone.
    again = wait(c, c.post("/api/repos/remote", json={"url": "acme/shop"}).json()["job"])
    assert again["repo"]["id"] == repo["id"] and len(clone_calls(fake)) == 1


def test_api_clone_failure_has_no_token(api):
    c, fake, _ = api
    fake.clone_fail = f"fatal: could not read Username {TOKEN}"
    j = wait(c, c.post("/api/repos/remote", json={"url": "acme/shop"}).json()["job"])
    assert j["state"] == "error" and TOKEN not in json.dumps(j) and j["error"]
    assert c.get("/api/repos").json() == []


def test_api_bad_url_pull_local_and_unknown(api, tmp_path):
    c, _, _ = api
    assert c.post("/api/repos/remote", json={"url": "nonsense"}).status_code == 422
    assert c.get("/api/repos/remote/nope").status_code == 404
    local = tmp_path / "loc"
    local.mkdir()
    rid = c.post("/api/repos", json={"path": str(local)}).json()["id"]
    assert c.post(f"/api/repos/{rid}/pull").status_code == 422
    assert c.get("/api/remotes/bitbucket/repos").status_code == 404


def test_api_token_roundtrip_never_returned(api):
    c, fake, _ = api
    fake.gh_ok = False
    assert c.get("/api/remotes/status").json()[0]["via"] is None
    r = c.put("/api/remotes/github/token", json={"value": f" {TOKEN} "})
    assert r.status_code == 200 and r.json()["account"] == "me" and TOKEN not in r.text
    body = c.get("/api/remotes/status").json()
    assert body[0]["via"] == "token" and TOKEN not in json.dumps(body)
    assert c.delete("/api/remotes/github/token").status_code == 200
    assert c.get("/api/remotes/status").json()[0]["via"] is None


def test_api_rejected_token_is_not_kept(api):
    c, fake, _ = api
    fake.gh_ok = False
    r = c.put("/api/remotes/gitlab/token", json={"value": "bad-token"})
    assert r.status_code == 422
    assert c.get("/api/remotes/status").json()[1]["via"] is None
