from __future__ import annotations

import math
import asyncio
import time
from collections import OrderedDict, deque
from datetime import datetime, timezone


class KnowledgeRagMonitor:
    def __init__(self, max_sessions: int = 128):
        self.max_sessions = max_sessions
        self.sessions = OrderedDict()
        self.samples = deque(maxlen=200)

    def record(self, session: str, stats: dict) -> None:
        stored = {key: stats[key] for key in ("outcome", "chunks", "elapsed_ms", "error_type", "citations_used") if key in stats}
        stored["at"] = datetime.now(timezone.utc).isoformat()
        self.sessions.pop(session, None)
        self.sessions[session] = stored
        while len(self.sessions) > self.max_sessions:
            self.sessions.popitem(last=False)
        if stored.get("outcome") in {"injected", "empty", "error", "timeout", "probe"}:
            self.samples.append(float(stored.get("elapsed_ms", 0)))

    def record_response(self, session: str, stats: dict) -> None:
        if session in self.sessions:
            self.sessions[session]["citations_used"] = int(stats.get("citations_used", 0))

    def summary(self, session: str) -> dict:
        samples = sorted(self.samples)
        result = {"last": dict(self.sessions[session]) if session in self.sessions else None, "samples": len(samples)}
        if samples:
            result.update(p50_ms=samples[math.ceil(len(samples) * .5) - 1], p95_ms=samples[math.ceil(len(samples) * .95) - 1])
        return result


async def evaluate_retrieval(service, cases: list[dict], *, timeout_sec=5.0, record=None) -> dict:
    result = {"positive_count": 0, "positive_hits": 0, "chat_candidates": 0, "errors": 0, "details": []}
    latencies = []
    for case in cases[:40]:
        expected = set(case.get("expected_titles", []))
        result["positive_count"] += bool(expected)
        started = time.perf_counter()
        error = ""
        try:
            hits = await asyncio.wait_for(service.retrieve(case["query"], max_chunks=3), timeout=timeout_sec)
        except Exception as exc:
            hits, error = [], type(exc).__name__
            result["errors"] += 1
        elapsed = round((time.perf_counter() - started) * 1000)
        latencies.append(elapsed)
        titles = [str(hit.get("doc_name") or "") for hit in hits]
        if expected:
            result["positive_hits"] += bool(expected.intersection(titles))
        else:
            result["chat_candidates"] += bool(hits)
        result["details"].append({"query": case["query"], "titles": titles, "elapsed_ms": elapsed, "error_type": error})
        if record:
            record({"outcome": "probe" if not error else "timeout" if error == "TimeoutError" else "error", "chunks": len(hits), "elapsed_ms": elapsed, "error_type": error})
    ordered = sorted(latencies)
    result["p50_ms"] = ordered[math.ceil(len(ordered) * .5) - 1] if ordered else 0
    result["p95_ms"] = ordered[math.ceil(len(ordered) * .95) - 1] if ordered else 0
    return result


def format_status(details: dict, monitoring: dict, settings: dict, *, agentic=False, native_configured=False) -> str:
    lines = [
        f"WF 知识状态：{details['name']}",
        f"RAG：{'开' if settings.get('enabled', True) else '关'}；私聊：{'开' if settings.get('private_enabled', True) else '关'}",
        f"索引：{'可用' if details.get('ready') else '不可用'}；文档 {details.get('documents') if details.get('documents') is not None else '未知'}，分块 {details.get('chunks') if details.get('chunks') is not None else '未知'}",
        f"插件管理 {details['managed_count']} 条，其中主题资料 {details['topic_count']} 条",
        f"Embedding：{details.get('embedding_provider_id') or '未知'} / {details.get('embedding_model') or '未知'}",
    ]
    if details.get("embedding_dimensions"):
        lines.append(f"向量维度：{details['embedding_dimensions']}")
    if details.get("input_type"):
        lines.append(f"提供商 input_type={details['input_type']}")
    lines.append(f"Rerank：{details.get('rerank_provider_id') or '未配置'}")
    lines.append("模式：Agentic（插件自动 RAG 已避让）" if agentic else "模式：复用原生自动检索" if native_configured else "模式：插件自动检索")
    last = monitoring.get("last")
    if last:
        lines.append(f"本会话最近一次：{last['outcome']}；片段 {last.get('chunks', 0)}；引用 {last.get('citations_used', 0)}")
        timing = "解析" if last["outcome"].startswith("native_") else "处理"
        lines.append(f"{timing}耗时：{last.get('elapsed_ms', 0)} ms" + ("（原生检索耗时未测）" if timing == "解析" else ""))
    else:
        lines.append("本会话尚无 RAG 记录；插件重载会清空诊断统计。")
    count = monitoring.get("samples", 0)
    if count:
        lines.append(f"直接检索最近 {count} 个样本：P50 {monitoring['p50_ms']:.0f} ms / P95 {monitoring['p95_ms']:.0f} ms")
    else:
        lines.append("尚无插件直接检索耗时样本。")
    return "\n".join(lines)
