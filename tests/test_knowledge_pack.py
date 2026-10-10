from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).parents[1]


def test_pack_has_unique_reviewed_topics_and_evaluation_covers_every_topic():
    pack = json.loads((ROOT / "assets/knowledge/starter_topics_zh.json").read_text(encoding="utf-8"))
    cases = json.loads((ROOT / "assets/knowledge/evaluation_questions_zh.json").read_text(encoding="utf-8"))
    docs = pack["documents"]
    assert 20 <= len(docs) <= 30
    assert len({doc["id"] for doc in docs}) == len(docs)
    titles = {doc["title"] for doc in docs}
    assert len(titles) == len(docs)
    covered = {title for case in cases for title in case["expected_titles"]}
    assert covered == titles and any(not case["expected_titles"] for case in cases)
    for doc in docs:
        assert doc["content"].strip() and "问题：" not in doc["content"]
        assert urlsplit(doc["source"]).hostname == "www.warframe.com"
        date.fromisoformat(doc.get("verified_at", pack["verified_at"]))
