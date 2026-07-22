from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _main_tree() -> ast.Module:
    return ast.parse((ROOT / "main.py").read_text(encoding="utf-8-sig"))


def _command_names() -> set[str]:
    names: set[str] = set()
    for node in ast.walk(_main_tree()):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "command":
            continue
        if node.args and isinstance(node.args[0], ast.Constant):
            if isinstance(node.args[0].value, str):
                names.add(node.args[0].value)
        for keyword in node.keywords:
            if keyword.arg == "alias":
                names.update(
                    value.value
                    for value in ast.walk(keyword.value)
                    if isinstance(value, ast.Constant) and isinstance(value.value, str)
                )
    return names


def _plugin_methods() -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in ast.walk(_main_tree())
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(isinstance(parent, ast.ClassDef) for parent in ast.walk(_main_tree()))
    }


def _source(node: ast.AST) -> str:
    return ast.unparse(node)


def _main_source() -> str:
    return (ROOT / "main.py").read_text(encoding="utf-8-sig")


def test_wiki_and_mapping_decorators_are_present():
    names = _command_names()
    assert "wk" in names
    assert "wfmapdel" in names


def test_main_imports_new_services_and_keeps_only_public_export_client():
    tree = _main_tree()
    imported = {
        alias.name
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "HuijiWikiClient" in imported
    assert "mapping_commands" in imported
    assert "wiki_commands" in imported
    assert "PublicExportClient" in imported
    assert "DropDataClient" not in imported
    assert "drop_data_commands" not in imported
    assert "public_export_commands" not in imported
    assert "HuijiWikiClient()" in _main_source()


def test_wmr_has_only_wr_alias_and_wiki_has_no_purple_alias():
    source = _main_source()
    wmr_start = source.index('@filter.command("wmr"')
    wmr_end = source.index("\n    async def", wmr_start)
    wmr = source[wmr_start:wmr_end]
    assert 'alias={"wr"}' in wmr
    assert "wk" not in wmr
    wk_start = source.index('@filter.command("wk"')
    wk_end = source.index("\n    async def", wk_start)
    assert "紫卡" not in source[wk_start:wk_end]


def test_mapping_decorators_and_no_prefix_keys_exist():
    names = _command_names()
    assert {"wfmap", "wfmapdel", "wfmapq"} <= names
    source = _main_source()
    for command in ("wfmap", "wfmapdel", "wfmapq"):
        assert f'"{command}": self.{command}' in source
    assert '"wk": self.wk' in source


def test_compatible_alias_add_is_delegated_and_old_resource_routes_are_absent():
    source = _main_source()
    assert "mapping_commands.compatible_alias_add" in source
    old_names = (
        "武器", "weapon", "wfweapon", "战甲", "warframe", "frame", "wfwarframe",
        "MOD", "mod", "模组", "mods", "掉落", "drop", "drops", "遗物", "relic", "relics",
    )
    assert not any(f'@filter.command("{name}"' in source for name in old_names)
    old_methods = ("wf_weapon", "wf_warframe", "wf_mod", "wf_drops", "wf_relic")
    assert not any(f"def {name}(" in source for name in old_methods)
    no_prefix_start = source.index("def _no_prefix_handler_map")
    no_prefix_end = source.index("\n    def _get_no_prefix_head_regex", no_prefix_start)
    no_prefix = source[no_prefix_start:no_prefix_end]
    assert not any(f'"{name}":' in no_prefix for name in old_names)
    assert "DropDataClient" not in source
    assert "drop_data_commands" not in source
    assert "public_export_commands" not in source


def test_help_mentions_new_wiki_and_mapping_commands():
    source = _main_source()
    help_start = source.index("async def _handle_wf_help")
    help_end = source.index("\n    @", help_start)
    help_source = source[help_start:help_end]
    for command in ("/wk", "/wfmap", "/wfmapdel", "/wfmapq", "/简称补充"):
        assert command in help_source
