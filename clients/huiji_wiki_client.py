from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlsplit

import aiohttp

from ..http_utils import request_kwargs_for_url


_ABSENT = object()


class HuijiWikiStatus(str, Enum):
    FOUND = "found"
    MISSING = "missing"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class HuijiWikiResult:
    status: HuijiWikiStatus
    title: str | None = None
    url: str | None = None


class HuijiWikiClient:
    def __init__(
        self,
        *,
        site: str = "warframe",
        http_timeout_sec: float = 10.0,
        max_response_bytes: int = 128 * 1024,
    ) -> None:
        site_name = str(site or "").strip().lower()
        allowed_site_chars = "abcdefghijklmnopqrstuvwxyz0123456789-"
        if not site_name or any(ch not in allowed_site_chars for ch in site_name):
            raise ValueError("site must contain only lowercase letters, digits, or hyphens")

        self._site_hostname = f"{site_name}.huijiwiki.com"
        self._site_root = f"https://{self._site_hostname}"
        self.api_url = f"{self._site_root}/api.php"
        self._timeout = aiohttp.ClientTimeout(total=float(http_timeout_sec))
        self._max_response_bytes = max(1, int(max_response_bytes))

    async def lookup(self, keyword: str) -> HuijiWikiResult:
        title = str(keyword or "").strip()
        if not title or "|" in title:
            return self._unavailable()

        params: dict[str, str | int] = {
            "action": "query",
            "prop": "info",
            "inprop": "url",
            "titles": title,
            "redirects": 1,
            "format": "json",
            "formatversion": 2,
        }
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0 Safari/537.36"
            ),
            "Accept": "application/json, application/*+json;q=0.9",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
            "Referer": f"{self._site_root}/",
        }

        try:
            async with aiohttp.ClientSession(
                timeout=self._timeout,
                trust_env=True,
            ) as session:
                api_result, may_fallback = await self._lookup_via_api(
                    session,
                    params=params,
                    headers=headers,
                )
                if api_result.status is not HuijiWikiStatus.UNAVAILABLE:
                    return api_result
                if not may_fallback:
                    return api_result
                search_result, may_probe_direct = await self._lookup_via_search_redirect(
                    session,
                    title=title,
                    headers=headers,
                )
                if search_result.status is HuijiWikiStatus.FOUND:
                    return search_result
                if not may_probe_direct:
                    return search_result
                return await self._lookup_via_direct_page(
                    session,
                    title=title,
                    headers=headers,
                )
        except Exception:
            return self._unavailable()

    async def _lookup_via_api(
        self,
        session: Any,
        *,
        params: dict[str, str | int],
        headers: dict[str, str],
    ) -> tuple[HuijiWikiResult, bool]:
        try:
            request_kwargs = request_kwargs_for_url(self.api_url)
            async with session.get(
                self.api_url,
                params=params,
                headers=headers,
                **request_kwargs,
            ) as response:
                if response.status != 200:
                    return self._unavailable(), True
                if not _is_application_json(response.headers.get("Content-Type")):
                    return self._unavailable(), False

                body = await _read_limited_body(
                    response,
                    max_bytes=self._max_response_bytes,
                )
                if body is None:
                    return self._unavailable(), False
        except Exception:
            return self._unavailable(), True

        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._unavailable(), False
        return self._parse_payload(payload), False

    async def _lookup_via_search_redirect(
        self,
        session: Any,
        *,
        title: str,
        headers: dict[str, str],
    ) -> tuple[HuijiWikiResult, bool]:
        search_url = self.build_search_url(title)
        html_headers = {
            **headers,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        }
        request_kwargs = request_kwargs_for_url(search_url)
        try:
            async with session.get(
                search_url,
                headers=html_headers,
                allow_redirects=False,
                **request_kwargs,
            ) as response:
                if response.status == 200:
                    response_url = str(getattr(response, "url", "") or "")
                    if _is_exact_page_url(
                        response_url,
                        expected_hostname=self._site_hostname,
                    ):
                        return (
                            HuijiWikiResult(
                                HuijiWikiStatus.FOUND,
                                title=title,
                                url=response_url,
                            ),
                            False,
                        )
                    return self._unavailable(), True
                if response.status not in {301, 302, 303, 307, 308}:
                    may_probe_direct = response.status in {403, 429, 500, 502, 503}
                    return self._unavailable(), may_probe_direct
                location = response.headers.get("Location")
                if not isinstance(location, str) or not location.strip():
                    return self._unavailable(), False
        except Exception:
            return self._unavailable(), True

        page_url = urljoin(search_url, location.strip())
        if not _is_exact_page_url(
            page_url,
            expected_hostname=self._site_hostname,
        ):
            return self._unavailable(), False
        return (
            HuijiWikiResult(HuijiWikiStatus.FOUND, title=title, url=page_url),
            False,
        )

    async def _lookup_via_direct_page(
        self,
        session: Any,
        *,
        title: str,
        headers: dict[str, str],
    ) -> HuijiWikiResult:
        direct_url = self.build_page_url(title)
        if not direct_url:
            return self._unavailable()
        html_headers = {
            **headers,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        }
        request_kwargs = request_kwargs_for_url(direct_url)
        async with session.get(
            direct_url,
            headers=html_headers,
            allow_redirects=False,
            **request_kwargs,
        ) as response:
            if response.status == 200:
                response_url = str(getattr(response, "url", "") or direct_url)
                if _is_exact_page_url(
                    response_url,
                    expected_hostname=self._site_hostname,
                ):
                    return HuijiWikiResult(
                        HuijiWikiStatus.FOUND,
                        title=title,
                        url=response_url,
                    )
                return self._unavailable()
            if response.status not in {301, 302, 303, 307, 308}:
                return self._unavailable()
            location = response.headers.get("Location")
            if not isinstance(location, str) or not location.strip():
                return self._unavailable()

        page_url = urljoin(direct_url, location.strip())
        if not _is_exact_page_url(
            page_url,
            expected_hostname=self._site_hostname,
        ):
            return self._unavailable()
        return HuijiWikiResult(HuijiWikiStatus.FOUND, title=title, url=page_url)

    def build_search_url(self, keyword: str) -> str:
        query = urlencode(
            {
                "title": "特殊:搜索",
                "profile": "default",
                "search": str(keyword or ""),
                "sort": "just_match",
            }
        )
        return f"{self._site_root}/index.php?{query}"

    def build_page_url(self, keyword: str) -> str:
        page_title = "_".join(str(keyword or "").split())
        if not page_title:
            return ""
        return f"{self._site_root}/wiki/{quote(page_title, safe='_')}"

    def _parse_payload(self, payload: Any) -> HuijiWikiResult:
        if not isinstance(payload, dict) or "error" in payload:
            return self._unavailable()

        query = payload.get("query")
        if not isinstance(query, dict):
            return self._unavailable()
        pages = query.get("pages")
        if not isinstance(pages, list) or len(pages) != 1:
            return self._unavailable()

        page = pages[0]
        if not isinstance(page, dict):
            return self._unavailable()

        missing_flag = page.get("missing", _ABSENT)
        invalid_flag = page.get("invalid", _ABSENT)
        present_flags = [
            flag for flag in (missing_flag, invalid_flag) if flag is not _ABSENT
        ]
        if present_flags:
            if all(flag is True for flag in present_flags):
                return HuijiWikiResult(HuijiWikiStatus.MISSING)
            return self._unavailable()

        page_id = page.get("pageid")
        namespace = page.get("ns")
        if (
            not isinstance(page_id, int)
            or isinstance(page_id, bool)
            or page_id <= 0
            or not isinstance(namespace, int)
            or isinstance(namespace, bool)
        ):
            return self._unavailable()

        final_title = page.get("title")
        if not isinstance(final_title, str) or not final_title.strip():
            return self._unavailable()
        final_title = final_title.strip()

        fullurl = page.get("fullurl")
        if fullurl is None or fullurl == "":
            fullurl = f"{self._site_root}/wiki/{quote(final_title, safe='')}"
        elif not isinstance(fullurl, str) or not _is_expected_page_url(
            fullurl,
            expected_hostname=self._site_hostname,
        ):
            return self._unavailable()

        return HuijiWikiResult(HuijiWikiStatus.FOUND, final_title, fullurl)

    @staticmethod
    def _unavailable() -> HuijiWikiResult:
        return HuijiWikiResult(HuijiWikiStatus.UNAVAILABLE)


def _is_application_json(content_type: object) -> bool:
    if not isinstance(content_type, str):
        return False
    media_type = content_type.split(";", 1)[0].strip().lower()
    if not media_type.startswith("application/"):
        return False
    subtype = media_type.removeprefix("application/")
    return subtype == "json" or subtype.endswith("+json")


def _is_expected_page_url(value: str, *, expected_hostname: str) -> bool:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname == expected_hostname
        and parsed.username is None
        and parsed.password is None
        and port in {None, 443}
    )


def _is_exact_page_url(value: str, *, expected_hostname: str) -> bool:
    if not _is_expected_page_url(value, expected_hostname=expected_hostname):
        return False
    parsed = urlsplit(value)
    if parsed.path.startswith("/wiki/") and parsed.path != "/wiki/":
        return True
    if parsed.path != "/index.php":
        return False
    titles = parse_qs(parsed.query).get("title", [])
    return bool(titles) and all(title.casefold() != "特殊:搜索" for title in titles)


async def _read_limited_body(response: Any, *, max_bytes: int) -> bytes | None:
    raw_length = response.headers.get("Content-Length")
    if raw_length is not None:
        try:
            if int(raw_length) > max_bytes:
                return None
        except (TypeError, ValueError):
            pass

    body = bytearray()
    async for chunk in response.content.iter_chunked(64 * 1024):
        if not isinstance(chunk, (bytes, bytearray)):
            return None
        if len(body) + len(chunk) > max_bytes:
            return None
        body.extend(chunk)
    return bytes(body)
