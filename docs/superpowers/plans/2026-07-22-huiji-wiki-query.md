# Huiji Wiki Query Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace legacy resource lookup commands with a resilient `/wk` Huiji Wiki link query and a persistent `/wfmap`, `/wfmapdel`, `/wfmapq` alias-management command family that does not depend on warframe.market validation.

**Architecture:** Extend `NicknameRegistry` with versioned migration and user-alias CRUD, then expose alias-only operations through `WarframeTermMapper`. Add focused Wiki and mapping command services, wire them through `main.py`, and keep all network failures inside a three-state Huiji client so users always receive a usable page or search link.

**Tech Stack:** Python 3.12, AstrBot command filters, `aiohttp`, MediaWiki Action API, `pytest`, AST wiring tests.

---

## File Structure

- Create `clients/huiji_wiki_client.py`: MediaWiki request, three-state result parsing, page/search URL construction.
- Create `services/wiki_commands.py`: `/wk` alias resolution and user-facing text.
- Create `services/mapping_commands.py`: mapping command argument handling, permission checks, and text responses.
- Modify `mappers/nickname_registry.py`: schema migration, user-alias CRUD, effective reverse lookup.
- Modify `mappers/term_mapping.py`: alias-only resolve/write/delete/reverse APIs without market initialization.
- Modify `main.py`: command registration, no-prefix routing, help text, dependency cleanup, old command removal.
- Modify `services/market/wmr.py`: remove `wk` from Riven usage.
- Modify `README.md` and `CHANGELOG.md`: document the new command family and removed commands.
- Create focused tests under `tests/` for each unit and AST-level command wiring.

### Task 1: Versioned Nickname Data Migration And CRUD

**Files:**
- Modify: `mappers/nickname_registry.py`
- Create: `tests/test_nickname_registry.py`

- [ ] **Step 1: Write failing migration and CRUD tests**

Cover user alias insertion, deletion, refusal to delete built-ins, legacy runtime-base additions and overrides migrating into `USER_ALIASES`, unchanged built-ins not migrating, current built-ins replacing runtime built-ins after migration, migrated legacy admin entries becoming deletable through the same delete API used by `/wfmapdel`, and repeated migration remaining idempotent. Add optional `data_path` and `default_path` constructor injection to `NicknameRegistry` so tests use `tmp_path` and never import `astrbot.core.utils.astrbot_path` or touch real plugin data.

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `pytest tests/test_nickname_registry.py -q`

Expected: failures for missing migration/delete/effective reverse APIs.

- [ ] **Step 3: Implement minimal registry behavior**

Add optional path injection, a schema version constant, migration before default synchronization, persisted migrated user aliases, `delete_user_alias(alias)`, and effective merged entries with their winning source section. Preserve order `base < riven weapon < user` and keep Riven stat aliases out of this mapping family.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_nickname_registry.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit the registry slice**

```powershell
git add mappers/nickname_registry.py tests/test_nickname_registry.py
git commit -m "重构：增加别名迁移与持久化管理"
```

### Task 2: Alias-Only Term Mapper API

**Files:**
- Modify: `mappers/term_mapping.py`
- Create: `tests/test_term_mapping_aliases.py`

- [ ] **Step 1: Write failing alias-only tests**

Test exact lookup, longest-prefix lookup, unknown input passthrough, user-over-built-in precedence, write/delete immediate reload, reverse lookup of only effective mappings, deletion fallback to built-in, full-name case/leading/trailing/repeated-space normalization, rejection of an alias supplied where `/wfmapq` requires a full name, and the `照相机 -> 奥克绪罗斯` flow. Inject a temporary `NicknameRegistry` into `WarframeTermMapper`; assert alias-only methods never call `initialize()`, load the market item cache, or refresh warframe.market data.

- [ ] **Step 2: Run and confirm red state**

Run: `pytest tests/test_term_mapping_aliases.py -q`

Expected: failures because the public alias-only API does not exist.

- [ ] **Step 3: Implement the public alias-only API**

Add optional registry injection plus focused methods such as `resolve_alias_only`, `upsert_user_alias`, `delete_user_alias`, and `find_effective_aliases`. Reuse existing normalization and longest-prefix logic, but keep market modifier/item matching outside these methods. Change existing `upsert_alias` compatibility behavior to write `USER_ALIASES`, not the packaged default file.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_term_mapping_aliases.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit the mapper slice**

```powershell
git add mappers/term_mapping.py tests/test_term_mapping_aliases.py
git commit -m "重构：拆分别名解析与市场校验"
```

### Task 3: Resilient Huiji MediaWiki Client

**Files:**
- Create: `clients/huiji_wiki_client.py`
- Create: `tests/test_huiji_wiki_client.py`

- [ ] **Step 1: Write failing client tests**

Test exact pages, redirects, `fullurl`, confirmed `missing` and `invalid`, fallback page URL construction, and search URL round-trip encoding for Chinese, spaces, `+`, `&`, `?`, `#`, `%`, and `|`. Cover timeout/connection/TLS errors, 429, other 4xx, 5xx, API `error`, HTML Cloudflare responses, malformed JSON, empty/multiple pages, and missing fields. A non-JSON `Content-Type` must return `UNAVAILABLE` even when its body happens to parse as JSON. Assert `|` skips exact multi-title lookup.

- [ ] **Step 2: Run and confirm red state**

Run: `pytest tests/test_huiji_wiki_client.py -q`

Expected: import failure because the client is not implemented.

- [ ] **Step 3: Implement the three-state client**

Define a small immutable result type with `FOUND`, `MISSING`, and `UNAVAILABLE`. Request `/api.php` with `action=query`, `prop=info`, `inprop=url`, `redirects=1`, `format=json`, and `formatversion=2`; use plugin proxy settings and browser-compatible Huiji headers. Return `UNAVAILABLE` for every unverified response instead of raising. Build search URLs with `urllib.parse.urlencode`.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_huiji_wiki_client.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit the client slice**

```powershell
git add clients/huiji_wiki_client.py tests/test_huiji_wiki_client.py
git commit -m "新增：灰机百科查询客户端"
```

### Task 4: Mapping Command Service

**Files:**
- Create: `services/mapping_commands.py`
- Create: `tests/test_mapping_commands.py`

- [ ] **Step 1: Write failing command-service tests**

Cover `/wfmap <alias> <full name>` parsing with multi-word names, missing arguments, admin and non-admin events, `/wfmapdel` success/missing/built-in-only/fallback, `/wfmapq` public access and source-labelled effective aliases, full-name case/whitespace normalization, rejection of alias-as-full-name lookup, plus the compatibility add path. Test permission checks inside the shared service entry; route-level execution is covered separately in Task 6.

- [ ] **Step 2: Run and confirm red state**

Run: `pytest tests/test_mapping_commands.py -q`

Expected: import failure because the service is not implemented.

- [ ] **Step 3: Implement minimal plain-text command functions**

Keep AstrBot event usage limited to `event.is_admin()` and `event.plain_result()`. Parse the first token as alias and preserve the entire remainder as full name. Return deterministic messages for added, updated, deleted, restored-to-built-in, immutable-built-in, missing, and query results.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_mapping_commands.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit the mapping service slice**

```powershell
git add services/mapping_commands.py tests/test_mapping_commands.py
git commit -m "新增：别名映射管理命令"
```

### Task 5: Wiki Command Service

**Files:**
- Create: `services/wiki_commands.py`
- Create: `tests/test_wiki_commands.py`

- [ ] **Step 1: Write failing Wiki command tests**

Cover empty input, raw exact hit, alias exact hit, confirmed missing, API unavailable, non-tradable alias targets, and search URL use of the resolved full name while reply labels retain the original keyword.

- [ ] **Step 2: Run and confirm red state**

Run: `pytest tests/test_wiki_commands.py -q`

Expected: import failure because the service is not implemented.

- [ ] **Step 3: Implement `/wk` orchestration**

Resolve through `resolve_alias_only`, call the Huiji client, and return the approved three messages: exact page, confirmed missing search page, or unable-to-confirm search page. Always return plain text with the URL on its own line.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/test_wiki_commands.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit the Wiki service slice**

```powershell
git add services/wiki_commands.py tests/test_wiki_commands.py
git commit -m "新增：统一灰机百科查询命令"
```

### Task 6: AstrBot Wiring And Legacy Command Removal

**Files:**
- Modify: `main.py`
- Modify: `services/market/wmr.py`
- Create: `tests/test_wiki_mapping_command_wiring.py`
- Create: `tests/test_wiki_mapping_routes.py`

- [ ] **Step 1: Write failing AST wiring tests**

Assert `/wk` and no-prefix `wk` target the Wiki handler; Riven aliases contain `wr` but not `wk`; mapping handlers and no-prefix routes include `wfmap`, `wfmapdel`, `wfmapq`; help lists the new commands; all legacy resource command decorators, methods, aliases, and no-prefix entries are absent. Also assert `DropDataClient`, `drop_data_commands`, and `public_export_commands` imports are removed when no longer used.

- [ ] **Step 2: Run and confirm red state**

Run: `pytest tests/test_wiki_mapping_command_wiring.py tests/test_wiki_mapping_routes.py -q`

Expected: failures reflecting current wiring.

- [ ] **Step 3: Wire the new services**

Instantiate `HuijiWikiClient`, add decorated handlers for `/wk`, `/wfmap`, `/wfmapdel`, and `/wfmapq`, route no-prefix commands to the same methods, route `/简称补充` through the same user-alias writer, update help rows, and remove the old market-validation `wfmap` implementation.

- [ ] **Step 4: Remove legacy resource query commands**

Delete `/武器`, `/战甲`, `/MOD`, `/掉落`, `/遗物` methods and all specified aliases/routes. Remove now-unused drop-data client construction and command imports while retaining `PublicExportClient` because cache warmup and worldstate localization still use it.

- [ ] **Step 5: Update Riven usage and run wiring tests**

Use minimal AstrBot stubs to execute both paths: call the decorated `wfmap` handler as the slash-command path and call `no_prefix_command_router` with `wfmap ...` as the no-prefix path. For each path, assert a non-admin cannot mutate data and an admin can. Then run:

`pytest tests/test_wiki_mapping_command_wiring.py tests/test_wiki_mapping_routes.py tests/test_mapping_commands.py tests/test_wiki_commands.py -q`

Expected: all tests pass.

- [ ] **Step 6: Preserve pre-existing dirty hunks and commit only isolated clean files**

Before editing, inspect and retain the existing `git diff -- main.py` as the baseline. After editing, verify existing worldstate/background hunks are still present. Do not stage all of `main.py`, because it was already dirty before this feature. Stage only files that were clean before this task:

```powershell
git add services/market/wmr.py tests/test_wiki_mapping_command_wiring.py tests/test_wiki_mapping_routes.py
git commit -m "测试：约束百科与映射命令接线"
```

Leave the feature hunks in pre-dirty `main.py` unstaged for the later combined branch integration; do not use interactive staging or broad `git add`.

### Task 7: Documentation And Full Regression

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `metadata.yaml` only if the current pending release version has not already been advanced for this branch

- [ ] **Step 1: Update user documentation**

Document `/wk`, `/wfmap`, `/wfmapdel`, `/wfmapq`, admin permissions, non-tradable aliases, API fallback wording, removed legacy commands, and Riven aliases `/wmr` and `/wr` only. Preserve unrelated existing README and changelog edits in the dirty worktree.

- [ ] **Step 2: Run focused tests together**

Run: `pytest tests/test_nickname_registry.py tests/test_term_mapping_aliases.py tests/test_huiji_wiki_client.py tests/test_mapping_commands.py tests/test_wiki_commands.py tests/test_wiki_mapping_command_wiring.py tests/test_wiki_mapping_routes.py -q`

Expected: all focused tests pass.

- [ ] **Step 3: Run the full suite**

Run: `pytest -q`

Expected: all tests pass with no regressions.

- [ ] **Step 4: Run static sanity checks**

Run: `python -m compileall -q clients mappers services main.py`

Run: `git diff --check`

Expected: both commands exit successfully.

- [ ] **Step 5: Inspect final scope**

Run: `git status --short`

Run: `git diff --stat`

Confirm no unrelated user changes were overwritten and no generated caches are staged.

- [ ] **Step 6: Preserve pre-existing documentation hunks**

`README.md`, `CHANGELOG.md`, and `metadata.yaml` were already dirty before this feature. Compare their final diffs with the pre-feature baseline and leave them unstaged rather than mixing unrelated worldstate/background changes into a Wiki-only commit. Do not use broad or interactive staging. Report these intentional unstaged integration changes in the completion summary.
