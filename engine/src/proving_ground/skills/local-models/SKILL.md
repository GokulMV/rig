---
name: local-models
description: "Models you run yourself (Ollama, LM Studio, llama.cpp, vLLM, Jan) - how they are found, which hosts count as local, how they answer, and what they can be used for."
values:
  # Looked for on this machine when the Lab or the agent picker (top right) opens. Each must answer with the
  # JSON shape named by `list`, or it isn't counted (another app may own the port).
  probes:
    - {kind: ollama, label: Ollama, base: "http://127.0.0.1:11434", list: /api/tags, shape: ollama}
    - {kind: lmstudio, label: LM Studio, base: "http://127.0.0.1:1234", list: /v1/models, shape: openai}
    - {kind: llamacpp, label: llama.cpp, base: "http://127.0.0.1:8080", list: /v1/models, shape: openai}
    - {kind: vllm, label: vLLM, base: "http://127.0.0.1:8000", list: /v1/models, shape: openai}
    - {kind: jan, label: Jan, base: "http://127.0.0.1:1337", list: /v1/models, shape: openai}
  probe_timeout_s: 0.6
  # Only these hosts are accepted: a "local" model must not send your code to someone else's server.
  local_hosts: [localhost, 127.0.0.1, "::1", host.docker.internal]
  local_suffixes: [.local, .lan, .home.arpa, .internal]
  private_networks: true  # 10/8, 172.16/12, 192.168/16, fc00::/7
  # Helper calls (estimates, picks, scenario drafts, the judge): OpenAI-style chat completions
  # with the tool forced; if the server refuses tools, the same ask as plain JSON.
  call_timeout_s: 600
  # Agent time limit on a local model, times the task's own: a real 9B run took 622s on a
  # 600s task with the workflow (two subagents) and timed out.
  timeout_factor: 3
  # Readiness for Claude Code: its prompt is 10-15k tokens before any work.
  min_ctx: 32768
  recommended_ctx: 65536
  agent_max_tokens: 256  # the readiness ask only needs to start a tool call
  min_max_tokens: 4096  # thinking models spend tokens before they answer
  # In the Lab a local model costs nothing per token; its result is a guess like the rest, and
  # small local models usually do worse than the hosted ones, so the guess starts lower.
  lab: {cost: 0.0, prior: -4.0, tier: local}
  # Running an agent on it: the sandbox reaches the host as host.docker.internal.
  sandbox_host: host.docker.internal
  agents:
    claude-code: "Needs the server to speak Anthropic's Messages API (/v1/messages): llama.cpp and Ollama do. Runs with ANTHROPIC_BASE_URL pointed at it."
    opencode: "Any OpenAI-compatible server, as a custom provider."
  # Measure in repo mode ("Rig a Repo"): the run's "Run on" choice, as the Lab's bench panel has.
  # A run there on a local model is free: no sign-in, no budget, and cost can't be a metric
  # (cost_metric: said and refused for the Lab's runs on one too).
  repo:
    sign_in: "{agent} · your sign-in"
    group: "Local Models (Free, on This Machine)"
    cant_run: " · can't run Claude Code"
    none: "No local model added yet: a run on one is free. Start a server (Ollama, or llama.cpp's llama-server with --jinja -c 65536), then add it under Local models below."
    notice: "Claude Code runs in the sandbox with every model it asks for (subagents too) served by {label}, reached as host.docker.internal, with {factor}× each task's time limit. Small local models often can't hold an agent loop: a run full of errors says that, not that the change is bad."
    nudge: "Small local models rarely open a skill they are only offered, so on a local model this starts on."
    confirm: "Real agent runs in Docker sandboxes, on {label} on this machine: free, nothing is billed, so there is no budget to set."
    start: "Start, Free"
    cost_metric: "A local model costs nothing, so cost per solved task can't be compared. Pick tokens or time, or the pass rate."
    # Try it, on Measure in either mode: on the same "Run on" choice (try_note_workflow: the
    # Lab's, a workflow tried in an empty folder). Checking answers against the goal is a model
    # call of its own, so a try that does is priced and capped as usual.
    try_price: "Free: each input runs once on {label} on this machine, with {factor}× the try's time limit. Nothing is billed, so there is no budget to set."
    try_start: "Run {inputs}, Free"
    try_note: "Each input runs once, in an isolated test copy of the repo, never in your own files. Free, on {label}; nothing runs until you click."
    try_note_workflow: "Each input runs once, in an isolated test copy, never in your own files. Free, on {label}; nothing runs until you click."
  # The Lab: a suite runs bench after bench on the sign-in, never on a local model.
  suite_local: "A suite runs on {agent}, your sign-in; pick a single bench to run on a local model."
---

# Local models

## Rules
- A local model is one on this machine or your own network. A public host is refused, with the
  reason: the point of a local model is that nothing leaves.
- Found models are offered, never added silently: the person adds the ones they want.
- No key is stored. If a server wants one, it's typed in this session and held in memory only.
- Test before use, in stages. Helper: one small forced-JSON ask (a model that can't return the
  JSON can't do estimates or judging). Agent, if the server speaks Anthropic's API: a later user
  turn after a reply, tools on, a tool forced; it must come back as a tool call. Context: the
  server's own n_ctx must reach `min_ctx`. Each stage says why it failed. Helper ready and
  Claude Code ready are shown separately; passing the first says nothing about the second.
- A refused later system message is fixed from the server's own template (never a bundled
  one), saved under <home>/templates, with the command to restart it.
- For judging, check the judge against the bench's good and bad examples first (calibration):
  small models often can't tell them apart, and the check shows that.
- A repo's run on Measure can run on a local model too, through the same path as the Lab's: Claude
  Code only, `timeout_factor` times each task's limit, the prompt told to open a skill by default,
  and the run's meta.json naming the model (`local_model`, `local_label`). It needs no sign-in
  and no budget, and is refused when scored on cost (nothing to compare). Try it, on Measure in
  either mode (a repo's skill, or the Lab's workflow), follows the same choice: free, no sign-in,
  the same time limit factor and a skill handed over. Checking answers against the goal is a
  model call of its own, so a try that does is priced and capped as usual.
- The Lab's runs on a local model are refused when scored on cost too, said before the start as
  on Measure. A suite runs on the sign-in only: one asked for on a local model is refused.
- What can't be checked from here is said plainly: speed, and whether an agent loop holds up on
  a small model, are only known by running it.

## Known from real runs (2026-10-25, Colima, llama.cpp 0.7.0, Qwen 3.5 9B Q4)
- Claude Code in the sandbox reached the host's server at host.docker.internal with only that
  host allowed, and fixed a bench bug in both arms (about 2.5 and 7.5 minutes a trial).
- Qwen 3.5's built-in chat template refuses Claude Code's requests ("System message must be at
  the beginning"). The generic chatml template accepts them but loses tool calls (the agent only
  talks). What worked: the model's own template with that one check turned into a system turn,
  passed with `--chat-template-file`.
- Give the server room: Claude Code's prompt is 10-15k tokens before any work (`-c 65536`).
- The small model didn't open the workflow skill on its own, so the "with" arm ran without it.
  Adherence reports that ("never opened the workflow"); read it before reading the result.
