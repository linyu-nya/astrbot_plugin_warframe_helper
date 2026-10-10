from __future__ import annotations

import json
import zipfile
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).parents[1]


def test_pack_has_unique_reviewed_topics_and_evaluation_covers_every_topic():
    pack = json.loads((ROOT / "assets/knowledge/starter_topics_zh.json").read_text(encoding="utf-8"))
    cases = json.loads((ROOT / "assets/knowledge/evaluation_questions_zh.json").read_text(encoding="utf-8"))
    docs = pack["documents"]
    assert 40 <= len(docs) <= 50
    assert len({doc["id"] for doc in docs}) == len(docs)
    titles = {doc["title"] for doc in docs}
    assert len(titles) == len(docs)
    covered = {title for case in cases for title in case["expected_titles"]}
    assert covered == titles and any(not case["expected_titles"] for case in cases)
    for doc in docs:
        assert doc["content"].strip() and "问题：" not in doc["content"]
        assert urlsplit(doc["source"]).hostname in {"www.warframe.com", "support.warframe.com"}
        date.fromisoformat(doc.get("verified_at", pack["verified_at"]))


def test_topics_have_substantive_sections_not_link_only_summaries():
    pack = json.loads((ROOT / "assets/knowledge/starter_topics_zh.json").read_text(encoding="utf-8"))
    assert pack["id"] == "warframe.official.starter.zh"
    assert pack["version"] != "2026-10-10.1"
    assert sum(len(doc["content"]) for doc in pack["documents"]) >= 12000
    for doc in pack["documents"]:
        assert 240 <= len(doc["content"]) <= 16000, doc["title"]
        assert doc["content"].count("## ") >= 3, doc["title"]


def test_export_keeps_complete_topic_body_and_sources(tmp_path):
    from scripts.export_knowledge_pack import export

    output = tmp_path / "topics.zip"
    assert export(output) == 0
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        pack = json.loads(archive.read("manifest.json"))
        names = [name for name in archive.namelist() if name.endswith(".md")]
        assert len(names) == len(pack["documents"])
        for doc in pack["documents"]:
            name = next(name for name in names if name.startswith(doc["id"] + "-"))
            text = archive.read(name).decode("utf-8")
            assert doc["content"] in text
            assert "来源：" + doc["source"] in text
