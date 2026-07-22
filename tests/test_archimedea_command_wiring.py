from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _tree(path: str) -> ast.Module:
    return ast.parse((ROOT / path).read_text(encoding="utf-8-sig"))


def _function(path: str, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    return next(
        node
        for node in ast.walk(_tree(path))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    )


def test_archimedea_command_fetches_query_only_worldstate() -> None:
    command = _function("services/worldstate_commands.py", "cmd_archimedeas")
    source = ast.unparse(command)

    assert "worldstate_client.fetch_archimedeas" in source
    assert "深层科研" in source
    assert "时光科研" in source
    assert "event.plain_result" in source


def test_plugin_registers_research_query_command() -> None:
    method = _function("main.py", "wf_archimedeas")
    source = ast.unparse(method)

    assert "worldstate_commands.cmd_archimedeas" in source
    assert "_yield_result_and_cleanup_image" in source


def test_no_prefix_router_contains_research_command() -> None:
    router_map = _function("main.py", "_no_prefix_handler_map")
    source = ast.unparse(router_map)

    assert "'科研': self.wf_archimedeas" in source


def test_no_prefix_research_aliases_inject_the_selected_mode() -> None:
    router = _function("main.py", "no_prefix_command_router")
    source = ast.unparse(router)

    assert "command == '深层科研'" in source
    assert "command == '时光科研'" in source
    assert "raw_args = f'深层 {raw_args}'.strip()" in source
    assert "raw_args = f'时光 {raw_args}'.strip()" in source
