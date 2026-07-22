from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from types import ModuleType
from urllib.parse import quote, urlencode

import pytest

from astrbot_plugin_warframe_helper.clients.huiji_wiki_client import (
    HuijiWikiResult,
    HuijiWikiStatus,
)
services_package = ModuleType("services")
services_package.__path__ = [str(Path(__file__).parents[1] / "services")]
sys.modules.setdefault("services", services_package)

from services.wiki_commands import wk


@dataclass
class Resolution:
    matched: bool
    canonical_full_name: str


class FakeEvent:
    def __init__(self, *, asynchronous: bool):
        self.asynchronous = asynchronous
        self.messages: list[str] = []

    def plain_result(self, text: str):
        self.messages.append(text)
        if self.asynchronous:
            async def done():
                return None

            return done()
        return None


class FakeMapper:
    def __init__(self, resolution=None, error=None):
        self.resolution = resolution
        self.error = error
        self.calls: list[str] = []
        self.initialize_called = False
        self.market_called = False

    def resolve_alias_only(self, query: str):
        self.calls.append(query)
        if self.error is not None:
            raise self.error
        return self.resolution or Resolution(False, query)

    def initialize(self):
        self.initialize_called = True

    def market(self):
        self.market_called = True


class FakeClient:
    def __init__(self, result=None, error=None, search_error=None):
        self.result = result or HuijiWikiResult(HuijiWikiStatus.UNAVAILABLE)
        self.error = error
        self.search_error = search_error
        self.lookups: list[str] = []
        self.searches: list[str] = []

    async def lookup(self, keyword: str):
        self.lookups.append(keyword)
        if self.error is not None:
            raise self.error
        return self.result

    def build_search_url(self, keyword: str) -> str:
        self.searches.append(keyword)
        if self.search_error is not None:
            raise self.search_error
        return "https://wiki.test/search?keyword=" + quote(keyword, safe="")


def _found(url: str = "https://wiki.test/wiki/Volt"):
    return HuijiWikiResult(HuijiWikiStatus.FOUND, url=url)


@pytest.mark.asyncio
async def test_empty_input_replies_with_usage_without_calling_dependencies():
    event = FakeEvent(asynchronous=True)
    mapper = FakeMapper()
    client = FakeClient()

    await wk(event, ["  ", "\t"], mapper, client)

    assert event.messages == ["用法：/wk 关键词"]
    assert mapper.calls == []
    assert client.lookups == []


@pytest.mark.asyncio
async def test_original_keyword_found_uses_single_space_label_and_wiki_url():
    event = FakeEvent(asynchronous=True)
    mapper = FakeMapper()
    client = FakeClient(_found("https://wiki.test/wiki/My_Page"))

    await wk(event, ["  My", "  Page  "], mapper, client)

    assert mapper.calls == ["My Page"]
    assert client.lookups == ["My Page"]
    assert event.messages == ["以下是“My Page”的 Wiki 页面：\nhttps://wiki.test/wiki/My_Page"]


@pytest.mark.asyncio
async def test_alias_found_uses_canonical_name_but_preserves_original_label():
    event = FakeEvent(asynchronous=True)
    mapper = FakeMapper(Resolution(True, "Oxylus"))
    client = FakeClient(_found("https://wiki.test/wiki/Oxylus"))

    await wk(event, ["照相机"], mapper, client)

    assert client.lookups == ["Oxylus"]
    assert event.messages == ["以下是“照相机”的 Wiki 页面：\nhttps://wiki.test/wiki/Oxylus"]
    assert not mapper.initialize_called
    assert not mapper.market_called


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [None, "", 123])
async def test_found_with_invalid_url_degrades_to_unavailable_search(url):
    event = FakeEvent(asynchronous=True)
    client = FakeClient(_found(url))

    await wk(event, ["Volt"], FakeMapper(), client)

    assert event.messages == [
        "暂时无法确认“Volt”是否有精确词条，以下是 Wiki 搜索页：\n"
        "https://wiki.test/search?keyword=Volt"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "prefix"),
    [
        (HuijiWikiStatus.MISSING, "没有查到“原词”，以下是 Wiki 搜索页："),
        (
            HuijiWikiStatus.UNAVAILABLE,
            "暂时无法确认“原词”是否有精确词条，以下是 Wiki 搜索页：",
        ),
    ],
)
async def test_non_found_statuses_reply_with_search_page(status, prefix):
    event = FakeEvent(asynchronous=True)
    mapper = FakeMapper(Resolution(True, "规范词"))
    client = FakeClient(HuijiWikiResult(status), None)

    await wk(event, ["原词"], mapper, client)

    assert client.lookups == ["规范词"]
    assert client.searches == ["规范词"]
    assert event.messages == [prefix + "\nhttps://wiki.test/search?keyword=%E8%A7%84%E8%8C%83%E8%AF%8D"]


@pytest.mark.asyncio
@pytest.mark.parametrize("asynchronous", [False, True])
async def test_plain_result_supports_sync_and_async_events(asynchronous):
    event = FakeEvent(asynchronous=asynchronous)
    await wk(event, ["Volt"], FakeMapper(), FakeClient(_found()))
    assert event.messages == ["以下是“Volt”的 Wiki 页面：\nhttps://wiki.test/wiki/Volt"]


@pytest.mark.asyncio
async def test_mapper_exception_falls_back_to_original_keyword_search():
    event = FakeEvent(asynchronous=True)
    mapper = FakeMapper(error=RuntimeError("mapper down"))
    client = FakeClient(HuijiWikiResult(HuijiWikiStatus.MISSING))

    await wk(event, ["原始  词"], mapper, client)

    assert client.lookups == ["原始 词"]
    assert client.searches == ["原始 词"]
    assert event.messages == [
        "没有查到“原始 词”，以下是 Wiki 搜索页：\nhttps://wiki.test/search?keyword=%E5%8E%9F%E5%A7%8B%20%E8%AF%8D"
    ]


@pytest.mark.asyncio
async def test_client_exception_degrades_to_unavailable_search():
    event = FakeEvent(asynchronous=True)
    client = FakeClient(error=RuntimeError("client down"))

    await wk(event, ["Volt"], FakeMapper(), client)

    assert event.messages == [
        "暂时无法确认“Volt”是否有精确词条，以下是 Wiki 搜索页：\nhttps://wiki.test/search?keyword=Volt"
    ]


@pytest.mark.asyncio
async def test_search_url_exception_uses_encoded_huiji_fallback_url():
    event = FakeEvent(asynchronous=True)
    keyword = "电男 Prime +&?#%|"
    client = FakeClient(
        HuijiWikiResult(HuijiWikiStatus.UNAVAILABLE),
        search_error=RuntimeError("search builder down"),
    )

    await wk(event, keyword.split(), FakeMapper(), client)

    expected_url = "https://warframe.huijiwiki.com/index.php?" + urlencode(
        {
            "title": "特殊:搜索",
            "profile": "default",
            "search": keyword,
            "sort": "just_match",
        }
    )
    assert event.messages == [
        "暂时无法确认“电男 Prime +&?#%|”是否有精确词条，以下是 Wiki 搜索页：\n"
        + expected_url
    ]


@pytest.mark.asyncio
async def test_base_exception_from_mapper_is_not_caught():
    event = FakeEvent(asynchronous=True)
    with pytest.raises(KeyboardInterrupt):
        await wk(event, ["Volt"], FakeMapper(error=KeyboardInterrupt()), FakeClient())


@pytest.mark.asyncio
async def test_base_exception_from_client_is_not_caught():
    event = FakeEvent(asynchronous=True)
    with pytest.raises(KeyboardInterrupt):
        await wk(event, ["Volt"], FakeMapper(), FakeClient(error=KeyboardInterrupt()))


@pytest.mark.asyncio
async def test_pipe_is_passed_to_client_and_search_url_encodes_complete_keyword():
    event = FakeEvent(asynchronous=True)
    client = FakeClient()

    await wk(event, ["A|B"], FakeMapper(), client)

    assert client.lookups == ["A|B"]
    assert client.searches == ["A|B"]
    assert event.messages == [
        "暂时无法确认“A|B”是否有精确词条，以下是 Wiki 搜索页：\nhttps://wiki.test/search?keyword=A%7CB"
    ]
