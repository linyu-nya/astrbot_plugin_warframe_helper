from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
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
    kind: str = "qa"
    verified_at: str = ""
    applies_to: str = ""
    pack_id: str = ""
    pack_version: str = ""
    kb_name: str = ""

    def document_text(self) -> str:
        labels = ("标题", "正文") if self.kind == "topic" else ("问题", "答案")
        text = f"{labels[0]}：{self.question}\n{labels[1]}：{self.answer}"
        for label, value in (("来源", self.source), ("核验日期", self.verified_at), ("适用范围", self.applies_to)):
            if value:
                text += f"\n{label}：{value}"
        return text


def parse_knowledge_command(raw: str) -> tuple[str, str, str, str]:
    raw = raw.strip()
    for prefix, action in (("删除 ", "delete"), ("查看 ", "show"), ("测试 ", "probe")):
        if raw.startswith(prefix):
            question = raw[len(prefix):].strip()
            if not question:
                raise ValueError("请提供问题。")
            return action, question, "", ""
    actions = {"列表": "list", "初始化": "seed", "状态": "status", "资料包": "pack", "导入资料包": "pack", "导入": "import", "评测": "evaluate"}
    if raw in actions:
        return actions[raw], "", "", ""
    action = "upsert"
    if raw.startswith("收录 "):
        raw, action = raw[3:].strip(), "topic"
    if raw.startswith("添加 "):
        raw = raw[3:].strip()
    parts = [part.strip() for part in raw.replace("｜", "|").split("|", 2)]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise ValueError("用法：wf知识 问题 | 答案 | 来源链接（可选）")
    question, answer = parts[:2]
    source = parts[2] if len(parts) > 2 else ""
    if len(question) > 200 or len(answer) > (16000 if action == "topic" else 3000):
        raise ValueError("标题或问题最多 200 字；问答最多 3000 字，主题正文最多 16000 字。")
    if source:
        parsed = urlparse(source)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("来源需填写完整的 HTTP(S) 链接。")
    return action, question, answer, source


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
    """Keep managed questions and topic documents synchronized with AstrBot."""

    def __init__(self, kb_manager: object, kb_name: str, path: Path):
        self.kb_manager = kb_manager
        self.kb_name = kb_name.strip()
        self.path = Path(path)
        self._lock = asyncio.Lock()
        self._entries: dict[str, KnowledgeEntry] = {}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._entries = {
                key: KnowledgeEntry(**{**entry, "kb_name": entry.get("kb_name", data.get("kb_name", ""))})
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
        payload = {"version": 2, "kb_name": self.kb_name, "entries": {key: asdict(entry) for key, entry in self._entries.items()}}
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)

    async def upsert(self, question: str, answer: str, source: str, editor: str) -> KnowledgeEntry:
        return await self._upsert(question, answer, source, editor)

    async def upsert_topic(self, title: str, content: str, source: str, editor: str, *, verified_at="", applies_to="", pack_id="", pack_version="") -> KnowledgeEntry:
        return await self._upsert(title, content, source, editor, kind="topic", verified_at=verified_at, applies_to=applies_to, pack_id=pack_id, pack_version=pack_version)

    async def _upsert(self, question: str, answer: str, source: str, editor: str, *, kind="qa", verified_at="", applies_to="", pack_id="", pack_version="") -> KnowledgeEntry:
        question, answer, source = question.strip(), answer.strip(), source.strip()
        key = normalize_question(question)
        if not key or not answer or len(question) > 200 or len(answer) > 16000:
            raise ValueError("标题和正文不能为空，标题最多 200 字，正文最多 16000 字。")
        if source:
            parsed = urlparse(source)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or any(c.isspace() for c in source):
                raise ValueError("来源需填写完整的 HTTP(S) 链接。")
        if verified_at:
            datetime.fromisoformat(verified_at)
        async with self._lock:
            kb = await self._kb()
            old = self._entries.get(key)
            file_name = f"wfkb-{hashlib.sha256(key.encode()).hexdigest()[:20]}.txt"
            if kind == "topic":
                readable = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", question)[:50].strip(" .")
                file_name = f"wfkb-{readable}-{hashlib.sha256(key.encode()).hexdigest()[:12]}.txt"
            entry = KnowledgeEntry(question, answer, source, editor, datetime.now(timezone.utc).isoformat(), file_name, "", kind, verified_at, applies_to, pack_id, pack_version, kb_name=self.kb_name)
            doc = await kb.upload_document(
                file_name=file_name,
                file_content=entry.document_text().encode("utf-8"),
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
                    kind=kind,
                    verified_at=verified_at,
                    applies_to=applies_to,
                    pack_id=pack_id,
                    pack_version=pack_version,
                    kb_name=self.kb_name,
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
                    await self._delete_owned_document(kb, old)
                except Exception:
                    _LOGGER.warning("Old knowledge document could not be removed: %s", old.doc_id, exc_info=True)
            return entry

    async def _delete_owned_document(self, kb, entry: KnowledgeEntry) -> None:
        if entry.kb_name and entry.kb_name != self.kb_name:
            return
        metadata = getattr(kb, "kb", None)
        if metadata is not None and hasattr(kb, "get_document"):
            document = await kb.get_document(entry.doc_id)
            if document is None or getattr(document, "kb_id", None) != getattr(metadata, "kb_id", None):
                return
        await kb.delete_document(entry.doc_id)

    async def import_pack(self, pack: dict, editor: str) -> dict:
        report = {"added": 0, "updated": 0, "skipped": 0, "failed": 0, "pending": 0}
        for index, document in enumerate(pack["documents"]):
            existing = self.get(document["title"])
            if existing and (existing.pack_id != pack["id"] or (existing.pack_version == pack["version"] and existing.answer == document["content"] and existing.source == document["source"] and existing.kb_name in {"", self.kb_name})):
                report["skipped"] += 1
                continue
            try:
                await self.upsert_topic(document["title"], document["content"], document["source"], editor, verified_at=document.get("verified_at", pack.get("verified_at", "")), applies_to=document.get("applies_to", pack.get("applies_to", "")), pack_id=pack["id"], pack_version=pack["version"])
            except Exception:
                report["failed"] += 1
                report["pending"] = len(pack["documents"]) - index - 1
                _LOGGER.warning("Knowledge pack import interrupted: %s", document["title"], exc_info=True)
                break
            report["updated" if existing else "added"] += 1
        return report

    async def import_directory(self, directory: Path, editor: str) -> dict:
        directory.mkdir(parents=True, exist_ok=True)
        report = {"added": 0, "updated": 0, "skipped": 0, "failed": 0}
        files = sorted(path for path in directory.iterdir() if path.suffix.lower() in {".md", ".txt"})
        if len(files) > 50:
            raise ValueError("每次最多导入 50 个 Markdown 或文本文件。")
        for path in files:
            try:
                if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(directory.resolve()) or path.stat().st_size > 256 * 1024:
                    raise ValueError("导入文件超出允许范围。")
                lines = path.read_text(encoding="utf-8-sig").splitlines()
                title = path.stem
                if lines and lines[0].startswith("# "):
                    title = lines.pop(0)[2:].strip()
                metadata = {"source": "", "verified_at": "", "applies_to": ""}
                body = []
                for line in lines:
                    match = re.match(r"^(来源|核验日期|适用范围)[：:]\s*(.*)$", line)
                    if match:
                        metadata[{"来源": "source", "核验日期": "verified_at", "适用范围": "applies_to"}[match.group(1)]] = match.group(2).strip()
                    else:
                        body.append(line)
                existing = self.get(title)
                await self.upsert_topic(title, "\n".join(body).strip(), metadata.pop("source"), editor, **metadata)
                report["updated" if existing else "added"] += 1
            except Exception:
                report["failed"] += 1
                _LOGGER.warning("Knowledge file import failed: %s", path.name, exc_info=True)
        return report

    async def status(self) -> dict:
        kb = await self._kb()
        metadata = getattr(kb, "kb", None)
        result = {"name": self.kb_name, "managed_count": len(self._entries), "topic_count": sum(e.kind == "topic" for e in self._entries.values()), "documents": getattr(metadata, "doc_count", None), "chunks": getattr(metadata, "chunk_count", None), "embedding_provider_id": getattr(metadata, "embedding_provider_id", ""), "rerank_provider_id": getattr(metadata, "rerank_provider_id", ""), "ready": not bool(getattr(kb, "init_error", None))}
        if hasattr(kb, "get_ep"):
            try:
                provider = await kb.get_ep()
                result["embedding_model"] = provider.get_model()
                result["embedding_dimensions"] = provider.get_dim()
                result["input_type"] = getattr(provider, "input_type", "")
            except Exception:
                result["ready"] = False
        return result

    def enrich_native_hits(self, hits: list[dict]) -> list[dict]:
        by_file = {entry.file_name: entry for entry in self._entries.values()}
        results = []
        for hit in hits:
            filename = str(hit.get("doc_name") or "").rsplit(" / ", 1)[-1]
            entry = by_file.get(filename)
            if entry:
                hit = {**hit, "doc_name": entry.question, "source": entry.source}
                if entry.kind == "qa":
                    hit["content"] = entry.document_text()
            elif filename.startswith("wfkb-"):
                continue
            results.append(hit)
        return results

    async def delete(self, question: str) -> bool:
        key = normalize_question(question)
        async with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return False
            kb = await self._kb()
            await self._delete_owned_document(kb, entry)
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
                content = hit.get("content") if entry.kind == "topic" else entry.document_text()
                hit = {**hit, "doc_name": entry.question, "content": content, "source": entry.source}
            if str(hit.get("content") or "").strip():
                hits.append(hit)
        return hits[:max_chunks]
