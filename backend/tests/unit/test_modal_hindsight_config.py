"""Regression guard for the stateful Modal Hindsight deployment.

.. deprecated::
    Modal deployment was superseded on 2026-07-21 by local Docker + Cloudflare
    Tunnel. This test validates the historical Modal config (max_containers=1)
    and is retained as a regression guard for the archived script.
"""

from __future__ import annotations

import ast
from pathlib import Path


def test_pg0_modal_deployment_is_single_container() -> None:
    """Embedded PostgreSQL must never share its data directory across containers."""
    script_path = Path(__file__).parents[2] / "scripts" / "modal_hindsight.py"
    module = ast.parse(script_path.read_text(encoding="utf-8"))

    function = next(
        node
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "run_hindsight"
    )
    app_function = next(
        decorator
        for decorator in function.decorator_list
        if isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr == "function"
    )
    keywords = {keyword.arg: keyword.value for keyword in app_function.keywords}

    assert ast.literal_eval(keywords["max_containers"]) == 1
