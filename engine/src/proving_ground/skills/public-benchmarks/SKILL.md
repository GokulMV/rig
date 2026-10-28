---
name: public-benchmarks
description: "Measure workflows on public, community benchmarks from the Harbor registry (terminal-bench, SWE-bench, aider-polyglot...): list them, download a small seeded sample of one benchmark's tasks pinned at the registry's commit, and add it as a bench."
values:
  # The registry Harbor itself reads (harbor.constants.DEFAULT_REGISTRY_URL).
  registry_url: "https://raw.githubusercontent.com/laude-institute/harbor/main/registry.json"
  cache_ttl_s: 86400          # refetch the registry once a day; offline, the last copy is used
  fetch_timeout_s: 30
  retry_after_s: 600          # after a failed fetch, wait this long before trying again
  download_timeout_s: 900     # one benchmark sample, all its git fetches
  default_sample: 5           # each task runs with and without the workflow: every task costs money
  max_sample: 50
  seed: 20251025              # the sample is the same for the same benchmark, version and size
  # Where task repos may come from. Anything else is refused before git runs.
  url_schemes: [https]
  # Hugging Face hosts. Their git server can't send a subset (Harbor skips the partial-clone
  # filter there, so git would bring the whole repository), so these come over the Hub's HTTP
  # API instead: the sampled folders are listed, then fetched file by file at the commit.
  hf_hosts: [huggingface.co, hf.co]
  hf_workers: 8               # files fetched at once
  # One download's budget, checked against the Hub's listing before anything comes down
  # (git hosts can't say a size up front; the time budget above still bounds them).
  download_max_bytes: 2000000000
  download_max_files: 3000    # each file is a request; the Hub rate-limits anonymous use
  # Not agent tasks, or too big / not runnable here (Modal-only, RL-training environments,
  # function-call or safety suites, audio). Matched against "name" and "name@version".
  exclude:
    - "*-modal"
    - seta-env
    - termigen-environments
    - kumo@1.0
    - kumo@easy
    - bfcl
    - bfcl_parity
    - strongreject
    - mmau
  # Tasks that ship big Docker images (a whole repo and its toolchain per task): the first run
  # of each pulls or builds gigabytes.
  heavy_images:
    - "swebench*"
    - swtbench-verified
    - swesmith
    - swe-gen-js
    - swe-lancer-diamond
    - "featurebench*"
    - gso
    - vmax-tasks
    - cooperbench
  # Which workflows each benchmark measures, by the disciplines the Lab uses. Unlisted ones
  # are still offered, under "Other public benchmarks".
  disciplines:
    aider-polyglot: [development]
    aime: [research]
    algotune: [development]
    arc_agi_2: [research]
    autocodebench: [development]
    binary-audit: [security]
    bixbench: [research, data]
    bixbench-cli: [research, data]
    codepde: [development, research]
    compilebench: [devops, development]
    cooperbench: [development]
    crustbench: [development]
    dabstep: [data]
    ds-1000: [data, development]
    evoeval: [development]
    gaia: [research]
    gpqa-diamond: [research]
    hello-world: [development]
    humanevalfix: [development, qa]
    ineqmath: [research]
    mmmlu: [research]
    lawbench: [compliance]
    livecodebench: [development]
    mlgym-bench: [research, data]
    otel-bench: [devops]
    reasoning-gym-easy: [research]
    reasoning-gym-hard: [research]
    replicationbench: [research]
    researchcodebench: [research, development]
    rexbench: [research, development]
    simpleqa: [research]
    sldbench: [research, data]
    spider2-dbt: [data]
    swe-gen-js: [development]
    swe-lancer-diamond: [development]
    swebench-verified: [development]
    swebenchpro: [development]
    swebench_multilingual: [development]
    swesmith: [development]
    swtbench-verified: [qa, development]
    terminal-bench: [devops, development]
    terminal-bench-pro: [devops, development]
    terminal-bench-sample: [devops, development]
    openthoughts-tblite: [devops, development]
    usaco: [development]
    bird-bench: [data]
    code-contests: [development]
    vmax-tasks: [development]
    kumo: [research]
    bigcodebench-hard-complete: [development]
    financeagent: [finance, research]
    satbench: [research]
    spreadsheetbench-verified: [finance, data]
    labbench: [research]
    qcircuitbench: [research]
    quixbugs: [development, qa]
    deveval: [development, qa]
    medagentbench: [research]
    pixiu: [finance]
    ade-bench: [data]
    ml-dev-bench: [data, development]
    featurebench-lite: [development]
    featurebench: [development]
    scale-ai/swe-atlas-qna: [development, docs]
    scale-ai/swe-atlas-tw: [qa, development]
    legacy-bench: [development]
    gso: [development]
---

# Public benchmarks

## Rules
- The built-in benches are small and hand-made. Public benchmarks are the broad ones the
  community reports on; measuring a workflow on a sample of one says more about real work.
- The list is the Harbor registry, fetched and kept under the app home for `cache_ttl_s`.
  Offline, the last copy is shown; with none, the list is empty and says why.
- Adding one downloads only a sample of its tasks: `default_sample` unless the person picks
  another size (up to `max_sample`). Every task is run with and without the workflow, on the
  person's sign-in, so a bigger sample costs more. Say so before downloading.
- The sample is seeded (`seed`, the benchmark and its version): the same size gives the same
  tasks, so results stay comparable between people and runs.
- Only the sampled task folders come down: Harbor's own task client does a shallow,
  sparse git checkout at the registry's pinned commit (no shell). Hugging Face repos
  (`hf_hosts`) can't do that over git, so their folders are listed through the Hub's HTTP API
  and fetched file by file at the same commit (large files included). A sample over
  `download_max_bytes` or `download_max_files` is refused before anything downloads; every
  download stops at `download_timeout_s`. Files with a `#!` line are made executable (HTTP
  doesn't carry git's executable bit).
  A task whose commit is not pinned in the registry is fetched at the repo's head and the
  commit it got is recorded.
- Before anything downloads, every entry is checked: an `https` URL (`url_schemes`; on a
  Hugging Face host, exactly one repo), a relative path
  with no `..`, `.` or empty parts and no pattern characters (it becomes a sparse-checkout
  pattern), and a full commit id or none. One bad entry refuses the
  whole sample. Every file the Hub lists must sit inside its task folder. Entries are
  deduplicated by URL, commit and path.
- Each downloaded folder must be a Harbor task (task.toml, instruction.md, environment/,
  tests/test.sh); others are dropped and reported. The rest become an imported bench marked
  public, with its source repo and commit, run as they are and graded by their own tests.
- `heavy_images` benchmarks build or pull large Docker images per task: warn first.
- Removing a public bench removes its downloaded folder and its results.
