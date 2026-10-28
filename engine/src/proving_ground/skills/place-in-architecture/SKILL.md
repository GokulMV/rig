---
name: place-in-architecture
description: Decide where a library item (skill, agent, MCP server, hook, harness, workflow, eval) goes on a repo's canvas, and say why.
values:
  max_targets: 2
  second_target_ratio: 0.8    # a second target only if it scores at least this share of the best
  name_match: 3               # points per word the item shares with a block's name
  detail_match: 1             # points per word it shares with a block's description
  kind_match: 4               # points when the block is the kind of place this item belongs
  theme_match: 3              # points when the item's theme fits the block
  theme_word_match: 2         # points per word of the item's theme in the block's name or description
  categories:
    skill: [step, frontend, backend, database, security, external, setup]
    agent: [step, setup]
    mcp: [database, external, cloud, security]
    hook: [setup]
    harness: [setup]
    workflow: [first-step]
    eval: [test-step]
  # `root` is the agent setup's instructions (CLAUDE.md or AGENTS.md): what applies to the whole
  # repo goes there.
  themes:
    "Testing & quality": [test-step, review-step]
    "Code review": [review-step, test-step]
    "Frontend & design": [frontend]
    "Docs & writing": [root]
    "Security": [security, backend]
    "Data & ML": [database]
    "DevOps & cloud": [cloud]
    "Memory & context": [root]
    "Planning & orchestration": [first-step]
    "Conventions & style": [root]
  # A skill from this machine has no theme: it gets the one whose words it uses most (the first
  # listed on a tie), with at least one. Words are whole and lower case.
  theme_words:
    "Testing & quality": [test, tests, testing, tdd, pytest, jest, vitest, playwright, cypress, coverage, e2e, qa, regression, fixtures, assertions]
    "Code review": [review, reviews, reviewer, diff, diffs, pr, prs]
    "Frontend & design": [frontend, ui, ux, css, html, react, vue, svelte, tailwind, vite, component, components, layout, animation, animations, accessibility, a11y, visual, browser, web]
    "Security": [security, secure, vulnerability, vulnerabilities, owasp, secrets, injection, pentest, xss, csrf]
    "Data & ML": [sql, database, databases, postgres, postgresql, sqlite, mysql, migration, migrations, schema, pandas, dataset, datasets]
    "DevOps & cloud": [docker, kubernetes, k8s, terraform, deploy, deployment, aws, gcp, azure, helm, infrastructure]
    "Conventions & style": [naming, convention, conventions, style, styleguide, lint, linting, formatting, idiomatic]
    "Docs & writing": [docs, documentation, readme, changelog, docstring, docstrings, prose]
    "Memory & context": [memory, remember]
    "Planning & orchestration": [plan, planning, orchestrate, orchestration, subagents]
  step_types:
    test-step: [test, verify, qa, check]
    review-step: [review, verify]
  # Agent setup blocks that are a place of their own.
  setup_places: {CLAUDE.md: root, AGENTS.md: root, Test command: test-step}
  place_names:
    frontend: the front end
    backend: a service
    database: a store
    external: an outside service
    cloud: the infrastructure
    security: a security part
    first-step: the first step
    test-step: where the tests run
    review-step: the review step
  # `at`: the block it goes next to when the canvas has one by that name (else any block of its kind).
  one_place:
    hook: {at: Hooks, why: "a hook runs with the agent setup"}
    harness: {at: CLAUDE.md, why: "a harness changes the agent setup"}
    workflow: {why: "a workflow starts at the first step"}
    eval: {at: Test command, why: "an eval suite checks the work the way the tests do"}
  nouns: {skill: skill, agent: agent, mcp: MCP server, hook: hook, harness: harness, workflow: workflow, eval: eval suite}
  # The one line shown on the card and in the inspector. {block} is the block's name.
  reasons:
    words: "Applies to {block}: because the {noun} mentions {words}."
    theme: "Applies to {block}: because the {noun} is about {theme} and {block} is {place}."
    theme_words: "Applies to {block}: because the {noun} is about {theme} and {block} uses {words}."
    one_place: "Applies to {block}: because {why}."
    whole_repo: "Applies to the whole repo: because it is about {theme}, so it goes with {block}."
  unlinked: "No part of this repo matches; added to the agent setup."
---

# Place a library item

When "Add" is clicked, the item goes next to the block it serves and is linked to it, so the
canvas shows where it acts, with one line saying why. Dropping by hand still works and wins.

## How

1. List the canvas blocks: architecture parts, the agent setup, and the workflow steps. Some
   agent setup blocks are places of their own (`setup_places`): CLAUDE.md or AGENTS.md is the
   root, what applies to the whole repo; the test command is where the tests run.
2. Find the item's theme: the catalog's, or for a skill on this machine the theme whose words
   (`theme_words`) it uses most.
3. A block can be linked only for a reason a person can check:
   - the item shares a word with the block's name (everyday words like "read" don't count);
   - its theme fits the block (`themes`, `step_types`), and either the block's name or
     description has one of the theme's words ("web" is React, a frontend word), or it is the
     only block of that place: a testing skill goes where the tests run, a frontend skill to the
     front end, a review skill to the review step;
   - its kind has one place (`one_place`: a hook with the agent setup).
   A word shared only with a block's description, or a kind alone ("a skill can sit at an outside
   service"), is not enough: it adds to the score (`detail_match`, `kind_match`) and nothing more.
4. Score the blocks that can be linked: `name_match` per shared name word, `detail_match` per
   description word, `kind_match` for the kind of place (`categories`), `theme_match` for the
   theme, `theme_word_match` per theme word the block has. Take the best; also a second one if
   it scores at least `second_target_ratio` of the best, up to `max_targets`.
5. An item about the whole repo (conventions and style, docs, memory: a theme whose place is
   `root`) is linked to CLAUDE.md (or AGENTS.md, or the CLAUDE.md the canvas says to add) and
   says so: "Applies to the whole repo: because it is about conventions & style, so it goes with
   CLAUDE.md."
6. Nothing fits: the item goes beside the agent setup, linked to nothing, and says `unlinked`.
   A link to a block that has nothing to do with it is worse than no link.
7. An item written for a language the repo has no files in (recommend-for-repo:
   `item_languages`) says so after its reason: "For Go; this repo has none."
8. The reason is one plain sentence (`reasons`), shown on the card and in the inspector.
