from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _tree() -> ast.Module:
    return ast.parse((ROOT / "main.py").read_text(encoding="utf-8-sig"))


def _method(name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    plugin = next(
        node
        for node in _tree().body
        if isinstance(node, ast.ClassDef) and node.name == "WarframeHelperPlugin"
    )
    return next(
        node
        for node in plugin.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    )


def test_plugin_lifecycle_starts_and_stops_auto_push() -> None:
    constructor = ast.unparse(_method("__init__"))
    initialize = ast.unparse(_method("initialize"))
    terminate = ast.unparse(_method("terminate"))

    assert "AutoPushService" in constructor
    assert "self._auto_push.start()" in initialize
    assert "await self._auto_push.stop()" in terminate


def test_plugin_exposes_group_push_commands() -> None:
    assert "self._auto_push.enable" in ast.unparse(_method("wf_auto_push_enable"))
    assert "self._auto_push.disable" in ast.unparse(_method("wf_auto_push_disable"))
    assert "self._auto_push.status" in ast.unparse(_method("wf_auto_push_status"))
