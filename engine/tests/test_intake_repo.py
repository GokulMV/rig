import json
from pathlib import Path

from proving_ground.intake.repo import scan_repo, scan_to_text


def make(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


def test_detects_languages_stack_and_agent_setup(tmp_path: Path):
    make(
        tmp_path,
        {
            "package.json": json.dumps(
                {"dependencies": {"next": "15", "pg": "8"}, "devDependencies": {"vitest": "2"}}
            ),
            "src/app.tsx": "x",
            "src/util.ts": "x",
            "scripts/seed.py": "x",
            "pyproject.toml": '[project]\ndependencies = ["fastapi>=0.110", "anthropic"]\n',
            "Dockerfile": "FROM node:22",
            ".github/workflows/ci.yml": "on: push",
            "CLAUDE.md": "# rules",
            ".mcp.json": "{}",
            ".claude/skills/release-notes/SKILL.md": "---\nname: release-notes\ndescription: Writes release notes\n---\nBody\n",
            "node_modules/react/index.js": "ignored",
            ".git/config": "ignored",
        },
    )
    scan = scan_repo(tmp_path)
    assert scan.languages == {"TypeScript": 2, "Python": 1}
    assert {
        "Next.js",
        "Postgres",
        "Vitest",
        "FastAPI",
        "Anthropic SDK",
        "Docker",
        "GitHub Actions",
    } <= set(scan.stack)
    assert scan.agent_setup == ["CLAUDE.md", "MCP servers", "Skills"]
    [skill] = scan.skills
    assert (skill.name, skill.description) == ("release-notes", "Writes release notes")
    assert skill.tokens_est > 0
    assert not any("node_modules" in f or ".git/" in f for f in scan.key_files)
    assert scan.truncated is False


def test_skill_without_frontmatter_uses_folder_name(tmp_path: Path):
    make(tmp_path, {".claude/skills/lint-fix/SKILL.md": "No frontmatter here."})
    [skill] = scan_repo(tmp_path).skills
    assert skill.name == "lint-fix"
    assert skill.description == ""


def test_kubernetes_and_terraform(tmp_path: Path):
    make(
        tmp_path,
        {
            "k8s/deploy.yaml": "apiVersion: apps/v1\nkind: Deployment\n",
            "infra/main.tf": 'resource "aws_s3_bucket" "b" {}',
        },
    )
    scan = scan_repo(tmp_path)
    assert "Kubernetes" in scan.stack
    assert "Terraform" in scan.stack


def test_truncates_large_repos(tmp_path: Path):
    make(tmp_path, {f"f{i}.py": "x" for i in range(30)})
    scan = scan_repo(tmp_path, max_files=10)
    assert scan.truncated is True
    assert scan.file_count == 10


def test_scan_to_text_includes_summary_and_files(tmp_path: Path):
    make(tmp_path, {"README.md": "Hello project", "a.py": "x"})
    text = scan_to_text(scan_repo(tmp_path))
    assert "Languages: Python: 1" in text
    assert "### README.md" in text
    assert "Hello project" in text


def test_same_skill_in_many_agent_folders_is_listed_once(tmp_path: Path):
    body = "---\nname: impeccable\ndescription: Design skill\n---\nBody\n"
    make(
        tmp_path,
        {
            ".claude/skills/impeccable/SKILL.md": body,
            ".cursor/skills/impeccable/SKILL.md": body,
            ".gemini/skills/impeccable/SKILL.md": body,
        },
    )
    [skill] = scan_repo(tmp_path).skills
    assert skill.name == "impeccable"
    assert skill.path == ".claude/skills/impeccable/SKILL.md"


def skill_md(name: str) -> str:
    return f"---\nname: {name}\ndescription: {name} rules\n---\nBody\n"


# Built in a temp folder, not kept under tests/: a .claude/skills folder in Rig's own tree would
# be one of Rig's skills for an agent working in that folder.
AGENT_AND_OTHER_SKILLS = {
    # Loaded by a coding agent
    ".claude/skills/release-notes/SKILL.md": skill_md("release-notes"),
    ".agents/skills/codex-review/SKILL.md": skill_md("codex-review"),
    ".opencode/skills/oc-style/SKILL.md": skill_md("oc-style"),
    ".gemini/skills/gem-docs/SKILL.md": skill_md("gem-docs"),
    "services/api/.claude/skills/api-errors/SKILL.md": skill_md("api-errors"),
    "plugins/deploy/.claude-plugin/plugin.json": json.dumps(
        {"name": "deploy", "skills": ["./extra"]}
    ),
    "plugins/deploy/skills/ship-it/SKILL.md": skill_md("ship-it"),
    "plugins/deploy/extra/rollback/SKILL.md": skill_md("rollback"),
    "plugins/one/.claude-plugin/plugin.json": json.dumps({"name": "one"}),
    "plugins/one/SKILL.md": skill_md("one-skill"),
    ".claude-plugin/marketplace.json": json.dumps(
        {
            "plugins": [
                {"name": "kit", "source": "./kit"},
                {"name": "far", "source": {"github": "x/y"}},
            ]
        }
    ),
    "kit/skills/kit-skill/SKILL.md": skill_md("kit-skill"),
    # Not loaded by any agent: an app's own config, docs, a vendored copy, a nested .gemini
    "engine/src/app/skills/rig-score/SKILL.md": skill_md("rig-score"),
    "skills/loose/SKILL.md": skill_md("loose"),
    "docs/SKILL.md": skill_md("doc-page"),
    "plugins/fake/skills/no-manifest/SKILL.md": skill_md("no-manifest"),
    "pkg/.gemini/skills/nested-gem/SKILL.md": skill_md("nested-gem"),
    ".claude/skills/too/deep/SKILL.md": skill_md("too-deep"),
}


def test_only_skills_an_agent_loads_are_the_repos(tmp_path: Path):
    make(tmp_path, AGENT_AND_OTHER_SKILLS)
    scan = scan_repo(tmp_path)
    assert sorted(s.name for s in scan.skills) == [
        "api-errors",
        "codex-review",
        "gem-docs",
        "kit-skill",
        "oc-style",
        "one-skill",
        "release-notes",
        "rollback",
        "ship-it",
    ]
    assert "Skills" in scan.agent_setup


def test_a_repo_whose_only_skill_files_are_its_own_config_has_no_skills(tmp_path: Path):
    make(tmp_path, {"engine/src/app/skills/rig-score/SKILL.md": skill_md("rig-score"), "a.py": "x"})
    scan = scan_repo(tmp_path)
    assert scan.skills == []
    assert "Skills" not in scan.agent_setup
