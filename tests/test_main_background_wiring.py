from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _main_tree() -> ast.Module:
    return ast.parse((ROOT / "main.py").read_text(encoding="utf-8-sig"))


def _plugin_method(name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = _main_tree()
    plugin = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "WarframeHelperPlugin"
    )
    return next(
        node
        for node in plugin.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )


def test_plugin_constructor_builds_runtime_and_installs_resolver():
    constructor = _plugin_method("__init__")
    source = ast.unparse(constructor)

    assert "BackgroundThemeRuntime.from_config" in source
    assert "self._background_runtime" in source
    assert "set_render_theme_resolver(self._background_runtime.resolve)" in source


def test_plugin_initializes_background_before_starting_subscriptions():
    initialize = _plugin_method("initialize")
    source = ast.unparse(initialize)

    background_index = source.index("await self._background_runtime.initialize()")
    subscriptions_index = source.index("self._subscriptions.start()")
    assert background_index < subscriptions_index
