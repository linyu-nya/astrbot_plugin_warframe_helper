# Fissure Tier Sorting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make fissure replies sort by `古纪 -> 前纪 -> 中纪 -> 后纪 -> 安魂 -> 全能` by default, with an AstrBot configuration switch that restores ETA-only sorting.

**Architecture:** Add a focused `services/fissure_sorting.py` module that owns tier aliases, configuration parsing, and the shared sort operation. Parse the switch once in `WarframeHelperPlugin`, pass it through `worldstate_commands`, and use the shared operation in both text and image rendering paths.

**Tech Stack:** Python 3.12, AstrBot plugin configuration schema, pytest

---

## File Structure

- Create `services/fissure_sorting.py`: tier ranking, safe configuration parsing, and shared fissure sorting.
- Create `tests/test_fissure_sorting.py`: behavior tests for tier order, ETA tie-breaking, unknown tiers, and disabled mode.
- Create `tests/test_fissure_sorting_schema.py`: schema default and menu metadata test.
- Create `tests/test_fissure_sorting_wiring.py`: command and renderer configuration propagation tests.
- Modify `services/fissures.py`: replace duplicated ETA sorts with the shared sorter.
- Modify `services/worldstate_commands.py`: carry the parsed switch to both rendering paths.
- Modify `main.py`: parse the switch once and pass it for all four fissure commands.
- Modify `_conf_schema.json`: expose the boolean menu switch with a default of `true`.
- Modify `README.md` and `CHANGELOG.md`: document the new default and compatibility switch.

### Task 1: Shared Fissure Sorting

**Files:**
- Create: `services/fissure_sorting.py`
- Create: `tests/test_fissure_sorting.py`

- [ ] **Step 1: Write failing ordering tests**

Create simple fissure-shaped test values and assert the desired public API:

```python
from dataclasses import dataclass

from astrbot_plugin_warframe_helper.services.fissure_sorting import sort_fissures


@dataclass(frozen=True)
class Fissure:
    tier: str
    eta: str


def test_tier_first_sort_uses_canonical_order_and_eta_within_tier():
    rows = [
        Fissure("全能", "1分"),
        Fissure("古纪", "9分"),
        Fissure("前纪", "4分"),
        Fissure("古纪", "2分"),
        Fissure("安魂", "3分"),
        Fissure("后纪", "5分"),
        Fissure("中纪", "6分"),
    ]

    sorted_rows = sort_fissures(rows, tier_first=True)

    assert [(row.tier, row.eta) for row in sorted_rows] == [
        ("古纪", "2分"),
        ("古纪", "9分"),
        ("前纪", "4分"),
        ("中纪", "6分"),
        ("后纪", "5分"),
        ("安魂", "3分"),
        ("全能", "1分"),
    ]
```

Add separate tests proving English/code aliases receive the same ranks and `tier_first=False` sorts only by ETA. The unknown-tier test must contain at least two unknown values in reverse ETA order:

```python
def test_unknown_tiers_follow_known_tiers_and_sort_by_eta():
    rows = [
        Fissure("新纪元B", "8分"),
        Fissure("古纪", "9分"),
        Fissure("新纪元A", "2分"),
    ]

    sorted_rows = sort_fissures(rows, tier_first=True)

    assert [(row.tier, row.eta) for row in sorted_rows] == [
        ("古纪", "9分"),
        ("新纪元A", "2分"),
        ("新纪元B", "8分"),
    ]
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
& '..\..\.venv\Scripts\python.exe' -m pytest tests/test_fissure_sorting.py -q
```

Expected: collection fails because `services.fissure_sorting` does not exist.

- [ ] **Step 3: Implement the minimal sorting module**

Create `services/fissure_sorting.py` with a protocol-based API so tests do not depend on network clients:

```python
from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, TypeVar

from ..helpers import eta_key_zh


class FissureLike(Protocol):
    tier: str
    eta: str


FissureT = TypeVar("FissureT", bound=FissureLike)

_TIER_ORDER = (
    ("古纪", "lith", "voidt1"),
    ("前纪", "meso", "voidt2"),
    ("中纪", "neo", "voidt3"),
    ("后纪", "axi", "voidt4"),
    ("安魂", "requiem", "voidt5"),
    ("全能", "omnia", "voidt6"),
)
_TIER_RANK = {
    alias.casefold(): rank
    for rank, aliases in enumerate(_TIER_ORDER)
    for alias in aliases
}


def sort_fissures(
    fissures: Iterable[FissureT], *, tier_first: bool
) -> list[FissureT]:
    if not tier_first:
        return sorted(fissures, key=lambda fissure: eta_key_zh(fissure.eta))
    return sorted(
        fissures,
        key=lambda fissure: (
            _TIER_RANK.get(fissure.tier.strip().casefold(), len(_TIER_ORDER)),
            eta_key_zh(fissure.eta),
        ),
    )
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Task 1 pytest command again.

Expected: all tests in `test_fissure_sorting.py` pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add services/fissure_sorting.py tests/test_fissure_sorting.py
git commit -m "新增：统一裂缝纪元排序规则"
```

### Task 2: Configuration Menu and Command Wiring

**Files:**
- Create: `tests/test_fissure_sorting_schema.py`
- Create: `tests/test_fissure_sorting_wiring.py`
- Modify: `_conf_schema.json`
- Modify: `main.py`
- Modify: `services/worldstate_commands.py`
- Modify: `services/fissures.py`

- [ ] **Step 1: Write failing configuration and rendering-path tests**

Test schema exposure and parser defaults:

```python
def test_fissure_sort_schema_defaults_to_tier_first():
    schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
    field = schema["fissure_tier_sort_enabled"]
    assert field["type"] == "bool"
    assert field["default"] is True
    assert field["description"].strip()
    assert field["hint"].strip()


def test_fissure_sort_config_defaults_true_and_allows_false():
    assert fissure_tier_sort_enabled(None) is True
    assert fissure_tier_sort_enabled({}) is True
    assert fissure_tier_sort_enabled({"fissure_tier_sort_enabled": False}) is False
```

Add `tests/test_fissure_sorting_wiring.py`. Follow the existing AST-based wiring test pattern in `tests/test_main_background_wiring.py` to make all four command-entry expectations directly executable:

```python
@pytest.mark.parametrize(
    "method_name",
    ["wf_fissures", "wf_fissures_normal", "wf_fissures_hard", "wf_fissures_storm"],
)
def test_every_fissure_command_passes_configured_sort_mode(method_name: str):
    source = ast.unparse(_plugin_method(method_name))
    assert "tier_first=self._fissure_tier_sort_enabled" in source


@pytest.mark.parametrize("function_name", ["cmd_fissures", "cmd_fissures_kind"])
def test_worldstate_commands_forward_sort_mode_to_image_and_text(function_name: str):
    source = ast.unparse(_module_function("services/worldstate_commands.py", function_name))
    assert source.count("tier_first=tier_first") == 2
```

Also load `services/fissures.py` with the lightweight AstrBot path stubs already used by the test suite. Use one shared fake fissure list and monkeypatch `render_worldstate_rows_image_to_file` to capture `rows`. Parameterize `tier_first=True/False`, then assert the tier order in text lines exactly matches the captured `WorldstateRow.title` order. Monkeypatch the module-level `sort_fissures` with a recording wrapper and assert each renderer calls it once with the requested mode. These tests must fail before the renderer signatures and shared sorter calls are added.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
& '..\..\.venv\Scripts\python.exe' -m pytest tests/test_fissure_sorting.py tests/test_fissure_sorting_schema.py tests/test_fissure_sorting_wiring.py -q
```

Expected: parser import/schema tests fail because the parser and field are absent; rendering and command wiring tests fail because `tier_first` is not accepted or forwarded.

- [ ] **Step 3: Add the configuration field**

Add this top-level field to `_conf_schema.json` near other rendering/query behavior settings:

```json
"fissure_tier_sort_enabled": {
  "type": "bool",
  "default": true,
  "description": "裂缝按纪元排序",
  "hint": "开启后按古纪、前纪、中纪、后纪、安魂、全能排序，同一纪元按剩余时间排序；关闭后仅按剩余时间排序。"
}
```

Add the parser to `services/fissure_sorting.py` only after observing the parser test fail:

```python
from collections.abc import Iterable, Mapping


def fissure_tier_sort_enabled(config: Mapping[str, object] | None) -> bool:
    if not isinstance(config, Mapping):
        return True
    value = config.get("fissure_tier_sort_enabled", True)
    return value if isinstance(value, bool) else True
```

- [ ] **Step 4: Use the shared sorter in both render paths**

In `services/fissures.py`, add a required `tier_first: bool` keyword to both render functions and replace both in-place sorts with:

```python
picked = sort_fissures(picked, tier_first=tier_first)
```

In `services/worldstate_commands.py`, add `tier_first: bool` to `cmd_fissures` and `cmd_fissures_kind`, then pass it to both image and text render calls.

- [ ] **Step 5: Parse once and wire all commands**

In `main.py`, import `fissure_tier_sort_enabled`, initialize:

```python
self._fissure_tier_sort_enabled = fissure_tier_sort_enabled(self.config)
```

Pass `tier_first=self._fissure_tier_sort_enabled` from `/裂缝`, `/普通裂缝`, `/钢铁裂缝`, and `/九重天裂缝` into the relevant worldstate command function.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run the Task 2 pytest command again.

Expected: all sorting and schema tests pass.

- [ ] **Step 7: Commit Task 2**

```powershell
git add _conf_schema.json main.py services/fissure_sorting.py services/fissures.py services/worldstate_commands.py tests/test_fissure_sorting.py tests/test_fissure_sorting_schema.py tests/test_fissure_sorting_wiring.py
git commit -m "新增：配置裂缝纪元优先排序"
```

### Task 3: Documentation and Full Verification

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Add: `docs/superpowers/plans/2026-07-11-fissure-tier-sorting.md`

- [ ] **Step 1: Document behavior and compatibility switch**

Add a concise README configuration note stating that fissures default to canonical tier order and that disabling “裂缝按纪元排序” restores ETA-only ordering. Add the same user-visible change to `CHANGELOG.md`.

- [ ] **Step 2: Run the complete test suite**

Run:

```powershell
& '..\..\.venv\Scripts\python.exe' -m pytest -q
```

Expected: all existing and new tests pass.

- [ ] **Step 3: Validate Python and JSON syntax**

Run:

```powershell
& '..\..\.venv\Scripts\python.exe' -m compileall -q main.py services tests
```

Expected: exit code 0 with no output.

Run:

```powershell
& '..\..\.venv\Scripts\python.exe' -m json.tool _conf_schema.json > $null
```

Expected: exit code 0.

- [ ] **Step 4: Commit documentation**

```powershell
git add README.md CHANGELOG.md docs/superpowers/plans/2026-07-11-fissure-tier-sorting.md
git commit -m "文档：说明裂缝排序配置"
```

- [ ] **Step 5: Review final diff**

Run `git status --short`, `git diff master...HEAD --stat`, and `git log --oneline master..HEAD`.

Expected: clean worktree; changes limited to the files listed in this plan; three implementation commits after the design commit.
