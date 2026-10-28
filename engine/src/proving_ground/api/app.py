"""The FastAPI app: a workspace of repos, each with its own project state."""

from __future__ import annotations

import json
import math
import threading
import time
from contextlib import nullcontext
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from proving_ground import (
    ablation,
    adherence,
    buildspec,
    catalog_arch,
    difficulty,
    forensics,
    improve,
    lab,
    measurability,
    priors,
    skill_models,
    skills,
    validity,
)
from proving_ground import bench as bench_mod
from proving_ground import compare as compare_mod
from proving_ground import gate as gate_mod
from proving_ground import judge as judge_mod
from proving_ground import local_models as local_mod
from proving_ground import proven as proven_mod
from proving_ground import rig_score as rig_mod
from proving_ground import suite as suite_mod
from proving_ground.agents import AGENTS, CliLogin, Credentials, agent, claude_host_login
from proving_ground.api import rig as rig_api
from proving_ground.api import tryit as try_mod
from proving_ground.api import tutorial as tutorial_api
from proving_ground.api.guard import refusal
from proving_ground.api.runs import RunManager, sse
from proving_ground.api.views import (
    costs_json,
    evidence_json,
    experiment_json,
    items_json,
    scenario_json,
    source_cost,
    summary_json,
    treatments_json,
)
from proving_ground.architecture import load_architecture
from proving_ground.architecture.advise import advise, apply
from proving_ground.architecture.mapper import MapError, map_architecture, supported
from proving_ground.architecture.review import review as review_architecture
from proving_ground.baseline import meta as run_meta
from proving_ground.beforeafter import BeforeAfterError
from proving_ground.beforeafter import compare as compare_change
from proving_ground.beforeafter import refs as repo_refs
from proving_ground.beforeafter import resolve as resolve_change
from proving_ground.budget import (
    CostModel,
    cant_start,
    forecast,
    full_pairs,
    in_trial_option,
    overspend,
    per_pair,
    probe_price,
    status_text,
)
from proving_ground.catalog import (
    CATEGORY_LABEL,
    Catalog,
    GitHub,
    default_github,
    goal_terms,
    install_skill,
    list_skills,
    project_terms,
    rank,
    readme,
    reclassified,
    repo_parts,
)
from proving_ground.catalog import kinds as catalog_kinds
from proving_ground.catalog import page as catalog_page
from proving_ground.catalog.starter import PREFIX as GITHUB_SKILL
from proving_ground.catalog.starter import StarterLibrary
from proving_ground.estimate import EstimateInput, Estimator
from proving_ground.files import (
    PG_DIR,
    FileFormatError,
    ensure_pg_dir,
    load_scenarios,
    load_workflows,
    save_scenario,
)
from proving_ground.generate import client as gen_client
from proving_ground.generate.apply import PlanConflictError
from proving_ground.generate.client import AnthropicClient, ClaudeCliClient, GenerationError
from proving_ground.generate.examples import scenario_example
from proving_ground.generate.prompt import build_prompt
from proving_ground.generate.run import generate as run_generate
from proving_ground.generate.run import plan_tool
from proving_ground.generate.schema import DEFAULT_MIX, InvalidPlanError, parse_mix
from proving_ground.intake import run_intake
from proving_ground.intake.repo import SKILL_RULE, parse_skill, scan_repo, scan_to_text
from proving_ground.models import SLUG, Scenario, ScenarioKind, hash_tree
from proving_ground.placement import Block, place
from proving_ground.prove import ProveJobs, prove_scenario
from proving_ground.public_bench import PublicBenchError, PublicBenches
from proving_ground.recommend import (
    cache_key,
    draft,
    fitting,
    language_note,
    needs_for,
    rough,
    save_draft,
    with_model,
)
from proving_ground.remotes import PROVIDERS as remotes_mod_providers
from proving_ground.remotes import CloneJobs, RemoteError, Remotes, parse_remote, redact
from proving_ground.sandbox.doctor import run_checks
from proving_ground.service import (
    DEFAULT_MODEL,
    ServiceError,
    extend_plan,
    prepare_experiment,
)
from proving_ground.stats import summarize
from proving_ground.store import SourceRow, Store
from proving_ground.workspace import Repo, Workspace

MAX_UPLOAD_BYTES = 25_000_000
HOME = Path.home() / ".proving-ground"
# src/proving_ground/api/app.py -> the repo's web/dist
WEB_DIST = Path(__file__).resolve().parents[4] / "web" / "dist"
NOT_BUILT = """<!doctype html><meta charset="utf-8"><title>Rig</title>
<body style="font: 16px/1.5 system-ui; margin: 48px; max-width: 40rem">
<h1 style="font-size: 22px">The web app is not built yet</h1>
<p>The API is running. Build the app once, then reload this page:</p>
<pre style="background: #f4f6f8; padding: 16px">cd web
npm ci
npm run build</pre></body>"""


class WebFiles(StaticFiles):
    """The built app. The page is never cached, so an updated Rig shows at once; the assets it
    names carry a content hash in their file name, so they can be kept for good."""

    async def get_response(self, path, scope):
        r = await super().get_response(path, scope)
        if path.startswith("assets/"):
            r.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif r.media_type == "text/html":
            r.headers["Cache-Control"] = "no-cache"
        return r


class LabRun(BaseModel):
    workflow: dict
    bench: str
    size: Literal["pilot", "full"] = "pilot"
    budget: float = Field(5.0, gt=0, le=500)
    agent: str = "claude-code"
    auto: bool = True  # keep adding pairs until it's decided (judge-experiment: auto_extend)
    local_model: str | None = None  # run the agent on a model served on this machine instead
    reuse_baseline: bool = True  # false: run the baseline fresh
    nudge_prompt: bool | None = None  # tell the agent to open the treatment; None: workflows
    improved_from: int | None = None  # the experiment this workflow was improved from
    tier: str = skills.value("bench-difficulty", "default_tier")  # standard, hard or all
    # What the run is scored on (rig-score: Metric), as on a repo's Measure. None: the pass rate.
    metric: Literal["pass_rate", "tokens", "cost", "time"] | None = None


class LabProbe(BaseModel):
    """A baseline check: only the agent alone, each task of a tier once (bench-difficulty)."""

    bench: str
    tier: str = skills.value("bench-difficulty", "default_tier")
    agent: str = "claude-code"
    workflow: dict | None = None  # its session model is the model checked (else `model`)
    model: str | None = None
    local_model: str | None = None
    budget: float | None = Field(default=None, gt=0, le=500)  # None: the price, rounded up


class ImproveBody(BaseModel):
    workflow: dict | None = None  # fallback: the saved workflow of the experiment is used
    bench: str
    experiment: int


class SuiteRun(BaseModel):
    workflow: dict
    budget: float = Field(20.0, gt=0, le=500)  # in total, split over the benches
    agent: str = "claude-code"
    size: Literal["pilot", "full"] = skills.value("judge-experiment", "suite")["size"]
    # What every bench's run and the pooled result are scored on (rig-score: Metric, Suites).
    metric: Literal["pass_rate", "tokens", "cost", "time"] | None = None
    # Refused when set: a suite runs on the sign-in (local-models: suite_local).
    local_model: str | None = None


class CompareRun(BaseModel):
    workflows: list[dict]  # 2 to 4, in the order they run (judge-experiment: compare)
    bench: str
    budget: float = Field(20.0, gt=0, le=500)  # in total, split evenly
    agent: str = "claude-code"
    size: Literal["pilot", "full"] = "pilot"


class CompareStanding(BaseModel):
    bench: str
    # {id, name} or the whole workflow: each one's latest valid result on the bench. With its
    # steps, only a result on its current session model counts as its result (an earlier one on
    # another model is shown marked, never ranked).
    workflows: list[dict]
    agent: str = "claude-code"


class LabAblate(BaseModel):
    workflow: dict
    bench: str
    budget: float = Field(5.0, gt=0, le=500)  # the whole job's cap
    agent: str = "claude-code"
    size: Literal["pilot", "full"] = "pilot"
    auto: bool = True
    local_model: str | None = None


class AddLocal(BaseModel):
    base: str
    model: str
    kind: str = "openai"
    label: str | None = None


class LocalHelper(BaseModel):
    id: str | None = None


class ScanLocal(BaseModel):
    base: str


class MakeBench(BaseModel):
    workflow: dict


class ImportSuite(BaseModel):
    path: str
    name: str = Field(min_length=1, max_length=60)
    disciplines: list[str] = []


class AddPublic(BaseModel):
    key: str = Field(min_length=1, max_length=200)  # "name@version" in the Harbor registry
    sample: int = Field(skills.value("public-benchmarks", "default_sample"), ge=1)


_LIM = skills.value("build-spec", "added_limits")
ESTIMATE_SLOTS = skills.value("estimate-effect", "concurrent")
SUMMARY_TTL_S = skills.value("estimate-effect", "summary_ttl_s")
ESTIMATE_BATCH_MAX = skills.value("rough-estimate", "batch_max")
_Name = Annotated[str, Field(min_length=1, max_length=_LIM["name"])]
_Path = Annotated[str, Field(max_length=_LIM["path"])]
_Text = Annotated[str, Field(max_length=_LIM["text"])]
_GhRepo = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", max_length=200)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AddedSkill(_Strict):
    name: _Name
    path: _Path = ""  # its folder on this machine, as the canvas has it; never read
    repo: _GhRepo | None = None  # where it was installed from, when from GitHub
    folder: _Path = ""  # its folder in that repo


class AddedPart(_Strict):
    kind: Annotated[str, Field(min_length=1, max_length=40)]
    name: _Name
    path: _Path
    url: _Path = ""
    description: _Text = ""


class AddedRepo(_Strict):
    repo: _GhRepo
    name: _Name
    category: Annotated[str, Field(max_length=40)] = ""
    parts: list[AddedPart] = Field(default=[], max_length=_LIM["parts"])


class AddedPlanned(_Strict):
    name: _Name
    ref: _Path = ""
    # What to put in it, for a planned part of the agent setup (a CLAUDE.md to add).
    do: _Text = ""


class AddedLink(_Strict):
    from_: _Name = Field(alias="from")
    to: _Name
    relation: Literal["applies to", "uses", "connects to"] = "connects to"


class AddedNote(_Strict):
    on: _Name
    text: Annotated[str, Field(min_length=1, max_length=_LIM["text"])]


class CanvasAdded(_Strict):
    """What was placed on the canvas, as text: it goes into the brief, nothing is read from it."""

    skills: list[AddedSkill] = Field(default=[], max_length=_LIM["items"])
    repos: list[AddedRepo] = Field(default=[], max_length=_LIM["items"])
    planned: list[AddedPlanned] = Field(default=[], max_length=_LIM["items"])
    links: list[AddedLink] = Field(default=[], max_length=_LIM["links"])
    notes: list[AddedNote] = Field(default=[], max_length=_LIM["items"])


class DesignChoice(_Strict):
    """The Garage design chosen in step 2, with the parameter values edited there."""

    id: Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")]
    parameters: Annotated[
        dict[
            Annotated[str, Field(min_length=1, max_length=80)],
            Annotated[str, Field(max_length=_LIM["design_value"])] | int | float | bool,
        ],
        Field(max_length=_LIM["design_parameters"]),
    ] = {}


class BuildSpecRequest(BaseModel):
    source: Literal["repo", "suggested", "workflow", "design"] = "repo"
    workflow: dict | None = None
    # The Garage design chosen in step 2: built from with nothing yet, moved toward in a repo.
    design: DesignChoice | None = None
    # The goal in use in the browser (step 1's box, saved or not): a new project's language, and a
    # repo brief's "Goal". None: a repo's brief reads the repo's saved goal.
    use_case: Annotated[str | None, Field(max_length=4000)] = None
    # The goal step 1 says, whole: BUILD.md's Goal and its rules (goal-rules). Else a workflow's
    # own brief, else the use case (a repo's saved one).
    goal: Annotated[str, Field(max_length=4000)] = ""
    # Parts taken off the canvas (component ids): left out of the brief with their links.
    removed: list[str] = Field(default=[], max_length=_LIM["items"])
    # What was placed on the canvas: skills, GitHub repos and their parts, planned skills, links, notes.
    added: CanvasAdded | None = None


class MatcherChoice(BaseModel):
    on: bool


class LabRandom(BaseModel):
    discipline: str | None = None
    seed: int | None = None
    shown: list[str] = []


class DraftRequest(BaseModel):
    name: str
    need: str = ""
    what: str = ""
    improves: str | None = None


class SaveDraft(BaseModel):
    name: str
    text: str
    improves: str | None = None


class Decision(BaseModel):
    state: Literal["open", "accepted", "dismissed"]


class PlaceRequest(BaseModel):
    name: str
    description: str = ""
    topics: list[str] = []
    category: str = "skill"
    theme: str = ""
    workflow: str | None = None


class MapRequest(BaseModel):
    agent: str = "claude-code"


class UseCase(BaseModel):
    text: str
    # The one-click goal it was picked from (repo-goals: templates), if any.
    template: str | None = Field(default=None, max_length=100)


class InstructionsDraft(BaseModel):
    """An edited copy of the repo's CLAUDE.md (or AGENTS.md), to measure against the committed one."""

    text: Annotated[str, Field(min_length=1, max_length=100_000)]
    file: Literal["CLAUDE.md", "AGENTS.md"] = "CLAUDE.md"
    name: str | None = Field(default=None, pattern=SLUG)


class GoalCheck(BaseModel):
    use_case: str = Field(default="", max_length=4000)


class CheckText(BaseModel):
    check: str = Field(min_length=1, max_length=4000)


class GarageRecommend(BaseModel):
    use_case: str = Field(min_length=1, max_length=4000)
    repo: str | None = None
    explain: bool = False


class GarageWorkflow(BaseModel):
    entry: str = Field(min_length=1, max_length=200)
    use_case: str = Field(default="", max_length=4000)


class RunEstimate(BaseModel):
    """What a run is predicted to cost, before it starts (and before any sign-in)."""

    pairs: int = Field(ge=0, le=10_000)
    agent: str = "claude-code"
    model: str | None = None
    bench: str | None = None
    repo: str | None = None
    workflow: dict | None = None
    treatment_path: str | None = None
    local: bool = False
    budget: float | None = Field(default=None, ge=0)
    # A full run: the pilot's pairs, to say when the budget makes it no better than the pilot.
    pilot_pairs: int | None = Field(default=None, ge=0, le=10_000)
    # The full run's pairs, whatever size is chosen: what "Full" buys at this budget (full_label).
    full_pairs: int | None = Field(default=None, ge=0, le=10_000)
    # One bench or repo: the size chosen and its tasks. Then the engine plans the pairs (a full
    # run grows with the budget: budget.full_pairs), and `pairs`, pilot_pairs, full_pairs are
    # its own, not the request's.
    size: Literal["pilot", "full"] | None = None
    # A saving metric (rig-score: Metric): a full run grows to the guard's pairs, and the answer
    # says what the planned pairs can show (metric_plan).
    metric: Literal["pass_rate", "tokens", "cost", "time"] | None = None
    # "Keep going until it's decided" on (the Lab, or a repo's Measure): the answer says what the
    # run may grow to (`extends`), and on a saving it adds pairs toward the guard's
    # (judge-experiment: auto_extend), and the plan says so.
    auto: bool = False
    tasks: int | None = Field(default=None, ge=1, le=10_000)
    tier: str | None = None  # a bench's tier: prices from that tier's earlier trials only


class AddRepo(BaseModel):
    path: str


class RemoteRepo(BaseModel):
    url: str


class RemoteToken(BaseModel):
    value: str = Field(min_length=1)


class CredentialBody(BaseModel):
    agent: str
    option: str
    value: str = Field(min_length=1)


class BeforeAfterBody(BaseModel):
    """A code change measured before and after (measurability: before_after): the base commit
    is the "without" arm; `after` (a commit or branch, or None: the uncommitted working tree)
    is the "with" arm."""

    base: str = Field(default="HEAD", max_length=256)
    after: str | None = Field(default=None, max_length=256)


class ExperimentRequest(BaseModel):
    # A skill, hook, MCP server or instructions file; empty with `before_after`.
    treatment_path: str = ""
    before_after: BeforeAfterBody | None = None
    budget: float = Field(gt=0)
    n: int = Field(default=40, ge=1, le=2_000)
    model: str = DEFAULT_MODEL
    agent: str = "claude-code"
    kinds: list[ScenarioKind] = []
    scenario_ids: list[str] = []
    resume: int | None = None
    nudge_prompt: bool | None = None  # None: workflows only; plain skills are left to find
    # What the run is scored on (rig-score: Metric). None: the goal's hint, else the pass rate.
    metric: Literal["pass_rate", "tokens", "cost", "time"] | None = None
    # With scenario_ids: the engine plans the pairs for this size (as /api/runs/estimate), not n.
    size: Literal["pilot", "full"] | None = None
    # Run Claude Code on a model served on this machine instead (as LabRun): free, no sign-in.
    local_model: str | None = None
    # Keep adding pairs until it's decided (judge-experiment: auto_extend), as the Lab's: up to
    # the budget, or on a local model (free) the caps. Off unless asked, as before.
    auto: bool = False


class GenerateRequest(BaseModel):
    mix: str = DEFAULT_MIX
    model: str = "claude-opus-5-5"
    max_tokens: int = 32_000
    dry_run: bool = False
    # The goal in use in the browser (an unsaved draft included): written from in place of the
    # repo's saved one, for this call only. None or blank: the saved goal.
    use_case: Annotated[str | None, Field(max_length=4000)] = None


class NewScenario(BaseModel):
    id: str = Field(pattern=SLUG)
    title: str = ""
    kind: ScenarioKind = ScenarioKind.TYPICAL
    instruction: str = Field(min_length=1)
    check: str = Field(min_length=1)
    setup: str | None = None
    step: str | None = None


class EstimateRequest(BaseModel):
    treatment_path: str
    steps: list[str] = []
    quick: bool = False  # the rough guess only: instant, no model
    # Ask the model for a sharper number. Only an explicit request calls a model: never by default.
    model: bool = False


class EstimateItem(BaseModel):
    treatment_path: str
    steps: list[str] = []


class EstimateBatch(BaseModel):
    """Rough guesses only: never a model. Bounded, so one request can't tie up the server."""

    items: Annotated[list[EstimateItem], Field(max_length=ESTIMATE_BATCH_MAX)]


class InstallRequest(BaseModel):
    repo: str = Field(pattern=r"^[\w.-]+/[\w.-]+$")
    path: str = ""


@dataclass
class Project:
    repo: Repo
    root: Path
    store: Store
    pid: int


class CatalogService:
    """Builds the GitHub catalog in the background; the first build takes about a minute."""

    def __init__(self, github: GitHub | None, cache: Path):
        self._github = github
        self._cache = cache
        self._lock = threading.Lock()
        self._building = False
        self.error: str | None = None

    def github(self) -> GitHub:
        if self._github is None:
            self._github = default_github()
        return self._github

    def catalog(self) -> Catalog:
        return Catalog(self.github(), self._cache)

    def snapshot(self) -> dict | None:
        """The cached catalog, starting a build when there is none (or it is stale)."""
        try:
            data = json.loads(self._cache.read_text()) if self._cache.is_file() else None
        except ValueError:
            data = None
        fresh = data is not None and (
            __import__("time").time() - data.get("fetched_at", 0)
            < (600 if data.get("partial") else 24 * 3600)
        )
        if not fresh:
            self.refresh()
        # Each item in the kind it matches best under the current rules (curate-catalog classify).
        return reclassified(data)

    def refresh(self) -> None:
        with self._lock:
            if self._building:
                return
            self._building = True

        def work() -> None:
            try:
                self.catalog().load(refresh=True)
                self.error = None
            except Exception as e:  # noqa: BLE001 - shown to the page
                self.error = str(e)
            finally:
                self._building = False

        threading.Thread(target=work, daemon=True).start()

    @property
    def building(self) -> bool:
        return self._building


def create_app(
    root: Path | None = None,
    user_skills_dir: Path | None = None,
    web_dist: Path | None = None,
    workspace: Workspace | None = None,
    credentials: Credentials | None = None,
    github: GitHub | None = None,
    home: Path | None = None,
    mapper=map_architecture,
    host_login=claude_host_login,
    cli_model=ClaudeCliClient,
    reviewer=None,
    local_http=None,
    remotes: Remotes | None = None,
    public_benches: PublicBenches | None = None,
    skill_matcher: skill_models.Matcher | None = None,
) -> FastAPI:
    home = home or HOME
    ws = workspace or Workspace(None if root else home / "workspace.json")
    if root is not None:
        ws.add(root)
    creds = credentials or Credentials()
    remote_hub = remotes or Remotes(home)
    clone_jobs = CloneJobs()
    user_dir = user_skills_dir or Path.home() / ".claude" / "skills"
    library = home / "library"
    catalog = CatalogService(github, home / "catalog.json")
    starter = StarterLibrary(catalog.github, home / "starter-skills.json")
    projects: dict[str, Project] = {}
    local = local_mod.Registry(home / "local-models.json")
    # The skill matcher's models: fetched on the first Lab visit, used once warm (skill_models).
    matcher = skill_matcher or skill_models.Matcher(
        home / skill_models.V["dir"], warm=lambda m, lib: lab.warm_skills(lib, m)
    )
    skill_models.use(matcher)
    app = FastAPI(title="Rig", docs_url=None, redoc_url=None, openapi_url=None)
    runs = RunManager()
    app.state.workspace, app.state.runs, app.state.credentials = ws, runs, creds

    @app.middleware("http")
    async def guard(request: Request, call_next):
        return refusal(request) or await call_next(request)

    opening = threading.Lock()

    def open_project(r: Repo) -> Project:
        # One at a time: two requests creating the same database at once collide on its tables.
        with opening:
            if r.id not in projects:
                rp = Path(r.root)
                ensure_pg_dir(rp)
                store = Store.for_project(rp)
                projects[r.id] = Project(r, rp, store, store.ensure_project(str(rp)))
            return projects[r.id]

    def current(repo: str | None = Query(default=None)) -> Project:
        repos = ws.repos()
        if not repos:
            raise HTTPException(409, "Attach a repo first.")
        r = ws.get(repo) if repo else repos[0]
        if r is None:
            raise HTTPException(404, f"No repo with id {repo!r}.")
        return open_project(r)

    def use_case_of(p: Project) -> str | None:
        return next((s.text for s in p.store.list_sources(p.pid) if s.kind == "usecase"), None)

    def goal_metric(p: Project) -> str | None:
        """The goal's metric hint, kept beside the use case (its source's meta `metric`) by a
        goal template; None when there is none or it isn't one of the rig-score metrics."""
        src = next((s for s in p.store.list_sources(p.pid) if s.kind == "usecase"), None)
        hint = (src.meta or {}).get("metric") if src else None
        return hint if hint in rig_mod.M["ids"] else None

    def run_metric(root: Path, eid: int) -> str:
        """What a run is scored on: its meta.json's `metric`; a run from before the choice
        existed is scored on the pass rate."""
        got = run_meta(root, eid).get("metric")
        return got if got in rig_mod.M["ids"] else rig_mod.M["default"]

    def scenarios(p: Project) -> list[Scenario]:
        try:
            return load_scenarios(p.root)
        except FileFormatError as e:
            raise HTTPException(422, str(e)) from e

    def workflows(p: Project):
        try:
            return load_workflows(p.root)
        except FileFormatError as e:
            raise HTTPException(422, str(e)) from e

    def repo_meta(p: Project) -> dict:
        repo = [s for s in p.store.list_sources(p.pid) if s.kind == "repo"]
        if repo and repo[-1].meta.get("skill_rule") != SKILL_RULE:
            # Read before the repo's skills were only the ones an agent loads: read it again.
            run_intake(p.store, p.root)
            repo = [s for s in p.store.list_sources(p.pid) if s.kind == "repo"]
        return repo[-1].meta if repo else {}

    def anthropic_key() -> str | None:
        env = creds.env_for("claude-code")
        return env.get("ANTHROPIC_API_KEY")

    # ---------- Workspace, agents, sign-in ----------

    @app.get("/api/repos")
    def get_repos():
        return [asdict(r) for r in ws.repos()]

    def home_warning(r: Repo) -> str | None:
        # Colima and some Docker VMs share only the home folder with the sandboxes.
        if Path(r.root).resolve().is_relative_to(Path.home().resolve()):
            return None
        return (
            "This repo is outside your home folder. Colima and some Docker VMs share only "
            "the home folder, so its sandboxes may see an empty project. Run `pg doctor` to "
            "check, or move it under ~."
        )

    @app.post("/api/repos")
    def add_repo(body: AddRepo):
        try:
            r = ws.add(Path(body.path))
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        p = open_project(r)
        if not repo_meta(p):
            run_intake(p.store, p.root)
        out = asdict(r)
        if w := home_warning(r):
            out["warning"] = w
        return out

    @app.post("/api/repos/remote")
    def add_remote_repo(body: RemoteRepo):
        try:
            remote = parse_remote(body.url)
        except RemoteError as e:
            raise HTTPException(422, str(e)) from e
        dest = remote_hub.dest_for(remote)

        def work(stage) -> dict:
            token = remote_hub.token_for(remote)
            try:
                if not (dest / ".git").exists():
                    stage(f"Cloning {remote.full_name} from {remote.host}…")
                    remote_hub.clone(remote.url, dest, token)
                stage("Reading the repo…")
                r = ws.add(dest, remote.url, remote.provider)
                p = open_project(r)
                if not repo_meta(p):
                    run_intake(p.store, p.root)
            except Exception as e:
                raise RuntimeError(redact(str(e), token)) from None
            out = {"repo": asdict(r)}
            if w := home_warning(r):
                out["warning"] = w
            return out

        return {"job": clone_jobs.start(remote.url, work)["id"]}

    @app.get("/api/repos/remote/{job}")
    def remote_repo_job(job: str):
        j = clone_jobs.get(job)
        if j is None:
            raise HTTPException(404, "No such clone.")
        return j

    @app.post("/api/repos/{rid}/pull")
    def pull_repo(rid: str):
        r = ws.get(rid)
        if r is None:
            raise HTTPException(404, f"No repo with id {rid!r}.")
        if not r.remote:
            raise HTTPException(422, "This repo wasn't cloned from GitHub or GitLab.")
        token = remote_hub.token_for(parse_remote(r.remote))
        try:
            head = remote_hub.pull(Path(r.root), token)
        except RemoteError as e:
            raise HTTPException(502, redact(str(e), token)) from e
        p = open_project(r)
        run_intake(p.store, p.root)
        return {"repo": asdict(r), "head": head}

    @app.get("/api/remotes/status")
    def remotes_status():
        return remote_hub.status()

    def remote_provider(provider: str) -> str:
        if provider not in remotes_mod_providers:
            raise HTTPException(404, f"No provider {provider!r}.")
        return provider

    @app.put("/api/remotes/{provider}/token")
    def put_remote_token(provider: str, body: RemoteToken):
        remote_provider(provider)
        token = body.value.strip()
        try:
            account = remote_hub.verify_token(provider, token)
            remote_hub.tokens.set(provider, token)
        except RemoteError as e:
            raise HTTPException(422, redact(str(e), token)) from e
        return {"provider": provider, "signed_in": True, "account": account}

    @app.delete("/api/remotes/{provider}/token")
    def delete_remote_token(provider: str):
        remote_provider(provider)
        remote_hub.tokens.clear(provider)
        return {"provider": provider, "token_set": False}

    @app.get("/api/remotes/{provider}/repos")
    def remote_repos(provider: str, q: str = ""):
        remote_provider(provider)
        try:
            return remote_hub.list_mine(provider, q)
        except RemoteError as e:
            raise HTTPException(422, str(e)) from e

    @app.delete("/api/repos/{rid}")
    def remove_repo(rid: str):
        ws.remove(rid)
        projects.pop(rid, None)
        return {"removed": rid}

    logins: dict[str, CliLogin] = {}
    _host: dict = {"at": 0.0, "value": None}

    def host() -> dict | None:
        # `claude auth status` takes a moment: ask at most once a minute.
        if time.time() - _host["at"] > 60:
            _host.update(at=time.time(), value=host_login())
        return _host["value"]

    def login_job(aid: str) -> CliLogin:
        try:
            agent(aid)
        except KeyError as e:
            raise HTTPException(404, f"No agent {aid!r}.") from e
        if aid not in logins:
            logins[aid] = CliLogin(creds, aid)
        return logins[aid]

    @app.get("/api/agents")
    def get_agents():
        # Claude Code's own login on this Mac: enough for Map with Archify, not for sandboxes.
        here = host()
        return [
            {
                "id": a.id,
                "label": a.label,
                "default_model": a.default_model,
                "sign_in": creds.status(a.id),
                "ready": creds.ready(a.id),
                "host": here if a.id == "claude-code" else None,
                # Stops itself mid-trial at the budget (trial-budget: in_trial_cap); else only
                # pairs that would go over aren't started.
                "budget_cap": in_trial_option(a.id) is not None,
                "login": (
                    {"auto": bool(a.login.cmd), "install": a.login.install} if a.login else None
                ),
            }
            for a in AGENTS
        ]

    @app.get("/api/agents/{aid}/login")
    def login_status(aid: str):
        return login_job(aid).view()

    @app.post("/api/agents/{aid}/login", status_code=202)
    def login_start(aid: str):
        return login_job(aid).start()

    @app.delete("/api/agents/{aid}/login")
    def login_cancel(aid: str):
        job = login_job(aid)
        job.cancel()
        return job.view()

    @app.put("/api/credentials")
    def put_credentials(body: CredentialBody):
        try:
            agent(body.agent)
            creds.set(body.agent, body.option, body.value)
        except (KeyError, ValueError) as e:
            raise HTTPException(422, str(e)) from e
        return {"agent": body.agent, "ready": creds.ready(body.agent)}

    @app.delete("/api/credentials/{aid}")
    def delete_credentials(aid: str):
        creds.clear(aid)
        return {"agent": aid, "ready": creds.ready(aid)}

    # ---------- Catalog ----------

    @app.get("/api/catalog")
    def get_catalog(
        category: str = "skill",
        view: str = "recommended",
        q: str = "",
        repo: str | None = Query(default=None),
    ):
        # "all": every kind at once, for searching from the Library's home.
        if category not in CATEGORY_LABEL and category != "all":
            raise HTTPException(422, f"category must be all or one of {', '.join(CATEGORY_LABEL)}")
        data = catalog.snapshot()
        if data is None:
            return {
                "loading": True,
                "items": [],
                "themes": {},
                "kinds": catalog_kinds(),
                "error": catalog.error,
            }
        terms: set[str] = set()
        goal: set[str] = set()
        langs: dict = {}
        if ws.repos():
            try:
                p = current(repo)
                meta = repo_meta(p)
                langs = meta.get("languages", {})
                uc = next(
                    (s.text for s in p.store.list_sources(p.pid) if s.kind == "usecase"), None
                )
                terms = project_terms(meta.get("stack", []), meta.get("languages", {}), uc)
                goal = goal_terms(uc)
            except HTTPException:
                pass
        shown = catalog_page(data["items"], category, view, q, terms, goal)
        if langs:
            shown["items"] = [
                i | {"fit_note": n}
                if (n := language_note(i.get("name", ""), i.get("description", ""), langs))
                else i
                for i in shown["items"]
            ]
        return {
            "loading": catalog.building,
            "partial": data.get("partial", False),
            "fetched_at": data.get("fetched_at"),
            **shown,
            "terms": sorted(terms),
            "error": catalog.error,
        }

    @app.post("/api/catalog/refresh")
    def refresh_catalog():
        catalog.refresh()
        return {"loading": True}

    readmes: dict[str, str] = {}

    @app.get("/api/catalog/readme")
    def get_readme(name: str):
        gh = catalog.github()
        try:
            if name not in readmes:
                readmes[name] = readme(gh, name)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        return {"name": name, "text": readmes[name], "url": f"https://github.com/{name}"}

    @app.get("/api/skill")
    def get_skill(path: str, p: Project = Depends(current)):
        # Only skills the app lists: in this repo, your skills folder, or the library.
        f = Path(path).resolve() / "SKILL.md"
        roots = [p.root.resolve(), user_dir.resolve(), library.resolve()]
        if not f.is_file() or not any(f.is_relative_to(r) for r in roots):
            raise HTTPException(404, "No such skill.")
        text = f.read_text(errors="replace")
        files = sorted(str(x.relative_to(f.parent)) for x in f.parent.rglob("*") if x.is_file())
        return {"path": str(f.parent), "text": text[:12000], "files": files[:50]}

    @app.get("/api/catalog/parts")
    def catalog_parts(name: str = Query(pattern=r"^[\w.-]+/[\w.-]+$")):
        """A harness or workflow repository's parts and their links, to lay out on the canvas."""
        try:
            return repo_parts(catalog.github(), name)
        except Exception as e:  # noqa: BLE001 - GitHub down or the repo gone: say so
            raise HTTPException(502, f"Couldn't read {name} from GitHub: {e}") from e

    @app.get("/api/catalog/skills")
    def catalog_skills(name: str = Query(pattern=r"^[\w.-]+/[\w.-]+$")):
        try:
            return list_skills(catalog.github(), name)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"Could not read {name} from GitHub: {e}") from e

    @app.post("/api/catalog/install")
    def catalog_install(body: InstallRequest):
        try:
            path = install_skill(catalog.github(), body.repo, body.path, library)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"Could not download from GitHub: {e}") from e
        return {"path": str(path), "name": path.name}

    # ---------- One repo ----------

    @app.get("/api/project")
    def project(p: Project = Depends(current)):
        sources = p.store.list_sources(p.pid)
        meta = repo_meta(p)
        graph = next((s for s in sources if s.kind == "graph"), None)
        goal = next((s for s in sources if s.kind == "usecase"), None)
        use_case = goal.text if goal else None
        items = scenarios(p)
        return {
            "id": p.repo.id,
            "name": p.root.name,
            "root": str(p.root),
            "key_set": creds.ready("claude-code"),
            "scanned": bool(meta),
            "scan": {
                "files": meta.get("files", 0),
                "truncated": meta.get("truncated", False),
                "languages": meta.get("languages", {}),
                "stack": meta.get("stack", []),
                "agent_setup": meta.get("agent_setup", []),
                "skills": meta.get("skill_details", []),
            },
            # The coding agent's setup, as the canvas's first lane draws it.
            "agent": buildspec.setup_lane(p.root, meta),
            # Placeholders for a new scenario, in this repo's language or work (generate-scenarios).
            "example": scenario_example(meta, use_case),
            "graph": graph.meta | {"name": graph.name} if graph else None,
            "sources": [
                {"id": s.id, "kind": s.kind, "name": s.name, "chars": len(s.text)} for s in sources
            ],
            "use_case": use_case,
            # The one-click goal it was saved from and what that goal is about (repo-goals):
            # pass_rate, tokens, cost or time; None for a goal typed from scratch.
            "goal_template": (goal.meta.get("template") if goal else None),
            "goal_metric": goal_metric(p),  # only a rig-score metric, else None
            "counts": {
                # approved, runnable (a command for a check) and the approved ones that aren't.
                **validity.counts(items),
                "workflows": len(workflows(p)),
                "experiments": len(p.store.list_experiments(p.pid)),
            },
        }

    @app.get("/api/architecture")
    def architecture(refresh: bool = False, p: Project = Depends(current)):
        return load_architecture(p.root, refresh=refresh).dump()

    # "Map with Archify": one agent session per repo at a time, in the background.
    maps: dict[str, dict] = {}

    @app.get("/api/architecture/map")
    def map_status(p: Project = Depends(current)):
        return maps.get(p.repo.id, {"state": "idle"})

    @app.post("/api/architecture/map", status_code=202)
    def start_map(body: MapRequest, p: Project = Depends(current)):
        if not supported(body.agent):
            raise HTTPException(
                400,
                "Map with Archify runs through Claude Code for now: click the agent at the top right and pick it.",
            )
        if maps.get(p.repo.id, {}).get("state") == "running":
            raise HTTPException(409, "Already mapping this repo.")
        # Only the secret itself: the *_FORCE_* flags are for sandboxed trials, not this CLI.
        env = {k: v for k, v in creds.env_for(body.agent).items() if "_FORCE_" not in k}
        job = {"state": "running", "agent": body.agent, "started_at": time.time()}
        maps[p.repo.id] = job

        def work():
            try:
                mapper(p.root, body.agent, env)
                job.update(state="done")
            except MapError as e:
                job.update(state="error", error=str(e))
            except Exception as e:  # noqa: BLE001 - shown to the user, never raised in a thread
                job.update(state="error", error=f"Mapping failed: {e}")

        threading.Thread(target=work, daemon=True).start()
        return job

    # ---------- Suggestions and placement ----------

    def _workflow(p: Project, wid: str | None):
        ws_ = workflows(p)
        return next((w for w in ws_ if w.id == wid), ws_[0] if ws_ else None)

    def _suggest_file(p: Project) -> Path:
        return p.root / PG_DIR / "suggestions.json"

    def _suggest_state(p: Project) -> dict:
        try:
            return json.loads(_suggest_file(p).read_text())
        except (OSError, ValueError):
            return {"decisions": {}, "review": []}

    def _save_suggest(p: Project, data: dict) -> None:
        _suggest_file(p).write_text(json.dumps(data, indent=2))

    def _proposals(p: Project, wid: str | None) -> list[dict]:
        arch = load_architecture(p.root)
        w = _workflow(p, wid)
        approved: dict[str, int] = {}
        for s in scenarios(p):
            if s.step and s.check_status == "approved":
                approved[s.step] = approved.get(s.step, 0) + 1
        rules = advise(
            p.root,
            arch,
            [(st.name, st.type.value) for st in w.steps] if w else None,
            approved,
            scan_repo(p.root).agent_setup,
        )
        state = _suggest_state(p)
        out = [x.dump() for x in rules] + state.get("review", [])
        for x in out:
            x["state"] = state["decisions"].get(x["id"], "open")
            # Whether Measure can test it (measurability), shown on its card.
            x["measure"] = measurability.of_proposal(x)
        return out

    @app.get("/api/suggestions")
    def get_suggestions(workflow: str | None = None, p: Project = Depends(current)):
        return {
            "proposals": _proposals(p, workflow),
            "review": reviews.get(p.repo.id, {"state": "idle"}),
        }

    @app.put("/api/suggestions/{pid}")
    def decide(pid: str, body: Decision, p: Project = Depends(current)):
        state = _suggest_state(p)
        state["decisions"][pid] = body.state
        _save_suggest(p, state)
        return {"id": pid, "state": body.state}

    @app.get("/api/architecture/proposed")
    def proposed(
        workflow: str | None = None, preview: str | None = None, p: Project = Depends(current)
    ):
        # The accepted suggestions, or just the one being looked at (preview); what they take
        # away stays on the canvas, marked, so the change shows. Open ones are only drawn when
        # previewed: accepting is what puts one in the proposed architecture.
        props = _proposals(p, workflow)
        if preview:
            accepted = [x for x in props if x["id"] == preview]
        else:
            accepted = [x for x in props if x["state"] == "accepted"]
        a = apply(load_architecture(p.root), accepted, keep_removed=True)
        # Which suggestion drew each new or taken-away part, so its details can name it.
        origins: dict[str, dict] = {}
        for x in accepted:
            d = x.get("delta") or {}
            for cid in [c.get("id") for c in d.get("add", [])] + list(d.get("remove", [])):
                if cid and cid not in origins:
                    origins[cid] = {"id": x["id"], "title": x["title"], "state": x["state"]}
        diff = {
            "added": [c.label for c in a.components if c.source == "proposed"],
            "removed": [c.label for c in a.components if c.source == "removed"],
            "connected": sum(1 for c in a.connections if c.variant == "added"),
            "disconnected": sum(1 for c in a.connections if c.variant == "removed"),
            "suggestions": len(accepted),
            # The ones that change the diagram (add, take away or link parts); the rest are only
            # in the brief.
            "drawn": sum(
                1
                for x in accepted
                if any(
                    (x.get("delta") or {}).get(k)
                    for k in ("add", "remove", "connect", "disconnect")
                )
            ),
            # In the brief's own unit: accepted suggestions that are tasks (they change code or
            # config), the ones that only fix the diagram, and the ones still open.
            "tasks": sum(
                1 for x in props if x["state"] == "accepted" and not buildspec.diagram_only(x)
            ),
            "notes": sum(
                1 for x in props if x["state"] == "accepted" and buildspec.diagram_only(x)
            ),
            "open": sum(1 for x in props if x["state"] == "open"),
            # The same, by name: what "With the accepted suggestions" adds to the brief, each with
            # its measurability state, so Ship marks them as Build's badges do.
            "task_items": [
                {"id": x["id"], "title": x["title"], "measure": x["measure"]}
                for x in props
                if x["state"] == "accepted" and not buildspec.diagram_only(x)
            ],
            "note_items": [
                {"id": x["id"], "title": x["title"], "measure": x["measure"]}
                for x in props
                if x["state"] == "accepted" and buildspec.diagram_only(x)
            ],
        }
        spec = {
            "diagram_type": "architecture",
            "meta": {"title": a.title},
            "components": [
                {
                    k: v
                    for k, v in c.model_dump(mode="json").items()
                    if k in ("id", "type", "role", "label", "sublabel", "evidence") and v
                }
                for c in a.components
            ],
            "boundaries": [b.model_dump(mode="json") for b in a.boundaries],
            "connections": [
                {
                    k: v
                    for k, v in c.model_dump(mode="json", by_alias=True).items()
                    if k in ("from", "to", "label", "variant") and v
                }
                for c in a.connections
            ],
        }
        return {
            "architecture": a.dump(),
            "archify": spec,
            "accepted": [x["id"] for x in accepted if x["state"] == "accepted"],
            "shown": [x["id"] for x in accepted],
            "origins": origins,
            "diff": diff,
        }

    reviews: dict[str, dict] = {}
    reviewer = reviewer or review_architecture

    @app.post("/api/suggestions/review", status_code=202)
    def start_review(body: MapRequest, p: Project = Depends(current)):
        if not supported(body.agent):
            raise HTTPException(
                400,
                "The deeper review runs through Claude Code for now: click the agent at the top right and pick it.",
            )
        if reviews.get(p.repo.id, {}).get("state") == "running":
            raise HTTPException(409, "Already reviewing this repo.")
        env = {k: v for k, v in creds.env_for(body.agent).items() if "_FORCE_" not in k}
        job = {"state": "running", "agent": body.agent, "started_at": time.time()}
        reviews[p.repo.id] = job
        arch = load_architecture(p.root)

        def work():
            try:
                found = reviewer(p.root, arch, body.agent, env)
                state = _suggest_state(p)
                state["review"] = [x.dump() for x in found]
                _save_suggest(p, state)
                job.update(state="done", count=len(found))
            except MapError as e:
                job.update(state="error", error=str(e))
            except Exception as e:  # noqa: BLE001 - shown to the user, never raised in a thread
                job.update(state="error", error=f"Review failed: {e}")

        threading.Thread(target=work, daemon=True).start()
        return job

    @app.get("/api/suggestions/review")
    def review_status(p: Project = Depends(current)):
        return reviews.get(p.repo.id, {"state": "idle"})

    @app.post("/api/place")
    def place_item(body: PlaceRequest, p: Project = Depends(current)):
        arch = load_architecture(p.root)
        # People and the OS start flows; nothing is installed next to them.
        blocks = [
            Block(f"arch:{c.id}", c.type, c.label, f"{c.role or ''} {c.sublabel or ''}")
            for c in arch.components
            if c.role not in ("Person", "Operating system")
        ]
        w = _workflow(p, body.workflow)
        for n, st in enumerate(w.steps if w else []):
            blocks.append(Block(f"step:{st.name}", "step", st.name, st.why, st.type.value, n))
        meta = repo_meta(p) or {}
        for s in buildspec.setup_lane(p.root, meta):
            if s["label"] != "Skills":  # the repo's skills are drawn one by one
                blocks.append(
                    Block(
                        s["id"],
                        "setup",
                        s["label"],
                        f"agent setup {s['detail']}",
                        present=s["present"],
                    )
                )
        return place(
            blocks,
            body.name,
            body.description,
            body.topics,
            body.category,
            body.theme,
            meta.get("languages", {}),
        )

    @app.post("/api/goal/check")
    def goal_check(body: GoalCheck, p: Project = Depends(current)):
        """A goal (saved or a draft) against the repo: a language or tool it names that the repo
        has no files in (build-spec: stack_words). No model call."""
        meta = repo_meta(p) or {
            "languages": scan_repo(p.root).languages
        }  # not read yet: read it now
        return {"warnings": buildspec.stack_warnings(body.use_case, meta)}

    @app.put("/api/usecase")
    def put_use_case(body: UseCase, p: Project = Depends(current)):
        text = body.text.strip()
        if not text:
            raise HTTPException(422, "Describe the use case in a sentence or two.")
        before = use_case_of(p)
        if validity.use_case_tag(before) != validity.use_case_tag(text):
            # Generated scenarios from before scenarios remembered their use case were written for
            # the one being replaced: stamp them with it, so they read "written for a different goal".
            for s in scenarios(p):
                if s.origin == "generated" and s.written_for is None:
                    save_scenario(
                        p.root, s.model_copy(update={"written_for": validity.use_case_tag(before)})
                    )
        # A goal picked from a template keeps it, and its metric, while it still starts with the
        # template's text (repo-goals); a goal typed from scratch has neither.
        t = next(
            (
                x
                for x in skills.value("repo-goals", "templates")
                if x["id"] == body.template and text.startswith(x["text"].strip())
            ),
            None,
        )
        meta = {"template": t["id"], "metric": t["metric"]} if t else {}
        p.store.add_source(p.pid, "usecase", "use-case", text, meta)
        return {
            "use_case": text,
            "goal_template": meta.get("template"),
            "goal_metric": meta.get("metric"),
        }

    @app.post("/api/intake")
    def intake(p: Project = Depends(current)):
        run_intake(p.store, p.root)
        load_architecture(p.root, refresh=True)
        return project(p)

    @app.post("/api/sources")
    async def upload(files: list[UploadFile], p: Project = Depends(current)):
        up = p.root / PG_DIR / "uploads"
        up.mkdir(parents=True, exist_ok=True)
        paths = []
        for f in files:
            name = Path(f.filename or "").name
            if not name or name.startswith("."):
                raise HTTPException(422, f"Unusable file name: {f.filename!r}")
            data = await f.read(MAX_UPLOAD_BYTES + 1)
            if len(data) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, f"{name} is over 25 MB.")
            (up / name).write_bytes(data)
            paths.append(up / name)
        res = run_intake(p.store, p.root, paths)
        for name in res.skipped:
            (up / name).unlink(missing_ok=True)
        names = {x.name for x in paths}
        return {"added": [[k, n] for k, n in res.sources if n in names], "skipped": res.skipped}

    @app.post("/api/generate")
    def generate(body: GenerateRequest, p: Project = Depends(current)):
        try:
            kinds = parse_mix(body.mix)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        existing = {s.id for s in scenarios(p)}
        sources = p.store.list_sources(p.pid)
        draft = (body.use_case or "").strip()
        if draft:  # the draft stands in for the saved goal; nothing is written back
            sources = [s for s in sources if s.kind != "usecase"] + [
                SourceRow(id=0, kind="usecase", name="use-case", text=draft, meta={})
            ]
        if not sources:
            raise HTTPException(422, "Nothing to work from yet. Scan the repo or add a use case.")
        mix = {k.value: n for k, n in kinds.items()}
        if body.dry_run:
            pr = build_prompt(sources, kinds, existing)
            return {
                "included": pr.included,
                "dropped": pr.dropped,
                "tokens_est": (pr.chars + len(json.dumps(plan_tool()))) // 4,
                "model": body.model,
                "mix": mix,
            }
        if not anthropic_key():
            raise HTTPException(
                400,
                "Add an Anthropic API key to generate tasks: click the agent at the top right.",
            )
        try:
            res = run_generate(
                p.root, sources, kinds, gen_client.make_client(), body.model, body.max_tokens
            )
        except InvalidPlanError as e:
            return JSONResponse(
                {
                    "detail": "The generated plan was rejected. Nothing was written.",
                    "problems": e.problems,
                },
                422,
            )
        except PlanConflictError as e:
            raise HTTPException(409, str(e)) from e
        except GenerationError as e:
            raise HTTPException(502, str(e)) from e
        # Each generated scenario remembers the use case it was written for (evidence-validity):
        # the draft when one was sent, so saving that draft later keeps them current.
        goal = draft or use_case_of(p)
        stamped = [
            s.model_copy(update={"written_for": validity.use_case_tag(goal)}) for s in res.scenarios
        ]
        for s in stamped:
            save_scenario(p.root, s)
        return {
            "workflow": res.plan.workflow.model_dump(mode="json"),
            "scenarios": [scenario_json(p.root, s, goal) for s in stamped],
            "treatments": [t.model_dump(mode="json") for t in res.plan.treatments],
            "tokens": {"in": res.tokens_in, "out": res.tokens_out},
            "written": len(res.written),
        }

    @app.post("/api/scenarios")
    def create_scenario(body: NewScenario, p: Project = Depends(current)):
        if any(s.id == body.id for s in scenarios(p)):
            raise HTTPException(409, f"A task called {body.id!r} already exists.")
        if why := validity.check_problem(body.check):
            raise HTTPException(422, why)
        try:
            s = Scenario(
                id=body.id,
                title=body.title or body.id,
                kind=body.kind,
                instruction=body.instruction,
                check=body.check,
                setup=body.setup,
                step=body.step,
                origin="user",
                # You wrote the check yourself, so it counts as reviewed.
                check_status="approved",
            )
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        save_scenario(p.root, s)
        return scenario_json(p.root, s, use_case_of(p))

    @app.post("/api/scenarios/{sid}/approve")
    def approve(sid: str, p: Project = Depends(current)):
        s = next((x for x in scenarios(p) if x.id == sid), None)
        if s is None:
            raise HTTPException(404, f"No task with id '{sid}'.")
        if not s.check:
            raise HTTPException(422, f"Task '{sid}' has no check. Add one before approving.")
        if why := validity.check_problem(s.check):
            raise HTTPException(422, f"Task '{sid}' can't be approved: {why}")
        s = s.model_copy(update={"check_status": "approved"})
        save_scenario(p.root, s)
        return scenario_json(p.root, s, use_case_of(p))

    @app.put("/api/scenarios/{sid}/check")
    def set_check(sid: str, body: CheckText, p: Project = Depends(current)):
        """A task's check rewritten as a command (one whose check was prose never runs). Writing
        it yourself counts as reviewed, as for a task you add."""
        s = next((x for x in scenarios(p) if x.id == sid), None)
        if s is None:
            raise HTTPException(404, f"No task with id '{sid}'.")
        check = body.check.strip()
        if why := validity.check_problem(check):
            raise HTTPException(422, why)
        s = s.model_copy(update={"check": check, "check_status": "approved"})
        save_scenario(p.root, s)
        return scenario_json(p.root, s, use_case_of(p))

    prove_jobs = ProveJobs()

    @app.post("/api/scenarios/{sid}/prove")
    def prove(sid: str, p: Project = Depends(current)):
        s = next((x for x in scenarios(p) if x.id == sid), None)
        if s is None:
            raise HTTPException(404, f"No task with id '{sid}'.")
        if not s.check:
            raise HTTPException(422, f"Task '{sid}' has no check to prove.")
        prove_jobs.start((p.repo.id, sid), lambda: prove_scenario(s, p.root))
        return {"status": "running"}

    @app.get("/api/scenarios/{sid}/prove")
    def prove_status(sid: str, p: Project = Depends(current)):
        return prove_jobs.get((p.repo.id, sid))

    @app.get("/api/workflows")
    def get_workflows(p: Project = Depends(current)):
        return [w.model_dump(mode="json") for w in workflows(p)]

    @app.get("/api/scenarios")
    def get_scenarios(p: Project = Depends(current)):
        goal = use_case_of(p)
        return [scenario_json(p.root, s, goal) for s in scenarios(p)]

    @app.get("/api/treatments")
    def get_treatments(p: Project = Depends(current)):
        meta = repo_meta(p)
        out = treatments_json(
            p.root,
            p.store,
            p.store.list_experiments(p.pid),
            meta.get("skill_details", []),
            user_dir,
            library,
        )
        langs = meta.get("languages", {})
        for g in ("repo", "user", "installed", "created"):
            for x in out.get(g, []):
                if langs and (note := language_note(x["name"], x["description"], langs)):
                    x["fit_note"] = note
            # A skill for a language the repo has none of goes last in its group, still listed.
            out[g] = sorted(out.get(g, []), key=lambda x: "fit_note" in x)
        return out

    @app.post("/api/treatments/instructions")
    def save_instructions_draft(body: InstructionsDraft, p: Project = Depends(current)):
        """Save an edited copy of the repo's instructions under .proving-ground/ (treatment-kinds:
        drafts_dir), where no snapshot includes it: measured, it replaces the committed file in
        the "with" arm only."""
        v = skills.load("treatment-kinds").values
        if not body.text.strip():
            raise HTTPException(422, "The edited copy is empty.")
        folder = p.root / v["drafts_dir"] / (body.name or v["draft_name"])
        folder.mkdir(parents=True, exist_ok=True)
        for n in v["instruction_files"]:  # one instructions file per draft
            (folder / n).unlink(missing_ok=True)
        (folder / body.file).write_text(body.text if body.text.endswith("\n") else body.text + "\n")
        return {"path": str(folder.resolve()), "name": folder.name, "file": body.file}

    def reachable_model():
        """The local model chosen for helper calls, else an API key, else Claude Code's own
        login here, else nothing."""
        lm = local.helper()
        if lm is not None:
            return local_mod.OpenAICompatClient(lm, local_http)
        key = anthropic_key()
        if key:
            import anthropic

            return AnthropicClient(anthropic.Anthropic(api_key=key, max_retries=2))
        return cli_model() if host() else None

    @app.get("/api/recommend")
    def recommend_for_repo(
        category: str = "skill",
        refresh: bool = False,
        workflow: str | None = None,
        model: bool = False,  # ask the model to pick; without it, never a model call
        p: Project = Depends(current),
    ):
        if category not in CATEGORY_LABEL:
            raise HTTPException(422, f"category must be one of {', '.join(CATEGORY_LABEL)}")
        data = catalog.snapshot() or {"items": []}
        langs = repo_meta(p).get("languages", {})
        # Written for a language the repo has none of: listed in the library, never picked.
        items = fitting(
            rank([i for i in data["items"] if i["category"] == category], "recommended"), langs
        )
        t = treatments_json(
            p.root,
            p.store,
            p.store.list_experiments(p.pid),
            repo_meta(p).get("skill_details", []),
            user_dir,
            library,
        )
        local = fitting(
            [
                {"path": x["path"], "name": x["name"], "description": x["description"]}
                for g in ("repo", "user", "installed", "created")
                for x in t.get(g, [])
            ],
            langs,
        )
        w = _workflow(p, workflow)
        weak = [
            x["name"] for g in ("repo", "user", "installed", "created") for x in t.get(g, [])
            if (x.get("evidence") or {}).get("verdict") in ("hurts", "inconclusive")
        ]  # fmt: skip
        use_case = next((s.text for s in p.store.list_sources(p.pid) if s.kind == "usecase"), None)
        needs = needs_for(
            load_architecture(p.root),
            [(st.name, st.type.value, st.why) for st in w.steps] if w else [],
            [s.title or s.id for s in scenarios(p) if s.check_status == "approved"],
            [x["title"] for x in _proposals(p, workflow) if x["state"] != "dismissed"][:4],
            weak,
            use_case,
        )
        key = cache_key(
            category,
            [n.text for n in needs],
            [i["id"] for i in items[:40]],
            [x["path"] for x in local],
        )
        cache_file = p.root / PG_DIR / "recommend.json"
        try:
            cached = json.loads(cache_file.read_text())
        except (OSError, ValueError):
            cached = {}
        # Only a model's picks are kept: showing them again costs nothing. The rough picker is
        # instant, so it runs fresh. A model is asked only when the request says model=true.
        out = None if refresh else cached.get(key)
        if out is None and model:
            client = reachable_model()
            out = rough(needs, items, local)
            if client is None:
                out["note"] = (
                    "No model to ask: add an Anthropic key or click the agent at the top right to sign in. These are rough picks."
                )
            else:
                try:
                    out = with_model(client, needs, items, local, CATEGORY_LABEL[category])
                except GenerationError as e:
                    out["note"] = f"The model didn't answer ({e}); these are rough picks."
            if out["basis"] == "model":
                cached[key] = out
                cache_file.write_text(json.dumps(cached))
        if out is None:
            out = rough(needs, items, local)
        by_id = {i["id"]: i for i in items}
        return {
            "needs": [{"text": n.text, "source": n.source} for n in needs],
            **out,
            "picks": [p_ | {"item": by_id.get(p_["id"])} for p_ in out["picks"]],
            "creatable": category in skills.value("recommend-for-repo", "create_kinds"),
            "model_pick_usd": skills.value("recommend-for-repo", "model_pick_usd"),
        }

    # ---------- Garage: the architecture catalog ----------

    def blueprint(e: dict) -> dict:
        return e | {"architecture": catalog_arch.as_architecture(e).dump()}

    # Skills whose values the web app reads as they are: the words and rules it shows.
    shared_rules = ("measurability", "repo-goals")

    @app.get("/api/rules/{name}")
    def rules(name: str):
        """A skill's values for the web app (measurability, repo-goals), so its wording and
        rules live in the skill, not in the app's code."""
        if name not in shared_rules:
            raise HTTPException(404, f"No rules called {name!r}.")
        return skills.load(name).values

    @app.get("/api/glossary")
    def glossary():
        """The plain meaning of each measurement word, for the (?) beside it (glossary skill)."""
        terms: dict[str, dict] = {}
        for k, t in skills.value("glossary", "terms").items():
            entry = {"term": t["term"], "short": t["short"]}
            terms[k] = entry
            for alias in t.get("aliases", []):  # an older word ("scenario") finds the same entry
                terms.setdefault(alias, entry)
        return {"terms": terms}

    @app.get("/api/garage/catalog")
    def garage_catalog():
        return {
            "families": [{"id": f, "entries": es} for f, es in catalog_arch.grouped().items()],
            "count": len(catalog_arch.entries()),
        }

    @app.get("/api/garage/catalog/{entry_id}")
    def garage_entry(entry_id: str):
        e = catalog_arch.entry(entry_id)
        if e is None:
            raise HTTPException(404, f"No architecture called {entry_id!r} in the catalog.")
        return blueprint(e)

    @app.post("/api/garage/recommend")
    def garage_recommend(body: GarageRecommend):
        meta: dict = {}
        if body.repo:
            r = ws.get(body.repo)
            if r is None:
                raise HTTPException(404, f"No repo with id {body.repo!r}.")
            p = open_project(r)
            meta = dict(repo_meta(p))
            meta["docs_words"] = sum(
                len(s.text.split())
                for s in p.store.list_sources(p.pid)
                if s.kind not in ("repo", "usecase", "graph")
            )
        # The local embedding model is one more signal once it's on this machine; else rules only.
        scored = catalog_arch.scored(body.use_case, meta, matcher.ready())
        ranked = catalog_arch.ranked(scored)
        note = None
        explanations: dict[str, str] = {}
        if body.explain and not ranked:
            # No picks, no call: say so rather than let it read as the model's silence.
            note = skills.value("architecture-catalog", "explain_nothing")
        elif body.explain:
            model = reachable_model()
            if model is None:
                note = "Sign in or add a key to get explanations; the ranking is the same."
            else:
                try:
                    explanations = catalog_arch.explain(model, body.use_case, ranked)
                except GenerationError as e:
                    note = f"The model didn't answer ({e}); the ranking is the same."
        by_id = {e["id"]: e for e in catalog_arch.entries()}
        return {
            "picks": [
                r | {"entry": by_id[r["id"]], "explanation": explanations.get(r["id"])}
                for r in ranked
            ],
            "note": note,
            # With no picks: the designs its words came close to, and what to add.
            "empty": None if ranked else catalog_arch.empty_state(body.use_case, scored),
            # What "Explain the top three with the model" costs, roughly: said before and while asking.
            "explain_usd": skills.value("architecture-catalog", "explain_usd"),
        }

    @app.post("/api/garage/workflow")
    def garage_workflow(body: GarageWorkflow):
        """The Lab workflow that runs a design, set up for the use case (architecture-catalog:
        lab_workflow and lab_handoff)."""
        try:
            got = catalog_arch.lab_workflow(body.entry, body.use_case, lab_library()[0])
        except KeyError as e:
            raise HTTPException(404, str(e.args[0])) from e
        label = lab.S["disciplines"].get(got["discipline"], {}).get("label", got["discipline"])
        return {
            "workflow": learned([got["workflow"].dump()])[0],
            "discipline": got["discipline"],
            "discipline_label": label,
            "matched": got["matched"],
            "note": got["note"],
        }

    @app.post("/api/draft")
    def draft_skill(body: DraftRequest, p: Project = Depends(current)):
        base = None
        if body.improves:
            f = Path(body.improves) / "SKILL.md"
            if not f.is_file():
                raise HTTPException(404, "No such skill to improve.")
            base = f.read_text(errors="replace")
        try:
            text = draft(
                reachable_model(),
                body.name,
                body.need,
                body.what,
                scan_to_text(scan_repo(p.root), per_file_chars=600),
                base,
            )
        except GenerationError as e:
            raise HTTPException(502, str(e)) from e
        return {"name": body.name, "text": text, "improves": body.improves}

    @app.post("/api/draft/save")
    def save_skill(body: SaveDraft):
        try:
            dest = save_draft(library, body.name, body.text, body.improves)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        return {"path": str(dest), "name": dest.name}

    # ---------- Workflow Lab (no repo needed) ----------

    def lab_library() -> tuple[list[dict], dict]:
        """Your skills, then the preloaded GitHub ones (starter-skills) whose names you don't
        already have; and the GitHub index's state for the page."""
        out = []
        for base in (user_dir, library, library / "created"):
            if not base.is_dir():
                continue
            for d in sorted(x for x in base.iterdir() if (x / "SKILL.md").is_file()):
                sk = parse_skill(f"{d.name}/SKILL.md", (d / "SKILL.md").read_text(errors="replace"))
                entry = {
                    "path": str(d.resolve()),
                    "name": sk.name,
                    "description": sk.description,
                    "source": "local",
                }
                try:  # downloaded from GitHub (catalog or a starter skill): say where from
                    src = json.loads((d / ".source.json").read_text())
                    entry |= {
                        "source": "github",
                        "repo": src["repo"],
                        "folder": src["path"],
                        "url": f"https://github.com/{src['repo']}/tree/HEAD/{src['path']}".rstrip(
                            "/"
                        ),
                    }
                except (OSError, ValueError, KeyError, TypeError):
                    pass
                out.append(entry)
        snap = starter.snapshot()
        names = {s["name"] for s in out}
        have = {(s.get("repo"), s.get("folder")) for s in out}
        for s in snap["skills"]:
            if s["name"] not in names and (s["repo"], s["folder"]) not in have:
                names.add(s["name"])
                out.append(s)
        n_github = sum(s["source"] == "github" for s in out)
        status = {
            "state": snap["state"],
            "note": snap["note"],
            "github": n_github,
            "local": len(out) - n_github,
        }
        return out, status

    def resolve_skills(wf: lab.Workflow) -> dict[str, str]:
        """Download the GitHub skills a workflow uses (once each), point its steps at the
        downloaded folders, and return every skill's text by path for compiling."""
        texts: dict[str, str] = {}
        for st in wf.steps:
            for s_ in st.skills:
                if s_["path"].startswith(GITHUB_SKILL):
                    try:
                        s_["path"] = str(starter.ensure(s_["path"], library).resolve())
                    except ValueError as e:
                        raise HTTPException(422, f"Can't use the skill {s_['name']}: {e}") from e
                    except Exception as e:  # noqa: BLE001 - offline, rate-limited
                        raise HTTPException(
                            502, f"Could not download the skill {s_['name']} from GitHub: {e}"
                        ) from e
                f = Path(s_["path"]) / "SKILL.md"
                if f.is_file():
                    texts[s_["path"]] = f.read_text(errors="replace")
        return texts

    # ---------- Local models ----------

    def local_json() -> dict:
        mine = local.models()
        helper = local.helper()
        return {
            "models": [m.dump() for m in mine],
            "helper": helper.id if helper else None,
            "notes": local_mod.L["agents"],
            "lab": local_mod.L["lab"],
            # Measure's words for a repo run on one, and its time limit's factor.
            "repo": local_mod.L["repo"],
            "timeout_factor": local_mod.L["timeout_factor"],
            # The Lab's words for a suite asked for on one ({agent}: the signed-in agent).
            "suite_local": local_mod.L["suite_local"],
        }

    def local_run(meta_: dict) -> dict | None:
        """The local model a run ran on, as {id, label}: its label as recorded, else as added
        (Lab runs record only the id), else the id; None for a run on the signed-in agent."""
        mid = meta_.get("local_model")
        if not mid:
            return None
        m = local.get(mid)
        label = meta_.get("local_label") or (m.label if m else mid.removeprefix("local:"))
        return {"id": mid, "label": label}

    @app.get("/api/local-models")
    def get_local_models(scan: bool = False):
        out = local_json()
        if scan:
            have = {m.id for m in local.models()}
            out["found"] = [m.dump() for m in local_mod.detect(local_http) if m.id not in have]
        return out

    @app.post("/api/local-models/scan")
    def scan_local(body: ScanLocal):
        if not local_mod.is_local(body.base):
            raise HTTPException(422, f"{body.base} isn't on this machine or your network.")
        found = local_mod.detect(local_http, extra=[body.base])
        base = body.base.rstrip("/").removesuffix("/v1")
        return [m.dump() for m in found if m.base == base]

    @app.post("/api/local-models")
    def add_local(body: AddLocal):
        try:
            m = local_mod.make(body.base, body.model, body.kind, body.label)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        m = local_mod.LocalModel(
            m.id, m.label, m.base, m.model, m.kind, local_mod.speaks_anthropic(m.base, local_http)
        )
        local.add(m)
        return local_json()

    @app.delete("/api/local-models/{mid}")
    def remove_local(mid: str):
        local.remove(mid)
        return local_json()

    @app.post("/api/local-models/{mid}/test")
    def test_local(mid: str):
        m = local.get(mid)
        if m is None:
            raise HTTPException(404, f"No local model {mid!r}.")
        return local_mod.try_model(local_mod.OpenAICompatClient(m, local_http))

    @app.post("/api/local-models/{mid}/template-fix")
    def local_template_fix(mid: str):
        m = local.get(mid)
        if m is None:
            raise HTTPException(404, f"No local model {mid!r}.")
        try:
            return local_mod.save_fixed_template(m, home, local_http)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e

    @app.post("/api/local-models/helper")
    def set_local_helper(body: LocalHelper):
        try:
            local.set_helper(body.id)
        except KeyError as e:
            raise HTTPException(404, str(e)) from e
        return local_json()

    @app.get("/api/lab")
    def get_lab():
        lib, lib_status = lab_library()
        matcher.start()
        with skill_models.pinned(matcher.ready(lib)):
            return lab_page(lib, lib_status, matcher.status(lib))

    def lab_page(lib: list[dict], lib_status: dict, matcher_status: dict) -> dict:
        base = lab.W["baseline_model"]
        got = measured()
        return {
            "disciplines": [
                d | {"workflows": learned(d["workflows"], got)} for d in lab.starters(lib)
            ],
            "business": learned([w.dump() for w in lab.business(lib)], got),
            "rag": learned([w.dump() for w in lab.rag(lib)], got),
            "templates": lab.templates(),
            "patterns": learned(
                [
                    lab.from_pattern(pid, base, lib).dump() | {"group": p_["group"]}
                    for pid, p_ in lab.W["patterns"].items()
                ],
                got,
            ),
            "models": lab.W["models"],
            "local_models": [m.dump() for m in local.models()],
            "harness": lab.W["harness"],
            "skills": lib,
            "skills_status": lib_status,
            "matcher": matcher_status,
            # An edited workflow is kept in "Your drafts" when another is opened, at most this many.
            "drafts_max": skills.value("starter-workflows", "drafts_kept"),
            "saved": learned(
                [
                    json.loads((d / "workflow.json").read_text())
                    | {"path": str(d), "proven": proven_mod.read(d)}
                    for d in sorted((library / "workflows").glob("[!.]*"))  # not one mid-compile
                    if (d / "workflow.json").is_file() and (d / ".saved").is_file()
                ],
                got,
            ),
        }

    @app.post("/api/lab/matcher")
    def lab_matcher(body: MatcherChoice):
        """Get and use the skill matcher's models (on: asked for by the user, as the download is
        about a gigabyte), or go back to the word rules (off)."""
        try:
            matcher.turn(body.on)
        except PermissionError as e:
            raise HTTPException(409, str(e)) from e
        return matcher.status(lab_library()[0])

    @app.post("/api/lab/random")
    def lab_random(body: LabRandom):
        lib = lab_library()[0]
        with skill_models.pinned(matcher.ready(lib)):
            wf = lab.random_workflow(lib, body.discipline, body.seed, set(body.shown))
        return learned([wf.dump()])[0]

    @app.post("/api/lab/price")
    def lab_price(body: dict):
        try:
            wf = lab.load_workflow(body)
        except (KeyError, TypeError, ValueError) as e:
            raise HTTPException(422, f"Not a workflow: {e}") from e
        return learned([wf.dump()])[0]

    @app.post("/api/lab/save")
    def lab_save(body: dict):
        try:
            wf = lab.load_workflow(body)
        except (KeyError, TypeError, ValueError) as e:
            raise HTTPException(422, f"Not a workflow: {e}") from e
        texts = resolve_skills(wf)
        dest = lab.compile_workflow(wf, library / "workflows" / f"workflow-{wf.id}", texts)
        # Runs compile into the same folder; this marks the ones you chose to keep.
        (dest / ".saved").write_text("")
        refresh_proven(dest.name)  # compiling starts the folder over: put its measured claim back
        return {"path": str(dest), "id": wf.id, "name": wf.name}

    # ---------- Ship to any agent: BUILD.md and rig.json ----------

    def all_proposals(p: Project) -> list[dict]:
        """Every suggestion for the repo, for any of its workflows, once each."""
        out: dict[str, dict] = {}
        for w in workflows(p) or [None]:
            for x in _proposals(p, w.id if w else None):
                out.setdefault(x["id"], x)
        return list(out.values())

    def build_for(body: BuildSpecRequest, repo: str | None) -> tuple[dict, str, Path]:
        """The spec, its Markdown and the folder it is saved in."""
        entry = None
        if body.design is not None:
            entry = catalog_arch.entry(body.design.id)
            if entry is None:
                raise HTTPException(422, f"No design called {body.design.id!r} in the catalog.")
        p = None
        if body.source == "workflow":
            try:
                wf = lab.load_workflow(body.workflow or {})
            except (KeyError, TypeError, ValueError) as e:
                raise HTTPException(422, f"Not a workflow: {e}") from e
            runs_ = [r for r in measured() if r["id"] == wf.id]
            rows = {(x["bench"], x["id"]): x for x in lab_rows(live=False)} if runs_ else {}
            extras = {
                "results": [
                    {
                        "name": wf.name,
                        "bench": r["bench"],
                        "diff": round(r["diff"], 1),
                        "pairs": r["pairs"],
                        "verdict": row.get("verdict"),
                        "rig": row.get("rig"),
                    }
                    for r in runs_
                    if r["diff"] is not None
                    for row in [rows.get((r["bench"], r["experiment"])) or {}]
                ],
            }
            spec = buildspec.spec_from_workflow(wf, extras, body.use_case or "", body.goal or None)
            dest = library / "builds" / wf.id
        elif body.source == "design":
            # Nothing yet, only a design: a new project built from its parts.
            if entry is None:
                raise HTTPException(422, "Choose a design to build from.")
            goal = body.goal or body.use_case
            spec = buildspec.spec_from_architecture(
                catalog_arch.as_architecture(entry),
                {},
                body.use_case or entry["when_to_use"],
                goal=goal or None,
                # No goal: nothing says the work isn't software, so the layout stays the plan.
                discipline=catalog_arch.discipline_for(goal, entry["family"])[0] if goal else None,
            )
            dest = library / "builds" / f"design-{entry['id']}"
        else:
            # A repo: the changes to make in it, never a new project.
            p = current(repo)
            arch = load_architecture(p.root)
            gone = set(body.removed)
            removed = [{"id": c.id, "label": c.label} for c in arch.components if c.id in gone]
            if gone:
                arch = arch.model_copy(
                    update={
                        "components": [c for c in arch.components if c.id not in gone],
                        "connections": [
                            x for x in arch.connections if x.from_ not in gone and x.to not in gone
                        ],
                        "flows": [
                            f
                            for f in arch.flows
                            if not any(st.from_ in gone or st.to in gone for st in f.steps)
                        ],
                    }
                )
            items = scenarios(p)
            extras = {
                # Only runnable ones are a way to check it (build-spec); the rest are counted.
                "scenarios": [{"id": x.id, "title": x.title} for x in items if validity.can_run(x)],
                "scenarios_left_out": sum(not validity.can_run(x) for x in items),
                "results": [
                    {
                        "name": e.treatment_name,
                        "diff": None if ev["diff"] is None else round(ev["diff"] * 100, 1),
                        "pairs": ev["n_pairs"],
                        "verdict": ev["verdict"],
                        "rig": repo_rig(p, e),
                    }
                    for e in p.store.list_experiments(p.pid)[:5]
                    for ev in [evidence_json(p.store, e)]
                ],
            }
            # The goal the browser is using (an unsaved draft included), else the saved one.
            use_case = (
                body.use_case
                if body.use_case is not None
                else next(
                    (s.text for s in p.store.list_sources(p.pid) if s.kind == "usecase"), None
                )
            )
            meta = repo_meta(p)
            if not meta:  # not read yet: read it now, the same way intake does
                sc = scan_repo(p.root)
                meta = {
                    "files": sc.file_count,
                    "languages": sc.languages,
                    "stack": sc.stack,
                    "agent_setup": sc.agent_setup,
                    "skill_details": [{"name": k.name, "path": k.path} for k in sc.skills],
                }
            spec = buildspec.spec_for_repo(
                arch,
                p.root,
                meta,
                use_case=body.goal or use_case,
                suggestions=all_proposals(p),
                with_suggestions=body.source == "suggested",
                removed=removed,
                extras=extras,
            )
            dest = p.root / PG_DIR / "build"
        if entry is not None:
            spec = buildspec.with_design(spec, entry, body.design.parameters)
        if body.added is not None:
            spec = buildspec.with_canvas(
                spec, body.added.model_dump(by_alias=True), p.root if p else None
            )
        return spec, buildspec.render_markdown(spec), dest

    def shipped_for(body: BuildSpecRequest, repo: str | None) -> dict | None:
        """The newest result of what is being shipped, for the Ship step's header: this
        workflow's own runs, or a repo's runs of the parts on its canvas (its own skills and the
        ones placed there). None when none of it was measured."""
        if body.source == "design":
            return None
        if body.source == "workflow":
            try:
                wf = lab.load_workflow(body.workflow or {})
            except (KeyError, TypeError, ValueError):
                return None
            names = {lab.workflow_name(wf, a.id) for a in AGENTS}
            mine = [
                r
                for r in lab_rows(live=False)
                if r.get("workflow_id") == wf.id or r["treatment"] in names
            ]
            if not mine:
                return None
            r = max(mine, key=lambda x: (x["date"], x["id"]))
            return {"name": wf.name, "where": r["bench_name"], "rig": r["rig"]}
        p = current(repo)
        meta = repo_meta(p)
        parts = {k.get("name") for k in meta.get("skill_details") or []}
        parts |= {Path(k.get("path") or "").name for k in meta.get("skill_details") or []}
        for k in body.added.skills if body.added else []:
            parts |= {k.name, Path(k.path).name}
        parts.discard("")
        for e in p.store.list_experiments(p.pid):  # newest first
            if e.treatment_name in parts:
                return {"name": e.treatment_name, "where": None, "rig": repo_rig(p, e)}
        return None

    @app.post("/api/buildspec")
    def make_buildspec(body: BuildSpecRequest, repo: str | None = Query(default=None)):
        spec, md, _ = build_for(body, repo)
        return {"json": spec, "markdown": md, "shipped": shipped_for(body, repo)}

    @app.post("/api/buildspec/save")
    def save_buildspec(body: BuildSpecRequest, repo: str | None = Query(default=None)):
        spec, md, dest = build_for(body, repo)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "BUILD.md").write_text(md, encoding="utf-8")
        (dest / "rig.json").write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
        return {
            "dir": str(dest),
            "markdown": str(dest / "BUILD.md"),
            "json": str(dest / "rig.json"),
        }

    @app.delete("/api/lab/saved/{wid}")
    def unsave(wid: str):
        """Off your saved list. The folder stays while measured results still point at it."""
        d = library / "workflows" / f"workflow-{wid}"
        if not (d / ".saved").is_file():
            raise HTTPException(404, f"No saved workflow {wid!r}.")
        (d / ".saved").unlink()
        return {"removed": wid}

    # ---------- Test benches: measure a workflow without a repo ----------

    benches_dir = home / "benches"
    bench_mod.IMPORTS = home / "imported-benches.json"
    bench_mod.GENERATED = home / "generated-benches"
    public = public_benches or PublicBenches(home)

    calibrations_file = home / "calibrations.json"
    calibration_lock = threading.Lock()

    materialize_lock = threading.Lock()

    def bench_project(bid: str) -> Project:
        try:
            b = bench_mod.bench(bid)
        except KeyError as e:
            raise HTTPException(404, str(e.args[0])) from e
        root = benches_dir / bid
        with materialize_lock:  # a job's thread and a request can both find it missing
            if not root.is_dir():
                bench_mod.materialize(b, root)
        r = Repo(id=f"bench-{bid}", root=str(root), name=b.name)
        return open_project(r)

    def task_json(n: int, s: dict) -> dict:
        # A held-out task is run but not shown, so a workflow can't be tuned to it.
        return {
            "id": s["id"] if not s.get("held_out") else f"held-out-{n}",
            "kind": s["kind"],
            "title": s["title"] if not s.get("held_out") else "Held-out task",
            "judged": bool(s.get("judge")),
            "held_out": bool(s.get("held_out")),
            "tier": bench_mod.tier_of(s),
        }

    def bench_baseline(b: bench_mod.Bench) -> dict:
        """Per tier, per session model: the agent alone's pass rate on the tier's current
        version, from trials already recorded, and whether that is too easy (bench-difficulty)."""
        if b.tasks is not None or not (benches_dir / b.id / PG_DIR).is_dir():
            return {}
        p = bench_project(b.id)
        out = {}
        for tier in bench_mod.tiers(b):
            t = bench_mod.for_tier(b, tier)
            got = difficulty.baseline(
                p.store,
                p.root,
                p.pid,
                bench_mod.version(t),
                [s["id"] for s in t.scenarios],
                label=model_label,
            )
            for v in got.values():
                if v["too_easy"]:  # what Measure says before Rig & Measure
                    hard = tier == "standard" and "hard" in bench_mod.tiers(b)
                    v["warn"] = difficulty.D["warn"] + (
                        f" {difficulty.D['warn_hard']}" if hard else ""
                    )
            if got:
                out[tier] = got
        return out

    @app.get("/api/lab/benches")
    def lab_benches():
        return [
            {
                "id": b.id,
                "name": b.name,
                "discipline": b.discipline,
                "summary": b.summary,
                "scenarios": [task_json(n, s) for n, s in enumerate(b.scenarios, 1)],
                # The hard tier's tasks, run when a run picks the hard tier or all.
                "hard": [task_json(n, s) for n, s in enumerate(b.hard, 1)],
                "tiers": [
                    {
                        "id": t,
                        "label": difficulty.D["tier_labels"][t],
                        "tasks": len(bench_mod.for_tier(b, t).scenarios),
                    }
                    for t in bench_mod.tiers(b)
                ],
                "baseline": bench_baseline(b),
                "disciplines": b.disciplines,
                "judged": b.judged,
                "calibration": saved_calibration(b),
                "imported": b.tasks is not None,
                "generated": b.generated,
                "public": (
                    {k: b.public.get(k) for k in ("key", "total", "source", "heavy")}
                    if b.public
                    else None
                ),
            }
            for b in bench_mod.benches()
        ]

    @app.post("/api/lab/benches/generate")
    def generate_bench(body: MakeBench):
        """A bench fitted to this workflow: one model call writes it, Docker proves each task."""
        from proving_ground import benchgen

        model = reachable_model()
        if model is None:
            raise HTTPException(
                400,
                "Making a bench needs a model: pick a local model for helper calls, add an Anthropic key, or sign in to Claude Code.",
            )
        lm = local.helper()
        name = lm.label if lm else benchgen.G["model"]
        try:
            made = benchgen.make(model, body.workflow, home / "generated-benches", name)
        except GenerationError as e:
            raise HTTPException(502, str(e)) from e
        out = {"kept": made.kept, "dropped": made.dropped, "model": made.model, "bench": None}
        if made.bench_id:
            out["bench"] = next(x for x in lab_benches() if x["id"] == made.bench_id)
        return out

    @app.post("/api/lab/benches/import")
    def import_suite(body: ImportSuite):
        """A folder of Harbor tasks (an existing eval suite) as a bench. Nothing runs yet."""
        try:
            b = bench_mod.import_suite(Path(body.path), body.name, body.disciplines)
        except (ValueError, OSError) as e:
            raise HTTPException(422, str(e)) from e
        return next(x for x in lab_benches() if x["id"] == b.id)

    @app.get("/api/lab/public-benches")
    def public_benches_list(refresh: bool = False):
        """Public benchmarks in the Harbor registry (cached a day; offline, the last copy)."""
        return public.listing(refresh)

    @app.post("/api/lab/public-benches")
    def public_bench_add(body: AddPublic):
        """Download a seeded sample of a public benchmark's tasks and add it as a bench."""
        try:
            b, dropped = public.add(body.key, body.sample)
        except KeyError as e:
            raise HTTPException(404, str(e.args[0])) from e
        except PublicBenchError as e:
            raise HTTPException(422, str(e)) from e
        return {"bench": next(x for x in lab_benches() if x["id"] == b.id), "dropped": dropped}

    def judge_identity() -> str:
        """Who grades: the local helper's id, else the Claude judge model."""
        lm = local.helper()
        return lm.id if lm else f"claude:{judge_mod.J['model']}"

    def calibration_key(b) -> str:
        gold = b.path / "gold"
        return f"{b.id}|{judge_identity()}|{hash_tree(gold) if gold.is_dir() else 'none'}"

    def saved_calibration(b) -> dict | None:
        try:
            return json.loads(calibrations_file.read_text()).get(calibration_key(b))
        except (OSError, ValueError):
            return None

    def save_calibration(b, cal: dict) -> None:
        with calibration_lock:
            try:
                data = json.loads(calibrations_file.read_text())
            except (OSError, ValueError):
                data = {}
            data[calibration_key(b)] = cal
            calibrations_file.parent.mkdir(parents=True, exist_ok=True)
            calibrations_file.write_text(json.dumps(data, indent=2))

    @app.post("/api/lab/benches/{bid}/calibrate")
    def calibrate_bench(bid: str):
        """Run the judge on each judged task's known-good and known-bad example (2 calls each)."""
        try:
            b = bench_mod.bench(bid)
        except KeyError as e:
            raise HTTPException(404, str(e.args[0])) from e
        model = reachable_model()
        if model is None:
            raise HTTPException(
                400,
                "Calibrating needs a judge model: add an Anthropic key or sign in to Claude Code.",
            )
        root = benches_dir / bid
        if not root.is_dir():
            bench_mod.materialize(b, root)
        out = {}
        for s_ in b.scenarios:
            gold = b.path / "gold" / s_["id"]
            if not s_.get("judge") or not (gold / "good.md").is_file():
                continue
            try:
                out[s_["id"]] = judge_mod.calibrate(
                    model,
                    s_["instruction"],
                    s_["judge"]["rubric"],
                    (gold / "good.md").read_text(),
                    (gold / "bad.md").read_text(),
                    judge_mod.read_context(root, s_["judge"].get("context", [])),
                )
            except GenerationError as e:
                out[s_["id"]] = {"error": str(e)}
        cal = {
            "scenarios": out,
            "trustworthy": bool(out) and all(v.get("trustworthy") for v in out.values()),
        }
        save_calibration(b, cal)
        return cal

    @app.post("/api/lab/run")
    def lab_run(body: LabRun):
        live = next((j for j in suites.values() if j.active()), None)
        if live is not None:
            raise HTTPException(409, f"A suite run ({live.id}) is still going. Stop it or wait.")
        if any(j.active() for j in compares.values()):
            raise HTTPException(409, "A comparison run is still going. Stop it or wait.")
        return start_lab_run(body, grow=True)

    def tiered(bid: str, tier: str) -> bench_mod.Bench:
        """A bench with one tier's tasks (bench-difficulty: tiers); 404 or 422 when it can't."""
        try:
            b = bench_mod.bench(bid)
        except KeyError as e:
            raise HTTPException(404, str(e.args[0])) from e
        try:
            return bench_mod.for_tier(b, tier)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e

    def run_target(
        agent_id: str, local_model: str | None, wf: lab.Workflow | None, model: str | None = None
    ) -> tuple[str, dict, str | None, Any]:
        """Where a bench run's trials run: (model it is recorded under, env, the name the agent
        asks its server for, the local model or None). Raises when it can't run there."""
        lm = local.get(local_model) if local_model else None
        if local_model and lm is None:
            raise HTTPException(404, f"No local model {local_model!r}.")
        if lm is not None and (agent_id != "claude-code" or not lm.anthropic):
            raise HTTPException(
                422,
                f"{lm.label} can run Claude Code only when its server speaks Anthropic's Messages "
                "API (llama.cpp and Ollama do). Other agents on local models aren't wired up yet.",
            )
        if lm is None and not creds.ready(agent_id):
            raise HTTPException(
                400,
                f"Sign in to {agent(agent_id).label} first: click the agent at the top right to sign in.",
            )
        # The session runs on the model most of the work is done on; each step's subagent on its own.
        if wf is not None:
            models = [st.model for st in wf.steps if st.kind == "do"] or [
                st.model for st in wf.steps
            ]
            model = gate_mod.session_model(models)
        model = model or DEFAULT_MODEL
        env = creds.env_for(agent_id)
        harbor_model = None
        if lm is not None:
            # Every model Claude Code asks for (subagents too) is served by the local one.
            model, (harbor_model, env) = lm.id, local_mod.agent_env(lm)
        elif agent_id != "claude-code":
            # The agent's own default model: per-step Claude models only apply on Claude Code.
            harbor_model = agent(agent_id).default_model or ""
            model = harbor_model or f"{agent_id}:default"
        return model, env, harbor_model, lm

    def bench_judge(b: bench_mod.Bench, root: Path):
        """A judged bench's grader for its documents (None for one graded by checks alone)."""
        if not b.judged:
            return None
        if local.helper() is not None and not (saved_calibration(b) or {}).get("trustworthy"):
            raise HTTPException(
                409,
                "Check the judge first: small local models often can't grade documents.",
            )
        judge_model = reachable_model()
        if judge_model is None:
            raise HTTPException(
                400,
                f"{b.name} grades documents with a judge model: add an Anthropic key, sign in to Claude Code, or pick a local model for helper calls first.",
            )

        def judge_fn(scenario, artifact: Path) -> tuple[bool, str]:
            g = judge_mod.grade(
                judge_model,
                scenario.instruction,
                scenario.judge.rubric,
                artifact.read_text(errors="replace"),
                judge_mod.read_context(root, scenario.judge.context),
            )
            (artifact.parent / "grade.json").write_text(json.dumps(g.dump(), indent=2))
            return g.passed, g.reason

        return judge_fn

    def start_lab_run(body: LabRun, grow: bool = False) -> dict:
        """Prepare and start one workflow on one bench (shared by a single run, a suite and a
        comparison). `grow`: a full run plans the pairs the budget reaches, up to the sizing
        (budget.full_pairs), as /api/runs/estimate priced it; a suite's and a comparison's
        benches keep the fixed full size their plans price."""
        try:
            agent(body.agent)
            wf = lab.load_workflow(body.workflow)
        except (KeyError, TypeError, ValueError) as e:
            raise HTTPException(422, f"{e}") from e
        b = tiered(body.bench, body.tier)
        model, env, harbor_model, lm = run_target(body.agent, body.local_model, wf)
        metric = body.metric or rig_mod.M["default"]
        if lm is not None and metric == "cost":  # as a repo's run: nothing to compare
            raise HTTPException(422, local_mod.L["repo"]["cost_metric"])
        busy = runs.busy()
        if busy is not None:
            raise HTTPException(409, f"Run {busy} is still going. Wait for it to finish.")
        texts = resolve_skills(wf)
        try:
            folder = lab.compile_workflow(
                wf, library / "workflows" / lab.workflow_name(wf, body.agent), texts, body.agent
            )
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        # Held while the bench is put back: a request reading it meanwhile (bench_project, a
        # Compare page polling) would otherwise find it missing and materialize it over the copy.
        with materialize_lock:
            root = bench_mod.refresh(b, benches_dir / b.id)
        p = bench_project(b.id)
        judge_fn = bench_judge(b, root)
        n = gate_mod.trial_count(b, body.size)
        costs = run_costs(
            body.agent,
            model,
            lab.workflow_name(wf, body.agent),
            bench=b.id,
            free=lm is not None,
            tier=b.tier,
        )
        if grow and body.size == "full":
            n = full_pairs(len(b.scenarios), per_pair(costs), body.budget, n, sized_for(metric))
        try:
            prep = prepare_experiment(
                root,
                folder,
                body.budget,
                n,
                model,
                agent=body.agent,
                env=env,
                extra_meta={
                    "bench_version": bench_mod.version(b),
                    "tier": b.tier,
                    "workflow": wf.id,
                    "local_model": lm.id if lm else None,
                    "improved_from": body.improved_from,
                    "metric": metric,
                },
                judge=judge_fn,
                harbor_model=harbor_model,
                free=lm is not None,
                ready_tasks=bench_mod.task_dirs(b),
                timeout_factor=local_mod.L["timeout_factor"] if lm is not None else 1.0,
                nudge=body.nudge_prompt,
                reuse_baseline=body.reuse_baseline,
                refuse=lambda: cant_start(costs, body.budget),
            )
        except ServiceError as e:
            raise HTTPException(422, str(e)) from e
        if body.auto:
            prep.auto = skills.value("judge-experiment", "auto_extend")
        runs.start(prep, key=f"lab:{b.id}:{prep.eid}", after=lambda: refresh_proven(folder.name))
        return {
            "id": prep.eid,
            "bench": b.id,
            "workflow": wf.name,
            "trials": 2 * prep.repeats * len(prep.scenarios),
            "scenarios": [s.id for s in prep.scenarios],
            "model": model,
            "budget": body.budget,
            "project": p.repo.id,
            "tier": b.tier,
            "metric": metric,
            # The local model it runs on ({id, label}), or None: the live run names it.
            "local_model": {"id": lm.id, "label": lm.label} if lm else None,
        }

    # ---------- Baseline check: the agent alone on a bench, before paying for both arms ----------

    PROBE = skills.value("bench-difficulty", "probe")

    def probe_treatment() -> Path:
        """The placeholder a baseline check is recorded under: its "with" arm never runs."""
        d = library / PROBE["treatment"]
        if not (d / "SKILL.md").is_file():
            d.mkdir(parents=True, exist_ok=True)
            (d / "SKILL.md").write_text(
                f"---\nname: {PROBE['treatment']}\ndescription: {PROBE['label']}: the agent "
                "alone, nothing added.\n---\n\n# Baseline check\n\nNot a treatment: a baseline "
                "check runs only the agent alone.\n"
            )
        return d

    def probe_plan(body: LabProbe) -> dict:
        """What a baseline check would run and cost: no model call, no sign-in needed."""
        try:
            agent(body.agent)
            wf = lab.load_workflow(body.workflow) if body.workflow is not None else None
        except (KeyError, TypeError, ValueError) as e:
            raise HTTPException(422, f"{e}") from e
        b = tiered(body.bench, body.tier)
        lm = local.get(body.local_model) if body.local_model else None
        if wf is not None and body.agent == "claude-code" and lm is None:
            models = [st.model for st in wf.steps if st.kind == "do"] or [
                st.model for st in wf.steps
            ]
            model = gate_mod.session_model(models)
        elif lm is not None:
            model = lm.id
        elif body.agent != "claude-code":
            model = agent(body.agent).default_model or f"{body.agent}:default"
        else:
            model = body.model or DEFAULT_MODEL
        costs = run_costs(
            body.agent, model, PROBE["treatment"], bench=b.id, free=lm is not None, tier=b.tier
        )
        price = probe_price(costs, len(b.scenarios))
        usd = f"${price['total_usd']:.2f}" if not price["free"] else "nothing (a local model)"
        trials = f"{price['trials']} trial{'s' if price['trials'] != 1 else ''}"
        return price | {
            "bench": b.id,
            "tier": b.tier,
            "model": model,
            "model_label": model_label(model),
            "offer": PROBE["offer"].format(usd=usd, trials=trials),
            "wf": wf,
        }

    @app.post("/api/lab/probe/price")
    def lab_probe_price(body: LabProbe):
        plan = probe_plan(body)
        plan.pop("wf")
        return plan

    @app.post("/api/lab/probe")
    def lab_probe(body: LabProbe):
        """Run only the "without" arm on each task of a tier once, capped at its price. Its
        trials are a run's like any other, so a later run reuses them as its baseline."""
        if any(j.active() for j in suites.values()) or any(j.active() for j in compares.values()):
            raise HTTPException(409, "A suite or comparison is still going. Stop it or wait.")
        plan = probe_plan(body)
        b = tiered(body.bench, body.tier)
        model, env, harbor_model, lm = run_target(
            body.agent, body.local_model, plan["wf"], plan["model"]
        )
        busy = runs.busy()
        if busy is not None:
            raise HTTPException(409, f"Run {busy} is still going. Wait for it to finish.")
        budget = body.budget if body.budget is not None else max(plan["budget"], 0.01)
        with materialize_lock:
            root = bench_mod.refresh(b, benches_dir / b.id)
        judge_fn = bench_judge(b, root)
        costs = run_costs(
            body.agent, model, PROBE["treatment"], bench=b.id, free=lm is not None, tier=b.tier
        )

        def refuse() -> str | None:
            need, source = costs.estimate("without", [])
            if costs.free or need <= budget:
                return None
            up = math.ceil(need * 100 - 1e-9) / 100
            return PROBE["cant_start"].format(
                budget=f"${budget:.2f}", need=f"${up:.2f}", source=source
            )

        try:
            prep = prepare_experiment(
                root,
                probe_treatment(),
                budget,
                len(b.scenarios) * int(PROBE["repeats"]),
                model,
                agent=body.agent,
                env=env,
                extra_meta={
                    "bench_version": bench_mod.version(b),
                    "tier": b.tier,
                    "probe": True,
                    "workflow": None,
                    "local_model": lm.id if lm else None,
                },
                judge=judge_fn,
                harbor_model=harbor_model,
                free=lm is not None,
                ready_tasks=bench_mod.task_dirs(b),
                timeout_factor=local_mod.L["timeout_factor"] if lm is not None else 1.0,
                refuse=refuse,
                arms=(PROBE["arm"],),
                # Fresh trials: a check copying earlier ones would learn nothing new.
                reuse_baseline=False,
            )
        except ServiceError as e:
            raise HTTPException(422, str(e)) from e
        runs.start(prep, key=f"lab:{b.id}:{prep.eid}")
        return {
            "id": prep.eid,
            "bench": b.id,
            "tier": b.tier,
            "workflow": PROBE["label"],
            "probe": True,
            "trials": prep.repeats * len(prep.scenarios),
            "scenarios": [s.id for s in prep.scenarios],
            "model": model,
            "budget": budget,
            "price": {k: v for k, v in plan.items() if k != "wf"},
        }

    suites: dict[str, suite_mod.SuiteJob] = {}

    def suite_view(j: suite_mod.SuiteJob) -> dict:
        """Progress, each bench's change, and the pooled result over the pairs measured so far."""
        with j.lock:
            rows = [dict(r) for r in j.benches]
            status = j.status
        per_bench = {}
        priced = {}  # each bench's trials with what its reused baseline trials ran at
        for r in rows:
            r["diff"] = r["ci_low"] = r["ci_high"] = None
            r["n_pairs"] = 0
            if r["experiment"] is None:
                continue
            p = bench_project(r["bench"])
            trials = p.store.trials(r["experiment"])
            per_bench[r["bench"]] = trials
            priced[r["bench"]] = (trials, source_cost(p.store))
            h = summarize(trials).headline
            if h is not None:
                r.update(diff=h.diff, ci_low=h.ci_low, ci_high=h.ci_high, n_pairs=h.n_pairs)
            r["spent"] = round(p.store.spent(r["experiment"]), 4)
        # Each bench's Rig score from its results row, and one over the pooled pairs.
        full: dict = {}
        first = next((r for r in rows if r["experiment"] is not None), None)
        if first is not None:
            name = bench_project(first["bench"]).store.get_experiment(first["experiment"])
            started = {r["bench"] for r in rows if r["experiment"] is not None}
            full = {(x["bench"], x["id"]): x for x in lab_rows(name.treatment_name, only=started)}
        mine = []
        for r in rows:
            got = full.get((r["bench"], r["experiment"]))
            r["rig"] = got["rig"] if got else None
            if got:
                mine.append(got)
        pooled = suite_mod.pool(per_bench)
        saving = suite_mod.pool_metric(priced, j.metric)
        pooled["rig"] = rig_mod.rig_score(rig_mod.pool_evidence(mine, pooled, saving))
        return {
            "job": j.id,
            "workflow": j.workflow_name,
            "metric": j.metric,
            "status": status,
            "budget": j.budget,
            "spent": round(sum(r["spent"] for r in rows), 4),
            "benches": rows,
            "pooled": pooled,
        }

    def drive_suite(j: suite_mod.SuiteJob) -> None:
        """Run each bench in turn; each gets what's left divided by the benches left."""
        remaining = j.budget
        for i, row in enumerate(j.benches):
            if j.stop.is_set() or remaining <= 0:
                with j.lock:
                    for r in j.benches[i:]:
                        r["status"] = "skipped"
                break
            share = remaining / (len(j.benches) - i)
            with j.lock:
                row["budget"] = round(share, 4)
            try:
                started = start_lab_run(
                    LabRun(
                        workflow=j.workflow,
                        bench=row["bench"],
                        size=j.size,
                        budget=share,
                        agent=j.agent,
                        metric=j.metric,
                        # Decided on the pool: each bench runs its planned pairs (suite.auto_extend).
                        auto=bool(suite_mod.rule("auto_extend")),
                    )
                )
            except HTTPException as e:
                with j.lock:
                    row.update(status="error", detail=str(e.detail))
                continue
            key = f"lab:{row['bench']}:{started['id']}"
            with j.lock:
                row.update(experiment=started["id"], status="running")
            while not runs.runs[key].done:
                if j.stop.is_set():
                    runs.stop(key)
                time.sleep(0.05)
            p = bench_project(row["bench"])
            spent = p.store.spent(started["id"])
            remaining -= spent
            end = runs.runs[key].events[-1]
            with j.lock:
                row["spent"] = round(spent, 4)
                if end.get("type") == "error":
                    row.update(status="error", detail=end.get("detail"))
                else:
                    row["status"] = "stopped" if j.stop.is_set() else "done"
        with j.lock:
            j.status = "stopped" if j.stop.is_set() else "done"

    @app.post("/api/lab/suite")
    def lab_suite(body: SuiteRun):
        try:
            wf = lab.load_workflow(body.workflow)
            agent(body.agent)
        except (KeyError, TypeError, ValueError) as e:
            raise HTTPException(422, f"{e}") from e
        fits = suite_mod.fitting(wf.discipline)
        if not fits:
            raise HTTPException(422, f"No built-in bench measures {wf.discipline!r}.")
        if body.local_model:
            # Cost first, as a single bench says it; then that a suite can't run there at all.
            raise HTTPException(
                422,
                local_mod.L["repo"]["cost_metric"]
                if body.metric == "cost"
                else local_mod.L["suite_local"].format(agent=agent(body.agent).label),
            )
        if not creds.ready(body.agent):
            raise HTTPException(
                400,
                f"Sign in to {agent(body.agent).label} first: click the agent at the top right to sign in.",
            )
        busy = runs.busy()
        live = next((j for j in suites.values() if j.active()), None)
        if busy is not None or live is not None or any(j.active() for j in compares.values()):
            raise HTTPException(409, "A run is still going. Wait for it to finish.")
        j = suite_mod.SuiteJob(
            workflow=body.workflow,
            workflow_name=wf.name,
            agent=body.agent,
            budget=body.budget,
            size=body.size,
            metric=body.metric or rig_mod.M["default"],
            benches=[
                {
                    "bench": b.id,
                    "name": b.name,
                    "tasks": len(b.scenarios),
                    "experiment": None,
                    "status": "queued",
                    "budget": None,
                    "spent": 0.0,
                    "detail": None,
                }
                for b in fits
            ],
        )
        suites[j.id] = j
        threading.Thread(target=drive_suite, args=(j,), daemon=True).start()
        return {"job": j.id, "benches": [r["bench"] for r in j.benches], "metric": j.metric}

    @app.get("/api/lab/suite/{job}")
    def lab_suite_get(job: str):
        j = suites.get(job)
        if j is None:
            raise HTTPException(404, f"No suite run {job!r}.")
        return suite_view(j)

    @app.post("/api/lab/suite/{job}/stop")
    def lab_suite_stop(job: str):
        j = suites.get(job)
        if j is None or not j.active():
            raise HTTPException(404, "That suite run isn't going.")
        with j.lock:
            j.status = "stopping"
        j.stop.set()
        return {
            "stopping": True,
            "note": "It stops after the trial in progress and skips the rest.",
        }

    # ---------- compare 2 to 4 workflows on one bench (judge-experiment: compare) ----------

    compares: dict[str, compare_mod.CompareJob] = {}

    def model_label(m: str) -> str:
        """A model as people read it: a local model by its label (as Measure's modelText)."""
        if m.startswith("local:"):
            lm = local.get(m)
            return f"{lm.label if lm else m.removeprefix('local:')} (local)"
        return lab.W["models"].get(m, {}).get("label", m)

    def session_model_of(wf: lab.Workflow, agent_id: str) -> str:
        """The model a run of this workflow is recorded under, as start_lab_run picks it."""
        if agent_id == "claude-code":
            models = [st.model for st in wf.steps if st.kind == "do"] or [
                st.model for st in wf.steps
            ]
            return gate_mod.session_model(models)
        return agent(agent_id).default_model or f"{agent_id}:default"

    def compare_set(body: CompareRun) -> tuple[list[lab.Workflow], bench_mod.Bench]:
        try:
            agent(body.agent)
            wfs = [lab.load_workflow(w) for w in body.workflows]
            b = bench_mod.bench(body.bench)
        except (KeyError, TypeError, ValueError) as e:
            raise HTTPException(422, f"{e}") from e
        lo, hi = int(compare_mod.rule("min")), int(compare_mod.rule("max"))
        if not lo <= len(wfs) <= hi:
            raise HTTPException(422, f"Compare {lo} to {hi} workflows, not {len(wfs)}.")
        if len({w.id for w in wfs}) != len(wfs):
            raise HTTPException(422, "The same workflow is in the set twice.")
        return wfs, b

    @app.post("/api/lab/compare/plan")
    def lab_compare_plan(body: CompareRun):
        """The trial-budget prediction for measuring the set: each workflow's pairs and cost with
        the shared baseline counted once per session model. No model call, no sign-in needed."""
        from proving_ground.budget import CostModel, earlier, full_size, prior_usd

        wfs, b = compare_set(body)

        def pairs_of(size: str) -> int:
            n = gate_mod.trial_count(b, size)
            return math.ceil(n / len(b.scenarios)) * len(b.scenarios) if b.scenarios else 0

        pairs = pairs_of(body.size)

        def item(wf: lab.Workflow, model: str) -> dict:
            seen: dict = {"with": [], "without": []}
            if (benches_dir / b.id / PG_DIR).is_dir():
                p = bench_project(b.id)
                seen = earlier(
                    p.store, p.root, p.pid, model, body.agent, lab.workflow_name(wf, body.agent)
                )
            costs = CostModel(prior_usd(model), seen)
            w, w_src = costs.estimate("with", [])
            wo, wo_src = costs.estimate("without", [])
            return {
                "id": wf.id,
                "name": wf.name,
                "model": model,
                "with_usd": w,
                "without_usd": wo,
                "source": w_src if w_src == wo_src else f"with {w_src}; without {wo_src}",
            }

        models = [session_model_of(wf, body.agent) for wf in wfs]
        items = [item(wf, m) for wf, m in zip(wfs, models, strict=True)]
        now = compare_mod.plan(items, pairs, body.budget)
        # On more than one model: each pays for its own baseline. Priced all on one instead.
        priced = (
            {
                m: compare_mod.plan([item(wf, m) for wf in wfs], pairs, body.budget)
                for m in compare_mod.align_candidates(models)
            }
            if now["baselines"] > 1
            else {}
        )
        # What "Full" buys at this budget, whatever size is chosen: the set is only as conclusive
        # as the workflow its share pays for least (trial-budget: full_label).
        full = pairs_of("full")
        reach = min(
            r["pairs_in_budget"] for r in compare_mod.plan(items, full, body.budget)["workflows"]
        )
        return now | {
            "bench": b.id,
            "bench_name": b.name,
            "size": body.size,
            "align": compare_mod.align(now, priced, model_label),
            "full": full_size(reach, full, pairs_of("pilot")),
        }

    def compare_rows(
        bench_id: str,
        picks: list[tuple[str, str, int | None]],
        models: dict[str, str | None] | None = None,
    ) -> list[dict]:
        """Each workflow's result on the bench: run `eid` if given, else its latest valid one
        (its latest of any kind when none is valid, shown but not ranked). With `models` (each
        one's current session model), a result is its own only on that model; with none there,
        its latest on another model is returned marked `other_model`, and not ranked."""
        models = models or {}
        if not (benches_dir / bench_id / PG_DIR).is_dir():
            rows = []
        else:
            rows = lab_rows(only={bench_id})
        out = []
        for wid, name, eid in picks:
            if eid is not None:
                got = next((r for r in rows if r["id"] == eid), None)
            else:
                mine = [r for r in rows if r.get("workflow_id") == wid and r["status"] != "running"]
                model = models.get(wid)
                if model is not None:
                    here = [r for r in mine if r.get("model") == model]
                    mine = (here or [max(mine, key=lambda r: r["id"])]) if mine else []
                valid = [r for r in mine if (r.get("validity") or {}).get("status") == "valid"]
                got = max(valid or mine, key=lambda r: r["id"], default=None)
            res = None
            if got is not None:
                res = {
                    k: got.get(k)
                    for k in (
                        "id",
                        "bench",
                        "status",
                        "verdict",
                        "diff",
                        "ci_low",
                        "ci_high",
                        "n_pairs",
                        "pass_with",
                        "pass_without",
                        "spent_usd",
                        "reused",
                        "rig",
                        "validity",
                        "treatment",
                        "date",
                        "model",
                        "local_model",
                    )
                }
                # The "with" arm's spend per trial: the tie-break when ranking across models.
                w = (got.get("costs") or {}).get("with") or {}
                res["cost_with"] = round(w["spent_usd"] / w["tasks"], 4) if w.get("tasks") else None
                if "items" in got:  # partial credit, only when every pair counted items
                    res["items"] = got["items"]
                now = models.get(wid)
                # Measured on another session model than the workflow is on now: not its result.
                res["other_model"] = (
                    {
                        "model": got.get("model"),
                        "label": model_label(got.get("model") or ""),
                        "text": compare_mod.rule("text")["other_model"].format(
                            model=model_label(got.get("model") or "")
                        ),
                    }
                    if now is not None and got.get("model") != now
                    else None
                )
            out.append({"id": wid, "name": name, "result": res})
        return out

    def ranking(rows: list[dict]) -> dict:
        return compare_mod.rank(
            [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "rig": ((r["result"] or {}).get("rig") or {}).get("score"),
                    "diff": (r["result"] or {}).get("diff"),
                    "ci_low": (r["result"] or {}).get("ci_low"),
                    "ci_high": (r["result"] or {}).get("ci_high"),
                    "n_pairs": (r["result"] or {}).get("n_pairs") or 0,
                    "model": (r["result"] or {}).get("model"),
                    "pass_with": (r["result"] or {}).get("pass_with"),
                    "cost": (r["result"] or {}).get("cost_with"),
                    "valid": ((r["result"] or {}).get("validity") or {}).get("status") == "valid"
                    and (r["result"] or {}).get("status") != "running"
                    and not (r["result"] or {}).get("other_model"),
                }
                for r in rows
            ],
            model_label,
        )

    @app.post("/api/lab/compare/standing")
    def lab_compare_standing(body: CompareStanding):
        """Where the set stands on a bench now: each one's latest valid result, and the ranking."""
        try:
            b = bench_mod.bench(body.bench)
        except KeyError as e:
            raise HTTPException(422, f"{e}") from e
        models: dict[str, str | None] = {}
        for w in body.workflows:
            if w.get("steps"):
                try:
                    models[str(w["id"])] = session_model_of(lab.load_workflow(w), body.agent)
                except (KeyError, TypeError, ValueError) as e:
                    raise HTTPException(422, f"{e}") from e
        rows = compare_rows(
            b.id,
            [(str(w["id"]), str(w.get("name", w["id"])), None) for w in body.workflows],
            models,
        )
        return {
            "bench": b.id,
            "bench_name": b.name,
            "workflows": rows,
            "models": models,
            "rank": ranking(rows),
        }

    def compare_view(j: compare_mod.CompareJob) -> dict:
        with j.lock:
            rows = [{k: v for k, v in r.items() if k != "workflow"} for r in j.rows]
            status = j.status
        got = {
            r["id"]: r
            for r in compare_rows(
                j.bench,
                [
                    (r["id"], r["name"], r["experiment"])
                    for r in rows
                    if r["experiment"] is not None
                ],
            )
        }
        for r in rows:
            r["result"] = got[r["id"]]["result"] if r["id"] in got else None
            if r["experiment"] is not None:
                r["spent"] = round(bench_project(j.bench).store.spent(r["experiment"]), 4)
        return {
            "job": j.id,
            "bench": j.bench,
            "bench_name": j.bench_name,
            "status": status,
            "budget": j.budget,
            "share": round(compare_mod.share(j.budget, len(rows)), 4),
            "spent": round(sum(r["spent"] for r in rows), 4),
            "workflows": rows,
            "rank": ranking(rows),
        }

    def run_compare(j: compare_mod.CompareJob) -> None:
        def start(wf: dict, budget: float) -> int:
            try:
                got = start_lab_run(
                    LabRun(
                        workflow=wf,
                        bench=j.bench,
                        size=j.size,
                        budget=budget,
                        agent=j.agent,
                        auto=bool(compare_mod.rule("auto_extend")),
                        reuse_baseline=bool(compare_mod.rule("reuse_baseline")),
                    )
                )
            except HTTPException as e:
                raise compare_mod.StartError(str(e.detail)) from e
            return got["id"]

        key = lambda eid: f"lab:{j.bench}:{eid}"  # noqa: E731

        def error(eid: int) -> str | None:
            end = runs.runs[key(eid)].events[-1]
            return end.get("detail") if end.get("type") == "error" else None

        compare_mod.drive(
            j,
            start=start,
            finished=lambda eid: runs.runs[key(eid)].done,
            spent=lambda eid: bench_project(j.bench).store.spent(eid),
            stop_run=lambda eid: runs.stop(key(eid)),
            error=error,
        )

    @app.post("/api/lab/compare")
    def lab_compare(body: CompareRun):
        """Measure the set: each workflow in turn on one bench, one shared baseline."""
        wfs, b = compare_set(body)
        if not creds.ready(body.agent):
            raise HTTPException(
                400,
                f"Sign in to {agent(body.agent).label} first: click the agent at the top right to sign in.",
            )
        live = runs.busy() is not None or any(x.active() for x in suites.values())
        if live or any(x.active() for x in compares.values()):
            raise HTTPException(409, "A run is still going. Wait for it to finish.")
        j = compare_mod.new_job(
            b.id,
            b.name,
            body.agent,
            body.budget,
            body.size,
            body.workflows,
            [session_model_of(wf, body.agent) for wf in wfs],
        )
        compares[j.id] = j
        threading.Thread(target=run_compare, args=(j,), daemon=True).start()
        return {"job": j.id, "workflows": [r["id"] for r in j.rows]}

    @app.get("/api/lab/compare/{job}")
    def lab_compare_get(job: str):
        j = compares.get(job)
        if j is None:
            raise HTTPException(404, f"No comparison run {job!r}.")
        return compare_view(j)

    @app.post("/api/lab/compare/{job}/stop")
    def lab_compare_stop(job: str):
        j = compares.get(job)
        if j is None or not j.active():
            raise HTTPException(404, "That comparison run isn't going.")
        with j.lock:
            j.status = "stopping"
        j.stop.set()
        return {
            "stopping": True,
            "note": "It stops after the trial in progress and skips the rest.",
        }

    @app.post("/api/lab/improve")
    def lab_improve(body: ImproveBody):
        """Propose edits to a measured workflow from the visible tasks it failed. One model call;
        held-out tasks are never shown to it. Nothing is saved or run."""
        try:
            b = bench_mod.bench(body.bench)
        except KeyError as e:
            raise HTTPException(404, f"{e}") from e
        if not (benches_dir / b.id / PG_DIR).is_dir():
            raise HTTPException(404, "Nothing has been measured on this bench yet.")
        p = bench_project(b.id)
        e = next((x for x in p.store.list_experiments(p.pid) if x.id == body.experiment), None)
        if e is None:
            raise HTTPException(404, f"No result {body.experiment} on {b.name}.")
        saved = library / "workflows" / e.treatment_name / "workflow.json"
        try:
            wf = lab.load_workflow(
                json.loads(saved.read_text()) if saved.is_file() else body.workflow or {}
            )
        except (KeyError, TypeError, ValueError) as err:
            raise HTTPException(422, f"No workflow to improve: {err}") from err
        # The run's own tier's tasks: a hard run's failures are hard tasks.
        tier = run_meta(p.root, e.id).get("tier", "standard")
        if tier in bench_mod.tiers(b):
            b = bench_mod.for_tier(b, tier)
        items = improve.evidence(p.store.trials(e.id), b.scenarios)
        if not items:
            raise HTTPException(422, "This result has no failing visible trials to learn from.")
        model = reachable_model()
        if model is None:
            raise HTTPException(
                400,
                "Improving a workflow needs a model: pick a local model for helper calls, add an Anthropic key, or sign in to Claude Code.",
            )
        try:
            got = improve.propose(model, wf, items)
        except GenerationError as err:
            raise HTTPException(502, str(err)) from err
        lm = local.helper()
        return {
            "proposal": {
                "changes": got["changes"],
                "summary": got["summary"],
                "model": lm.label if lm else improve.V["model"],
                "failures": len(items),
                "from": e.id,
            },
            "workflow": got["workflow"].dump(),
        }

    @app.post("/api/lab/runs/{bid}/{eid}/stop")
    def lab_stop(bid: str, eid: int):
        if not runs.stop(f"lab:{bid}:{eid}"):
            raise HTTPException(404, "That run isn't going.")
        return {"stopping": True, "note": "It stops after the trial in progress."}

    @app.delete("/api/lab/results/{bid}/{eid}")
    def lab_forget(bid: str, eid: int):
        """Forget a measured run: its trials and its folder. Not while it's running."""
        live = runs.runs.get(f"lab:{bid}:{eid}")
        if live is not None and not live.done:
            raise HTTPException(409, "Stop the run first.")
        if not (benches_dir / bid / PG_DIR).is_dir():
            raise HTTPException(404, f"No results for {bid!r}.")
        p = bench_project(bid)
        try:
            p.store.get_experiment(eid)
        except KeyError as e:
            raise HTTPException(404, f"No run {eid} on {bid}.") from e
        p.store.delete_experiment(eid)
        import shutil

        shutil.rmtree(p.root / PG_DIR / "runs" / str(eid), ignore_errors=True)
        return {"removed": eid}

    @app.delete("/api/lab/benches/{bid}")
    def remove_bench(bid: str):
        """Remove an imported suite or a generated bench (built-in benches stay)."""
        import shutil

        if bid.startswith("imp-") and bench_mod.IMPORTS and bench_mod.IMPORTS.is_file():
            data = json.loads(bench_mod.IMPORTS.read_text())
            gone = next((d for d in data if d["id"] == bid), None)
            if gone is None:
                raise HTTPException(404, f"No imported suite {bid!r}.")
            bench_mod.IMPORTS.write_text(json.dumps([d for d in data if d["id"] != bid], indent=2))
            if gone.get("public"):  # a public benchmark's sample: its download goes too
                public.remove(Path(gone["path"]))
        elif bid.startswith("gen-") and (home / "generated-benches" / bid).is_dir():
            shutil.rmtree(home / "generated-benches" / bid)
        else:
            raise HTTPException(422, "Only imported suites and generated benches can be removed.")
        shutil.rmtree(benches_dir / bid, ignore_errors=True)  # its runs, too
        return {"removed": bid}

    @app.get("/api/lab/runs/{bid}/{eid}/events")
    def lab_events(bid: str, eid: int):
        run = runs.runs.get(f"lab:{bid}:{eid}")
        stream = run.follow() if run else iter([{"type": "idle"}])
        return StreamingResponse(
            sse(stream),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
        )

    def _adherence(e, trials, root: Path) -> dict | None:
        """Did the "with" trials follow the workflow? Read from their session logs."""
        wf_file = library / "workflows" / e.treatment_name / "workflow.json"
        if not wf_file.is_file():
            return None
        wf = json.loads(wf_file.read_text())
        who = run_meta(root, e.id).get("agent", "claude-code")
        checked = [
            adherence.check(wf, Path(t.transcript_uri), e.model, who)
            for t in trials
            if t.arm == "with" and t.transcript_uri and t.outcome in ("pass", "fail")
        ]
        return adherence.summarize(checked) if checked else None

    def _mcp_usage(e, trials, root: Path) -> dict | None:
        """For an MCP-server experiment: in how many "with" trials did the agent call it?"""
        if e.treatment_kind != "mcp":
            return None
        from proving_ground.baseline import meta as run_meta

        servers = run_meta(root, e.id).get("mcp_servers") or []
        per = [
            adherence.mcp_tool_calls(Path(t.transcript_uri), servers)
            for t in trials
            if t.arm == "with" and t.transcript_uri and t.outcome in ("pass", "fail")
        ]
        return adherence.summarize_mcp(per) | {"servers": servers} if per else None

    def _adherent(e, trials, root: Path, of_pairs: int) -> dict | None:
        """The same comparison on pairs whose "with" trial followed the workflow (per-protocol).
        None when logs can't be read, no pair followed, or every pair did."""
        wf_file = library / "workflows" / e.treatment_name / "workflow.json"
        if not wf_file.is_file():
            return None
        wf = json.loads(wf_file.read_text())
        who = run_meta(root, e.id).get("agent", "claude-code")
        kept = set()
        for t in trials:
            if t.arm != "with" or not t.transcript_uri or t.outcome not in ("pass", "fail"):
                continue
            a = adherence.check(wf, Path(t.transcript_uri), e.model, who)
            if a.found and a.opened is not False and not a.missing:
                kept.add((t.scenario_id, t.repeat))
        sub = summarize([t for t in trials if (t.scenario_id, t.repeat) in kept]).headline
        if sub is None or sub.n_pairs >= of_pairs:
            return None
        return {
            "diff": sub.diff,
            "ci_low": sub.ci_low,
            "ci_high": sub.ci_high,
            "n_pairs": sub.n_pairs,
            "of_pairs": of_pairs,
        }

    def probe_result(trials) -> dict:
        """A baseline check's finding: how many clean trials the agent alone passed."""
        clean = [t for t in trials if t.arm == "without" and t.outcome in ("pass", "fail")]
        passed = sum(t.outcome == "pass" for t in clean)
        return {
            "passed": passed,
            "total": len(clean),
            "text": PROBE["result"].format(passed=passed, total=len(clean)),
        }

    def run_tier(b: bench_mod.Bench, meta_: dict) -> bench_mod.Bench:
        """The bench with the tasks of the tier a run ran (standard for runs before tiers)."""
        tier = meta_.get("tier", "standard")
        return bench_mod.for_tier(b, tier) if tier in bench_mod.tiers(b) else b

    def held_out_result(b, trials) -> dict | None:
        """The same comparison on the held-out tasks alone: a workflow tuned to the visible
        tasks shows it here."""
        hidden = {s["id"] for s in b.scenarios if s.get("held_out")}
        if not hidden:
            return None
        h = summarize([t for t in trials if t.scenario_id in hidden]).headline
        if h is None:
            return {"tasks": len(hidden), "diff": None, "n_pairs": 0}
        return {
            "tasks": len(hidden),
            "diff": h.diff,
            "pass_with": h.pass_with,
            "pass_without": h.pass_without,
            "n_pairs": h.n_pairs,
        }

    def visible_result(b, trials) -> dict:
        """The same comparison on the visible tasks alone, and how many "with" trials failed there."""
        hidden = {s["id"] for s in b.scenarios if s.get("held_out")}
        vis = [t for t in trials if t.scenario_id not in hidden]
        h = summarize(vis).headline
        return {
            "diff": h.diff if h else None,
            "n_pairs": h.n_pairs if h else 0,
            "failing": sum(1 for t in vis if t.arm == "with" and t.outcome == "fail"),
        }

    judged_cache: dict[tuple, tuple[dict | None, dict]] = {}

    def judged(bid: str, p, e, trials) -> tuple[dict | None, dict]:
        """(adherence, validity) of one Lab result (evidence-validity), kept until it changes:
        reading every trial's session logs on each call would make the Lab slow."""
        done = sum(t.outcome in ("pass", "fail") for t in trials)
        key = (bid, e.id, len(trials), done, e.status)
        if key not in judged_cache:
            for k in [k for k in judged_cache if k[:2] == key[:2]]:  # an older state of this run
                del judged_cache[k]
            ad = _adherence(e, trials, p.root)
            ran = {t.scenario_id for t in trials}
            try:
                broken = validity.broken_checks(s for s in load_scenarios(p.root) if s.id in ran)
            except (FileFormatError, ValueError):
                broken = {}
            judged_cache[key] = (
                ad,
                validity.judge(trials, ad, _mcp_usage(e, trials, p.root), broken),
            )
        return judged_cache[key]

    def measured() -> list[dict]:
        """Every finished Lab run with its workflow's shape: what learned priors learn from.
        Runs that aren't evidence (evidence-validity) are marked valid False and skipped there."""
        out = []
        for b in bench_mod.benches():
            if not (benches_dir / b.id / PG_DIR).is_dir():
                continue
            p = bench_project(b.id)
            for e in p.store.list_experiments(p.pid):
                wf_file = library / "workflows" / e.treatment_name / "workflow.json"
                if not wf_file.is_file():
                    continue
                try:
                    wf = lab.load_workflow(json.loads(wf_file.read_text()))
                except (TypeError, ValueError, KeyError):
                    continue
                ev = evidence_json(p.store, e)
                diff = ev.get("diff")
                _, valid = judged(b.id, p, e, p.store.trials(e.id))
                out.append(
                    {
                        "id": wf.id,
                        "features": lab.features(wf),
                        "diff": None if diff is None else diff * 100,
                        "pairs": ev.get("n_pairs") or 0,
                        "tier": priors.model_tier(e.model),
                        "discipline": b.discipline,
                        "bench": b.id,
                        "experiment": e.id,
                        "valid": valid["status"] == validity.VALID,
                    }
                )
        return out

    def learned(wfs: list[dict], runs_: list[dict] | None = None) -> list[dict]:
        """Each workflow with its guess moved by similar measured runs, where there are any."""
        runs_ = measured() if runs_ is None else runs_
        out = []
        for d in wfs:
            try:
                wf = lab.load_workflow(d)
            except (TypeError, ValueError, KeyError):
                out.append(d)
                continue
            got = priors.learn(
                wf.id,
                lab.features(wf),
                wf.prior,
                runs_,
                tier="cloud_frontier",
                discipline=wf.discipline,
            )
            out.append(d | {"learned": got.dump() if got else None})
        return out

    @app.get("/api/lab/results/{bid}/{eid}/forensics")
    def lab_forensics(bid: str, eid: int):
        """Why the with and without trials of the same task ended differently."""
        if not (benches_dir / bid / PG_DIR).is_dir():
            raise HTTPException(404, f"No results for {bid!r}.")
        p = bench_project(bid)
        try:
            e = p.store.get_experiment(eid)
        except KeyError as err:
            raise HTTPException(404, f"No run {eid} on {bid}.") from err
        wf_file = library / "workflows" / e.treatment_name / "workflow.json"
        wf = json.loads(wf_file.read_text()) if wf_file.is_file() else None
        by_id = {s.id: s for s in load_scenarios(p.root)}
        pairs = forensics.discordant(p.store.trials(eid), by_id, wf)
        counts: dict[str, int] = {}
        for pr in pairs:
            for arm in ("with", "without"):
                if pr[arm]["outcome"] != "pass":
                    counts[pr[arm]["bucket"]] = counts.get(pr[arm]["bucket"], 0) + 1
        return {"pairs": pairs, "counts": counts}

    @app.get("/api/lab/workflow")
    def lab_workflow_of(treatment: str = Query(pattern=r"^workflow-[\w.-]+$")):
        """The workflow a measured run ran (its compiled folder's workflow.json), to open it again."""
        f = library / "workflows" / treatment / "workflow.json"
        if not f.is_file():
            raise HTTPException(404, f"The workflow for {treatment} is no longer in the library.")
        try:
            wf = lab.load_workflow(json.loads(f.read_text()))
        except (KeyError, TypeError, ValueError) as e:
            raise HTTPException(422, f"Not a workflow: {e}") from e
        return learned([wf.dump()])[0]

    @app.get("/api/lab/results")
    def lab_results():
        return lab_rows()

    @app.get("/api/lab/results/{bid}/{eid}")
    def lab_result(bid: str, eid: int):
        """One Lab run, read-only: its results row, summary and trials (the Runs page's link)."""
        if not (benches_dir / bid / PG_DIR).is_dir():
            raise HTTPException(404, f"No results for {bid!r}.")
        row = next((r for r in lab_rows(only={bid}) if r["id"] == eid), None)
        if row is None:
            raise HTTPException(404, f"No run {eid} on {bid}.")
        p = bench_project(bid)
        e = p.store.get_experiment(eid)
        trials = p.store.trials(eid)
        return experiment_json(p.store, e) | {
            **row,
            "treatment_name": row["workflow"],
            "summary": summary_json(summarize(trials)),
            "trials": [
                asdict(t) | {"kind": t.kind.value, "timed_out": t.timed_out} for t in trials
            ],
        }

    def refresh_proven(name: str) -> None:
        """Write PROVEN.md and the `proven:` line for one workflow folder from its finished runs.
        A badge must never break a save or a run, so a failure here is dropped."""
        d = library / "workflows" / name
        if not (d / "SKILL.md").is_file():
            return
        wf_file = d / "workflow.json"
        label = json.loads(wf_file.read_text()).get("name", name) if wf_file.is_file() else name
        try:
            proven_mod.refresh(d, label, lab_rows(name, live=False))
        except Exception:  # noqa: BLE001
            pass

    def lab_rows(
        treatment: str | None = None, live: bool = True, only: set[str] | None = None
    ) -> list[dict]:
        """Every measured Lab run (or those of one workflow folder, on the benches in `only`).
        `live` lets a run still going read "running"."""
        names = {}
        for d in (library / "workflows").glob("workflow-*"):
            if (d / "workflow.json").is_file():
                names[d.name] = json.loads((d / "workflow.json").read_text()).get("name", d.name)
        out = []
        saving = {}  # (bench, id): a run scored on tokens, cost or time (rig-score: Metric)
        for b in bench_mod.benches():
            if not (benches_dir / b.id / PG_DIR).is_dir() or (
                only is not None and b.id not in only
            ):
                continue
            p = bench_project(b.id)
            for e in p.store.list_experiments(p.pid):
                if treatment is not None and e.treatment_name != treatment:
                    continue
                ev = evidence_json(p.store, e)
                trials = p.store.trials(e.id)
                h = summarize(trials).headline
                # Between auto-extend batches the experiment reads "done": the live run says otherwise.
                going = runs.runs.get(f"lab:{b.id}:{e.id}") if live else None
                if going is not None and not going.done:
                    ev["status"] = "running"
                    ev["status_text"] = status_text("running")
                reused = [t for t in trials if t.reused_from is not None]
                saved = sum(source_cost(p.store)(t) for t in reused)
                meta_ = run_meta(p.root, e.id)
                ad, valid = judged(b.id, p, e, trials)
                metric = run_metric(p.root, e.id)
                saving[(b.id, e.id)] = rig_mod.metric_evidence(trials, metric, source_cost(p.store))
                out.append(
                    {
                        "bench": b.id,
                        "bench_name": b.name,
                        "id": e.id,
                        "workflow": PROBE["label"]
                        if meta_.get("probe")
                        else names.get(e.treatment_name, e.treatment_name),
                        # A baseline check: the agent alone, no "with" arm (bench-difficulty).
                        "probe": bool(meta_.get("probe")),
                        "tier": meta_.get("tier", "standard"),
                        "probe_result": probe_result(trials) if meta_.get("probe") else None,
                        "treatment": e.treatment_name,
                        "model": e.model,
                        "agent": meta_.get("agent", "claude-code"),
                        "bench_version": meta_.get("bench_version"),
                        "date": e.created_at[:10],
                        "spent_usd": round(p.store.spent(e.id), 4),
                        "budget_usd": e.budget_usd,
                        # Spent over the budget: by how much, and whether it predates the cap.
                        "over_budget": overspend(
                            p.store.spent(e.id), e.budget_usd, meta_, e.created_at
                        ),
                        "workflow_id": meta_.get("workflow"),
                        "pass_with": h.pass_with if h else None,
                        "pass_without": h.pass_without if h else None,
                        "reused": len(reused),
                        "saved_usd": round(saved, 4),
                        "adherence": ad,
                        "validity": valid,
                        # One count of the trials that every line of the result cites.
                        "ledger": rig_mod.ledger(trials, ad["read"] if ad else None),
                        "discordant": forensics.discordant_count(trials),
                        "adherent": _adherent(e, trials, p.root, h.n_pairs) if h else None,
                        "costs": costs_json(p.store, trials),
                        # Cost, time and timeouts per arm and per task: the verdict's evidence.
                        "arms": rig_mod.arms(trials, source_cost(p.store)),
                        "held_out": held_out_result(run_tier(b, meta_), trials),
                        "visible": visible_result(run_tier(b, meta_), trials),
                        "improved_from": meta_.get("improved_from"),
                        "local": bool(meta_.get("local_model")),
                        "local_model": local_run(meta_),
                        "judge": judge_state(b),
                        # What the run is scored on; older runs read as the pass rate.
                        "metric": metric,
                        **ev,
                    }
                )
        by_id = {(r["bench"], r["id"]): r for r in out}
        for r in out:
            parent = by_id.get((r["bench"], r["improved_from"]))
            r["overfit"] = improve.overfit(parent, r) if parent else None
            m = saving[(r["bench"], r["id"])]
            r["rig"] = rig_mod.rig_score(
                rig_mod.evidence_from_row(r, "workflow") | ({"metric": m} if m else {})
            )
            if r["probe"]:  # no "with" arm: no verdict or Rig score, the agent alone's rate
                r["rig"] = r["verdict"] = None
        return out

    def judge_state(b) -> dict | None:
        """None for a bench graded by checks alone; else whether its judge was calibrated as
        trustworthy (the Rig score's Reliable part)."""
        if not b.judged:
            return None
        return {"trustworthy": bool((saved_calibration(b) or {}).get("trustworthy"))}

    def _ablation_parent(wf: lab.Workflow, bench: str, agent_id: str) -> dict:
        """The workflow's newest finished measured run on this bench, as a results row."""
        name = lab.workflow_name(wf, agent_id)
        rows = [
            r
            for r in lab_results()
            if r["bench"] == bench and r["treatment"] == name and r["status"] == "done"
        ]
        if not rows:
            raise HTTPException(422, "Measure this workflow on this bench first; then slim it.")
        return max(rows, key=lambda r: r["id"])

    def _run_done(bid: str, eid: int) -> bool:
        live = runs.runs.get(f"lab:{bid}:{eid}")
        return live is None or live.done

    ablations = ablation.Jobs(
        start=lambda args: start_lab_run(LabRun(**args)),
        finished=_run_done,
        spent=lambda bid, eid: bench_project(bid).store.spent(eid),
        stop_run=lambda bid, eid: runs.stop(f"lab:{bid}:{eid}"),
        busy=runs.busy,
    )

    @app.post("/api/lab/ablate/preview")
    def lab_ablate_preview(body: dict):
        try:
            wf = lab.load_workflow(body)
        except (KeyError, TypeError, ValueError) as e:
            raise HTTPException(422, f"{e}") from e
        chosen = ablation.planned(wf)
        return {
            "count": len(chosen),
            "of": len(ablation.plan(wf)),
            "variants": [v.label for v in chosen],
        }

    @app.post("/api/lab/ablate")
    def lab_ablate(body: LabAblate):
        try:
            agent(body.agent)
            wf = lab.load_workflow(body.workflow)
            bench_mod.bench(body.bench)
        except (KeyError, TypeError, ValueError) as e:
            raise HTTPException(422, f"{e}") from e
        parent = _ablation_parent(wf, body.bench, body.agent)
        if (going := ablations.running()) is not None:
            raise HTTPException(409, f"Slimming job {going.id} is still going.")
        if (busy := runs.busy()) is not None:
            raise HTTPException(409, f"Run {busy} is still going. Wait for it to finish.")
        try:
            job = ablations.create(
                wf,
                body.bench,
                body.budget,
                body.agent,
                parent_eid=parent["id"],
                size=body.size,
                auto=body.auto,
                local_model=body.local_model,
            )
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        return job.dump()

    @app.get("/api/lab/ablate/{jid}")
    def lab_ablate_get(jid: str):
        job = ablations.jobs.get(jid)
        if job is None:
            raise HTTPException(404, f"No slimming job {jid!r}.")
        out = job.dump()
        if job.status == "running" and not any(v["status"] == "done" for v in job.variants):
            return out | {"contributions": None}
        rows = {(r["bench"], r["id"]): r for r in lab_results()}
        done = [
            rows[(job.bench, v["experiment_id"])] | {"key": v["key"], "kind": v["kind"]}
            for v in job.variants
            if v["status"] == "done" and (job.bench, v["experiment_id"]) in rows
        ]
        parent = rows.get((job.bench, job.parent_eid))
        out["contributions"] = (
            ablation.contributions(parent, done) if parent and job.status != "running" else None
        )
        return out

    @app.post("/api/lab/ablate/{jid}/stop")
    def lab_ablate_stop(jid: str):
        if not ablations.stop(jid):
            raise HTTPException(404, "That job isn't going.")
        return {"stopping": True, "note": "The run in progress stops after its trial."}

    @app.get("/api/lab/matrix")
    def lab_matrix(bench: str = Query(pattern=r"^[\w.-]+$")):
        """Every workflow measured on one bench, on the same tasks: the cost-vs-lift frontier and
        the task-by-workflow grid. Held-out tasks keep their place in the grid, not their title."""
        from proving_ground.baseline import meta as run_meta

        try:
            b = bench_mod.bench(bench)
        except KeyError as e:
            raise HTTPException(404, str(e.args[0])) from e
        tasks, shown = [], {}
        for n, s in enumerate(b.scenarios, 1):
            hidden = bool(s.get("held_out"))
            sid = f"held-out-{n}" if hidden else s["id"]
            shown[s["id"]] = sid
            tasks.append({"id": sid, "title": "Held-out task" if hidden else s["title"]})
        if not (benches_dir / b.id / PG_DIR).is_dir():
            return {"bench": b.id, "latest": None, "rows": [], "tasks": tasks}
        p = bench_project(b.id)
        names = {}
        for d in (library / "workflows").glob("workflow-*"):
            if (d / "workflow.json").is_file():
                names[d.name] = json.loads((d / "workflow.json").read_text()).get("name", d.name)

        def cost_of(t) -> float:
            # A reused baseline trial costs what it cost when it ran, as in lab_results.
            if t.reused_from is None:
                return t.cost_usd
            src = [
                x.cost_usd
                for x in p.store.trials(t.reused_from)
                if x.arm == "without" and x.scenario_id == t.scenario_id
            ]
            return sum(src) / len(src) if src else 0.0

        rows = []
        experiments = p.store.list_experiments(p.pid)
        for e in experiments:
            trials = p.store.trials(e.id)
            summary = summarize(trials)
            h = summary.headline
            finished = [t for t in trials if t.outcome in ("pass", "fail")]
            mine = [t for t in finished if t.arm == "with"]
            # arm -> [passes, finished trials], per shown task
            per: dict[str, dict[str, list[int]]] = {}
            for t in finished:
                sid = shown.get(t.scenario_id)
                if sid is None or t.arm not in ("with", "without"):
                    continue
                c = per.setdefault(sid, {"with": [0, 0], "without": [0, 0]})[t.arm]
                c[0] += t.outcome == "pass"
                c[1] += 1
            rows.append(
                {
                    "experiment_id": e.id,
                    "workflow": names.get(e.treatment_name, e.treatment_name),
                    "treatment": e.treatment_name,
                    "model": e.model,
                    "local_model": local_run(run_meta(p.root, e.id)),
                    "agent": run_meta(p.root, e.id).get("agent", "claude-code"),
                    # Not evidence (evidence-validity): listed, never on the frontier.
                    "validity": judged(b.id, p, e, trials)[1],
                    "n_pairs": h.n_pairs if h else 0,
                    "diff": h.diff if h else None,
                    "ci_low": h.ci_low if h else None,
                    "ci_high": h.ci_high if h else None,
                    "pass_with": h.pass_with if h else None,
                    "pass_without": h.pass_without if h else None,
                    "cost_per_trial_usd": (
                        round(sum(cost_of(t) for t in mine) / len(mine), 4) if mine else None
                    ),
                    "mean_duration_s": (
                        round(sum(t.duration_s for t in mine) / len(mine), 1) if mine else None
                    ),
                    "per_task": {
                        sid: {
                            "with": c["with"][0] / c["with"][1] if c["with"][1] else None,
                            "without": c["without"][0] / c["without"][1]
                            if c["without"][1]
                            else None,
                            "n": c["with"][1],
                        }
                        for sid, c in per.items()
                    },
                }
                | items_json(summary)
            )
        latest = max((e.created_at for e in experiments), default=None)
        return {"bench": b.id, "latest": latest, "rows": rows, "tasks": tasks}

    estimate_slots = threading.BoundedSemaphore(ESTIMATE_SLOTS)
    summaries: dict[str, tuple[float, str]] = {}

    def repo_summary(root: Path) -> str:
        at, text = summaries.get(str(root), (0.0, ""))
        if time.time() - at > SUMMARY_TTL_S:
            text = scan_to_text(scan_repo(root), per_file_chars=800)
            summaries[str(root)] = (time.time(), text)
        return text

    def measured_for(p: Project, path: Path, items: list[Scenario]):
        """The newest valid run of this very skill (its evidence), and why an invalid one isn't."""
        measured, not_evidence = None, None
        digest = hash_tree(path)
        for e in p.store.list_experiments(p.pid):  # newest first
            if e.treatment_name == path.name and e.treatment_hash == digest:
                trials = p.store.trials(e.id)
                ran = {t.scenario_id for t in trials}
                v = validity.judge(
                    trials,
                    mcp_usage=_mcp_usage(e, trials, p.root),
                    broken=validity.broken_checks(s for s in items if s.id in ran),
                )
                if v["status"] == validity.VALID:
                    measured, not_evidence = evidence_json(p.store, e), None
                    break
                # A run that couldn't show a difference isn't a measurement: try an older one.
                not_evidence = not_evidence or (
                    f"Its last run isn't evidence ({v['badge']}), so this is an estimate."
                )
        return measured, not_evidence

    @app.post("/api/estimate/batch")
    def estimate_batch(body: EstimateBatch, p: Project = Depends(current)):
        """The rough guess (no model, ever) for many skills in one request: what a repo's own
        skills show the moment it opens. Answers in the order asked; a skill that can't be read
        gets {basis: none, reason} instead of failing the rest."""
        items = scenarios(p)
        names = [f"{s.title or s.id} ({s.kind.value})" for s in items]
        estimator = Estimator(None, p.root / PG_DIR / "estimates.json")
        cost_hint = {"sharpen_usd": skills.value("estimate-effect", "model_call_usd")}
        out = []
        for it in body.items:
            path = Path(it.treatment_path)
            if not (path / "SKILL.md").is_file():
                out.append({"basis": "none", "reason": f"{path} has no SKILL.md"})
                continue
            measured, not_evidence = measured_for(p, path, items)
            got = estimator.estimate(
                EstimateInput(
                    name=path.name,
                    skill_text=(path / "SKILL.md").read_text(errors="replace"),
                    steps=it.steps,
                    scenarios=names,
                    repo_summary="",
                    measured=measured,
                ),
                quick=True,
            )
            out.append(got | cost_hint | ({"note": not_evidence} if not_evidence else {}))
        return {"estimates": out}

    @app.post("/api/estimate")
    def estimate(body: EstimateRequest, p: Project = Depends(current)):
        path = Path(body.treatment_path)
        if not (path / "SKILL.md").is_file():
            raise HTTPException(422, f"{path} has no SKILL.md")
        items = scenarios(p)
        measured, not_evidence = measured_for(p, path, items)
        cost_hint = {"sharpen_usd": skills.value("estimate-effect", "model_call_usd")}
        # A model only when the request asks for one (model: true); every card starts rough.
        wants_model = body.model and not body.quick
        key = anthropic_key() if wants_model else None
        import anthropic

        # An API key if there is one, else Claude Code's own login here, else the rough guess.
        if key:
            model = AnthropicClient(anthropic.Anthropic(api_key=key, max_retries=2))
        elif wants_model and host():
            model = cli_model()
        else:
            model = None
        estimator = Estimator(model, p.root / PG_DIR / "estimates.json")
        quick = not wants_model
        # The rough guess needs no repo summary; a model estimate gets one read at most once a
        # few minutes per repo, and only a couple of model estimates run at once, so opening a
        # repo with many skills can't tie up the server.
        summary = "" if quick or model is None else repo_summary(p.root)
        try:
            with estimate_slots if model is not None and not quick else nullcontext():
                out = estimator.estimate(
                    EstimateInput(
                        name=path.name,
                        skill_text=(path / "SKILL.md").read_text(errors="replace"),
                        steps=body.steps,
                        scenarios=[f"{s.title or s.id} ({s.kind.value})" for s in items],
                        repo_summary=summary,
                        measured=measured,
                    ),
                    quick=quick,
                )
            if wants_model and model is None and out.get("basis") == "rough":
                out = out | {
                    "note": "No model to ask: add an Anthropic key or click the agent at the top right to sign in."
                }
            return out | cost_hint | ({"note": not_evidence} if not_evidence else {})
        except GenerationError as e:
            # The model didn't answer: still show the rough number, and say why.
            out = estimator.estimate(
                EstimateInput(
                    name=path.name,
                    skill_text=(path / "SKILL.md").read_text(errors="replace"),
                    steps=body.steps,
                    scenarios=[f"{s.title or s.id} ({s.kind.value})" for s in items],
                    repo_summary=summary,
                ),
                quick=True,
            )
            return (
                out
                | cost_hint
                | {"note": f"The model estimate failed ({e}); showing the rough guess."}
            )

    def settle(p: Project) -> None:
        """A run marked running whose thread is gone (the server was restarted) has stopped."""
        going = runs.current()
        for e in p.store.list_experiments(p.pid):
            live = (
                going is not None
                and going[0] == e.id
                and going[1].root.resolve() == p.root.resolve()
            )
            if e.status == "running" and not live:
                p.store.set_status(e.id, "stopped")

    def repo_judged(p: Project, e, trials) -> dict:
        """Everything a repo run's lines cite, read once: adherence (a workflow handed over),
        whether the agent opened the skill, MCP use, validity and the trial ledger."""
        workflow = (library / "workflows" / e.treatment_name / "workflow.json").is_file()
        opened = None
        if not workflow and e.treatment_kind == "skill":
            seen = [
                adherence.skill_opened(Path(t.transcript_uri), e.treatment_name)
                for t in trials
                if t.arm == "with" and t.transcript_uri and t.outcome in ("pass", "fail")
            ]
            seen = [x for x in seen if x is not None]
            opened = {"read": len(seen), "opened": sum(seen)} if seen else None
        ad = _adherence(e, trials, p.root) if workflow else None
        usage = _mcp_usage(e, trials, p.root)
        ran = {t.scenario_id for t in trials}
        try:
            broken = validity.broken_checks(s for s in scenarios(p) if s.id in ran)
        except (OSError, ValueError, HTTPException):
            broken = {}
        read = ad["read"] if ad else opened["read"] if opened else None
        return {
            "workflow": workflow,
            "adherence": ad,
            "opened": opened,
            "mcp_usage": usage,
            "validity": validity.judge(trials, ad, usage, broken),
            "ledger": rig_mod.ledger(trials, read),
        }

    def repo_rig(p: Project, e, trials=None, got: dict | None = None) -> dict:
        """The Rig score of one repo experiment: a skill (did the agent open it) or a workflow
        handed over (did it follow the steps)."""
        trials = p.store.trials(e.id) if trials is None else trials
        got = repo_judged(p, e, trials) if got is None else got
        workflow, opened = got["workflow"], got["opened"]
        h = summarize(trials).headline
        try:
            judged = {s_.id for s_ in load_scenarios(p.root) if s_.judge is not None}
        except (OSError, ValueError):  # a broken scenario file must not hide the results
            judged = set()
        row = evidence_json(p.store, e) | {
            "pass_with": h.pass_with if h else None,
            "pass_without": h.pass_without if h else None,
            "arms": rig_mod.arms(trials, source_cost(p.store)),
            "validity": got["validity"],
            "ledger": got["ledger"],
            "costs": costs_json(p.store, trials),
            "adherence": got["adherence"],
            "opened": opened,
            "local": bool(run_meta(p.root, e.id).get("local_model")),
            # Repo scenarios have no judge calibration: a judged one counts as not calibrated.
            "judge": {"trustworthy": False}
            if any(t.scenario_id in judged for t in trials)
            else None,
            # What the run is scored on (rig-score: Metric); None for the pass rate.
            "metric": rig_mod.metric_evidence(
                trials, run_metric(p.root, e.id), source_cost(p.store)
            ),
        }
        kind = "workflow" if workflow else e.treatment_kind
        if kind == "mcp" and got["mcp_usage"]:  # Followed: did the agent call the server
            row["opened"] = {"read": got["mcp_usage"]["read"], "opened": got["mcp_usage"]["used"]}
        return rig_mod.rig_score(
            rig_mod.evidence_from_row(
                row,
                kind
                if kind in ("workflow", "hook", "mcp", "instructions", "before_after")
                else "skill",
            )
        )

    @app.get("/api/experiments")
    def get_experiments(p: Project = Depends(current)):
        settle(p)
        out = []
        for e in p.store.list_experiments(p.pid):
            trials = p.store.trials(e.id)
            s_ = summarize(trials)
            got = repo_judged(p, e, trials)
            meta_ = run_meta(p.root, e.id)
            out.append(
                experiment_json(p.store, e)
                | {
                    "verdict": s_.verdict.value,
                    "n_pairs": s_.headline.n_pairs if s_.headline else 0,
                    "agent": meta_.get("agent", "claude-code"),
                    "metric": run_metric(p.root, e.id),
                    "before_after": meta_.get("before_after"),
                    "local_model": local_run(meta_),
                    "rig": repo_rig(p, e, trials, got),
                    "validity": got["validity"],
                    "ledger": got["ledger"],
                    "over_budget": overspend(
                        p.store.spent(e.id), e.budget_usd, meta_, e.created_at
                    ),
                }
                | items_json(s_)
            )
        return out

    @app.delete("/api/experiments/{eid}")
    def forget_experiment(eid: int, p: Project = Depends(current)):
        """Forget a repo's run: its trials and its folder. Not while it's running."""
        going = runs.current()
        if going is not None and going[0] == eid and going[1].root.resolve() == p.root.resolve():
            raise HTTPException(409, "Stop the run first.")
        try:
            p.store.get_experiment(eid)
        except KeyError as e:
            raise HTTPException(404, f"No run {eid} in this repo.") from e
        p.store.delete_experiment(eid)
        import shutil

        shutil.rmtree(p.root / PG_DIR / "runs" / str(eid), ignore_errors=True)
        return {"removed": eid}

    @app.get("/api/experiments/{eid}")
    def get_experiment(eid: int, p: Project = Depends(current)):
        try:
            e = p.store.get_experiment(eid)
        except KeyError as err:
            raise HTTPException(404, str(err.args[0])) from err
        trials = p.store.trials(eid)
        got = repo_judged(p, e, trials)
        meta_ = run_meta(p.root, e.id)
        s_ = summarize(trials)
        return (
            experiment_json(p.store, e)
            | items_json(s_)
            | {
                "rig": repo_rig(p, e, trials, got),
                "mcp_usage": got["mcp_usage"],
                # Whether it is evidence at all (evidence-validity); the estimate ignores it if not.
                "validity": got["validity"],
                "adherence": got["adherence"],
                "ledger": got["ledger"],
                "agent": meta_.get("agent", "claude-code"),
                "metric": run_metric(p.root, e.id),
                # A code change measured before and after: its two sides (Results names the arms).
                "before_after": meta_.get("before_after"),
                # The local model it ran on ({id, label}), or None for the signed-in agent.
                "local_model": local_run(meta_),
                "over_budget": overspend(p.store.spent(e.id), e.budget_usd, meta_, e.created_at),
                "summary": summary_json(s_),
                "trials": [
                    asdict(t) | {"kind": t.kind.value, "timed_out": t.timed_out} for t in trials
                ],
            }
        )

    @app.post("/api/experiments")
    def start_experiment(body: ExperimentRequest, p: Project = Depends(current)):
        try:
            agent(body.agent)
        except KeyError as e:
            raise HTTPException(422, str(e.args[0])) from e
        # A resumed run goes on where it ran: on its own local model, whatever the request says.
        local_id = (
            run_meta(p.root, body.resume).get("local_model")
            if body.resume is not None
            else body.local_model
        )
        model, env, harbor_model, lm = body.model, None, None, None
        if local_id:
            # As the Lab's: Claude Code on a server speaking Anthropic's API, no sign-in needed.
            model, env, harbor_model, lm = run_target(body.agent, local_id, None)
        elif not creds.ready(body.agent):
            raise HTTPException(
                400,
                f"Sign in to {agent(body.agent).label} first: click the agent at the top right to sign in.",
            )
        else:
            env = creds.env_for(body.agent)
        busy = runs.busy()
        if busy is not None:
            raise HTTPException(409, f"experiment {busy} is still running. Wait for it to finish.")
        n = body.n
        change = None
        if body.before_after is not None:  # refused before anything is priced or written
            try:
                change = resolve_change(p.root, body.before_after.base, body.before_after.after)
            except BeforeAfterError as e:
                raise HTTPException(422, str(e)) from e
        elif not body.treatment_path:
            raise HTTPException(422, "Pick a change to measure.")
        name = change.name if change is not None else Path(body.treatment_path).name
        costs = run_costs(body.agent, model, name, project=p, free=lm is not None)
        metric = body.metric or goal_metric(p) or rig_mod.M["default"]
        if lm is not None and metric == "cost" and body.resume is None:
            raise HTTPException(422, local_mod.L["repo"]["cost_metric"])
        if body.size is not None and body.scenario_ids and body.resume is None:
            tasks = len(set(body.scenario_ids))
            n = gate_mod.size_count(tasks, body.size)
            if body.size == "full":
                n = full_pairs(tasks, per_pair(costs), body.budget, n, sized_for(metric))
        # `metric`: the choice on Measure, else the goal's hint, else the pass rate (rig-score:
        # Metric). Kept in the run's meta.json.
        try:
            prep = prepare_experiment(
                p.root,
                Path(body.treatment_path) if change is None else None,
                body.budget,
                n,
                model,
                body.kinds,
                body.scenario_ids,
                body.resume,
                agent=body.agent,
                env=env,
                # A small local model never opens a skill it is only offered: told to, unless
                # the request says not to.
                nudge=True
                if lm is not None
                and body.nudge_prompt is None
                and change is None
                and (Path(body.treatment_path) / "SKILL.md").is_file()
                else body.nudge_prompt,
                refuse=lambda: cant_start(costs, body.budget),  # a resumed run isn't asked
                extra_meta={"metric": metric}
                | ({"local_model": lm.id, "local_label": lm.label} if lm is not None else {}),
                change=change,
                harbor_model=harbor_model,
                free=lm is not None,
                timeout_factor=local_mod.L["timeout_factor"] if lm is not None else 1.0,
            )
        except ServiceError as e:
            raise HTTPException(422, str(e)) from e
        if body.auto:
            prep.auto = skills.value("judge-experiment", "auto_extend")
        runs.start(prep)
        return {
            "id": prep.eid,
            "repeats": prep.repeats,
            "scenarios": [s.id for s in prep.scenarios],
            "trials": 2 * prep.repeats * len(prep.scenarios),
            "model": prep.model,
            "agent": body.agent,
            "budget": prep.budget,
            "commit": prep.commit,
            "dirty": prep.dirty,
            "metric": run_metric(p.root, prep.eid),
            "before_after": run_meta(p.root, prep.eid).get("before_after"),
            "local_model": local_run(run_meta(p.root, prep.eid)),
        }

    @app.get("/api/before-after/refs")
    def before_after_refs(p: Project = Depends(current)):
        """What Measure offers for a before/after run: HEAD, branches, recent commits, and
        whether there are uncommitted changes. Reads git only; changes nothing."""
        return repo_refs(p.root)

    @app.post("/api/before-after/compare")
    def before_after_compare(body: BeforeAfterBody, p: Project = Depends(current)):
        """What a before/after run would compare: both sides, the files that differ, and
        `same` when it would measure nothing. 422 for an unknown ref or a repo with no commit."""
        try:
            return compare_change(p.root, body.base, body.after)
        except BeforeAfterError as e:
            raise HTTPException(422, str(e)) from e

    @app.post("/api/experiments/{eid}/stop")
    def stop_experiment(eid: int, p: Project = Depends(current)):
        """Stop a repo's run after the trial in progress (a Docker trial isn't killed halfway)."""
        going = runs.current()
        if going is None or going[0] != eid or going[1].root.resolve() != p.root.resolve():
            raise HTTPException(404, f"Experiment {eid} isn't running in this repo.")
        runs.stop(eid)
        return {"stopping": True}

    @app.post("/api/runs/estimate")
    def run_estimate(body: RunEstimate):
        """The trial-budget prediction for a run that hasn't started: per trial on each arm, per
        pair, for the planned pairs, and how many pairs the budget pays for. No model call, no
        sign-in needed."""
        try:
            agent(body.agent)
        except KeyError as e:
            raise HTTPException(422, str(e.args[0])) from e
        model = body.model or DEFAULT_MODEL
        treatment = Path(body.treatment_path).name if body.treatment_path else ""
        if body.workflow is not None:
            try:
                wf = lab.load_workflow(body.workflow)
            except (KeyError, TypeError, ValueError) as e:
                raise HTTPException(422, f"Not a workflow: {e}") from e
            treatment = lab.workflow_name(wf, body.agent)
            if body.agent == "claude-code":
                models = [st.model for st in wf.steps if st.kind == "do"] or [
                    st.model for st in wf.steps
                ]
                model = body.model or gate_mod.session_model(models)
            else:
                model = agent(body.agent).default_model or f"{body.agent}:default"
        project = None
        if body.repo and not body.bench:
            r = ws.get(body.repo)
            if r is None:
                raise HTTPException(404, f"No repo with id {body.repo!r}.")
            project = open_project(r)
        costs = run_costs(
            body.agent,
            model,
            treatment,
            bench=body.bench,
            project=project,
            free=body.local,
            tier=(body.tier or skills.value("bench-difficulty", "default_tier"))
            if body.bench
            else None,
        )
        pairs, pilot, full, grows = body.pairs, body.pilot_pairs, body.full_pairs, False
        if body.size is not None and body.tasks is not None:
            # One bench or repo: the pairs the run will plan, as starting it plans them.
            pilot = body.tasks
            full = full_pairs(
                body.tasks,
                per_pair(costs),
                body.budget,
                gate_mod.size_count(body.tasks, "full"),
                sized_for(body.metric),
            )
            grows = body.size == "full"
            pairs = full if grows else pilot
        out = forecast(costs, pairs, body.budget, pilot, full, grows) | {"model": model}
        if body.metric and body.metric != rig_mod.M["default"]:
            # What the budget pays for is what runs: the guard is judged on that.
            got = min(pairs, out.get("pairs_in_budget", pairs))
            out["metric_plan"] = rig_mod.metric_plan(
                body.metric,
                got,
                None if costs.free else per_pair(costs),
                extends=body.auto,
                budget=body.budget,
            )
        if body.auto and body.size is not None and body.tasks is not None:
            # What it may grow to while undecided, as execute's caps allow; the budget still stops it.
            out["extends"] = extend_plan(
                skills.value("judge-experiment", "auto_extend"),
                pairs,
                body.tasks,
                bool(body.metric) and body.metric != rig_mod.M["default"],
                0.0 if costs.free else per_pair(costs),
                body.budget,
            )
        return out

    def sized_for(metric: str | None) -> int | None:
        """A saving metric's full run grows to the guard's pairs; the pass rate's, to its own."""
        return (
            None if not metric or metric == rig_mod.M["default"] else rig_mod.metric_guard_pairs()
        )

    def run_costs(
        agent_id: str,
        model: str,
        treatment: str,
        bench: str | None = None,
        project: Project | None = None,
        free: bool = False,
        tier: str | None = None,
    ) -> CostModel:
        """The budget check's cost model before a run: costs measured on earlier runs on this
        bench or repo, whatever their validity (trial-budget), else the prior."""
        from proving_ground.budget import measured as measured_costs
        from proving_ground.budget import prior_usd

        seen: dict = {"with": [], "without": []}
        notes: dict = {}
        p = None
        if bench:
            if (benches_dir / bench / PG_DIR).is_dir():
                p = bench_project(bench)
        else:
            p = project
        if p is not None:
            seen, notes = measured_costs(
                p.store, p.root, p.pid, model, agent_id, treatment, tier=tier if bench else None
            )
        return CostModel(prior_usd(model), seen, free=free, notes=notes)

    @app.get("/api/runs/active")
    def active_run():
        """What is running anywhere (any repo, or a bench in the Lab), for the top bar."""
        going = runs.current()
        if going is None:
            return {"running": None}
        key, prep = going
        spent = sum(t.cost_usd or 0 for t in prep.store.trials(prep.eid))
        where: dict = (
            {"kind": "bench", "bench": str(key).split(":")[1]}
            if str(key).startswith("lab:")
            else {"kind": "repo"}
        )
        if where["kind"] == "repo":
            r = next((x for x in ws.repos() if Path(x.root).resolve() == prep.root.resolve()), None)
            where |= {"repo": r.id if r else None, "repo_name": r.name if r else prep.root.name}
        probe = prep.arms == (PROBE["arm"],)
        return {
            "running": where
            | {
                "id": prep.eid,
                # A baseline check reads as one, not as its placeholder treatment.
                "treatment": PROBE["label"] if probe else prep.treatment.name,
                "probe": probe,
                "model": prep.model,
                "spent_usd": round(spent, 4),
                "budget_usd": prep.budget,
                "trials": len(prep.store.trials(prep.eid)),
            }
        }

    @app.get("/api/experiments/{eid}/events")
    def experiment_events(eid: int):
        run = runs.runs.get(eid)
        stream = run.follow() if run else iter([{"type": "idle"}])
        return StreamingResponse(
            sse(stream),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
        )

    @app.get("/api/doctor")
    def doctor():
        return [
            {"name": c.name, "ok": c.ok, "detail": c.detail}
            for c in run_checks(home / "runs-probe")
        ]

    # ---------- Try it: one sample per pasted input (try-it) ----------

    def try_history(model: str, aid: str, treatment: str, repo: str | None) -> dict:
        """Earlier runs' costs to price a try: the repo's runs, or every bench's runs of this
        workflow (else any workflow's "with" trials, as trial-budget's evidence)."""
        from proving_ground.budget import earlier, evidence

        if repo:
            r = ws.get(repo)
            if r is None:
                raise HTTPException(404, f"No repo with id {repo!r}.")
            p = open_project(r)
            return earlier(p.store, p.root, p.pid, model, aid, treatment)
        same: list[float] = []
        other: list[float] = []
        for d in sorted(benches_dir.iterdir()) if benches_dir.is_dir() else []:
            if not (d / PG_DIR).is_dir():
                continue
            try:
                p = bench_project(d.name)
            except HTTPException:
                continue
            for e in p.store.list_experiments(p.pid):
                if e.model != model or run_meta(p.root, e.id).get("agent", "claude-code") != aid:
                    continue
                got = evidence(p.store.trials(e.id))["with"]
                (same if e.treatment_name == treatment else other).extend(got)
        return {"with": same or other, "without": []}

    rig_api.mount(app)
    tutorial_api.mount(app)

    try_mod.mount(
        app,
        creds=creds,
        home=home,
        library=library,
        busy=runs.busy,
        resolve_skills=resolve_skills,
        current=current,
        earlier_with=try_history,
        judge_client=reachable_model,
        local=local,
    )

    dist = web_dist or WEB_DIST
    if (dist / "index.html").is_file():
        app.mount("/", WebFiles(directory=dist, html=True), name="web")
    else:

        @app.get("/", response_class=HTMLResponse)
        def not_built():
            return NOT_BUILT

    return app
