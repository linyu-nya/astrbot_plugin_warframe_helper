"""Regression tests for `/wm` item resolution.

Three defects were reported from live group testing:

1. `cmd_wm` treated `tokens[0]` as the item name and silently discarded every
   later token it did not recognise as an option, so `/wm 川流不息 Prime`
   queried 川流不息 and answered with Flow.
2. Weapon aliases live in the riven-weapon nickname section, which
   `prefer_prime` ignored. Weapons therefore never generated a `Prime Set`
   candidate and fell through to a token scan that returned whichever part
   sorted first (`/wm 悦音` -> 悦音 Prime 枪管).
3. Chinese component words glued to the base name tokenised as one blob, so
   `/wm 悦音枪机` matched nothing while `/wm 悦音 枪机` resolved correctly.

The tests drive the real `cmd_wm` rather than the mapper directly: defect 1
lived in the command's argument parsing and is invisible from below it.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import time
import types
from pathlib import Path
from typing import Any

import pytest

# The package modules reach for these AstrBot helpers at import time; stub them
# the same way the other mapper tests do.
astrbot_core = sys.modules.setdefault("astrbot.core", types.ModuleType("astrbot.core"))
astrbot_core_utils = sys.modules.setdefault(
    "astrbot.core.utils", types.ModuleType("astrbot.core.utils")
)
astrbot_path = types.ModuleType("astrbot.core.utils.astrbot_path")
astrbot_path.get_astrbot_plugin_data_path = lambda: "unused"
astrbot_core.utils = astrbot_core_utils
astrbot_core_utils.astrbot_path = astrbot_path
sys.modules["astrbot.core.utils.astrbot_path"] = astrbot_path

from astrbot_plugin_warframe_helper.mappers.nickname_registry import (
    NICKNAME_SCHEMA_VERSION,
    SYM_BASE_NICKNAMES,
    SYM_RIVEN_STAT_NICKNAMES,
    SYM_RIVEN_WEAPON_NICKNAMES,
    USER_ALIASES,
    NicknameRegistry,
)
from astrbot_plugin_warframe_helper.mappers import term_mapping
from astrbot_plugin_warframe_helper.mappers.term_mapping import (
    WarframeTermMapper,
    _normalize_name_key,
    _rewrite_prime_marker,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "astrbot_plugin_warframe_helper"

# Mirrors the warframe.market v2 `/items` payload as the plugin requests it
# (`Language: zh-hans`). Euphona Prime is split into four separate entries with
# no `euphona_prime` parent, which is what made the fallback scan arbitrary.
WFM_ROWS: list[dict[str, Any]] = [
    {
        "id": "1",
        "slug": "euphona_prime_set",
        "tags": ["set", "prime", "weapon"],
        "i18n": {
            "en": {"name": "Euphona Prime Set"},
            "zh-hans": {"name": "悦音 Prime 一套"},
        },
    },
    {
        "id": "2",
        "slug": "euphona_prime_blueprint",
        "tags": ["blueprint", "prime", "weapon"],
        "i18n": {
            "en": {"name": "Euphona Prime Blueprint"},
            "zh-hans": {"name": "悦音 Prime 蓝图"},
        },
    },
    {
        "id": "3",
        "slug": "euphona_prime_barrel",
        "tags": ["component", "prime", "weapon"],
        "i18n": {
            "en": {"name": "Euphona Prime Barrel"},
            "zh-hans": {"name": "悦音 Prime 枪管"},
        },
    },
    {
        "id": "4",
        "slug": "euphona_prime_receiver",
        "tags": ["component", "prime", "weapon"],
        "i18n": {
            "en": {"name": "Euphona Prime Receiver"},
            "zh-hans": {"name": "悦音 Prime 枪机"},
        },
    },
    {
        "id": "5",
        "slug": "flow",
        "tags": ["mod", "warframe", "rare"],
        "i18n": {
            "en": {"name": "Flow"},
            "zh-hans": {"name": "川流不息"},
        },
    },
    {
        "id": "6",
        "slug": "primed_flow",
        "tags": ["mod", "legendary", "warframe"],
        "i18n": {
            "en": {"name": "Primed Flow"},
            "zh-hans": {"name": "川流不息 Prime"},
        },
    },
    {
        "id": "7",
        "slug": "volt_prime_set",
        "tags": ["set", "prime", "warframe"],
        "i18n": {
            "en": {"name": "Volt Prime Set"},
            "zh-hans": {"name": "Volt Prime 一套"},
        },
    },
]


class _CacheStub:
    def put(self, **_kwargs: object) -> None:
        pass

    def get(self, **_kwargs: object) -> None:
        return None


class _PagerStub:
    def enabled_for(self, _event: object) -> bool:
        return False


class _RecordingMarketClient:
    def __init__(self) -> None:
        self.requested_slugs: list[str] = []

    async def fetch_orders_by_item_slug(self, slug: str, *, platform: str):
        self.requested_slugs.append(slug)
        return []


class _Result:
    def __init__(self, text: str) -> None:
        self.text = text
        self.chain: list[object] = []


class _Event:
    def __init__(self, text: str) -> None:
        self._text = text
        self.session_id = "session"
        self.message_obj = types.SimpleNamespace(message_id="message")

    def should_call_llm(self, *_args: object, **_kwargs: object) -> None:
        pass

    def get_message_str(self) -> str:
        return self._text

    def plain_result(self, text: str) -> _Result:
        return _Result(str(text))

    def image_result(self, *_args: object, **_kwargs: object) -> _Result:
        return _Result("<image>")

    def chain_result(self, _chain: object) -> _Result:
        return _Result("<chain>")

    async def send(self, *_args: object, **_kwargs: object) -> None:
        pass


def _nickname_payload() -> dict[str, Any]:
    """Alias table shaped like the shipped one.

    `volt` sits in the base section (a warframe) while the weapon aliases sit in
    the riven-weapon section, reproducing the split that `prefer_prime` missed.
    """

    return {
        "version": NICKNAME_SCHEMA_VERSION,
        SYM_BASE_NICKNAMES: {"volt": "volt", "伏特": "volt"},
        SYM_RIVEN_WEAPON_NICKNAMES: {
            "悦音 Prime": "euphona prime",
            "悦音P": "euphona prime",
        },
        SYM_RIVEN_STAT_NICKNAMES: {},
        USER_ALIASES: {},
    }


def _items_cache_payload() -> dict[str, Any]:
    """A fresh on-disk item cache, so `initialize()` never reaches the network.

    Rows are sorted by slug, mirroring `_fetch_items_v2`. The order matters:
    without it a tie in the fallback scan would be broken by fixture order and
    the set would win by accident rather than by scoring.
    """

    rows = [
        {
            "id": row["id"],
            "slug": row["slug"],
            "name": row["i18n"]["en"]["name"],
            "wiki_link": None,
            "tags": list(row["tags"]),
            "i18n": {
                locale: {"name": block["name"]}
                for locale, block in row["i18n"].items()
            },
            "thumb": None,
            "icon": None,
        }
        for row in WFM_ROWS
    ]
    rows.sort(key=lambda item: item["slug"])

    return {"ts": time.time(), "language": "zh-hans", "items": rows}


@pytest.fixture(autouse=True, scope="module")
def _no_network():
    """Fail loudly instead of silently hitting warframe.market from a test."""

    def _forbid(*_args: object, **_kwargs: object):
        raise AssertionError("tests must not perform network requests")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(term_mapping, "fetch_json", _forbid)
    yield
    monkeypatch.undo()


@pytest.fixture
def mapper(tmp_path: Path) -> WarframeTermMapper:
    payload = _nickname_payload()
    default_path = tmp_path / "warframe_nicknames.default.json"
    data_path = tmp_path / "warframe_nicknames.json"
    for path in (default_path, data_path):
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    items_cache_path = tmp_path / "items-cache.json"
    items_cache_path.write_text(
        json.dumps(_items_cache_payload(), ensure_ascii=False), encoding="utf-8"
    )

    registry = NicknameRegistry(data_path=data_path, default_path=default_path)
    return WarframeTermMapper(
        nickname_registry=registry,
        plugin_data_dir=tmp_path / "plugin-data",
        items_cache_path=items_cache_path,
    )


@pytest.fixture(scope="module")
def wm_module():
    """Load `services/market/wm.py` with its AstrBot and renderer imports stubbed.

    Module scoped: executing the module pulls in the real `term_mapping`
    import chain, and doing that once per parametrised case dominated the
    runtime.
    """

    monkeypatch = pytest.MonkeyPatch()

    async def _render_wm_page_image(**_kwargs: object):
        return None, []

    def stub(name: str, **attrs: object) -> None:
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        monkeypatch.setitem(sys.modules, name, module)

    for sub, folder in (
        (f"{PACKAGE}.services", ROOT / "services"),
        (f"{PACKAGE}.services.market", ROOT / "services" / "market"),
    ):
        module = types.ModuleType(sub)
        module.__path__ = [str(folder)]
        monkeypatch.setitem(sys.modules, sub, module)

    stub("astrbot.api.event", AstrMessageEvent=object)
    stub(f"{PACKAGE}.clients.market_client", WarframeMarketClient=object)
    stub(f"{PACKAGE}.components.event_ttl_cache", EventScopedTTLCache=_CacheStub)
    stub(
        f"{PACKAGE}.components.qq_official_webhook",
        QQOfficialWebhookPager=_PagerStub,
    )
    stub(
        f"{PACKAGE}.services.market.pager_common",
        filter_sort_wm_orders=lambda orders, **_kwargs: [],
        render_wm_page_image=_render_wm_page_image,
    )

    name = f"{PACKAGE}.services.market.wm"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "services" / "market" / "wm.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        monkeypatch.undo()


def _resolve_slug(wm_module, mapper: WarframeTermMapper, raw_args: str) -> str | None:
    """Run the real `cmd_wm` and report the slug it asked the market for."""

    client = _RecordingMarketClient()

    async def _run() -> None:
        async for _ in wm_module.cmd_wm(
            context=None,
            event=_Event(raw_args),
            raw_args=raw_args,
            config=None,
            term_mapper=mapper,
            market_client=client,
            pager_cache=_CacheStub(),
            wm_pick_cache=_CacheStub(),
            qq_pager=_PagerStub(),
        ):
            pass

    asyncio.run(_run())
    return client.requested_slugs[0] if client.requested_slugs else None


@pytest.mark.parametrize(
    ("raw_args", "expected_slug"),
    [
        # Defect 1: the trailing `Prime` used to be dropped, answering with Flow.
        ("川流不息 Prime", "primed_flow"),
        # Defect 3: CJK glued to Latin used to tokenise as one unmatched blob.
        ("川流不息prime", "primed_flow"),
        # Defect 3 + the trailing-`p` marker never being rewritten to Prime.
        ("川流不息p", "primed_flow"),
        # No modifier at all still means the plain mod.
        ("川流不息", "flow"),
        # Defect 2: no alias resolution, so the token scan picked a part.
        ("悦音", "euphona_prime_set"),
        # Defect 2 through the alias path.
        ("悦音p", "euphona_prime_set"),
        # Defect 1 + 3: the component used to be dropped, then glued.
        ("悦音 枪机", "euphona_prime_receiver"),
        ("悦音枪机", "euphona_prime_receiver"),
        # `一套` glued to the base name.
        ("悦音一套", "euphona_prime_set"),
        # The blueprint stays reachable when it is what the user asked for.
        ("悦音蓝图", "euphona_prime_blueprint"),
        # Base-section alias, the case that worked before the fix.
        ("volt prime set", "volt_prime_set"),
    ],
)
def test_cmd_wm_resolves_expected_item(
    wm_module, mapper: WarframeTermMapper, raw_args: str, expected_slug: str
) -> None:
    assert _resolve_slug(wm_module, mapper, raw_args) == expected_slug


def test_cmd_wm_reports_unresolved_item_instead_of_guessing(
    wm_module, mapper: WarframeTermMapper
) -> None:
    assert _resolve_slug(wm_module, mapper, "不存在的物品xyz") is None


def test_normalize_name_key_splits_glued_chinese_components() -> None:

    assert _normalize_name_key("悦音枪机") == "悦音 枪机"
    assert _normalize_name_key("悦音枪管") == "悦音 枪管"
    assert _normalize_name_key("悦音一套") == "悦音 一套"


def test_normalize_name_key_splits_cjk_latin_boundary() -> None:

    assert _normalize_name_key("川流不息prime") == "川流不息 prime"
    assert _normalize_name_key("悦音P") == "悦音 p"


def test_normalize_name_key_keeps_already_separated_names() -> None:

    assert _normalize_name_key("悦音 Prime 枪机") == "悦音 prime 枪机"
    assert _normalize_name_key("川流不息 Prime") == "川流不息 prime"


def test_rewrite_prime_marker_rewrites_chinese_tail() -> None:
    assert _rewrite_prime_marker("川流不息p") == "川流不息 Prime"
    assert _rewrite_prime_marker("川流不息 P") == "川流不息 Prime"


def test_rewrite_prime_marker_leaves_latin_names_alone() -> None:
    """A `p` glued to a Latin name is part of that name, not a Prime marker."""

    assert _rewrite_prime_marker("Amp") == "Amp"
    assert _rewrite_prime_marker("wukongp") == "wukongp"
    assert _rewrite_prime_marker("MK-1p") == "MK-1p"
    assert _rewrite_prime_marker("p") == "p"


def test_rewrite_prime_marker_consumes_chinese_prime_prefix() -> None:
    assert _rewrite_prime_marker("圣装咖喱") == "咖喱 Prime"


def test_rewrite_prime_marker_leaves_markerless_names_alone() -> None:
    """`_parse_modifiers` reports wants_prime for any trailing `p`, even on
    names that carry no marker at all. The rewrite must not invent one."""

    assert _rewrite_prime_marker("川流不息") == "川流不息"
    assert _rewrite_prime_marker("Euphona") == "Euphona"


def test_rewrite_prime_marker_is_idempotent() -> None:
    assert _rewrite_prime_marker("川流不息 Prime") == "川流不息 Prime"
    assert _rewrite_prime_marker(_rewrite_prime_marker("川流不息p")) == (
        "川流不息 Prime"
    )
