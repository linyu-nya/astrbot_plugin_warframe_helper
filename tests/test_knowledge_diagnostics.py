from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def load_module():
    spec = importlib.util.spec_from_file_location("wf_diagnostics", Path(__file__).parents[1] / "services" / "knowledge_diagnostics.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_monitor_separates_native_parsing_from_retrieval_latency_and_sessions():
    module = load_module()
    monitor = module.KnowledgeRagMonitor(max_sessions=2)
    for index in range(1, 21):
        monitor.record("group", {"outcome": "injected", "chunks": 2, "elapsed_ms": index * 10})
    monitor.record("private", {"outcome": "native_reused", "chunks": 1, "elapsed_ms": 0})
    monitor.record_response("private", {"citations_used": 1})
    result = monitor.summary("private")
    assert result["samples"] == 20 and result["p50_ms"] == 100 and result["p95_ms"] == 190
    assert result["last"]["outcome"] == "native_reused" and result["last"]["citations_used"] == 1
    assert monitor.summary("group")["last"]["elapsed_ms"] == 200
    monitor.record("other", {"outcome": "empty", "chunks": 0, "elapsed_ms": 50})
    assert monitor.summary("group")["last"] is None


def test_status_formatter_never_calls_successful_candidates_embedding_success():
    module = load_module()
    text = module.format_status(
        {"name": "Warframe", "managed_count": 22, "topic_count": 20, "documents": 25, "chunks": 40, "embedding_provider_id": "nvidia-wf", "embedding_model": "nvidia/nemotron-3-embed-1b", "embedding_dimensions": 2048, "input_type": "passage", "ready": True},
        {"last": {"outcome": "native_reused", "chunks": 1, "elapsed_ms": 0, "citations_used": 1}, "samples": 0},
        {"enabled": True, "private_enabled": True},
    )
    assert "Warframe" in text and "nvidia/nemotron-3-embed-1b" in text
    assert "解析" in text and "原生检索耗时未测" in text
    assert "向量检索成功" not in text and "input_type=passage" in text


@pytest.mark.asyncio
async def test_retrieval_evaluation_reports_topic_recall_separately_from_chat_candidates():
    module = load_module()
    class Service:
        async def retrieve(self, query, *, max_chunks):
            if query == "报错":
                raise RuntimeError("failed")
            return [{"doc_name": "Mod 容量"}]
    cases = [{"query": "卡槽空着为什么装不进去", "expected_titles": ["Mod 容量"]}, {"query": "你好", "expected_titles": []}, {"query": "报错", "expected_titles": ["初始战甲"]}]
    result = await module.evaluate_retrieval(Service(), cases)
    assert result["positive_hits"] == 1 and result["positive_count"] == 2
    assert result["chat_candidates"] == 1 and result["errors"] == 1
    assert len(result["details"]) == 3
