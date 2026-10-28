---
name: starter-skills
description: The GitHub skill repositories whose skills come preloaded in the Workflow Lab, so a
  workflow has skills to use before you have any of your own - how they are indexed, cached and
  downloaded.
values:
  # Checked 2026-10-25 with `gh api repos/<r>`: none archived, all pushed in October 2026.
  # Each one's SKILL.md folders are mostly Markdown, so they read and install as text.
  repos:
    - repo: anthropics/skills  # official; ~184k stars
      label: Anthropic (official)
    - repo: obra/superpowers  # ~305k stars; planning, TDD, debugging, review
      label: Superpowers
    - repo: wshobson/agents  # ~42k stars, MIT; 185 skills across development plugins
      label: wshobson/agents
    - repo: trailofbits/skills  # ~7.8k stars; security review and testing
      label: Trail of Bits
  cache_ttl_hours: 24
  # After a failed or partial fetch, try again this soon (the last good index is kept meanwhile).
  retry_minutes: 10
  # One request per indexed skill reads its SKILL.md, so this bounds the fetch: 4 repos x 40.
  max_skills_per_repo: 40
  # A folder named here is a scaffold, not a skill (anthropics/skills has template/).
  # Any folder on the way: a skill under tests/fixtures is a test's input, not a skill to use.
  skip_folders: [template, templates, tests, test, fixtures, examples]
  # A folder with any of these is left out: skills install as text, and these aren't.
  binary_extensions: [.ttf, .otf, .woff, .woff2, .png, .jpg, .jpeg, .gif, .webp, .ico, .pdf,
    .gz, .zip, .tar, .mp4, .mov, .wasm]
---

# Starter skills

The Workflow Lab picks skills for each step of a workflow. Taking them only from your own
skills folder means someone with no skills gets workflows with no skills in them. So the Lab
also lists the skills in a few well-known GitHub repositories, marked as from GitHub with a
link to read each one there first.

## Which repositories

`repos`, in order: Anthropic's official repository first, then widely used and maintained
ones. A repository is listed only when it is not archived, was pushed to recently, and its
skill folders are mostly Markdown (instructions an agent reads, not programs and fonts).

## The index

For each repository: its file tree (one request), then the frontmatter of each SKILL.md
(one request each) for the skill's name and description. A folder is left out when it is in
`skip_folders`, holds a file with one of `binary_extensions`, or is larger than the catalog's
install limits (curate-catalog `install_max_files`, `install_max_bytes`), so anything listed can
also be downloaded. When a repository has more than `max_skills_per_repo` skill folders, an
even spread across them is taken, so the first letters of the alphabet don't fill the list.

The index is cached on disk for `cache_ttl_hours`. It is built in the background the first
time the Lab opens and never holds up the server. When a repository can't be read (offline,
rate-limited, renamed), its skills from the last good index are kept and the fetch is tried
again after `retry_minutes`; with no earlier index the Lab says GitHub couldn't be reached and
uses your own skills alone.

## Your skills come first

A skill of yours with the same name as one from GitHub replaces it. A GitHub skill already
downloaded is listed once, from its downloaded folder.

## Downloading

Nothing is downloaded to list a skill. When a workflow that uses one is saved or run, that
one folder is downloaded into the library (the same place and limits as installing from the
catalog) and the workflow points at the downloaded copy. If the download fails, saving or
running stops with a message saying which skill and why.
