---
name: match-skills
description: How the Workflow Lab picks library skills for a workflow step - two small open-source models run on this machine once they are downloaded (an embedding model finds candidates, a reranker decides), and until then word rules - words reduced to a common form, rare words counting more, a skill's name having to fit the step - each with the reason it was picked.
values:
  # Points: a step word found in the skill's name counts name_word x its weight, one found only
  # in its description description_word x its weight. A word's weight is how rare it is in the
  # library: ln((skills + idf_prior_skills) / (skills using it + 1)), so a word every skill
  # uses counts for little. The prior keeps a small library from making every word look rare.
  name_word: 2
  description_word: 1
  idf_prior_skills: 100
  related_word: 0.5             # a related word (critique for review) counts this share of the word
  skill_match_min: 4.0          # points a library skill needs to be attached to a step
  # With nothing in its name matching, a skill needs this many different description words.
  description_words_min: 2
  # Skills named for one language, framework, tool, file format or testing technique fit only
  # steps that say it.
  specific: [csharp, java, kotlin, swift, rust, golang, go, ruby, php, python, javascript, typescript, react, vue, angular, svelte, django, rails, laravel, spring, flutter, android, ios, unity, jdk, dotnet, animation, figma, wordpress, shopify,
    solidity, solana, algorand, cairo, ton, web3, blockchain, godot, nextjs, helm, bazel, dbt, langchain,
    paypal, reader, dwarf, libafl, atheris, ruzzy, wycheproof,
    c, github, trailmark, superpowers, slack, gif, mcp, lean, spark, macos, pdf, docx, xlsx, pptx, academy,
    connectivity, mutation, constant-time, fuzz, sanitizer]  # the last line: techniques named by the GitHub starter skills
  # A skill whose name says what kind of work it does (a review, a test, code) fits only a step
  # about that work: the step, or its discipline's context, must say one of the words listed.
  facets:
    review: [review, critique, audit, inspect]
    code: [code, codebase, diff, pr, branch, commit, refactor, implement, function, module, patch, repo]
    test: [test, tdd, qa, e2e, pytest, playwright, coverage]
    webapp: [web, webapp, browser, frontend, playwright, e2e, page, ui]
    debug: [debug, bug, failure, fail, error, diagnose, root-cause, crash]
    plan: [plan]
    execute: [execute, carry, implement]
    verify: [verify, verification, confirm, validate, retest]
    security: [security, secure, vulnerability, threat, exploit, injection, auth, attack, cve, sast]
    vulnerability: [security, vulnerability, threat, exploit, injection, cve, sast]
    regression: [regression]
    changelog: [changelog, release]
    dashboard: [dashboard, kpi, metric]
    receive: [receive, feedback]
    request: [request, merge, pr]
    compliance: [compliance, conform, verify, audit]
    report: [report, summary]
    patch: [patch, fix, remediate]
    validation: [verify, validate, confirm]
  # A skill for code work fits only a step whose discipline works on code. In any discipline not
  # in `code_disciplines`, a skill is left out when its name has one of `code_facets` or its name
  # or description says one of `code_only` (a security scanner, a test runner, a linter): semgrep
  # never lands on a support ticket's approval step.
  discipline_gate:
    code_disciplines: [development, qa, devops, security, data, pattern]
    code_facets: [code, test, debug, regression, patch, webapp, vulnerability]
    code_only: [semgrep, sast, codeql, static analysis, static analyzer, security scan, linter, linters,
      lint, linting, eslint, ruff, pylint, prettier, test runner, test suite, unit test, unit tests,
      pytest, jest, vitest, playwright, cypress, codebase, source code, pull request, pull requests,
      compiler, fuzzing, fuzzer, fuzz, sanitizer, refactor, refactoring, stack trace, git diff]
  # Words a whole discipline is about, which count for facets but not for points: a
  # development step is about code even when it doesn't say so.
  context:
    development: [code]
    pattern: [code]
    security: [code, security]
    qa: [test]
    design: [ui]
  # Words that mean the same for matching. The first is the form both sides are reduced to.
  same:
    pr: [pr, prs, pull-request]
    doc: [doc, docs, documentation]
    spec: [spec, specs, specification, specifications]
    tdd: [tdd, test-driven, test-first, failing test, failing tests]
    e2e: [e2e, end-to-end]
    a11y: [a11y, accessibility]
    root-cause: [root-cause, root cause]
    verify: [verify, verifies, verified, verification, verifier, verifying, re-test, retest]
    test: [test, tests, testing, tested, tester, testers]
    review: [review, reviews, reviewing, reviewed, reviewer, reviewers]
    plan: [plan, plans, planning, planned, planner, planners]
    write: [write, writes, writing, written, wrote, writer]
    implement: [implement, implements, implementing, implemented, implementation, implementer, coder]
    execute: [execute, executes, executing, execution]
    debug: [debug, debugging, debugger]
    fail: [fail, fails, failed, failing]
    failure: [failure, failures]
    receive: [receive, receives, receiving]
    request: [request, requests, requesting]
    validate: [validate, validates, validated, validating, validation, validator]
    constant-time: [constant-time, constant time]
  # Words that are close but not the same: each counts related_word of a match.
  related:
    - [review, critique, audit]
    - [pr, diff, branch]
    - [debug, bug, failure, fail, error, diagnose, root-cause]
    - [verify, confirm, validate, check]
    - [doc, readme, guide]
    - [security, vulnerability, threat, exploit]
    - [parallel, independent, concurrent, worker, split, orchestrator]
    - [plan, spec]
    - [implement, execute, build]
    - [patch, fix]
    - [tdd, test]
  # Suffixes taken off any other word, longest first, keeping at least stem_min letters.
  suffixes: [ations, ation, ings, ing, ies, ied, es, ed, s]
  stem_min: 3
  # Words that never count: they say nothing about which skill fits.
  stopwords: [a, an, and, or, the, of, to, for, in, "on", at, by, with, from, as, is, are, be, been,
    it, its, this, that, these, those, any, all, each, every, one, two, three, first, then, than,
    what, how, why, who, when, where, which, if, so, not, "no", can, should, must, will, would, may,
    only, more, most, less, new, into, out, up, about, against, without, until, before, after,
    your, you, our, we, they, their, them, his, her, there, here, also, such, other, else, own,
    use, using, used, skill, skills, step, steps, task, tasks, work, make, do, does, done, write,
    list, run, find, check, add, get, give, keep, say, says, take, turn, thing, things, way, like,
    via, e, g, eg, ie, etc, need, needs, help, helps, want, wants, user, users, claude, ai,
    change, changes, small, short, whole, same, given, best, read, re, t, s, doesn, don, isn,
    was, were, has, have, had, de, whose, "off", yet]  # quoted: YAML reads on/no/off as booleans
  # Words in skill names that don't say what the skill is about, so the name isn't judged on them.
  generic_name_words: [development, driven, pattern, patterns, guide, guidelines, practices,
    advanced, workflow, workflows, setup, analysis, techniques, method, selection, creator,
    builder, management, expert, systematic, completion, finishing, design, before, automation]
  # The models (see "Models" below), chosen on the tune steps only.
  models:
    dir: models                 # under the app home, ~/.proving-ground
    host: https://huggingface.co  # files at <host>/<repo>/resolve/<revision>/<path>: no account, no token
    download_max_mb: 1250       # refuse a download bigger than this
    download_timeout_s: 1800    # give up (and keep to the word rules) after this long
    connect_timeout_s: 20
    read_timeout_s: 60
    retry_after_s: 600          # after a failure, try again on a Lab visit this much later
    threads: 4                  # CPU threads per model
    memory_gb: 1.9              # what the two loaded models take (measured), said before the download
    batch: 32                   # texts embedded at once
    candidates: 10              # skills from each source: the embedding's nearest, the word rules' best
    save_every_s: 5             # how often new scores are written to the cache file
    threshold: 0.5              # the reranker's chance of "yes" the best candidate needs to be attached
    embed:
      name: bge-small-en-v1.5
      repo: BAAI/bge-small-en-v1.5
      revision: 5c38ec7c405ec4b44b94cc5a9bb96e735b38267a
      license: MIT
      model: onnx/model.onnx
      max_tokens: 256
      query_prefix: "Represent this sentence for searching relevant passages: "
      files:
        onnx/model.onnx: {bytes: 133093490, sha256: 828e1496d7fabb79cfa4dcd84fa38625c0d3d21da474a00f08db0f559940cf35}
        tokenizer.json: {bytes: 711396, sha256: d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66}
    rerank:
      name: Qwen3-Reranker-0.6B
      repo: onnx-community/Qwen3-Reranker-0.6B-ONNX  # an ONNX export of Qwen/Qwen3-Reranker-0.6B, 4-bit weights
      revision: 9995c50e2310679108a55f5ccd16ba8be9f17c20
      license: Apache-2.0
      model: onnx/model_q4.onnx
      max_tokens: 640
      files:
        onnx/model_q4.onnx: {bytes: 995235866, sha256: 787193952a9aa58374381ec7647b160ac6c200a386dbfc3bc998a3c458081330}
        tokenizer.json: {bytes: 11422654, sha256: aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4}
      # The model's own prompt (from its model card), and what it is asked.
      prefix: "<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct provided. Note that the answer can only be \"yes\" or \"no\".<|im_end|>\n<|im_start|>user\n"
      suffix: "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
      instruction: Given a step of an agent's workflow, judge whether this agent skill's instructions would help the agent do that step
---

# Match skills

The Workflow Lab attaches library skills to each step of a workflow: your own skills and the
ones preloaded from GitHub (starter-skills). Two small open-source models running inside the
engine decide, once they're on this machine (see Models); until then, and whenever getting or
running them fails, the word rules below decide. Each attached skill carries the reason it
was picked, so the page can show it.

## Models

Nothing heavy happens unless you ask: by default the word rules match, and the Lab's status
line offers the models with their download size and memory (`memory_gb`). Asking is
remembered (`choice.json` next to the weights) and can be undone ("Turn it off", which lets
the loaded models go); `PG_SKILL_MODELS=off` keeps them off whatever was chosen. No account,
key or model server: the weights come once from public Hugging Face repos, pinned to a commit
and checked against a pinned size and SHA-256 (`models.embed`, `models.rerank`), into
`~/.proving-ground/models`. A download over
`download_max_mb` is refused; one taking longer than `download_timeout_s` is dropped; after a
failure it is tried again `retry_after_s` later. Nothing else is sent anywhere, and no token is
sent even if one is set.

- Candidates: the `candidates` skills nearest the step by meaning (bge-small-en-v1.5, MIT,
  133 MB) and the word rules' best `candidates`, less those the names rule out (below).
- Decision: Qwen3-Reranker-0.6B (Apache-2.0; a 4-bit ONNX export, 995 MB) reads the step and
  each candidate with its own prompt and `instruction`, and says yes or no. The best candidate
  is attached if its chance of yes is at least `threshold`; otherwise none is: that is what
  keeps a skill off a step none fits.

The step is read as "name: does words", a skill as "name: description". Embeddings and scores
are kept in memory and in `cache.json` next to the weights, keyed by the models' revisions and
the texts, so they are worked out once. The Lab uses the models for a library only after its
own steps have been matched against it in the background (minutes, the first time), and a page
is matched one way throughout; a line under Random says which, and what is happening.

The models were chosen, and `candidates` and `threshold` set, on the tune steps only. Small
off-the-shelf rerankers (MiniLM, bge-reranker-base and v2-m3, gte-modernbert, mxbai) and an
embedding alone scored lower on them.

## Words

A step has a headline (its name and the words its workflow gives it) and a body (what it
does); a skill has a name and a description. All are cut into words the same way: lower case;
phrases in `same` joined into one word (pull request → pr, failing test → tdd); the rest split
at hyphens; words in `stopwords` dropped; and every word brought to one form: the forms in
`same` (tests, testing → test; reviewer → review), else the word without its suffix
(`suffixes`, keeping at least `stem_min` letters, then a trailing e and a doubled last letter
dropped, so planning and plan agree).

## Points

A headline word in the skill's name scores `name_word` times the word's weight. A step word
in its description, or a name word only the body says, scores `description_word` times the
weight. The weight is how rare the word is across the library (inverse document frequency,
smoothed by `idf_prior_skills`): "code" or "implement" appear in dozens of skills and count for
little, "changelog" in a few and counts for a lot. A name word `related` to a headline word
(critique for review, diff for pr) counts `related_word` of a match.

Name points are scaled by how much of the name the step covers (words in
`generic_name_words`, like development or patterns, aren't judged): a step that says "failing
test" covers all of `test-driven-development`.

A skill must also fit the headline: a name word in it, a related one, or a description word
in it. "Plan" in "argue against the plan" doesn't make a planning skill fit a critique. With
no name word matched, it needs `description_words_min` different description words: one
shared word is a coincidence. Then it needs `skill_match_min` points; the best come first.

## Names that rule a skill out

- `specific`: a skill named for one language, framework, tool, file format or testing
  technique (`python-…`, `github-triage`, `pdf`, `mutation-testing`) fits only a step that
  says that word.
- `facets`: a skill whose name says what kind of work it does fits only a step about that work.
  `receiving-code-review` has the facets receive, code and review: the step has to be a review,
  about code (from its words or its discipline's `context`), and about feedback received.
  So Implement doesn't get a review skill and a product critique doesn't get a code-review one.

## Code skills stay on code work

A step in a discipline that doesn't work on code (support, research, finance, product, docs …,
anything not in `discipline_gate.code_disciplines`) never gets a skill made for code: one whose
name has a code facet (`code_facets`: test, debug, patch …) or whose name or description says a
`code_only` word (a scanner like semgrep, a test runner, a linter, "codebase"). The gate holds
for the word rules and the models alike, so a support approval step can't pick up a security
scanner because its description says "approval".

## Why

Each attached skill says why, e.g. "matched: failing test; name 1/1": the step's own words
that matched (as the step wrote them, strongest first; critique≈review for a related word),
and, when its name matched, how much of the name they covered.

With the models, a skill says e.g. "picked by Qwen3-Reranker-0.6B (0.94): the step says diff,
review", or "…: its description fits what the step does" when the word rules didn't rank it.

## Measured

`engine/tests/fixtures/skill_matching.json` lists 76 real Lab steps with the skills from the
GitHub index a careful person would attach, or none: 51 to tune on, 25 held out.
`skill_matching_fresh.json` adds 76 more, written and labelled before the models were tried
and never tuned on. At one skill per step:

| | tune | holdout | fresh | holdout + fresh |
|---|---|---|---|---|
| word rules | P 0.897, R 0.812, 2/19 false | 0.417, 0.333, 4/10 | 0.750, 0.577, 4/24 | 0.673, 0.522, 8/34 |
| models | 0.864, 0.594, 0/19 | 0.625, 0.333, 1/10 | 0.875, 0.673, 1/24 | 0.833, 0.597, 2/34 |

(P precision, R recall, then steps given a skill when none fits.) The word rules were tuned on
the tune steps, and are far worse on steps they weren't. The models attach fewer wrong skills
everywhere but miss many right ones: 15 of the 27 held-out misses are skills the names rule out
(a step about a Kubernetes chart doesn't say helm, one about a Word document doesn't say docx),
and the reranker gave most of them over 0.9. Plain word overlap scored 0.217, 0.277 and 21 of
29 on the first 76. Tests keep both where they are (`pytest -m models` for the models).
