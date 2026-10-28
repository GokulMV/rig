"""Whether Measure can test a suggestion: one state from the measurability skill.

The web app reads the same skill (/api/rules/measurability) for the cards on the canvas; this is
the suggestions' half, since only the engine knows which ones only fix the diagram.
"""

from __future__ import annotations

from proving_ground import buildspec, skills

V = skills.load("measurability").values


def of_proposal(p: dict) -> str:
    """A suggestion's state: a diagram note, the kind of thing it adds to the agent, a change to
    the app's code (measured before and after), or a task for the brief."""
    if buildspec.diagram_only(p):
        return "note"
    adds = p.get("adds") or ""
    if adds in V["treatments"]:
        return V["treatments"][adds]
    if adds in V["adds"]:
        return V["adds"][adds]
    d = p.get("delta") or {}
    if p.get("kind") in V["code_kinds"] or d.get("add") or d.get("remove"):
        return "before_after"
    return "brief"
