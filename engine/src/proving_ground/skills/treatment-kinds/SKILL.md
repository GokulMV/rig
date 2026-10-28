---
name: treatment-kinds
description: "What a treatment folder or file is detected as (skill, hook, MCP server, instructions) and where each lands in the sandbox for the 'with' arm."
values:
  # A treatment's kind is read from the file names inside it. Exactly one marker may match.
  skill_file: SKILL.md
  hooks_file: hooks.json
  mcp_file: mcp.json
  mcp_install_file: install.sh
  instruction_files: [CLAUDE.md, AGENTS.md]
  # Where the 'with' arm's task puts it (paths inside the repo copied to /app).
  settings_path: .claude/settings.json
  mcp_config_path: .mcp.json
  # Claude Code asks before using servers from a project's .mcp.json; a headless trial cannot
  # answer, so the 'with' arm pre-approves the servers it adds.
  approve_project_mcp: true
  # Where the app looks for hooks, MCP servers and instructions to offer as treatments.
  repo_roots: [.claude]
  repo_files: [CLAUDE.md, AGENTS.md]
  scan_depth: 2
  # Edited copies of the repo's instructions, saved from Measure (one folder each). Inside
  # .proving-ground/, so neither arm's repo copy ever has them unless they are the change.
  drafts_dir: .proving-ground/treatments
  draft_name: claude-md-edit
  draft_max_chars: 100000
  # What the two arms get, for each kind (and, for instructions, each case: see "What an
  # instructions run compares"). Shown on Measure under the change.
  compare_text:
    hook: "With: its hooks are merged into .claude/settings.json (the repo's own hooks run first). Without: the repo's settings as they are."
    mcp: "With: the server is added to .mcp.json and approved. Without: the repo's .mcp.json as it is. An install.sh runs in both arms."
    edited: "With: this file as it is now, uncommitted edits included. Without: the committed {name}. The run measures your edit."
    new: "With: this {name}. Without: none, since it isn't committed. The run measures having it at all."
    same: "This is the {name} both arms already have, so a run would measure nothing. Edit a copy below (or edit the file without committing) to measure the edit."
    replaces: "With: this file in place of the repo's {name}. Without: the committed {name}. The run measures the difference."
    adds: "With: this file as the repo's {name}. Without: none, since the repo has no {name}. The run measures having it."
  # Where a coding agent loads a repo's skills, as <dir>/<name>/SKILL.md. Any other SKILL.md is
  # just a file (an app's own config, a fixture) and is not one of the repo's skills.
  #   .claude/skills    Claude Code, also OpenCode   (code.claude.com/docs/en/skills)
  #   .agents/skills    Codex, Gemini CLI, OpenCode  (learn.chatgpt.com/docs/build-skills)
  #   .opencode/skills  OpenCode                     (opencode.ai/docs/skills)
  #   .gemini/skills    Gemini CLI, at the root only (geminicli.com/docs/cli/skills)
  # Claude Code, Codex and OpenCode also load these from a subfolder an agent starts in.
  skill_dirs: [.claude/skills, .agents/skills, .opencode/skills]
  root_skill_dirs: [.gemini/skills]
  # A Claude Code plugin: a folder holding .claude-plugin/plugin.json. Its skills are in skills/
  # beside that folder, plus any folders its manifest's `skills` names; a plugin with no skills/
  # and SKILL.md at its root is one skill. A marketplace.json lists plugin folders the same way
  # (code.claude.com/docs/en/plugins-reference).
  plugin_manifest: .claude-plugin/plugin.json
  marketplace_manifest: .claude-plugin/marketplace.json
---

# Treatment kinds

A treatment is whatever you want to measure: take it away and see whether the agent does better.
The kind is never guessed from a name; it is read from the files, and an ambiguous folder is an
error rather than a coin toss.

## Detection

1. A single file named `CLAUDE.md` or `AGENTS.md` is **instructions**.
2. A folder is **skill** if it has `SKILL.md`, **hook** if it has `hooks.json`, **MCP** if it has
   `mcp.json`, **instructions** if it has `CLAUDE.md` or `AGENTS.md`.
3. A folder matching more than one of those is rejected: split it. A folder matching none is
   rejected with the list of file names that would make it a treatment.

## The repo's own skills

A repo's skills are the SKILL.md files a coding agent loads from it (`skill_dirs`,
`root_skill_dirs`, and Claude Code plugins: `plugin_manifest`, `marketplace_manifest`). Rig's own
rules, a test fixture, or a vendored copy elsewhere in the tree are files, not skills of the repo:
they are not drawn on its canvas, listed in its library, or counted in its setup.

## Where the "with" arm gets it

- **Skill**: handed to the agent through Harbor (unchanged).
- **Hook**: `hooks.json` holds Claude Code's `hooks` object. It is merged into
  `/app/.claude/settings.json`; the repo's own settings stay, and the repo's own hooks for the
  same event run first.
- **MCP**: `mcp.json` holds `{"mcpServers": {...}}`. It is merged into `/app/.mcp.json` (the
  treatment's server wins on a name clash) and its servers are approved in the settings.
  An optional `install.sh` runs at image build for **both** arms, so the two arms share one image
  and differ only in config. Pin every version in it: an unpinned install makes the arms drift.
- **Instructions**: replaces `/app/CLAUDE.md` (or `AGENTS.md`) with the file. The "without" arm
  keeps the repo's own file untouched.

## What an instructions run compares

The "without" arm is the repo's committed snapshot (`git archive HEAD`; a folder that isn't a git
repo is copied as it is), so what an instructions change measures depends on where it lives:

- **The repo's own `CLAUDE.md` / `AGENTS.md`**: *edited* when the working copy differs from the
  committed one (with: your edit; without: the committed file); *new* when it isn't committed
  (with: the file; without: none); *same* otherwise, and a run of it is refused: both arms would
  get the same file. Not a git repo: always *same*, since the snapshot is the working tree.
- **An edited copy saved from Measure** (`drafts_dir/<name>/CLAUDE.md`), or an instructions
  folder anywhere else: *replaces* the committed file of the same name, or *adds* one when the
  repo has none. Drafts live in `.proving-ground/`, which no snapshot includes.

`compare_text` says each case in words, under the change on Measure.

The "without" arm is always the repo as it is today, so shared baselines stay valid.
