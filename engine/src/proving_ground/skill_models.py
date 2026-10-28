"""The two open-source models the skill matcher runs inside the engine, on the CPU: an embedding
model that finds candidate skills by meaning, and a reranker that reads a step and a skill
together and says whether the skill fits.

The weights come once from public Hugging Face repos, at pinned commits, checked against pinned
sizes and SHA-256s, with no account and no token, into the app home (~/.proving-ground/models).
After that nothing leaves the machine. Until they are there, or if getting them fails, the
matcher uses its word rules and the Lab says so. Every value is in the match-skills skill.
"""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path

from proving_ground import skills

V = skills.load("match-skills").values["models"]
HOME = Path.home() / ".proving-ground" / V["dir"]
OFF = "PG_SKILL_MODELS"  # set to "off" to keep to the word rules (no download)


def model_dir(spec: dict, home: Path) -> Path:
    return home / f"{spec['repo'].replace('/', '--')}@{spec['revision'][:12]}"


def total_bytes() -> int:
    return sum(f["bytes"] for k in ("embed", "rerank") for f in V[k]["files"].values())


def present(home: Path) -> bool:
    """Every pinned file there at its pinned size (the hash is checked when it downloads)."""
    for k in ("embed", "rerank"):
        d = model_dir(V[k], home)
        for path, f in V[k]["files"].items():
            p = d / path
            if not p.is_file() or p.stat().st_size != f["bytes"]:
                return False
    return True


def fetch(home: Path, progress: Callable[[int], None] = lambda n: None, http=None) -> None:
    """Download the pinned files that aren't there yet, over plain HTTPS, with no credentials.
    Refuses before starting if they add up to more than download_max_mb; stops at
    download_timeout_s; a file whose size or SHA-256 differs from the pin is thrown away."""
    import httpx

    if total_bytes() > V["download_max_mb"] * 1e6:
        raise RuntimeError(f"the models are over the {V['download_max_mb']} MB limit")
    deadline = time.monotonic() + V["download_timeout_s"]
    done = 0
    client = http or httpx.Client(
        timeout=httpx.Timeout(V["read_timeout_s"], connect=V["connect_timeout_s"]),
        follow_redirects=True,
        headers={"user-agent": "rig-skill-matcher"},
    )
    try:
        for k in ("embed", "rerank"):
            spec = V[k]
            d = model_dir(spec, home)
            for path, f in spec["files"].items():
                dest = d / path
                if dest.is_file() and dest.stat().st_size == f["bytes"]:
                    done += f["bytes"]
                    progress(done)
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                # One per download, so a download turned off and on again never shares a half file.
                part = dest.with_name(f"{dest.name}.{threading.get_ident()}.part")
                url = f"{V['host']}/{spec['repo']}/resolve/{spec['revision']}/{path}"
                h, n = hashlib.sha256(), 0
                try:
                    with client.stream("GET", url) as r, open(part, "wb") as out:
                        r.raise_for_status()
                        for chunk in r.iter_bytes(1 << 20):
                            n += len(chunk)
                            if n > f["bytes"]:
                                break
                            if time.monotonic() > deadline:
                                raise TimeoutError(f"took over {V['download_timeout_s']} s")
                            h.update(chunk)
                            out.write(chunk)
                            progress(done + n)
                    if n != f["bytes"] or h.hexdigest() != f["sha256"]:
                        raise RuntimeError(f"{spec['name']} {path} didn't match its pinned hash")
                except BaseException:
                    part.unlink(missing_ok=True)  # no half file left behind
                    raise
                os.replace(part, dest)
                done += n
    finally:
        if http is None:
            client.close()


def _session(path: Path):
    import onnxruntime as ort

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = V["threads"]
    opts.inter_op_num_threads = 1
    opts.log_severity_level = 3
    return ort.InferenceSession(str(path), sess_options=opts, providers=["CPUExecutionProvider"])


class Embedder:
    """BGE: unit vectors from the [CLS] token, queries with the model's search prefix."""

    def __init__(self, home: Path, spec: dict | None = None):
        from tokenizers import Tokenizer

        self.spec = spec = spec or V["embed"]
        d = model_dir(spec, home)
        self.tok = Tokenizer.from_file(str(d / "tokenizer.json"))
        self.tok.enable_truncation(max_length=spec["max_tokens"])
        pad = next(p for p in ("[PAD]", "<pad>") if self.tok.token_to_id(p) is not None)
        self.tok.enable_padding(pad_id=self.tok.token_to_id(pad), pad_token=pad)
        self.sess = _session(d / spec["model"])
        self.inputs = {i.name for i in self.sess.get_inputs()}

    def embed(self, texts: list[str], query: bool = False) -> list[list[float]]:
        import numpy as np

        out: list[list[float]] = []
        for i in range(0, len(texts), V["batch"]):
            chunk = [
                (self.spec["query_prefix"] + t) if query else t for t in texts[i : i + V["batch"]]
            ]
            encs = self.tok.encode_batch(chunk)
            feed = {
                "input_ids": np.array([e.ids for e in encs], dtype=np.int64),
                "attention_mask": np.array([e.attention_mask for e in encs], dtype=np.int64),
            }
            if "token_type_ids" in self.inputs:
                feed["token_type_ids"] = np.array([e.type_ids for e in encs], dtype=np.int64)
            h = self.sess.run(None, feed)[0][:, 0]
            out += (h / np.linalg.norm(h, axis=1, keepdims=True)).tolist()
        return out


class Reranker:
    """Qwen3-Reranker: the chance it answers "yes" (over "no") to whether the skill fits the
    step. The prompt up to the step is read once per step (kept as the model's cache); each
    skill then costs only its own words."""

    def __init__(self, home: Path, spec: dict | None = None):
        from tokenizers import Tokenizer

        self.spec = spec = spec or V["rerank"]
        d = model_dir(spec, home)
        self.tok = Tokenizer.from_file(str(d / "tokenizer.json"))
        self.sess = _session(d / spec["model"])
        self.past = [i for i in self.sess.get_inputs() if i.name.startswith("past_key_values")]
        self.outs = ["logits"] + [p.name.replace("past_key_values", "present") for p in self.past]
        self.yes, self.no = self.tok.token_to_id("yes"), self.tok.token_to_id("no")

    def _ids(self, text: str) -> list[int]:
        return self.tok.encode(text, add_special_tokens=False).ids

    def _run(self, ids: list[int], cache: list | None, start: int):
        import numpy as np

        n = len(ids)
        feed = {
            "input_ids": np.array([ids], dtype=np.int64),
            "attention_mask": np.ones((1, start + n), dtype=np.int64),
            "position_ids": np.arange(start, start + n, dtype=np.int64)[None],
        }
        for k, p in enumerate(self.past):
            dt = np.float16 if "float16" in p.type else np.float32
            feed[p.name] = cache[k] if cache else np.zeros((1, p.shape[1], 0, p.shape[3]), dt)
        got = self.sess.run(self.outs, feed)
        return got[0][0, -1], got[1:]

    def score(self, query: str, docs: list[str]) -> list[float]:
        import numpy as np

        s = self.spec
        head = self._ids(f"{s['prefix']}<Instruct>: {s['instruction']}\n<Query>: {query}\n")
        cut = s["max_tokens"] - len(head) - 16
        _, cache = self._run(head, None, 0)
        out = []
        for d in docs:
            ids = self._ids(f"<Document>: {d}")[: max(cut, 8)] + self._ids(s["suffix"])
            last, _ = self._run(ids, cache, len(head))
            y, n = float(last[self.yes]), float(last[self.no])
            out.append(float(1 / (1 + np.exp(n - y))))
        return out


class Models:
    """The loaded pair, with what they've already worked out kept: each text's embedding and
    each (step, skill) score, in memory and in a file next to the weights, keyed by the model
    revision and the text itself, so a changed skill or model is worked out again."""

    def __init__(self, embedder, reranker, cache_file: Path | None = None):
        self.embedder, self.reranker, self.cache_file = embedder, reranker, cache_file
        self.lock = threading.Lock()
        self.emb: dict[str, list[float]] = {}
        self.pair: dict[str, float] = {}
        self.dirty = False
        self.saved_at = time.monotonic()
        self.tag = V["embed"]["revision"][:12] + "/" + V["rerank"]["revision"][:12]
        if cache_file and cache_file.is_file():
            try:
                got = json.loads(cache_file.read_text())
                if got.get("tag") == self.tag:
                    self.emb, self.pair = got["emb"], got["pair"]
            except (OSError, ValueError, KeyError):
                pass

    @staticmethod
    def _key(*parts: str) -> str:
        return hashlib.sha256("\x00".join(parts).encode()).hexdigest()[:32]

    def embed(self, texts: list[str], query: bool = False) -> list[list[float]]:
        keys = [self._key("q" if query else "d", t) for t in texts]
        with self.lock:
            todo = [(k, t) for k, t in zip(keys, texts, strict=True) if k not in self.emb]
        if todo:
            uniq = dict(todo)
            vecs = self.embedder.embed(list(uniq.values()), query=query)
            with self.lock:
                self.emb.update(zip(uniq, vecs, strict=True))
                self.dirty = True
        with self.lock:
            return [self.emb[k] for k in keys]

    def score(self, query: str, docs: list[str]) -> list[float]:
        keys = [self._key(query, d) for d in docs]
        with self.lock:
            todo = list(
                dict.fromkeys(d for k, d in zip(keys, docs, strict=True) if k not in self.pair)
            )
        if todo:
            got = self.reranker.score(query, todo)
            with self.lock:
                self.pair.update({self._key(query, d): s for d, s in zip(todo, got, strict=True)})
                self.dirty = True
        with self.lock:
            return [self.pair[k] for k in keys]

    def save_soon(self) -> None:
        """Save if there's something new and the last save was a while ago (save_every_s)."""
        if self.dirty and time.monotonic() - self.saved_at > V["save_every_s"]:
            self.save()

    def save(self) -> None:
        self.saved_at = time.monotonic()
        if not self.cache_file:
            return
        with self.lock:
            if not self.dirty:
                return
            text = json.dumps({"tag": self.tag, "emb": self.emb, "pair": self.pair})
            self.dirty = False
        tmp = self.cache_file.with_suffix(".tmp")
        tmp.write_text(text)
        os.replace(tmp, self.cache_file)


def _load(home: Path) -> Models:
    return Models(Embedder(home), Reranker(home), home / "cache.json")


def library_key(library: list[dict]) -> str:
    return Models._key(*(f"{s['name']}\x01{s.get('description', '')}" for s in library))


class _TurnedOff(Exception):
    """Raised inside a download that was turned off meanwhile."""


class Matcher:
    """The models for this process. Nothing is downloaded until the user asks (`turn(True)`,
    remembered in choice.json next to the weights, so it survives a restart); then they are
    fetched in the background, loaded once, and used for a library only once `warm` has
    matched the Lab's own steps against it (again in the background), so a page never waits on
    the models and never mixes the two ways of matching. Until then, when turned off, and if
    anything fails, the word rules match. PG_SKILL_MODELS=off keeps them off whatever was
    chosen."""

    def __init__(
        self,
        home: Path | None = None,
        download: Callable[..., None] | None = None,
        load: Callable[[Path], Models] | None = None,
        warm: Callable[[Models, list[dict]], None] | None = None,
    ):
        self.home = home or HOME
        self.download, self.load, self.warm = download or fetch, load or _load, warm
        self.lock = threading.Lock()
        self.forced_off = os.environ.get(OFF, "").lower() == "off"
        self.on = self._read_choice()
        self.state = "disabled" if self.forced_off else ("idle" if self.on else "off")
        self.error: str | None = None
        self.got = 0
        self.failed_at = 0.0
        self.models: Models | None = None
        self.warmed: set[str] = set()
        self.warming: str | None = None
        self.gen = 0  # bumped when turned off: work begun before then is thrown away

    @property
    def choice_file(self) -> Path:
        return self.home / "choice.json"

    def _read_choice(self) -> bool:
        try:
            return json.loads(self.choice_file.read_text()).get("on") is True
        except (OSError, ValueError, AttributeError):
            return False

    def turn(self, on: bool) -> dict:
        """The user's choice: get and use the models (on), or keep to the word rules (off,
        and the loaded models are let go). Remembered; refused under PG_SKILL_MODELS=off."""
        if self.forced_off:
            raise PermissionError(f"the skill matcher is turned off ({OFF}=off)")
        self.home.mkdir(parents=True, exist_ok=True)
        tmp = self.choice_file.with_suffix(".tmp")
        tmp.write_text(json.dumps({"on": on, "at": time.time()}))
        os.replace(tmp, self.choice_file)
        with self.lock:
            self.on = on
            if not on:
                self.gen += 1
                self.state, self.models, self.warming, self.error = "off", None, None, None
                self.warmed = set()
            elif self.state in ("off", "failed"):
                self.state = "idle"
        if on:
            self.start()
        return self.status()

    def start(self) -> None:
        """Begin getting the models if the user asked for them, once (again after
        retry_after_s if it failed)."""
        with self.lock:
            if self.state == "failed" and time.monotonic() - self.failed_at > V["retry_after_s"]:
                self.state = "idle"
            if self.state != "idle" or not self.on:
                return
            self.state = "loading" if present(self.home) else "downloading"
            gen = self.gen
        threading.Thread(target=self._get, args=(gen,), name="skill-matcher", daemon=True).start()

    def _fail(self, e: Exception, gen: int) -> None:
        with self.lock:
            if gen != self.gen:
                return  # turned off meanwhile: that is not a failure
            self.state, self.error = "failed", str(e) or type(e).__name__
            self.failed_at, self.models, self.warming = time.monotonic(), None, None

    def _get(self, gen: int) -> None:
        def progress(n: int) -> None:
            if gen != self.gen:
                raise _TurnedOff
            self.got = n

        try:
            if self.state == "downloading":
                self.download(self.home, progress=progress)
                with self.lock:
                    if gen != self.gen:
                        return
                    self.state = "loading"
            models = self.load(self.home)
            with self.lock:
                if gen == self.gen:
                    self.models, self.state = models, "ready"
        except Exception as e:  # offline, a bad file, onnxruntime missing: keep to the word rules
            self._fail(e, gen)

    def _warm(self, models: Models, library: list[dict], key: str, gen: int) -> None:
        try:
            if self.warm:
                self.warm(models, library)
            models.save()
            with self.lock:
                if gen == self.gen:
                    self.warmed.add(key)
        except Exception as e:
            self._fail(e, gen)
        finally:
            with self.lock:
                if self.warming == key and gen == self.gen:
                    self.warming = None

    def ready(self, library: list[dict] | None = None) -> Models | None:
        """The models, if they're loaded and warm for this library; else None, and the warming
        for it begins (one library at a time)."""
        with self.lock:
            if self.state != "ready" or self.models is None:
                return None
            if library is None:
                return self.models
            key = library_key(library)
            if key in self.warmed:
                return self.models
            if self.warming is not None:
                return None
            self.warming, models, gen = key, self.models, self.gen
        threading.Thread(
            target=self._warm,
            args=(models, library, key, gen),
            name="skill-matcher-warm",
            daemon=True,
        ).start()
        return None

    def status(self, library: list[dict] | None = None) -> dict:
        """What the Lab shows: one line, the state (`warming` while the models match this
        library's steps for the first time), and what the user may do: `offer` (the button
        that asks for the download) or `can_turn_off`."""
        mb = round(total_bytes() / 1e6)
        name = V["rerank"]["name"]
        state = self.state
        if state == "ready" and library is not None and library_key(library) not in self.warmed:
            state = "warming"
        notes = {
            "disabled": f"Skills are matched by word rules (the skill matcher is turned off by {OFF}).",
            "off": "Skills are matched by word rules.",
            "idle": "Skills are matched by word rules.",
            "downloading": f"Getting the skill matcher (≈{mb:,} MB, {round(self.got / 1e6):,} so far)… word rules until then.",
            "loading": "Getting the skill matcher ready… word rules until then.",
            "warming": f"Matching skills with {name}… word rules until then.",
            "ready": f"Skills matched by {name}, on this machine.",
            "failed": f"Couldn't get the skill matcher ({self.error}); skills matched by word rules.",
        }
        offer = (
            f"Get the better skill matcher (≈{mb:,} MB download, runs on this machine, "
            f"~{V['memory_gb']} GB memory)"
            if state == "off"
            else None
        )
        return {
            "state": state,
            "note": notes[state],
            "mb": mb,
            "memory_gb": V["memory_gb"],
            "model": name,
            "offer": offer,
            "can_turn_off": self.on and not self.forced_off,
        }


_active: Matcher | None = None
_pin: contextvars.ContextVar[tuple | None] = contextvars.ContextVar(
    "skill_models_pin", default=None
)


def use(m: Matcher | None) -> None:
    """The process's matcher (the app sets it); None keeps to the word rules."""
    global _active
    _active = m


@contextlib.contextmanager
def pinned(models: Models | None):
    """Within it, every step is matched one way (these models, or the word rules for None),
    even if the models finish warming meanwhile: one page, one way of matching."""
    token = _pin.set((models,))
    try:
        yield
    finally:
        _pin.reset(token)


def active(library: list[dict] | None = None) -> Models | None:
    if (p := _pin.get()) is not None:
        return p[0]
    return _active.ready(library) if _active else None
