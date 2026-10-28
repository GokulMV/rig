---
name: map-architecture
description: 'Map with Archify: the chosen agent reads the repo read-only and writes an Archify architecture
  spec.'
values:
  agents:
  - claude-code
  tools: Read,Glob,Grep
  permission_mode: dontAsk
  mcp: none (--strict-mcp-config)
  timeout_s: 900
  components_min: 3
  components_max: 18
  kinds:
  - frontend
  - backend
  - database
  - cloud
  - security
  - messagebus
  - external
  env:
    ARCHIFY_UPDATE_CHECK_DISABLED: '1'
  saved_to: .proving-ground/archify.json
  priority:
  - the repo's own Archify spec
  - this mapped spec
  - inferred from the code
---

# Map with Archify

One agent session, asked for first in the UI. The agent's own CLI runs in the repo with read-only
tools (`tools`), no MCP servers and no prompts for permission. It cannot run commands, edit files
or reach the web.

The reply is parsed (the CLI's JSON wrapper, a fenced block, or the outer `{...}`), checked
against the Archify architecture schema, and saved to `saved_to`. Lines to components that
aren't in the spec are dropped. A spec with no components is refused. A part with no incoming
line (other than an actor) is flagged: the diagram doesn't show where its input comes from.

What the canvas shows, in order of `priority`.

## Checked against the code
Every spec, mapped or found in the repo, is checked against the code with no model:
- **found**: an evidence path exists and names the component, or a folder or file is named
  after it, or reading the code found the same part independently;
- **weak**: the repo mentions it, or its evidence exists but doesn't name it;
- **missing**: nothing in the repo shows it.
Parts that reading the code found but the spec leaves out (ways in, outside services, stores)
are listed as missed. A line is found when the code shows the same connection. The canvas
shows the score; weak and missing blocks are drawn dashed with the reason.

## Prompt

Map the architecture of the repository in the current directory as an Archify architecture spec
(tt-a1i/archify). Read the code, manifests, docker/compose files and docs. Show how it really
works: who or what starts each flow, where every part gets its input, what it sends on, and
what isn't wired up yet.

Reply with ONE JSON object and nothing else, in this shape:
{
  "diagram_type": "architecture",
  "meta": {"title": "<repo name> architecture"},
  "components": [
    {"id": "user", "type": "external", "role": "Person", "label": "Learner", "sublabel": "uses any app",
     "evidence": ["README.md"]},
    {"id": "api", "type": "backend", "role": "Planner service", "label": "Brain", "sublabel": "Spring Boot, WebSocket",
     "evidence": ["server/src/main/java/app/Wiring.java"]}
  ],
  "boundaries": [{"kind": "region", "label": "On the user's Mac", "wraps": ["driver", "overlay"]}],
  "connections": [
    {"from": "user", "to": "ext", "label": "asks for help", "evidence": ["extension/src/ask.ts"]},
    {"from": "driver", "to": "api", "label": "screen state", "variant": "planned"}
  ],
  "flows": [
    {"name": "Ask for help", "steps": [
      {"from": "user", "to": "ext", "what": "types a question in the ask bar"},
      {"from": "ext", "to": "api", "what": "sends the question and the page's state over the WebSocket"}
    ]}
  ]
}

Rules:
- "type" is one of: frontend, backend, database, cloud, security, messagebus, external. It only
  sets the colour. "role" says what the part really is, in 1 to 3 words ("Surface driver",
  "Overlay helper", "Planner service", "Job worker", "Person", "Operating system").
- 3 to 18 components: deployable services, apps, processes, data stores, queues, outside
  services, and the actors that start or feed the flows (people, the operating system, other
  apps). Not individual files or classes.
- Every component except actors has at least one incoming connection: show where its input
  comes from. If something that should feed it isn't built yet, add the connection with
  "variant": "planned" and say so in its label. Never leave a part floating.
- "id" is short, lowercase, unique. Every connection's "from" and "to" is a component id.
- Connection labels say what flows and how ("AX tree over JNA", "render requests, stdio JSON",
  "SQL", "jobs"), in a few words.
- 1 to 4 "flows": the main journeys through the system, in order, each step a connection with
  what happens on it in one sentence.
- Only what the repo shows. Do not invent components or connections; a "planned" connection must
  be backed by the repo (a doc, a TODO, an empty module) and cite it.
- Every component lists 1 to 3 "evidence" paths, relative to the repo root: the folder or files
  that show it exists. For an outside service, the file that calls it; for a data store, the
  file that connects to it or the manifest that declares it; for an actor, the file where it
  enters (a UI, an API listener, an OS API call).

## Checked against the code
Every spec, mapped or found in the repo, is checked against the code with no model:
- **found**: an evidence path exists and names the component, or a folder or file is named
  after it, or reading the code found the same part independently;
- **weak**: the repo mentions it, or its evidence exists but doesn't name it;
- **missing**: nothing in the repo shows it.
Parts that reading the code found but the spec leaves out (ways in, outside services, stores)
are listed as missed. A line is found when the code shows the same connection. The canvas
shows the score; weak and missing blocks are drawn dashed with the reason.

## Prompt

Map the architecture of the repository in the current directory as an Archify
architecture spec (tt-a1i/archify). Read the code, manifests, docker/compose files and docs.

Reply with ONE JSON object and nothing else, in this shape:
{
  "diagram_type": "architecture",
  "meta": {"title": "<repo name> architecture"},
  "components": [
    {"id": "api", "type": "backend", "label": "API", "sublabel": "FastAPI",
     "evidence": ["src/shop/api/", "src/shop/api/app.py"]}
  ],
  "boundaries": [{"kind": "region", "label": "Docker network", "wraps": ["api", "db"]}],
  "connections": [{"from": "web", "to": "api", "label": "HTTPS"}]
}

Rules:
- "type" is one of: frontend, backend, database, cloud, security, messagebus, external.
- 3 to 16 components: deployable services, apps, data stores, queues, outside services.
  Not individual files or classes.
- "id" is short, lowercase, unique. Every connection's "from" and "to" is a component id.
- Connection labels say what flows (HTTP, SQL, events, jobs), in a few words.
- Only what the repo shows. Do not invent components.
- Every component lists 1 to 3 "evidence" paths, relative to the repo root: the folder or files
  that show it exists. For an outside service, the file that calls it; for a data store, the
  file that connects to it or the manifest that declares it.
