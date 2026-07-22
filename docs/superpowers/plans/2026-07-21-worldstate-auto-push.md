# Worldstate Auto Push Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add query-only Archimedea, Duviri, and invasion support, plus opt-in group text pushes for selected world-state changes.

**Architecture:** Extend `WarframeWorldstateClient` with stable event identifiers and parsers for official `Conquests`, `Goals`, `Events`, and the current `EndlessXpSchedule` shape. Add a dedicated `AutoPushService` that stores enabled AstrBot session origins and per-session signatures, establishes a silent baseline on first enable, polls once per minute, and sends only newly observed text events.

**Tech Stack:** Python 3.12, AstrBot plugin API, aiohttp, pytest.

---

### Task 1: Archimedea and Circuit Queries

**Files:**
- Modify: `clients/worldstate_client.py`
- Modify: `services/worldstate_commands.py`
- Modify: `main.py`
- Test: `tests/test_archimedea_query.py`
- Test: `tests/test_duviri_circuit_current_schema.py`

- [ ] Write failing parser tests for official `Conquests` and aggregate `archimedeas`.
- [ ] Run focused tests and verify they fail because the query API is absent.
- [ ] Add research data classes, localization maps, client parser, command text, and `/科研` aliases.
- [ ] Write and verify a failing test for `EndlessXpSchedule.CategoryChoices`.
- [ ] Update Circuit parsing while retaining the legacy field fallback.
- [ ] Run focused query tests.

### Task 2: Push Event Data Sources

**Files:**
- Modify: `clients/worldstate_client.py`
- Create: `services/auto_push.py`
- Test: `tests/test_auto_push_events.py`

- [ ] Write failing tests for stable signatures and text formatting for fissures, alerts/events, news, sortie, Archon Hunt, and Void Trader inventory.
- [ ] Add identifiers and expiry timestamps to world-state models without breaking existing callers.
- [ ] Parse official and WarframeStat news/event shapes.
- [ ] Implement the exact fissure predicate: Steel Path, Sedna, Disruption, Omnia.
- [ ] Implement concise Chinese text payloads containing remaining time where applicable.
- [ ] Run focused event tests.

### Task 3: Persistent Group Push Service

**Files:**
- Create: `services/auto_push.py`
- Modify: `main.py`
- Modify: `_conf_schema.json`
- Test: `tests/test_auto_push_service.py`
- Test: `tests/test_auto_push_schema.py`

- [ ] Write failing tests for first-run silent baselines, per-session deduplication, restart persistence, and disable behavior.
- [ ] Implement `/推送开启`, `/推送关闭`, and `/推送状态` as group-admin commands.
- [ ] Poll at a configurable interval with a safe minimum of 30 seconds.
- [ ] Persist target sessions and last delivered signatures under the AstrBot plugin data directory.
- [ ] Start and stop the service with the plugin lifecycle.
- [ ] Run focused service tests.

### Task 4: Documentation and Verification

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `metadata.yaml`

- [ ] Document query commands, push scope, enable/disable commands, and first-run behavior.
- [ ] Increment the plugin patch version.
- [ ] Run formatting/static checks available in the repository.
- [ ] Run the complete pytest suite.
- [ ] Inspect the final diff for unrelated changes.
- [ ] Package an installable ZIP from tracked plugin files.
