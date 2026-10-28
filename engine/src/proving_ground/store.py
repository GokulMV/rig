"""SQLite (local) runtime records: projects, sources, experiments, trials."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import (
    JSON,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from proving_ground.files import PG_DIR
from proving_ground.models import ScenarioKind, Treatment
from proving_ground.trial import TrialOutcome

# One-time data migrations, by name, recorded in the `migrations` table once run.
OLD_TIMEOUTS = "errored-agent-timeouts-are-fails"

STATUSES = {"pending", "running", "done", "stopped_budget", "stopped", "failed_preflight"}


class DuplicateTrialError(Exception):
    pass


class Base(DeclarativeBase):
    pass


class ProjectT(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    root: Mapped[str] = mapped_column(String, unique=True)


class SourceT(Base):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("project_id", "kind", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    kind: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class ExperimentT(Base):
    __tablename__ = "experiments"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    treatment_name: Mapped[str] = mapped_column(String)
    treatment_kind: Mapped[str] = mapped_column(String)
    treatment_hash: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String)
    repeats: Mapped[int] = mapped_column(Integer)
    budget_usd: Mapped[float] = mapped_column(Float)
    seed: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[str] = mapped_column(String)


class TrialT(Base):
    __tablename__ = "trials"
    __table_args__ = (UniqueConstraint("experiment_id", "scenario_id", "arm", "repeat"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"))
    scenario_id: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    arm: Mapped[str] = mapped_column(String)
    repeat: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    duration_s: Mapped[float] = mapped_column(Float, default=0.0)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transcript_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    reused_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    items_right: Mapped[int | None] = mapped_column(Integer, nullable=True)
    items_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # "timed out after 600 s", an error, or None (TrialOutcome.detail).
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


@dataclass(frozen=True)
class SourceRow:
    id: int
    kind: str
    name: str
    text: str
    meta: dict


@dataclass(frozen=True)
class ExperimentRow:
    id: int
    project_id: int
    treatment_name: str
    treatment_kind: str
    treatment_hash: str
    model: str
    repeats: int
    budget_usd: float
    seed: int
    status: str
    created_at: str


def _experiment_row(r: ExperimentT) -> ExperimentRow:
    return ExperimentRow(
        r.id,
        r.project_id,
        r.treatment_name,
        r.treatment_kind,
        r.treatment_hash,
        r.model,
        r.repeats,
        r.budget_usd,
        r.seed,
        r.status,
        r.created_at,
    )


class Store:
    def __init__(self, url: str):
        self._engine = create_engine(url)
        Base.metadata.create_all(self._engine)
        self._migrate()
        self._session = sessionmaker(self._engine, expire_on_commit=False)
        self._mark_old_timeouts()

    def _migrate(self) -> None:
        """Columns added after a database was created (SQLite: add them in place)."""
        from sqlalchemy import inspect, text
        from sqlalchemy.exc import OperationalError

        have = {c["name"] for c in inspect(self._engine).get_columns("trials")}
        for col, typ in (
            ("reused_from", "INTEGER"),
            ("items_right", "INTEGER"),
            ("items_total", "INTEGER"),
            ("detail", "TEXT"),
        ):
            if col in have:
                continue
            try:
                with self._engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE trials ADD COLUMN {col} {typ}"))
            except OperationalError as e:
                # Two requests opened the same database at once and the other one added it.
                if "duplicate column" not in str(e):
                    raise

    def set_repeats(self, eid: int, repeats: int) -> None:
        with self._session.begin() as s:
            s.get(ExperimentT, eid).repeats = repeats

    @classmethod
    def for_project(cls, root: Path) -> Store:
        d = root / PG_DIR
        d.mkdir(parents=True, exist_ok=True)
        return cls(f"sqlite:///{d / 'pg.db'}")

    def ensure_project(self, root: str) -> int:
        with self._session.begin() as s:
            row = s.scalar(select(ProjectT).where(ProjectT.root == root))
            if row is None:
                row = ProjectT(root=root)
                s.add(row)
                s.flush()
            return row.id

    def add_source(
        self, project_id: int, kind: str, name: str, text: str, meta: dict | None = None
    ) -> int:
        with self._session.begin() as s:
            row = s.scalar(
                select(SourceT).where(
                    SourceT.project_id == project_id, SourceT.kind == kind, SourceT.name == name
                )
            )
            if row is None:
                row = SourceT(
                    project_id=project_id, kind=kind, name=name, text=text, meta=meta or {}
                )
                s.add(row)
            else:
                row.text, row.meta = text, meta or {}
            s.flush()
            return row.id

    def list_sources(self, project_id: int) -> list[SourceRow]:
        with self._session() as s:
            rows = s.scalars(
                select(SourceT).where(SourceT.project_id == project_id).order_by(SourceT.id)
            )
            return [SourceRow(r.id, r.kind, r.name, r.text, dict(r.meta or {})) for r in rows]

    def create_experiment(
        self,
        project_id: int,
        treatment: Treatment,
        model: str,
        repeats: int,
        budget_usd: float,
        seed: int,
    ) -> int:
        with self._session.begin() as s:
            row = ExperimentT(
                project_id=project_id,
                treatment_name=treatment.name,
                treatment_kind=treatment.kind.value,
                treatment_hash=treatment.content_hash,
                model=model,
                repeats=repeats,
                budget_usd=budget_usd,
                seed=seed,
                status="pending",
                created_at=datetime.now(UTC).isoformat(timespec="seconds"),
            )
            s.add(row)
            s.flush()
            return row.id

    def get_experiment(self, eid: int) -> ExperimentRow:
        with self._session() as s:
            r = s.get(ExperimentT, eid)
            if r is None:
                raise KeyError(f"experiment {eid} not found")
            return _experiment_row(r)

    def list_experiments(self, project_id: int) -> list[ExperimentRow]:
        with self._session() as s:
            rows = s.scalars(
                select(ExperimentT)
                .where(ExperimentT.project_id == project_id)
                .order_by(ExperimentT.id.desc())
            )
            return [_experiment_row(r) for r in rows]

    def delete_experiment(self, eid: int) -> None:
        """Forget an experiment and its trials. Trials other experiments reused from it keep
        their own copies."""
        from sqlalchemy import delete

        with self._session.begin() as s:
            s.execute(delete(TrialT).where(TrialT.experiment_id == eid))
            s.execute(delete(ExperimentT).where(ExperimentT.id == eid))

    def set_status(self, eid: int, status: str) -> None:
        if status not in STATUSES:
            raise ValueError(f"unknown status {status!r}")
        with self._session.begin() as s:
            s.get(ExperimentT, eid).status = status

    def record_trial(self, eid: int, t: TrialOutcome) -> None:
        try:
            with self._session.begin() as s:
                s.add(
                    TrialT(
                        experiment_id=eid,
                        scenario_id=t.scenario_id,
                        kind=t.kind.value,
                        arm=t.arm,
                        repeat=t.repeat,
                        outcome=t.outcome,
                        tokens_in=t.tokens_in,
                        tokens_out=t.tokens_out,
                        cost_usd=t.cost_usd,
                        duration_s=t.duration_s,
                        exit_code=t.exit_code,
                        transcript_uri=t.transcript_uri,
                        reused_from=t.reused_from,
                        items_right=t.items_right,
                        items_total=t.items_total,
                        detail=t.detail,
                    )
                )
        except IntegrityError as e:
            raise DuplicateTrialError(f"{t.scenario_id}/{t.arm}/{t.repeat} already recorded") from e

    def trials(self, eid: int) -> list[TrialOutcome]:
        with self._session() as s:
            rows = s.scalars(select(TrialT).where(TrialT.experiment_id == eid).order_by(TrialT.id))
            return [
                TrialOutcome(
                    r.scenario_id,
                    ScenarioKind(r.kind),
                    r.arm,
                    r.repeat,
                    r.outcome,
                    r.tokens_in,
                    r.tokens_out,
                    r.cost_usd,
                    r.duration_s,
                    r.exit_code,
                    r.transcript_uri,
                    r.reused_from,
                    r.items_right,
                    r.items_total,
                    r.detail,
                )
                for r in rows
            ]

    def _mark_old_timeouts(self) -> None:
        """Once per database (recorded in `migrations`): trials recorded before agent timeouts
        counted as fails were stored as errored with no detail. Each one's Harbor result.json
        is read: an AgentTimeoutError becomes the fail it is now ("timed out after N s");
        anything else keeps its outcome and gets its error as detail. Reads never write."""
        from sqlalchemy import text

        from proving_ground.runner.harbor import old_trial_detail

        with self._engine.begin() as conn:
            conn.execute(text("CREATE TABLE IF NOT EXISTS migrations (name TEXT PRIMARY KEY)"))
            done = conn.execute(
                text("SELECT 1 FROM migrations WHERE name = :n"), {"n": OLD_TIMEOUTS}
            ).first()
        if done:
            return
        with self._session.begin() as s:
            rows = s.scalars(
                select(TrialT).where(
                    TrialT.outcome == "errored",
                    TrialT.detail.is_(None),
                    TrialT.transcript_uri.is_not(None),
                )
            )
            for r in rows:
                outcome, detail = old_trial_detail(Path(r.transcript_uri))
                r.detail = detail
                if outcome is not None:
                    r.outcome = outcome
            s.execute(
                text("INSERT OR IGNORE INTO migrations (name) VALUES (:n)"), {"n": OLD_TIMEOUTS}
            )

    def done_keys(self, eid: int) -> set[tuple[str, str, int]]:
        return {(t.scenario_id, t.arm, t.repeat) for t in self.trials(eid)}

    def spent(self, eid: int) -> float:
        return sum(t.cost_usd for t in self.trials(eid))
