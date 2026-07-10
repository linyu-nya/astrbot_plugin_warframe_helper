from __future__ import annotations

import ast
import importlib.util
import sys
import types
from dataclasses import dataclass
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "astrbot_plugin_warframe_helper"
SERVICES_PACKAGE = f"{PACKAGE}.services"


def _tree(path: str) -> ast.Module:
    return ast.parse((ROOT / path).read_text(encoding="utf-8-sig"))


def _function(path: str, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    return next(
        node
        for node in ast.walk(_tree(path))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    )


def _plugin_method(name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = _tree("main.py")
    plugin = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "WarframeHelperPlugin"
    )
    return next(
        node
        for node in plugin.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    )


def _named_calls(
    node: ast.AST, function_name: str
) -> list[ast.Call]:
    return [
        child
        for child in ast.walk(node)
        if isinstance(child, ast.Call)
        and (
            (
                isinstance(child.func, ast.Attribute)
                and child.func.attr == function_name
            )
            or (
                isinstance(child.func, ast.Name)
                and child.func.id == function_name
            )
        )
    ]


def _keyword(call: ast.Call, name: str) -> ast.expr:
    return next(keyword.value for keyword in call.keywords if keyword.arg == name)


def test_plugin_constructor_parses_fissure_sort_config_once() -> None:
    constructor = _plugin_method("__init__")
    parser_calls = [
        node
        for node in ast.walk(constructor)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "fissure_tier_sort_enabled"
    ]

    assert len(parser_calls) == 1
    assignment = next(
        node
        for node in ast.walk(constructor)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
            and target.attr == "_fissure_tier_sort_enabled"
            for target in node.targets
        )
    )
    assert assignment.value is parser_calls[0]


@pytest.mark.parametrize(
    ("method_name", "command_name"),
    [
        ("wf_fissures", "cmd_fissures"),
        ("wf_fissures_normal", "cmd_fissures_kind"),
        ("wf_fissures_hard", "cmd_fissures_kind"),
        ("wf_fissures_storm", "cmd_fissures_kind"),
    ],
)
def test_fissure_entrypoint_passes_saved_sort_mode(
    method_name: str, command_name: str
) -> None:
    method = _plugin_method(method_name)
    calls = _named_calls(method, command_name)

    assert len(calls) == 1
    assert ast.dump(_keyword(calls[0], "tier_first")) == ast.dump(
        ast.Attribute(
            value=ast.Name(id="self", ctx=ast.Load()),
            attr="_fissure_tier_sort_enabled",
            ctx=ast.Load(),
        )
    )


@pytest.mark.parametrize("function_name", ["cmd_fissures", "cmd_fissures_kind"])
def test_worldstate_fissure_command_requires_and_forwards_sort_mode(
    function_name: str,
) -> None:
    function = _function("services/worldstate_commands.py", function_name)
    keyword_names = [argument.arg for argument in function.args.kwonlyargs]
    tier_index = keyword_names.index("tier_first")

    assert function.args.kw_defaults[tier_index] is None
    for renderer_name in ("render_fissures_image", "render_fissures_text"):
        calls = _named_calls(function, renderer_name)
        assert len(calls) == 1
        value = _keyword(calls[0], "tier_first")
        assert isinstance(value, ast.Name)
        assert value.id == "tier_first"


@dataclass(frozen=True)
class _FakeFissure:
    tier: str
    eta: str
    mission_type: str
    node: str
    enemy: str = ""
    is_storm: bool = False
    is_hard: bool = False


@dataclass(frozen=True)
class _FakeWorldstateRow:
    title: str
    subtitle: str | None = None
    right: str | None = None
    tag: str | None = None
    accent: tuple[int, int, int, int] | None = None


class _FakeWorldstateClient:
    def __init__(self, fissures: list[_FakeFissure]) -> None:
        self._fissures = fissures

    async def fetch_fissures(self, **_kwargs) -> list[_FakeFissure]:
        return list(self._fissures)


@pytest.fixture
def fissures_module(monkeypatch: pytest.MonkeyPatch):
    services_package = types.ModuleType(SERVICES_PACKAGE)
    services_package.__path__ = [str(ROOT / "services")]
    monkeypatch.setitem(sys.modules, SERVICES_PACKAGE, services_package)

    client_module = types.ModuleType(f"{PACKAGE}.clients.worldstate_client")
    client_module.Platform = str
    client_module.WarframeWorldstateClient = object
    monkeypatch.setitem(
        sys.modules, f"{PACKAGE}.clients.worldstate_client", client_module
    )

    renderer_module = types.ModuleType(f"{PACKAGE}.renderers.worldstate_render")
    renderer_module.WorldstateRow = _FakeWorldstateRow

    async def unused_renderer(**_kwargs):
        raise AssertionError("test must replace image renderer")

    renderer_module.render_worldstate_rows_image_to_file = unused_renderer
    monkeypatch.setitem(
        sys.modules, f"{PACKAGE}.renderers.worldstate_render", renderer_module
    )

    module_name = f"{SERVICES_PACKAGE}.fissures"
    spec = importlib.util.spec_from_file_location(
        module_name, ROOT / "services" / "fissures.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fake_fissures() -> list[_FakeFissure]:
    return [
        _FakeFissure("后纪", "5分", "捕获", "节点A"),
        _FakeFissure("古纪", "30分", "歼灭", "节点B"),
        _FakeFissure("中纪", "10分", "生存", "节点C"),
    ]


@pytest.mark.parametrize(
    ("tier_first", "expected_titles"),
    [
        (True, ["古纪 歼灭", "中纪 生存", "后纪 捕获"]),
        (False, ["后纪 捕获", "中纪 生存", "古纪 歼灭"]),
    ],
)
async def test_text_and_image_renderers_share_sorting_and_order(
    monkeypatch: pytest.MonkeyPatch,
    fissures_module,
    fake_fissures: list[_FakeFissure],
    tier_first: bool,
    expected_titles: list[str],
) -> None:
    sort_calls: list[bool] = []
    actual_sort = __import__(
        f"{SERVICES_PACKAGE}.fissure_sorting", fromlist=["sort_fissures"]
    ).sort_fissures

    def tracking_sort(fissures, *, tier_first: bool):
        sort_calls.append(tier_first)
        return actual_sort(fissures, tier_first=tier_first)

    captured_rows: list[_FakeWorldstateRow] = []

    async def capture_image_rows(*, rows, **_kwargs):
        captured_rows.extend(rows)
        return object()

    monkeypatch.setattr(fissures_module, "sort_fissures", tracking_sort, raising=False)
    monkeypatch.setattr(
        fissures_module,
        "render_worldstate_rows_image_to_file",
        capture_image_rows,
    )
    client = _FakeWorldstateClient(fake_fissures)

    text = await fissures_module.render_fissures_text(
        worldstate_client=client,
        platform_norm="pc",
        fissure_kind="普通",
        tier_first=tier_first,
    )
    assert sort_calls == [tier_first]

    await fissures_module.render_fissures_image(
        worldstate_client=client,
        platform_norm="pc",
        fissure_kind="普通",
        tier_first=tier_first,
    )

    text_titles = [
        line.removeprefix("- ").split(" - ", 1)[0]
        for line in text.splitlines()[1:]
    ]
    image_titles = [row.title for row in captured_rows]
    assert text_titles == expected_titles
    assert image_titles == expected_titles
    assert sort_calls == [tier_first, tier_first]
