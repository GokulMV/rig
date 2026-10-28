---
name: curate-catalog
description: Find, filter and rank open-source skills, agents, MCP servers, hooks, harnesses, workflows
  and eval suites on GitHub.
values:
  cache_ttl_hours: 24
  partial_retry_minutes: 10
  search_gap_s: 2.1
  per_query:
    by_stars: 30
    by_recent: 15
    recent_min_stars: 5
  recommended:
    fresh_since: '2026-08-01'
    stale_weight: 0.5
    relevance_weight: 50
    score: sqrt(stars) * freshness + relevance_weight * relevance
    # With project terms, an item matching the project (relevance >= relevant_min) always comes
    # before one that doesn't, however famous: a 0-relevance item never outranks a 2-relevance one.
    relevant_first: true
    relevant_min: 2
    # Words that describe the catalog itself, not the project: dropped from the project terms
    # (a use case saying "agent" would otherwise make every agent relevant).
    generic_terms: [agent, agents, agentic, claude, code, coding, skill, skills, mcp, server, servers,
      hook, hooks, harness, workflow, workflows, model, models, tool, tools, plugin, plugins, llm, llms,
      prompt, prompts, eval, evals]
  # Search: the query is split into words. Each word scores at the best place it matches:
  # name word > theme > topic > description word (weights below); an exact name match adds
  # exact_name; a query of two or more words found as that phrase in the name or description
  # adds phrase. A word matches a word exactly, or as its start (prefix: query words of min_prefix+
  # letters, or min_name_prefix+ against a name, so "rag" finds ragflow), or with one typo (fuzzy: one letter wrong, missing, extra or swapped; words of
  # min_fuzzy+ letters, same first letter). A theme matches when a query word matches a word of the
  # theme's name ("code review" -> Code review) and the item's text matches that theme's words.
  # Every rare word must match; a word that matches more than common_share of the items searched
  # (like "code" in "Claude Code") is not required and adds only common_weight of its score.
  # Ties keep the sort's order.
  # The web app mirrors these weights in web/src/lib/librarySearch.ts (a test checks they agree).
  # A word also matches its other forms: a query word and a word with the same stem (bugs,
  # bug; reviewing, review) match at `stem`, and a word made of the query word and one of
  # `compound_tails` matches at `stem` too ("bug" finds "bugfix"; three letters are enough).
  # Ranking goes in tiers before score: an exact name, then the query as a phrase in the name or
  # description, then every query word in the name, then every word anywhere, then the rest
  # (the rare words only). So "code review" puts a code-review skill before review-animations.
  search:
    exact_name: 100
    phrase: 6
    name: 8
    theme: 5
    topics: 3
    description: 1
    prefix: 0.8
    fuzzy: 0.5
    min_prefix: 4
    min_name_prefix: 3
    min_fuzzy: 5
    common_share: 0.5
    common_weight: 0.25
    common_min_items: 8
    stem: 0.9
    # Strong matches are shown first; the rest fold under "Weaker matches (N)". One word must
    # score at least this in the name or description, weights included: any name match passes;
    # in the description the word itself or another form of it (stem), not just a word start
    # ("postgres" in "PostgreSQL archive") or a typo. Several words must be said as a phrase or
    # all be in the name.
    strong_min: 0.9
  compound_tails: [fix, fixes, fixing, fixer, fixed, s, es, ed, ing, er, ers, tracker, tracking, report, reports, hunt, hunting]
  # Recommended with a goal: items that match the goal's own words come first, then items that
  # match the repo's stack, then the rest; each part by score. Words that say nothing about the
  # kind of work are left out of the goal.
  goal_stop: [repo, repos, repository, codebase, project, app, apps, want, need, make, better, help, helps, use, using, work, thing, things, every, some, more, less, very, also, like, just, should, would, could, about, from, into, with, that, this, your, have, when, only, them, they, their, there, what, which, where, will, does, done, each, both, many, much, over, under, after, before, then, than]
  max_items_shown: 120
  # Searching from the Library's home (all kinds at once): at most this many per kind.
  search_per_kind: 5
  install_max_files: 200
  install_max_bytes: 2000000
  archived: excluded
  parts:
    max_parts: 40
    max_read: 40
    # Order is the flow on the canvas, left to right: what starts work, who does it, what they use.
    kinds:
      instructions:
        label: Instructions
        match: ^(CLAUDE|AGENTS|GEMINI)\.md$
      command:
        label: Command
        match: (^|/)commands/[^/]+\.md$
      agent:
        label: Agent
        match: (^|/)agents/[^/]+\.md$
      skill:
        label: Skill
        match: (^|/)SKILL\.md$
      hook:
        label: Hook
        match: (^|/)hooks/[^/]+\.(sh|py|js|ts|json)$|(^|/)hooks\.json$
      mcp:
        label: MCP config
        match: (^|/)\.?mcp\.json$
    skip: (^|/)(node_modules|\.git|tests?|examples?|templates?|docs?)/
  # Which category a repository belongs to: each category's must_mention is searched in its name,
  # description and topics (separately; in names and topics - and _ are spaces). Score = name hits x name +
  # description hits x description + topic hits x topics, counting distinct matched words. It needs
  # at least one hit in the name or description, the context words too where a category lists them,
  # and none of its not_if words (nor not_apps). Highest score wins; a tie goes to the first in
  # this list. Pinned repositories keep their category.
  classify:
    name: 3
    description: 2
    topics: 1
    # A description that opens by saying what the repository is ("MCP server and Claude plugin
    # for Postgres ...") adds is_a to that category: what it is outranks what it mentions.
    is_a: 3
  # Per category: what its description's first clause says when the repository is one.
  is_a:
    mcp: ^(?:an? |the |official |open[- ]source )?(?:[\w.-]+ ){0,3}(?:mcp|model context protocol) servers?\b
  # Apps that are themselves an AI agent (a desktop client, an "agent OS") are none of the kinds:
  # you can't add them to your agent. Checked in name and description for every category.
  not_apps: \b(desktop (?:app|agent|client|ai|ui|workbench|workspace|studio)|native app|mobile app|electron app|operating system|agent os)\b
  # Words that say a text is about coding agents (the "context" of hooks, agents, skills ...).
  agentic: \b(claude|codex|cursor|copilot|gemini|opencode|windsurf|cline|agents?|agentic|llms?|ai|coding)\b
  categories:
    skill:
      label: Skills
      blurb: Teaches your agent one job, like reviewing a diff or writing a migration.
      queries:
      - topic:agent-skills
      - topic:claude-skills
      - topic:claude-code-skills
      must_mention: \b(skills?|skill\.md)\b
      context: agentic
    agent:
      label: Agents & Subagents
      blurb: A specialist your agent hands work to, like a reviewer or a planner.
      queries:
      - topic:subagents
      - topic:claude-code-agents
      - topic:claude-subagents
      - topic:coding-agent
      # Agents you add to Claude Code or Codex, not apps that are themselves an AI agent.
      must_mention: \b(sub[- ]?agents?|agent teams?|(?:specialists?|specialized|expert|custom|reviewer|\d+\+?) (?:ai |coding |claude code )?agents|agents? (?:for|in) (?:claude|codex)|(?:claude code|codex) agents?|agent (?:prompts?|definitions?))\b
      context: agentic
      pinned:
      - wshobson/agents
      - VoltAgent/awesome-claude-code-subagents
      - lst97/claude-code-sub-agents
      - 0xfurai/claude-code-subagents
    mcp:
      label: MCP Servers
      blurb: Gives your agent a new tool, like a database, a browser or GitHub.
      queries:
      - topic:mcp-server
      - topic:mcp-servers
      - topic:model-context-protocol
      must_mention: \b(mcps?|model context protocol)\b
      pinned:
      - modelcontextprotocol/servers
      - punkpeye/awesome-mcp-servers
      - github/github-mcp-server
      - microsoft/playwright-mcp
    hook:
      label: Hooks & Commands
      blurb: Runs on each tool call to block or check something; a command is a saved prompt.
      queries:
      - topic:claude-code-hooks
      - topic:claude-hooks
      - topic:claude-code-commands
      # Hooks in Claude's sense (with the agentic context), not React hooks or git hooks alone.
      must_mention: \b(hooks?|pre[- ]?tool[- ]?use|post[- ]?tool[- ]?use|permission ?requests?|slash[- ]commands?|custom commands|notif(?:y|ications?)|pre[- ]execution guard|blocks? (?:destructive|risky|dangerous))\b
      context: agentic
    harness:
      label: Harness Techniques
      blurb: A whole setup around the agent (instructions, loops, memory) that changes how it works.
      queries:
      - topic:agent-harness
      - topic:claude-code-plugin
      - topic:context-engineering
      must_mention: \b(harness\w*|agent loops?|(?:self[- ]correcting|repair|ralph) loops?|loop engineer\w*|context engineering|(?:claude code|codex) (?:plugins?|setup|config\w*|kit|toolkit|framework|template|settings)|plugins? for claude code|claude\.md|agents\.md|memory|context (?:management|engineering|window|layer)|persistent context)\b
      context: agentic
    workflow:
      label: Workflows
      blurb: Chains steps or agents (plan, build, test, review) so big tasks don't drift.
      queries:
      - topic:agentic-workflow
      - topic:agentic-workflows
      - topic:multi-agent
      - topic:spec-driven-development
      must_mention: \b(workflows?|multi[- ]?agents?|orchestrat\w*|spec[- ]driven|sdd|pipelines?)\b
      context: agentic
    eval:
      label: Eval Suites
      blurb: Scores an agent on fixed tasks, so you can tell whether a change helped.
      queries:
      - topic:llm-evaluation
      - topic:agent-evaluation
      - topic:swe-bench
      - topic:evals
      must_mention: \b(evals?|evaluat\w*|benchmark\w*|bench|swe[- ]bench|leaderboards?|llm[- ]as[- ]a[- ]judge|red[- ]teaming)\b
      context: \b(llms?|agents?|agentic|models?|ai|rag|coding|language|prompts?|gpt|claude|code|swe[- ]bench)\b
      pinned:
      - SWE-bench/SWE-bench
      - laude-institute/terminal-bench
      - UKGovernmentBEIS/inspect_ai
      - promptfoo/promptfoo
      - confident-ai/deepeval
      - openai/evals
      - explodinggradients/ragas
      - EleutherAI/lm-evaluation-harness
  themes:
    Testing & quality: \b(tests?|testing|tdd|qa|lint\w*|quality|coverage)\b
    Code review: \b(review\w*|pr|pull requests?|diffs?)\b
    Frontend & design: \b(frontend|ui|ux|design\w*|css|react|figma)\b
    Docs & writing: \b(docs?|documentation|writing|readme|blog\w*|content)\b
    Security: \b(security|secure|vuln\w*|audit\w*|pentest\w*)\b
    Data & ML: \b(data|ml|machine learning|analytics|sql|pandas)\b
    DevOps & cloud: \b(devops|deploy\w*|docker|kubernetes|k8s|ci|cloud|infra\w*)\b
    Memory & context: \b(memory|context|rag|knowledge)\b
    Planning & orchestration: \b(plans?|planning|specs?|spec-driven|orchestrat\w*|multi-agent|subagents?|workflows?|loops?)\b
---

# Curate the catalog

## Find
For each category, run each topic query twice on GitHub: by stars (`per_query.by_stars`) and by
recent pushes (`per_query.by_recent`, with at least `recent_min_stars` stars so empty forks stay
out). Searches are spaced `search_gap_s` apart (GitHub allows 30 a minute). The result is
cached for `cache_ttl_hours`; if some searches failed, it is retried after
`partial_retry_minutes`.

Topic search misses some canonical repositories (few set topic tags), so each category may also
list `pinned` repositories, looked up by exact name before searching. A pinned repository that
is archived, renamed or gone is skipped quietly; it does not make the catalog partial.

## Filter and classify
- Archived repositories are dropped.
- A repository goes to the category it matches best (`classify`), whichever search found it:
  each category's `must_mention` is counted in the name, description and topics, weighted, and
  the highest score wins (a tie: the first listed). It must mention the category in its name or
  description (topic tags alone are too noisy), with the `context` words where a category lists
  them (hooks in Claude's sense, not React hooks), and none of `not_if` or `not_apps` (a desktop
  app that is itself an AI agent is not something you add to yours). A repository that matches
  no category is left out. Pinned repositories skip all this: they keep their category.
- The cached catalog is classified again when it is read, so a change to these rules shows at
  once, without fetching from GitHub again.

## The Library's home
The Library opens on the kinds, one tile each with its `label`, its count and its `blurb`: one
plain line on what it is and why you'd add one. A tile opens that kind. Searching from the home
searches every kind at once: at most `search_per_kind` per kind, the kind with the best match
first, and a link to all of them.

## Search
`search`: the query is split into words, each scored where it matches best (an exact name, a
name word, a theme, a topic, a description word; a word start, another form of the word or one
typo count for less). A word matches its other forms: "bugs" and "bug" share a stem, and "bug"
finds "bugfix" (`compound_tails`). Every rare word must match; a word most items have ("code" in
"Claude Code") only adds a little. Results come in tiers, then score: the exact name, then the
whole query as a phrase, then all its words in the name, then all its words anywhere, then the
rest. So "code review" finds code-review skills before review-animations, which only says code
somewhere in its description. Ties keep the sort's order.

Strong and weak: a result is strong when the query's distinctive words are said in its name or
description: several words as a phrase (in the name, the description, or as one topic like
`code-review`) or all in the name; one word in the name or description at `strong_min` or
better. One that matches only by a topic tag, a theme (a generic word like "review" naming the
Code review theme) or scattered words ("Review UI code") is weak: strong ones come first, and
the weak ones are folded under "Weaker matches (N)". So "postgres" shows pg-aiguide, which says
Postgres, and folds the memory server that only has a `postgres` topic.

## Rank (the Sort menu)
- **Recommended:** `recommended.score`; pushed before `fresh_since` counts at `stale_weight`. With
  a goal (the use case), items that match its own words (less `goal_stop` and `generic_terms`,
  each word in any of its forms) come first, most matched first: a bug-fix goal puts debugging
  and test-first skills before a famous scroll-animation one. With
  project terms (the repo's stack and use case, less `generic_terms`), everything with
  `relevant_min` or more relevance comes before everything else (`relevant_first`): a 0-relevance
  item never outranks a 2-relevance one, however many stars it has.
- **Most starred:** stars, high to low.
- **Latest:** last push, newest first.
- **For this repo:** only items matching the repo's stack and use-case terms, most matches first,
  then stars. Keeps useful low-star repositories in view.

At most `max_items_shown` per category. Items are grouped by theme (whole-word `themes`).

## Parts (a harness or workflow repository, opened on the canvas)
A repository that is more than one skill is shown as its parts, read from its file tree with the
`parts.kinds` patterns, in that order: instructions, commands, agents, skills, hooks, MCP config.
Paths under `parts.skip` are left out; at most `parts.max_parts` parts. Each part's text (at most
`parts.max_read` of them) gives its description and its links: a part that names another part
(its file name, as a whole word) is drawn as using it. Nothing is guessed: a part that names no
other part has no link but the one from its repository.

## Install
Only the chosen skill's folder is downloaded, into the library outside every repo, refused
above `install_max_files` files or `install_max_bytes` bytes, and refused for unsafe paths.
