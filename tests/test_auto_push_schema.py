from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_auto_push_configuration_is_exposed() -> None:
    schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8-sig"))

    config = schema["auto_push"]
    assert config["type"] == "object"
    assert config["items"]["enabled"]["default"] is True
    assert config["items"]["poll_interval_sec"]["default"] == 60

