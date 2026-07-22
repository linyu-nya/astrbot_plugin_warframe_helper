from __future__ import annotations

import inspect
from urllib.parse import urlencode


_HUIJI_SEARCH_ROOT = "https://warframe.huijiwiki.com/index.php"


async def _reply(event, text: str):
    result = event.plain_result(text)
    if inspect.isawaitable(result):
        return await result
    return result


def _field(value, name: str, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _status_name(status) -> str:
    value = getattr(status, "value", status)
    return str(value).lower()


def _fallback_search_url(keyword: str) -> str:
    query = urlencode(
        {
            "title": "特殊:搜索",
            "profile": "default",
            "search": keyword,
            "sort": "just_match",
        }
    )
    return f"{_HUIJI_SEARCH_ROOT}?{query}"


async def wk(event, args, mapper, client):
    keyword = " ".join(
        part
        for arg in args
        for part in str(arg).split()
    )
    if not keyword:
        return await _reply(event, "用法：/wk 关键词")

    resolved_keyword = keyword
    try:
        resolution = mapper.resolve_alias_only(keyword)
        if _field(resolution, "matched", False):
            resolved_keyword = _field(
                resolution,
                "canonical_full_name",
                keyword,
            ) or keyword
    except Exception:
        pass

    try:
        result = await client.lookup(resolved_keyword)
    except Exception:
        result = None

    status = _status_name(_field(result, "status"))
    url = _field(result, "url")
    if status == "found" and isinstance(url, str) and url.strip():
        return await _reply(
            event,
            f"以下是“{keyword}”的 Wiki 页面：\n{url}",
        )

    try:
        search_url = client.build_search_url(resolved_keyword)
    except Exception:
        search_url = _fallback_search_url(resolved_keyword)
    if status == "missing":
        message = f"没有查到“{keyword}”，以下是 Wiki 搜索页："
    else:
        message = f"暂时无法确认“{keyword}”是否有精确词条，以下是 Wiki 搜索页："
    return await _reply(event, f"{message}\n{search_url}")
