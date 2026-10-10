from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


class KnowledgeUnavailable(RuntimeError):
    pass


_LOGGER = logging.getLogger(__name__)


def normalize_question(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return "".join(char for char in value if char.isalnum())


@dataclass(frozen=True)
class KnowledgeEntry:
    question: str
    answer: str
    source: str
    editor: str
    updated_at: str
    file_name: str
    doc_id: str


def parse_knowledge_command(raw: str) -> tuple[str, str, str, str]:
    raw = raw.strip()
    for prefix, action in (("删除 ", "delete"), ("查看 ", "show")):
        if raw.startswith(prefix):
            question = raw[len(prefix):].strip()
            if not question:
                raise ValueError("请提供问题。")
            return action, question, "", ""
    if raw == "列表":
        return "list", "", "", ""
    if raw == "初始化":
        return "seed", "", "", ""
    if raw.startswith("添加 "):
        raw = raw[3:].strip()
    parts = [part.strip() for part in raw.replace("｜", "|").split("|", 2)]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise ValueError("用法：wf知识 问题 | 答案 | 来源链接（可选）")
    question, answer = parts[:2]
    source = parts[2] if len(parts) > 2 else ""
    if len(question) > 200 or len(answer) > 3000:
        raise ValueError("问题最多 200 字，答案最多 3000 字。")
    if source:
        parsed = urlparse(source)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("来源需填写完整的 HTTP(S) 链接。")
    return "upsert", question, answer, source


def addressed_knowledge_question(event: object) -> str | None:
    question = (event.get_message_str() or "").strip()
    if not question or question.startswith("/"):
        return None
    if event.is_private_chat():
        return question
    self_id = str(event.get_self_id() or "")
    if not self_id:
        return None
    for component in event.get_messages() or []:
        if type(component).__name__ == "At" and str(getattr(component, "qq", "")) == self_id:
            return question
    return None


class KnowledgeService:
    """Keep a small, audited Q&A registry synchronized with AstrBot's KB."""

    def __init__(self, kb_manager: object, kb_name: str, path: Path):
        self.kb_manager = kb_manager
        self.kb_name = kb_name.strip()
        self.path = Path(path)
        self._lock = asyncio.Lock()
        self._entries: dict[str, KnowledgeEntry] = {}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._entries = {
                key: KnowledgeEntry(**entry)
                for key, entry in data.get("entries", {}).items()
            }

    def get(self, question: str) -> KnowledgeEntry | None:
        return self._entries.get(normalize_question(question))

    def list_entries(self) -> list[KnowledgeEntry]:
        return sorted(self._entries.values(), key=lambda entry: entry.question)

    async def _kb(self):
        if not self.kb_name or self.kb_manager is None:
            raise KnowledgeUnavailable("请先在 AstrBot 中创建并配置 Warframe 知识库。")
        kb = await self.kb_manager.get_kb_by_name(self.kb_name)
        if kb is None:
            raise KnowledgeUnavailable(f"找不到 AstrBot 知识库：{self.kb_name}")
        return kb

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "entries": {key: asdict(entry) for key, entry in self._entries.items()}}
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    async def upsert(self, question: str, answer: str, source: str, editor: str) -> KnowledgeEntry:
        key = normalize_question(question)
        if not key:
            raise ValueError("问题不能为空。")
        async with self._lock:
            kb = await self._kb()
            old = self._entries.get(key)
            file_name = f"wfkb-{hashlib.sha256(key.encode()).hexdigest()[:20]}.txt"
            content = f"问题：{question}\n答案：{answer}"
            if source:
                content += f"\n来源：{source}"
            doc = await kb.upload_document(
                file_name=file_name,
                file_content=content.encode("utf-8"),
                file_type="txt",
            )
            entry = KnowledgeEntry(
                question=question,
                answer=answer,
                source=source,
                editor=editor,
                updated_at=datetime.now(timezone.utc).isoformat(),
                file_name=file_name,
                doc_id=str(doc.doc_id),
            )
            try:
                self._entries[key] = entry
                self._save()
            except Exception:
                if old is None:
                    self._entries.pop(key, None)
                else:
                    self._entries[key] = old
                await kb.delete_document(str(doc.doc_id))
                raise
            if old is not None:
                try:
                    await kb.delete_document(old.doc_id)
                except Exception:
                    _LOGGER.warning("Old knowledge document could not be removed: %s", old.doc_id, exc_info=True)
            return entry

    async def delete(self, question: str) -> bool:
        key = normalize_question(question)
        async with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return False
            kb = await self._kb()
            await kb.delete_document(entry.doc_id)
            del self._entries[key]
            self._save()
            return True

    async def retrieve(self, question: str, *, max_chunks: int = 3) -> list[dict]:
        kb = await self._kb()
        if getattr(kb, "init_error", None):
            raise KnowledgeUnavailable("AstrBot 知识库索引不可用。")
        metadata = getattr(kb, "kb", None)
        if metadata is not None and getattr(metadata, "doc_count", None) == 0 and getattr(metadata, "chunk_count", None) == 0:
            return []
        result = await self.kb_manager.retrieve(
            query=question,
            kb_names=[self.kb_name],
            top_k_fusion=10,
            top_m_final=max_chunks,
        )
        if not isinstance(result, dict):
            return []
        hits = []
        candidates = {entry.file_name: entry for entry in self._entries.values()}
        for hit in result.get("results", []):
            if not isinstance(hit, dict):
                continue
            file_name = str(hit.get("doc_name") or "")
            if file_name.startswith("wfkb-"):
                entry = candidates.get(file_name)
                if entry is None or str(hit.get("doc_id")) != entry.doc_id:
                    continue
                hit = {**hit, "doc_name": entry.question, "content": f"问题：{entry.question}\n答案：{entry.answer}", "source": entry.source}
            if str(hit.get("content") or "").strip():
                hits.append(hit)
        return hits[:max_chunks]
