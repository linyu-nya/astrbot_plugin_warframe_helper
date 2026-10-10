from __future__ import annotations

import inspect
import re
from urllib.parse import urlencode

try:
    from ..utils.text import normalize_wiki_keyword
except ImportError:  # Compatibility for direct service-module loading.
    from utils.text import normalize_wiki_keyword


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

    resolved_keyword = normalize_wiki_keyword(keyword)
    mapping_matched = False
    try:
        resolution = mapper.resolve_alias_only(keyword)
        if _field(resolution, "matched", False):
            mapping_matched = True
            resolved_keyword = normalize_wiki_keyword(
                _field(
                    resolution,
                    "canonical_full_name",
                    keyword,
                )
                or keyword
            )
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

    if mapping_matched and status != "missing":
        try:
            page_url = client.build_page_url(resolved_keyword)
        except Exception:
            page_url = ""
        if isinstance(page_url, str) and page_url.strip():
            return await _reply(
                event,
                f"以下是“{keyword}”的 Wiki 页面：\n{page_url}",
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


async def translate(event, args, mapper):
    keyword = " ".join(part for arg in args for part in str(arg).split())
    if not keyword:
        return await _reply(event, "用法：/翻译 关键词")
    try:
        resolution = mapper.resolve_alias_only(keyword)
        if _field(resolution, "matched", False):
            target = normalize_wiki_keyword(_field(resolution, "canonical_full_name", ""))
            return await _reply(event, f"【{keyword}】=> {target}")

        normalized = normalize_wiki_keyword(keyword)
        suffix = ""
        base = normalized
        for marker, label in ((r"\s*蓝图$", "蓝图"), (r"\s+Prime$", "Prime")):
            hit = re.search(marker, base, re.IGNORECASE)
            if hit:
                base = base[:hit.start()].strip()
                suffix = f" {label}{suffix}"
        entries = mapper.find_effective_aliases(base)
        chinese = sorted(
            (str(_field(item, "alias", "")) for item in entries
             if re.search(r"[\u4e00-\u9fff]", str(_field(item, "alias", "")))),
            key=lambda name: (len(name), name),
        )
        if chinese:
            return await _reply(event, f"【{keyword}】=> {chinese[0]}{suffix}")
    except Exception:
        pass
    return await _reply(event, f"未找到“{keyword}”的本地翻译映射。")
