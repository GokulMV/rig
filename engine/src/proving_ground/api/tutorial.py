"""GET /api/tutorial (tutorial skill) and GET /api/tutorial/tokens (tutorial-tokens skill): the
tutorial's two tracks. Read-only, and each reads only the example shipped with the engine: never
the workspace, a repo, a run or a store."""

from __future__ import annotations

from fastapi import FastAPI

from proving_ground import tutorial
from proving_ground.tutorial import fewer_tokens


def mount(app: FastAPI) -> None:
    @app.get("/api/tutorial")
    def tutorial_view():
        """The tutorial's words, the example (repo, skill, tasks) and its recorded run."""
        return tutorial.view()

    @app.get("/api/tutorial/tokens")
    def tutorial_tokens_view():
        """The second track: Rig your own repo for fewer tokens, on the textkit example."""
        return fewer_tokens.view()
