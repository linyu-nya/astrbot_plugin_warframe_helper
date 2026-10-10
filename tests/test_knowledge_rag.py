from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

package = ModuleType("astrbot_plugin_warframe_helper.services")
package.__path__ = [str(Path(__file__).parents[1] / "services")]
sys.modules.setdefault(package.__name__, package)

from astrbot_plugin_warframe_helper.services import knowledge_rag as rag


class Part:
    def __init__(self, text):
        self.text = text
        self.temporary = False

    def mark_as_temp(self):
        self.temporary = True
        return self


class Event:
    def __init__(self):
        self.extra = {}

    def get_extra(self, key, default=None):
        return self.extra.get(key, default)

    def set_extra(self, key, value):
        self.extra[key] = value


class Service:
    def __init__(self, results=None, error=None, delay=0):
        self.results = results or []
        self.error = error
        self.delay = delay
        self.calls = 0

    async def retrieve(self, query, *, max_chunks):
        self.calls += 1
        await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.results[:max_chunks]


def request(parts=None):
    return SimpleNamespace(
        prompt="初始战甲选错了怎么办？", system_prompt="扮演藤田琴音", contexts=[{"role": "assistant", "content": "你好"}],
        func_tool=object(), extra_user_content_parts=list(parts or []),
    )


HIT = {"doc_name": "新手指南", "content": "可以通过建造获取其他战甲。\n来源：https://www.warframe.com/zh-hans/game/quickstart"}


@pytest.mark.asyncio
async def test_rag_injects_temporary_context_without_replacing_persona_or_tools():
    event, req, service = Event(), request(), Service([HIT])
    tools = req.func_tool
    result = await rag.prepare_rag(event, req, service, part_factory=Part)
    assert result["outcome"] == "injected"
    assert service.calls == 1
    assert req.system_prompt == "扮演藤田琴音" and req.func_tool is tools
    assert req.contexts == [{"role": "assistant", "content": "你好"}]
    assert req.prompt == "初始战甲选错了怎么办？"
    assert len(req.extra_user_content_parts) == 1 and req.extra_user_content_parts[0].temporary
    assert "[[WFKB:1]]" in req.extra_user_content_parts[0].text
    assert "新手指南" in req.extra_user_content_parts[0].text
    await rag.prepare_rag(event, req, service, part_factory=Part)
    assert service.calls == 1 and len(req.extra_user_content_parts) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("service", [Service(), Service(error=RuntimeError("HTTP 410")), Service(delay=.05)])
async def test_empty_failed_or_timed_out_retrieval_keeps_native_chat(service):
    event, req = Event(), request()
    result = await rag.prepare_rag(event, req, service, part_factory=Part, timeout_sec=.01)
    assert result["outcome"] in {"empty", "error", "timeout"}
    assert req.extra_user_content_parts == [] and req.system_prompt == "扮演藤田琴音"


@pytest.mark.asyncio
@pytest.mark.parametrize("heading", ["〖知识 1〗", "【知识 1】"])
@pytest.mark.parametrize("colon", [":", "："])
async def test_reuses_native_astrbot_results_without_a_second_retrieval(heading, colon):
    native = Part(f"[Related Knowledge Base Results]:\n以下是相关的知识库内容:\n{heading}\n来源{colon} Warframe / 新手指南\n内容{colon} 可以制作其他战甲。\n来源：https://www.warframe.com/guide\n相关度{colon} 0.03\n")
    event, req, service = Event(), request([native]), Service([HIT])
    result = await rag.prepare_rag(event, req, service, part_factory=Part, native_configured=True)
    assert result["outcome"] == "native_reused" and service.calls == 0
    assert len(req.extra_user_content_parts) == 1
    assert "可以制作其他战甲" in req.extra_user_content_parts[0].text
    response = rag.decorate_answer(event, "别担心，可以制作其他战甲。[[WFKB:1]]")
    assert "知识库参考" in response and "https://www.warframe.com/guide" in response


@pytest.mark.asyncio
async def test_native_legacy_multi_chunk_keeps_sources_separate_and_preserves_memory():
    native = Part(
        "[Related Knowledge Base Results]:\r\n"
        "【知识 1】\r\n来源: Warframe / 新手指南\r\n内容: 可以制作其他战甲。\r\n来源：https://www.warframe.com/guide\r\n相关度: 0.03\r\n"
        "【知识 2】\r\n来源: Warframe / 第二场梦\r\n内容: 完成 Natah 和接合点要求。\r\n来源：https://www.warframe.com/quests\r\n相关度: 0.02\r\n"
    )
    memory = Part("本轮回忆：用户喜欢某个战甲。")
    req, event, service = request([memory, native]), Event(), Service()
    stats = await rag.prepare_rag(event, req, service, part_factory=Part, native_configured=True)
    assert stats["chunks"] == 2 and service.calls == 0
    assert req.extra_user_content_parts[0] is memory
    text = req.extra_user_content_parts[1].text
    assert "相关度:" not in text
    answer = rag.decorate_answer(event, "完成系列任务和接合点要求。[[WFKB:2]]")
    assert "https://www.warframe.com/quests" in answer
    assert "https://www.warframe.com/guide" not in answer


@pytest.mark.asyncio
async def test_native_empty_result_does_not_retry_embedding():
    service = Service([HIT])
    result = await rag.prepare_rag(Event(), request(), service, part_factory=Part, native_configured=True)
    assert result["outcome"] == "native_empty" and service.calls == 0


@pytest.mark.asyncio
async def test_unknown_native_format_preserves_original_context_without_retry():
    native = Part("[Related Knowledge Base Results]:\n不支持的格式：原始资料")
    service = Service([HIT])
    req = request([native])
    result = await rag.prepare_rag(Event(), req, service, part_factory=Part)
    assert result["outcome"] == "native_unparsed" and service.calls == 0
    assert req.extra_user_content_parts == [native]


@pytest.mark.asyncio
async def test_deleted_managed_native_documents_are_not_reinjected():
    class ServiceWithoutDeletedEntries(Service):
        def enrich_native_hits(self, hits):
            return []
    native = Part("[Related Knowledge Base Results]:\n【知识 1】\n来源: Warframe / wfkb-deleted.txt\n内容: 过期资料\n相关度: 0.1")
    memory = Part("本轮记忆")
    req = request([memory, native])
    result = await rag.prepare_rag(Event(), req, ServiceWithoutDeletedEntries(), part_factory=Part)
    assert result["outcome"] == "native_empty" and req.extra_user_content_parts == [memory]


@pytest.mark.asyncio
async def test_citations_only_include_used_documents_and_never_invent_links():
    event = Event()
    req = request()
    await rag.prepare_rag(event, req, Service([HIT, {"doc_name": "管理员问答", "content": "其他信息"}]), part_factory=Part)
    assert rag.decorate_answer(event, "只是陪你聊天。") == "只是陪你聊天。"
    answer = rag.decorate_answer(event, "按照资料可以制作其他战甲。[[WFKB:1]][[WFKB:99]]")
    assert "[[WFKB:" not in answer
    assert "新手指南" in answer and "管理员问答" not in answer
    assert answer.count("https://www.warframe.com") == 1
    assert rag.decorate_answer(event, answer) == answer


@pytest.mark.asyncio
async def test_context_budget_and_invalid_sources_are_bounded():
    req, event = request(), Event()
    hit = {"doc_name": "指南", "source": "javascript:alert(1)", "content": "资料" * 10000}
    await rag.prepare_rag(event, req, Service([hit]), part_factory=Part, max_context_chars=800)
    assert len(req.extra_user_content_parts[0].text) < 2000
    assert "javascript:" not in rag.decorate_answer(event, "答案[[WFKB:1]]")
