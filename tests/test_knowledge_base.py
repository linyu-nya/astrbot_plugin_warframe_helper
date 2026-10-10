from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest

services_package = ModuleType("astrbot_plugin_warframe_helper.services")
services_package.__path__ = [str(Path(__file__).parents[1] / "services")]
sys.modules.setdefault("astrbot_plugin_warframe_helper.services", services_package)

from astrbot_plugin_warframe_helper.services import knowledge_base

KnowledgeService = knowledge_base.KnowledgeService
parse_knowledge_command = knowledge_base.parse_knowledge_command


@dataclass
class Doc:
    doc_id: str


class FakeKB:
    def __init__(self):
        self.docs: dict[str, str] = {}
        self.deleted: list[str] = []

    async def upload_document(self, *, file_name, file_content, file_type):
        assert file_type == "txt"
        doc_id = f"doc-{len(self.docs) + len(self.deleted) + 1}"
        self.docs[doc_id] = file_content.decode("utf-8")
        return Doc(doc_id)

    async def delete_document(self, doc_id):
        self.deleted.append(doc_id)
        self.docs.pop(doc_id)


class FakeManager:
    def __init__(self, kb):
        self.kb = kb
        self.results: list[dict] = []

    async def get_kb_by_name(self, name):
        assert name == "Warframe"
        return self.kb

    async def retrieve(self, **kwargs):
        assert kwargs["kb_names"] == ["Warframe"]
        return {"results": self.results}


@pytest.mark.asyncio
async def test_upsert_replaces_document_and_persists(tmp_path):
    kb = FakeKB()
    manager = FakeManager(kb)
    path = tmp_path / "knowledge.json"
    service = KnowledgeService(manager, "Warframe", path)

    await service.upsert("怎样开启双衍王境？", "完成相关系列任务后解锁。", "https://example.org/quest", "admin")
    first = service.get("怎样开启双衍王境")
    assert first is not None
    assert len(kb.docs) == 1
    assert "来源：https://example.org/quest" in next(iter(kb.docs.values()))

    await service.upsert("怎样开启双衍王境？", "完成双衍悖论系列任务。", "https://example.org/quest", "admin")
    assert len(kb.docs) == 1
    assert first.doc_id in kb.deleted
    assert KnowledgeService(manager, "Warframe", path).get("怎样开启双衍王境").answer == "完成双衍悖论系列任务。"


@pytest.mark.asyncio
async def test_semantic_retrieval_uses_current_managed_content_and_source(tmp_path):
    kb = FakeKB()
    manager = FakeManager(kb)
    service = KnowledgeService(manager, "Warframe", tmp_path / "knowledge.json")
    await service.upsert("Mod有什么用？", "Mod 用于强化装备。", "https://example.org/mod", "admin")
    entry = service.get("Mod有什么用")
    manager.results = [{"doc_name": entry.file_name, "doc_id": entry.doc_id, "content": "untrusted model bait"}]

    hits = await service.retrieve("怎么用卡片强化装备？", max_chunks=3)
    assert hits[0]["source"] == "https://example.org/mod"
    assert "Mod 用于强化装备。" in hits[0]["content"]
    assert "untrusted model bait" not in hits[0]["content"]
    manager.results = [{"doc_name": entry.file_name, "doc_id": "stale-doc"}]
    assert await service.retrieve("Mod有什么用？", max_chunks=3) == []


@pytest.mark.asyncio
async def test_manually_uploaded_document_is_searchable_without_local_questions(tmp_path):
    manager = FakeManager(FakeKB())
    service = KnowledgeService(manager, "Warframe", tmp_path / "knowledge.json")
    manager.results = [{"doc_name": "伤害机制.md", "doc_id": "manual-doc", "content": "病毒机制说明"}]
    assert (await service.retrieve("病毒增伤多少", max_chunks=3))[0]["content"] == "病毒机制说明"


@pytest.mark.asyncio
async def test_failed_registry_write_keeps_previous_answer(tmp_path, monkeypatch):
    kb = FakeKB()
    service = KnowledgeService(FakeManager(kb), "Warframe", tmp_path / "knowledge.json")
    original = await service.upsert("Mod 有什么用？", "强化装备。", "", "admin")
    monkeypatch.setattr(service, "_save", lambda: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        await service.upsert("Mod 有什么用？", "错误的新答案", "", "admin")
    assert service.get("Mod 有什么用？") == original
    assert original.doc_id in kb.docs


@pytest.mark.asyncio
async def test_delete_removes_document_and_answer(tmp_path):
    kb = FakeKB()
    manager = FakeManager(kb)
    service = KnowledgeService(manager, "Warframe", tmp_path / "knowledge.json")
    await service.upsert("如何获得战甲？", "通过制作获得。", "", "admin")
    doc_id = service.get("如何获得战甲").doc_id
    assert await service.delete("如何获得战甲？") is True
    assert doc_id in kb.deleted
    assert service.get("如何获得战甲") is None
    assert await service.delete("如何获得战甲") is False


def test_parse_admin_command_supports_spaces_and_source():
    assert parse_knowledge_command("圣英 Prime 怎么获得？ | 通过遗物获取 | https://example.org") == (
        "upsert", "圣英 Prime 怎么获得？", "通过遗物获取", "https://example.org"
    )
    assert parse_knowledge_command("删除 圣英 Prime 怎么获得？") == ("delete", "圣英 Prime 怎么获得？", "", "")
    assert parse_knowledge_command("查看 圣英 Prime 怎么获得？") == ("show", "圣英 Prime 怎么获得？", "", "")
    assert parse_knowledge_command("初始化") == ("seed", "", "", "")
    with pytest.raises(ValueError):
        parse_knowledge_command("问题 答案")


@dataclass
class At:
    qq: str


class Event:
    def __init__(self, text, components, *, private=False):
        self.text = text
        self.components = components
        self.private = private

    def get_message_str(self):
        return self.text

    def get_messages(self):
        return self.components

    def get_self_id(self):
        return "42"

    def is_private_chat(self):
        return self.private


def test_private_text_and_explicit_group_mention_are_handled():
    addressed_knowledge_question = knowledge_base.addressed_knowledge_question
    assert addressed_knowledge_question(Event("Mod 有什么用？", [], private=True)) == "Mod 有什么用？"
    assert addressed_knowledge_question(Event("/wk Mod", [], private=True)) is None
    assert addressed_knowledge_question(Event("", [], private=True)) is None
    assert addressed_knowledge_question(Event("Mod 有什么用？", [At("42")])) == "Mod 有什么用？"
    assert addressed_knowledge_question(Event("Mod 有什么用？", [])) is None
    assert addressed_knowledge_question(Event("Mod 有什么用？", [At("99")])) is None
    assert addressed_knowledge_question(Event("/wk Mod", [At("42")])) is None


def test_main_wires_admin_command_and_private_knowledge_route():
    source = (Path(__file__).parents[1] / "main.py").read_text(encoding="utf-8")
    assert '@filter.command("wf知识")' in source
    assert '"wf知识": self.wf_knowledge' in source
    assert "addressed_knowledge_question(event)" in source
    assert "event.is_admin()" in source
    assert '@filter.on_llm_request()' in source
    assert '@filter.on_llm_response()' in source
    start = source.index("async def wf_knowledge_rag_request(")
    end = source.index("\n    @filter.", start)
    assert "should_call_llm" not in source[start:end]
    assert "stop_event" not in source[start:end]


def test_command_replies_disable_astrbot_default_llm():
    source = (Path(__file__).parents[1] / "main.py").read_text(encoding="utf-8")
    start = source.index("def _safe_disable_llm(")
    end = source.index("\ndef _apply_proxy_config(", start)
    # AstrBot's ProcessStage invokes default AI when `not event.call_llm`.
    assert "event.should_call_llm(True)" in source[start:end]
