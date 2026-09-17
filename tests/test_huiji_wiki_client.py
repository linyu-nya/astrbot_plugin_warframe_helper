from __future__ import annotations

import asyncio
import json
import ssl
from dataclasses import FrozenInstanceError
from urllib.parse import parse_qs, urlparse

import pytest

from astrbot_plugin_warframe_helper.clients import huiji_wiki_client as wiki_module
from astrbot_plugin_warframe_helper.clients.huiji_wiki_client import (
    HuijiWikiClient,
    HuijiWikiResult,
    HuijiWikiStatus,
)


class FakeContent:
    def __init__(self, body: bytes, *, chunk_size: int | None = None) -> None:
        self._body = body
        self._chunk_size = chunk_size or max(1, len(body))

    async def iter_chunked(self, _size: int):
        for offset in range(0, len(self._body), self._chunk_size):
            yield self._body[offset : offset + self._chunk_size]


class FakeResponse:
    def __init__(
        self,
        payload: object = None,
        *,
        body: bytes | None = None,
        status: int = 200,
        content_type: str = "application/json; charset=utf-8",
        headers: dict[str, str] | None = None,
        chunk_size: int | None = None,
        url: str | None = None,
    ) -> None:
        raw = body if body is not None else json.dumps(payload).encode("utf-8")
        self.status = status
        self.headers = {"Content-Type": content_type, **(headers or {})}
        self.content = FakeContent(raw, chunk_size=chunk_size)
        self.url = url

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class FakeSession:
    def __init__(
        self,
        response_or_error: FakeResponse | BaseException | list[FakeResponse | BaseException],
    ) -> None:
        self.response_or_error = response_or_error
        self.get_calls: list[tuple[str, dict[str, object]]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def get(self, url: str, **kwargs):
        self.get_calls.append((url, kwargs))
        response_or_error = self.response_or_error
        if isinstance(response_or_error, list):
            index = min(len(self.get_calls) - 1, len(response_or_error) - 1)
            response_or_error = response_or_error[index]
        if isinstance(response_or_error, BaseException):
            raise response_or_error
        return response_or_error


def install_session(
    monkeypatch: pytest.MonkeyPatch,
    response_or_error: FakeResponse | BaseException | list[FakeResponse | BaseException],
):
    session = FakeSession(response_or_error)
    constructor_calls: list[dict[str, object]] = []

    def session_factory(**kwargs):
        constructor_calls.append(kwargs)
        return session

    monkeypatch.setattr(wiki_module.aiohttp, "ClientSession", session_factory)
    return session, constructor_calls


def page_payload(**page_overrides: object) -> dict[str, object]:
    page = {
        "pageid": 42,
        "ns": 0,
        "title": "圣装伏特",
        "fullurl": "https://warframe.huijiwiki.com/wiki/圣装伏特",
        **page_overrides,
    }
    return {"batchcomplete": True, "query": {"pages": [page]}}


@pytest.mark.asyncio
async def test_exact_lookup_returns_immutable_found_result(monkeypatch):
    session, constructor_calls = install_session(monkeypatch, FakeResponse(page_payload()))
    proxy_calls: list[str] = []

    def request_kwargs(url: str):
        proxy_calls.append(url)
        return {"proxy": "http://127.0.0.1:7890"}

    monkeypatch.setattr(wiki_module, "request_kwargs_for_url", request_kwargs)
    client = HuijiWikiClient(http_timeout_sec=7.5)

    result = await client.lookup("圣装伏特")

    assert result == HuijiWikiResult(
        HuijiWikiStatus.FOUND,
        title="圣装伏特",
        url="https://warframe.huijiwiki.com/wiki/圣装伏特",
    )
    with pytest.raises(FrozenInstanceError):
        result.title = "changed"  # type: ignore[misc]
    assert proxy_calls == ["https://warframe.huijiwiki.com/api.php"]
    assert len(constructor_calls) == 1
    assert constructor_calls[0]["trust_env"] is True
    assert constructor_calls[0]["timeout"].total == 7.5

    assert len(session.get_calls) == 1
    url, request = session.get_calls[0]
    assert url == "https://warframe.huijiwiki.com/api.php"
    assert request["proxy"] == "http://127.0.0.1:7890"
    assert request["params"] == {
        "action": "query",
        "prop": "info",
        "inprop": "url",
        "titles": "圣装伏特",
        "redirects": 1,
        "format": "json",
        "formatversion": 2,
    }
    headers = request["headers"]
    assert "Mozilla/5.0" in headers["User-Agent"]
    assert "application/json" in headers["Accept"]
    assert headers["Referer"] == "https://warframe.huijiwiki.com/"


@pytest.mark.asyncio
async def test_redirect_uses_final_page_title_and_fullurl(monkeypatch):
    install_session(
        monkeypatch,
        FakeResponse(
            page_payload(
                title="Volt Prime",
                fullurl="https://warframe.huijiwiki.com/wiki/Volt_Prime",
            )
        ),
    )

    result = await HuijiWikiClient().lookup("电男p")

    assert result.status is HuijiWikiStatus.FOUND
    assert result.title == "Volt Prime"
    assert result.url == "https://warframe.huijiwiki.com/wiki/Volt_Prime"


@pytest.mark.asyncio
async def test_api_failure_uses_exact_search_redirect_as_found_page(monkeypatch):
    session, _ = install_session(
        monkeypatch,
        [
            FakeResponse(page_payload(), status=403),
            FakeResponse(
                body=b"",
                status=302,
                content_type="text/html",
                headers={"Location": "/wiki/Afentis_Prime"},
            ),
        ],
    )

    result = await HuijiWikiClient().lookup("afentis Prime")

    assert result == HuijiWikiResult(
        HuijiWikiStatus.FOUND,
        title="afentis Prime",
        url="https://warframe.huijiwiki.com/wiki/Afentis_Prime",
    )
    assert len(session.get_calls) == 2
    search_url, request = session.get_calls[1]
    parsed = urlparse(search_url)
    assert parsed.path == "/index.php"
    assert parse_qs(parsed.query)["search"] == ["afentis Prime"]
    assert request["allow_redirects"] is False


@pytest.mark.asyncio
async def test_api_failure_rejects_external_search_redirect(monkeypatch):
    session, _ = install_session(
        monkeypatch,
        [
            FakeResponse(page_payload(), status=403),
            FakeResponse(
                body=b"",
                status=302,
                content_type="text/html",
                headers={"Location": "https://evil.example/wiki/Afentis_Prime"},
            ),
        ],
    )

    result = await HuijiWikiClient().lookup("afentis Prime")

    assert result == HuijiWikiResult(HuijiWikiStatus.UNAVAILABLE)
    assert len(session.get_calls) == 2


@pytest.mark.asyncio
async def test_api_failure_accepts_search_response_already_on_exact_page(monkeypatch):
    session, _ = install_session(
        monkeypatch,
        [
            FakeResponse(page_payload(), status=403),
            FakeResponse(
                body=b"<html></html>",
                status=200,
                content_type="text/html",
                url="https://warframe.huijiwiki.com/wiki/Afentis_Prime",
            ),
        ],
    )

    result = await HuijiWikiClient().lookup("afentis Prime")

    assert result == HuijiWikiResult(
        HuijiWikiStatus.FOUND,
        title="afentis Prime",
        url="https://warframe.huijiwiki.com/wiki/Afentis_Prime",
    )
    assert len(session.get_calls) == 2


@pytest.mark.asyncio
async def test_api_and_search_failure_probe_direct_page(monkeypatch):
    search_url = HuijiWikiClient().build_search_url("afentis Prime")
    session, _ = install_session(
        monkeypatch,
        [
            FakeResponse(page_payload(), status=403),
            FakeResponse(
                body=b"<html>search results</html>",
                status=200,
                content_type="text/html",
                url=search_url,
            ),
            FakeResponse(
                body=b"<html>exact page</html>",
                status=200,
                content_type="text/html",
                url="https://warframe.huijiwiki.com/wiki/afentis_Prime",
            ),
        ],
    )

    result = await HuijiWikiClient().lookup("afentis Prime")

    assert result == HuijiWikiResult(
        HuijiWikiStatus.FOUND,
        title="afentis Prime",
        url="https://warframe.huijiwiki.com/wiki/afentis_Prime",
    )
    assert len(session.get_calls) == 3
    direct_url, request = session.get_calls[2]
    assert direct_url == "https://warframe.huijiwiki.com/wiki/afentis_Prime"
    assert request["allow_redirects"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fullurl",
    [
        "https://evil.example/wiki/Volt",
        "https://warframe.huijiwiki.com@evil.example/wiki/Volt",
        "https://user@warframe.huijiwiki.com/wiki/Volt",
        "https://user:password@warframe.huijiwiki.com/wiki/Volt",
        "https://warframe.huijiwiki.com:444/wiki/Volt",
        "http://warframe.huijiwiki.com/wiki/Volt",
        "https://warframe.huijiwiki.com:not-a-port/wiki/Volt",
    ],
)
async def test_untrusted_or_malformed_fullurl_is_unavailable(monkeypatch, fullurl):
    install_session(
        monkeypatch,
        FakeResponse(page_payload(title="Volt", fullurl=fullurl)),
    )

    result = await HuijiWikiClient().lookup("Volt")

    assert result == HuijiWikiResult(HuijiWikiStatus.UNAVAILABLE, None, None)


@pytest.mark.asyncio
async def test_explicit_default_https_port_is_found(monkeypatch):
    fullurl = "https://warframe.huijiwiki.com:443/wiki/Volt"
    install_session(
        monkeypatch,
        FakeResponse(page_payload(title="Volt", fullurl=fullurl)),
    )

    result = await HuijiWikiClient().lookup("Volt")

    assert result == HuijiWikiResult(HuijiWikiStatus.FOUND, "Volt", fullurl)


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", ["missing", "invalid"])
async def test_confirmed_missing_or_invalid_page_returns_missing(monkeypatch, flag):
    install_session(monkeypatch, FakeResponse(page_payload(**{flag: True})))

    result = await HuijiWikiClient().lookup("不存在")

    assert result == HuijiWikiResult(HuijiWikiStatus.MISSING, None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "flags",
    [
        {"missing": False},
        {"missing": None},
        {"missing": 0},
        {"missing": ""},
        {"missing": {}},
        {"invalid": False},
        {"invalid": None},
        {"invalid": 0},
        {"invalid": ""},
        {"invalid": {}},
        {"missing": True, "invalid": False},
    ],
)
async def test_non_true_missing_or_invalid_flags_are_unavailable(
    monkeypatch, flags
):
    install_session(monkeypatch, FakeResponse(page_payload(**flags)))

    result = await HuijiWikiClient().lookup("不存在")

    assert result == HuijiWikiResult(HuijiWikiStatus.UNAVAILABLE, None, None)


@pytest.mark.asyncio
async def test_missing_fullurl_builds_encoded_page_url(monkeypatch):
    install_session(
        monkeypatch,
        FakeResponse(page_payload(title="Volt Prime/配装 + 测试", fullurl=None)),
    )

    result = await HuijiWikiClient().lookup("电男")

    assert result == HuijiWikiResult(
        HuijiWikiStatus.FOUND,
        "Volt Prime/配装 + 测试",
        "https://warframe.huijiwiki.com/wiki/Volt%20Prime%2F%E9%85%8D%E8%A3%85%20%2B%20%E6%B5%8B%E8%AF%95",
    )


@pytest.mark.parametrize(
    "keyword",
    ["中文", "two words", "+", "&", "?", "#", "%", "|", "混 合+&?#%|"],
)
def test_search_url_round_trips_all_keywords(keyword):
    url = HuijiWikiClient().build_search_url(keyword)
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)

    assert parsed.scheme == "https"
    assert parsed.netloc == "warframe.huijiwiki.com"
    assert parsed.path == "/index.php"
    assert query == {
        "title": ["特殊:搜索"],
        "profile": ["default"],
        "search": [keyword],
        "sort": ["just_match"],
    }
    if keyword == "|":
        assert "search=%7C" in url


def test_page_url_normalizes_spaces_and_encodes_title():
    assert (
        HuijiWikiClient().build_page_url(" afentis   Prime 蓝图 ")
        == "https://warframe.huijiwiki.com/wiki/afentis_Prime_%E8%93%9D%E5%9B%BE"
    )


@pytest.mark.asyncio
async def test_pipe_in_keyword_skips_network(monkeypatch):
    session, constructor_calls = install_session(monkeypatch, FakeResponse(page_payload()))

    result = await HuijiWikiClient().lookup("伏特|圣装伏特")

    assert result == HuijiWikiResult(HuijiWikiStatus.UNAVAILABLE, None, None)
    assert constructor_calls == []
    assert session.get_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        asyncio.TimeoutError(),
        OSError("dns/connection failed"),
        ConnectionError("connection reset"),
        ssl.SSLError("tls failed"),
    ],
)
async def test_network_failures_return_unavailable(monkeypatch, error):
    install_session(monkeypatch, error)

    result = await HuijiWikiClient().lookup("伏特")

    assert result.status is HuijiWikiStatus.UNAVAILABLE


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 403, 404, 429, 500, 502, 503])
async def test_non_200_statuses_return_unavailable(monkeypatch, status):
    install_session(monkeypatch, FakeResponse(page_payload(), status=status))

    result = await HuijiWikiClient().lookup("伏特")

    assert result.status is HuijiWikiStatus.UNAVAILABLE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content_type", "body"),
    [
        ("text/html", b"<html>Cloudflare challenge</html>"),
        ("text/plain", json.dumps(page_payload()).encode()),
        ("text/json", json.dumps(page_payload()).encode()),
        ("", json.dumps(page_payload()).encode()),
    ],
)
async def test_non_application_json_content_type_is_unavailable(
    monkeypatch, content_type, body
):
    install_session(
        monkeypatch,
        FakeResponse(body=body, content_type=content_type),
    )

    result = await HuijiWikiClient().lookup("伏特")

    assert result.status is HuijiWikiStatus.UNAVAILABLE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content_type",
    ["application/json", "application/json; charset=UTF-8", "application/problem+json"],
)
async def test_application_json_media_types_are_accepted(monkeypatch, content_type):
    install_session(
        monkeypatch,
        FakeResponse(page_payload(), content_type=content_type),
    )

    result = await HuijiWikiClient().lookup("伏特")

    assert result.status is HuijiWikiStatus.FOUND


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        FakeResponse(body=b"{not json"),
        FakeResponse({"error": {"code": "badrequest"}}),
        FakeResponse({}),
        FakeResponse({"query": {}}),
        FakeResponse({"query": {"pages": []}}),
        FakeResponse({"query": {"pages": [{}, {}]}}),
        FakeResponse({"query": {"pages": "not-a-list"}}),
        FakeResponse({"query": {"pages": ["not-a-page"]}}),
        FakeResponse({"query": {"pages": [{}]}}),
        FakeResponse({"query": {"pages": [{"title": ""}]}}),
        FakeResponse(
            {
                "query": {
                    "pages": [
                        {
                            "ns": 0,
                            "title": "伏特",
                            "fullurl": "https://warframe.huijiwiki.com/wiki/伏特",
                        }
                    ]
                }
            }
        ),
        FakeResponse(
            {
                "query": {
                    "pages": [
                        {
                            "pageid": 42,
                            "title": "伏特",
                            "fullurl": "https://warframe.huijiwiki.com/wiki/伏特",
                        }
                    ]
                }
            }
        ),
    ],
)
async def test_malformed_or_unverified_payloads_return_unavailable(
    monkeypatch, response
):
    install_session(monkeypatch, response)

    result = await HuijiWikiClient().lookup("伏特")

    assert result.status is HuijiWikiStatus.UNAVAILABLE


@pytest.mark.asyncio
async def test_declared_oversized_response_is_unavailable(monkeypatch):
    install_session(
        monkeypatch,
        FakeResponse(
            page_payload(),
            headers={"Content-Length": str(128 * 1024 + 1)},
        ),
    )

    result = await HuijiWikiClient(max_response_bytes=128 * 1024).lookup("伏特")

    assert result.status is HuijiWikiStatus.UNAVAILABLE


@pytest.mark.asyncio
async def test_streamed_oversized_response_is_unavailable(monkeypatch):
    install_session(
        monkeypatch,
        FakeResponse(
            body=b" " * 101,
            headers={"Content-Length": "invalid"},
            chunk_size=25,
        ),
    )

    result = await HuijiWikiClient(max_response_bytes=100).lookup("伏特")

    assert result.status is HuijiWikiStatus.UNAVAILABLE
