from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from test_knowledge_base import FakeKB, FakeManager, KnowledgeService


@pytest.mark.asyncio
async def test_topic_contains_knowledge_body_and_readable_filename(tmp_path):
    kb = FakeKB()
    service = KnowledgeService(FakeManager(kb), "Warframe", tmp_path / "entries.json")
    entry = await service.upsert_topic("第二场梦：解锁", "完成前置系列任务与接合点要求。", "https://www.warframe.com/guide", "admin", verified_at="2026-10-10")
    text = next(iter(kb.docs.values()))
    assert "标题：第二场梦：解锁" in text and "问题：" not in text
    assert "正文：完成前置" in text and "核验日期：2026-10-10" in text
    assert "第二场梦" in entry.file_name and entry.kind == "topic"
    assert KnowledgeService(service.kb_manager, "Warframe", service.path).get(entry.question).kind == "topic"


@pytest.mark.asyncio
async def test_existing_v1_question_registry_is_preserved(tmp_path):
    service = KnowledgeService(FakeManager(FakeKB()), "Warframe", tmp_path / "entries.json")
    entry = await service.upsert("旧问题", "旧答案", "", "admin")
    legacy = {key: value for key, value in asdict(entry).items() if key in {"question", "answer", "source", "editor", "updated_at", "file_name", "doc_id"}}
    service.path.write_text(json.dumps({"version": 1, "entries": {"旧问题": legacy}}), encoding="utf-8")
    restored = KnowledgeService(service.kb_manager, "Warframe", service.path)
    assert restored.get("旧问题").answer == "旧答案"
    await restored.upsert_topic("新主题", "新内容", "", "admin")
    assert restored.get("旧问题").kind == "qa"


@pytest.mark.asyncio
async def test_pack_import_is_idempotent_and_protects_admin_edits(tmp_path):
    service = KnowledgeService(FakeManager(FakeKB()), "Warframe", tmp_path / "entries.json")
    pack = {"id": "test.pack", "version": "1", "documents": [{"title": "初始战甲", "content": "初始选择可改变。", "source": "https://www.warframe.com/guide", "verified_at": "2026-10-10"}]}
    assert (await service.import_pack(pack, "admin"))["added"] == 1
    assert (await service.import_pack(pack, "admin"))["skipped"] == 1
    pack["version"] = "2"
    pack["documents"][0]["content"] = "新版本内容。"
    assert (await service.import_pack(pack, "admin"))["updated"] == 1
    await service.upsert_topic("初始战甲", "管理员自定义。", "", "admin")
    assert (await service.import_pack(pack, "admin"))["skipped"] == 1
    assert service.get("初始战甲").answer == "管理员自定义。"


@pytest.mark.asyncio
async def test_bulk_markdown_import_extracts_metadata_and_reports_bad_files(tmp_path):
    service = KnowledgeService(FakeManager(FakeKB()), "Warframe", tmp_path / "entries.json")
    folder = tmp_path / "knowledge_import"
    folder.mkdir()
    (folder / "mod.md").write_text("# Mod 容量\n\n容量决定可安装的 Mod 消耗总量。\n\n来源：https://www.warframe.com/guide\n核验日期：2026-10-10\n适用范围：国际服\n", encoding="utf-8")
    (folder / "broken.md").write_bytes(b"\xff\xfe")
    result = await service.import_directory(folder, "admin")
    assert result["added"] == 1 and result["failed"] == 1
    entry = service.get("Mod 容量")
    assert entry.answer == "容量决定可安装的 Mod 消耗总量。"
    assert entry.source == "https://www.warframe.com/guide" and entry.applies_to == "国际服"


@pytest.mark.asyncio
async def test_topic_retrieval_preserves_matched_chunk_and_native_source_metadata(tmp_path):
    manager = FakeManager(FakeKB())
    service = KnowledgeService(manager, "Warframe", tmp_path / "entries.json")
    entry = await service.upsert_topic("长篇机制", "前文\n" * 500 + "末段知识。", "https://www.warframe.com/guide", "admin")
    manager.results = [{"doc_name": entry.file_name, "doc_id": entry.doc_id, "content": "末段知识。"}]
    assert (await service.retrieve("末段机制", max_chunks=3))[0]["content"] == "末段知识。"
    native = service.enrich_native_hits([{"doc_name": "Warframe / " + entry.file_name, "content": "末段知识。"}])
    assert native[0]["source"] == entry.source and native[0]["doc_name"] == "长篇机制"


@pytest.mark.asyncio
async def test_pack_failure_preserves_partial_progress_and_can_resume(tmp_path):
    class UnstableKB(FakeKB):
        async def upload_document(self, **kwargs):
            if len(self.docs) == 1:
                raise RuntimeError("HTTP 410")
            return await super().upload_document(**kwargs)
    service = KnowledgeService(FakeManager(UnstableKB()), "Warframe", tmp_path / "entries.json")
    pack = {"id": "test", "version": "1", "documents": [{"title": f"主题{i}", "content": "内容", "source": ""} for i in range(3)]}
    result = await service.import_pack(pack, "admin")
    assert result["added"] == 1 and result["failed"] == 1 and result["pending"] == 1
    assert service.get("主题0") is not None


@pytest.mark.asyncio
async def test_changing_knowledge_base_does_not_delete_old_library_document(tmp_path):
    path = tmp_path / "entries.json"
    old_kb = FakeKB()
    old = KnowledgeService(FakeManager(old_kb), "Warframe", path)
    original = await old.upsert_topic("主题", "旧资料", "", "admin")
    new_kb = FakeKB()
    class NewManager(FakeManager):
        async def get_kb_by_name(self, name):
            return self.kb
    new = KnowledgeService(NewManager(new_kb), "Warframe-v2", path)
    await new.upsert_topic("主题", "新资料", "", "admin")
    assert original.doc_id in old_kb.docs
    assert new_kb.deleted == []


def test_topic_commands_accept_body_with_spaces():
    from astrbot_plugin_warframe_helper.services.knowledge_base import parse_knowledge_command
    assert parse_knowledge_command("收录 Mod 容量 | Mod 占用装备容量。 | https://www.warframe.com/guide") == ("topic", "Mod 容量", "Mod 占用装备容量。", "https://www.warframe.com/guide")
    assert parse_knowledge_command("状态")[0] == "status"
    assert parse_knowledge_command("资料包")[0] == "pack"
    assert parse_knowledge_command("导入")[0] == "import"
    assert parse_knowledge_command("测试 病毒增伤多少")[0:2] == ("probe", "病毒增伤多少")
