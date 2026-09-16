"""Workstream recipes — thin wrappers around ask/edit + existing farm surfaces."""

from __future__ import annotations

RECIPES = [
    {
        "id": "review",
        "label": "Review",
        "kind": "ask",
        "prompt": "Review the selected file(s) for bugs, regressions, and farm routing mistakes. Be concise. List findings first.",
    },
    {
        "id": "explain",
        "label": "Explain",
        "kind": "ask",
        "prompt": "Explain what the selected file(s) do, who calls them, and the safest way to change them.",
    },
    {
        "id": "fix",
        "label": "Propose fix",
        "kind": "edit",
        "prompt": "Fix the described issue in the selected file(s). Return a unified diff only.",
    },
    {
        "id": "tests",
        "label": "Add tests",
        "kind": "edit",
        "prompt": "Add focused unit tests for the selected file(s). Unified diff only.",
    },
    {
        "id": "aipm",
        "label": "Open AI-PM",
        "kind": "launch",
        "target": "aipm",
        "prompt": "",
    },
    {
        "id": "farm-coder",
        "label": "Farm /coder",
        "kind": "launch",
        "target": "coder",
        "prompt": "",
    },
]


def get_recipe(recipe_id: str) -> dict:
    for row in RECIPES:
        if row["id"] == recipe_id:
            return row
    raise KeyError(recipe_id)
