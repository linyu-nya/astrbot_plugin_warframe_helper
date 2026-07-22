from __future__ import annotations

import pytest


class _LocalizationSource:
    async def translate_display_name(self, name: str, *, language: str):
        return {
            "Saryn": "Saryn",
            "Vauban": "Vauban",
            "Lex": "雷克斯",
            "Magistar": "执法者",
        }.get(name, name)


@pytest.mark.asyncio
async def test_fetch_duviri_circuit_reads_endless_xp_schedule(
    worldstate_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = worldstate_module.WarframeWorldstateClient()
    client._public_export = _LocalizationSource()
    payload = {
        "Time": 1784505600,
        "EndlessXpSchedule": {
            "Activation": {"$date": {"$numberLong": "1784505600000"}},
            "Expiry": {"$date": {"$numberLong": "1785110400000"}},
            "CategoryChoices": [
                {"Category": "EXC_NORMAL", "Choices": ["Saryn", "Vauban"]},
                {"Category": "EXC_HARD", "Choices": ["Lex", "Magistar"]},
            ],
        },
    }

    async def fake_worldstate(**_kwargs):
        return payload

    monkeypatch.setattr(client, "_get_worldstate", fake_worldstate)

    result = await client.fetch_duviri_circuit_rewards(platform="pc", language="zh")

    assert result is not None
    assert result.normal_choices == ("Saryn", "Vauban")
    assert result.steel_choices == ("雷克斯", "执法者")
    assert result.expiry_utc is not None
    assert int(result.expiry_utc.timestamp()) == 1785110400
