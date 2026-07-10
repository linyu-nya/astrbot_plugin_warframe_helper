# Custom Render Background Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional, fully configurable global and category-specific background images to the plugin's HTML-rendered cards without breaking existing templates.

**Architecture:** Parse and validate configuration in a pure settings module, load local or remote images once during plugin initialization, and generate a sanitized render-theme context per template scope. The template loader injects this context into Jinja, while built-in templates opt in with one shared CSS insertion point; disabled or failed backgrounds fall back to the current styles.

**Tech Stack:** Python 3.12, dataclasses, Pillow, aiohttp via existing `fetch_bytes`, Jinja2, pytest, pytest-asyncio, Playwright.

---

## File Structure

- Create `renderers/background_config.py`: immutable settings model, defaults, validation, and CSS-safe value parsing.
- Create `renderers/background_assets.py`: local/remote image loading, Pillow validation, size limits, data URI storage, and scope fallback.
- Create `renderers/render_theme.py`: template-scope classification and sanitized CSS/theme-context generation.
- Create `renderers/background_runtime.py`: compose settings, assets, and immutable theme resolution without importing AstrBot.
- Modify `renderers/template_loader.py`: inject `render_theme` into every Jinja context.
- Modify `http_utils.py`: support bounded streaming reads for remote image downloads.
- Modify `main.py`: construct and initialize the background asset loader with plugin configuration.
- Modify `_conf_schema.json`: expose every supported background and glass parameter in AstrBot's configuration menu.
- Modify `assets/template/default/*.html`: opt built-in templates into `render_theme.css`.
- Create `tests/`: focused tests for parsing, loading, fallback, CSS generation, schema, and template integration.
- Create `scripts/render_background_preview.py`: reproducible three-card Playwright visual preview.
- Create `requirements-test.txt`: reproducible lightweight test dependencies.
- Create `pytest.ini`: enable asyncio tests and constrain discovery to `tests/`.
- Modify `README.md` and `CHANGELOG.md`: document configuration, Docker path behavior, reload requirements, and the new feature.

## Task 1: Test Harness and Background Configuration

**Files:**
- Create: `requirements-test.txt`
- Create: `pytest.ini`
- Create: `tests/conftest.py`
- Create: `tests/test_background_config.py`
- Create: `renderers/background_config.py`

- [ ] **Step 1: Add the test dependency and pytest configuration files**

Create `requirements-test.txt`:

```text
pytest>=8.3
pytest-asyncio>=0.25
aiohttp>=3.10
Jinja2>=3.1
Pillow>=11.0
playwright>=1.50
```

Create `pytest.ini`:

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

Create `tests/conftest.py` so tests import modules through the real plugin package name without
installing AstrBot:

```python
from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "astrbot_plugin_warframe_helper"

package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT)]
sys.modules.setdefault(PACKAGE, package)

astrbot = types.ModuleType("astrbot")
astrbot_api = types.ModuleType("astrbot.api")
astrbot_api.logger = types.SimpleNamespace(
    debug=lambda *_args, **_kwargs: None,
    info=lambda *_args, **_kwargs: None,
    warning=lambda *_args, **_kwargs: None,
)
astrbot.api = astrbot_api
sys.modules.setdefault("astrbot", astrbot)
sys.modules.setdefault("astrbot.api", astrbot_api)
```

All tests import modules as `astrbot_plugin_warframe_helper.<module>`. Unit tests must not import
`main.py`; AstrBot lifecycle wiring is covered separately by an AST contract test in Task 6.

- [ ] **Step 2: Create the isolated test environment**

Run:

```powershell
& 'C:\Users\linyu\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
```

Expected: the virtual environment can run `python -m pytest --version`.

- [ ] **Step 3: Write failing configuration tests**

Cover these behaviors in `tests/test_background_config.py`:

```python
from astrbot_plugin_warframe_helper.renderers.background_config import (
    parse_render_background_config,
)


def test_background_defaults_are_disabled():
    config = parse_render_background_config({})
    assert config.enabled is False
    assert config.default_source == ""
    assert config.glass_enabled is True
    assert config.blur_px == 6
    assert config.background_fit == "cover"


def test_background_values_are_trimmed_and_clamped():
    config = parse_render_background_config(
        {
            "render_background": {
                "enabled": True,
                "default_source": "  image.webp  ",
                "overlay_opacity": -5,
                "panel_opacity": 180,
                "blur_px": 99,
            }
        }
    )
    assert config.default_source == "image.webp"
    assert config.overlay_opacity == 0
    assert config.panel_opacity == 100
    assert config.blur_px == 30


def test_background_rejects_unsafe_css_values():
    config = parse_render_background_config(
        {
            "render_background": {
                "overlay_color": "red; background:url(x)",
                "panel_color": "rgb(0,0,0)",
                "background_position": "center; color:red",
                "background_fit": "stretch",
                "text_mode": "auto",
            }
        }
    )
    assert config.overlay_color == "#0f172a"
    assert config.panel_color == "#0f172a"
    assert config.background_position == "center center"
    assert config.background_fit == "cover"
    assert config.text_mode == "light"
```

- [ ] **Step 4: Run the tests and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_background_config.py -q`

Expected: FAIL during import because `renderers.background_config` does not exist.

- [ ] **Step 5: Implement the immutable settings parser**

Implement a frozen, slotted `RenderBackgroundConfig` dataclass containing all fields from the design document. Add:

```python
def parse_render_background_config(config: dict | None) -> RenderBackgroundConfig:
    raw = (config or {}).get("render_background") or {}
    if not isinstance(raw, dict):
        raw = {}
    # Parse bools, trim sources, clamp integer percentages, and whitelist
    # colors, text modes, fit modes, and position syntax.
```

Use `#RGB`/`#RRGGBB` validation, a position token whitelist (`left`, `center`, `right`, `top`, `bottom`, percentages), and these fit modes: `cover`, `contain`, `width`, `repeat-y`.

- [ ] **Step 6: Run the tests and verify GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_background_config.py -q`

Expected: all configuration tests PASS.

Run: `.\.venv\Scripts\python.exe -m pytest -q`

Expected: the complete suite PASS before committing.

- [ ] **Step 7: Commit**

```powershell
git add requirements-test.txt pytest.ini tests/conftest.py tests/test_background_config.py renderers/background_config.py
git commit -m "新增：解析自定义底图配置"
```

## Task 2: Validated Local and Remote Image Loading

**Files:**
- Create: `tests/test_background_assets.py`
- Create: `tests/test_http_utils_limited_fetch.py`
- Create: `renderers/background_assets.py`
- Modify: `http_utils.py`

- [ ] **Step 1: Write failing local-resource tests**

Use Pillow to create real 2x2 PNG, JPEG, and WebP fixtures in `tmp_path`. Test:

```python
async def test_loads_relative_local_image_from_plugin_root(tmp_path):
    settings = make_settings(enabled=True, default_source="background.png")
    write_png(tmp_path / "background.png")
    assets = BackgroundAssetLoader(settings, plugin_root=tmp_path)
    await assets.initialize()
    assert assets.uri_for("default").startswith("data:image/png;base64,")


async def test_category_failure_falls_back_to_global(tmp_path):
    settings = make_settings(
        enabled=True,
        default_source="global.png",
        fissure_source="missing.png",
    )
    write_png(tmp_path / "global.png")
    assets = BackgroundAssetLoader(settings, plugin_root=tmp_path)
    await assets.initialize()
    assert assets.uri_for("fissure") == assets.uri_for("default")
```

Also test absolute paths, nonexistent paths, fake extensions, unsupported GIF/SVG, corrupt data,
the 15 MiB byte limit, and the 40-megapixel decoded-image limit. Keep the pixel-limit test small
by monkeypatching the module constant and loading a real 2x2 PNG.

- [ ] **Step 2: Run local-resource tests and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_background_assets.py -q`

Expected: FAIL because `BackgroundAssetLoader` is missing.

- [ ] **Step 3: Implement local loading and validation**

Implement:

```python
class BackgroundAssetLoader:
    def __init__(self, settings, *, plugin_root: Path, fetcher=None, warning=None): ...
    async def initialize(self) -> None: ...
    def uri_for(self, scope: str) -> str: ...
```

Read local files with `asyncio.to_thread`, check byte length before Pillow decoding, convert Pillow
decompression-bomb warnings to errors, enforce `width * height <= 40_000_000`, call
`Image.verify()`, accept only `PNG`, `JPEG`, and `WEBP`, and build MIME from the detected format
rather than the filename. Accept injectable fetcher and warning callbacks and record at most one
warning per failed configured source. Do not import AstrBot or `http_utils` at module import time;
when no fetcher is injected and a remote source is present, lazily import `fetch_bytes` inside the
remote-loading coroutine. Use the standard library logger only as the final warning fallback.

- [ ] **Step 4: Run local-resource tests and verify GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_background_assets.py -q`

Expected: local-resource tests PASS.

- [ ] **Step 5: Write failing remote-resource tests**

Inject an async fake fetcher and test successful HTTP(S) loading, empty responses, oversized
responses, corrupt responses, and independent failure of one category. Assert that each configured
URL is fetched once during `initialize()` and never during `uri_for()`. Explicitly test that a
disabled total switch performs zero local reads and zero fetcher calls, a failed global resource
returns an empty URI so the original template is used, and each failure emits exactly one warning.

In `tests/test_http_utils_limited_fetch.py`, exercise a small fake response stream and assert the
bounded reader stops as soon as cumulative chunks exceed the limit instead of buffering the full
response.

- [ ] **Step 6: Run remote-resource tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_background_assets.py tests/test_http_utils_limited_fetch.py -q
```

Expected: new remote tests FAIL because URL sources are not handled.

- [ ] **Step 7: Implement remote loading and fallback**

Extend `fetch_bytes()` with an optional `max_bytes` parameter. Reject an oversized `Content-Length`
before reading and otherwise consume `resp.content.iter_chunked(64 * 1024)` while enforcing the
cumulative limit. Recognize only `http://` and `https://` in the loader, call the injected fetcher
with a 10-second timeout, image `Accept` header, and 15 MiB limit, validate returned bytes identically
to local files, and retain only data URIs in memory.

- [ ] **Step 8: Run tests and commit**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_background_assets.py tests/test_http_utils_limited_fetch.py -q
```

Expected: all asset tests PASS.

Run: `.\.venv\Scripts\python.exe -m pytest -q`

Expected: the complete suite PASS before committing.

```powershell
git add tests/test_background_assets.py tests/test_http_utils_limited_fetch.py renderers/background_assets.py http_utils.py
git commit -m "新增：加载并校验自定义底图"
```

## Task 3: Scope Selection and Theme CSS

**Files:**
- Create: `tests/test_render_theme.py`
- Create: `renderers/render_theme.py`

- [ ] **Step 1: Write failing scope-classification tests**

Test `classify_render_scope(filename, command_key)` for:

```python
assert classify_render_scope("crack.html", "裂缝") == "fissure"
assert classify_render_scope("status_list.html", "钢铁裂缝") == "fissure"
assert classify_render_scope("wm.html", "wm") == "market"
assert classify_render_scope("wfp.html", "wfp") == "market"
assert classify_render_scope("cycle_status.html", "平原") == "worldstate"
assert classify_render_scope("赏金.html", "赏金") == "worldstate"
assert classify_render_scope("guide.html", "wf") == "default"
```

- [ ] **Step 2: Run and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_render_theme.py -q`

Expected: FAIL because the module is missing.

- [ ] **Step 3: Implement scope classification**

Keep command and filename sets private and normalized without a leading slash. Filename rules take priority except that known fissure commands override the generic `status_list.html` filename.

- [ ] **Step 4: Run scope tests and verify GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_render_theme.py -q`

Expected: scope tests PASS.

- [ ] **Step 5: Write failing CSS-generation tests**

Test that:

- disabled settings or an empty URI produce a `RenderTheme` whose `enabled` is false and `css` is empty;
- `glass_enabled=False` omits both backdrop-filter declarations;
- enabled glass emits the configured `blur_px` value;
- `overlay_enabled=False` omits the overlay pseudo-element while preserving the background;
- overlay and panel colors use configured alpha values;
- `cover`, `contain`, `width`, and `repeat-y` map to expected `background-size` and `background-repeat` rules;
- light/dark text modes produce readable controlled color variables;
- no raw source path or URL appears in CSS; only a validated data URI is used.

- [ ] **Step 6: Run CSS tests and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_render_theme.py -q`

Expected: FAIL because theme-context generation is missing.

- [ ] **Step 7: Implement CSS/theme-context generation**

Expose an immutable theme object:

```python
@dataclass(frozen=True, slots=True)
class RenderTheme:
    enabled: bool
    css: str
    scope: str


def build_render_theme_context(
    settings: RenderBackgroundConfig,
    assets: BackgroundAssetLoader,
    *,
    filename: str,
    command_key: str,
) -> RenderTheme:
    ...
```

Generate CSS only from already validated settings. Scope rules to `.wf-custom-background`, `.row-card`, `.row`, `.header`, and `.head`, use `!important` only where required to override existing built-in backgrounds, and preserve all current CSS when disabled.

- [ ] **Step 8: Run tests and commit**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_render_theme.py -q`

Expected: all theme tests PASS.

Run: `.\.venv\Scripts\python.exe -m pytest -q`

Expected: the complete suite PASS before committing.

```powershell
git add tests/test_render_theme.py renderers/render_theme.py
git commit -m "新增：生成分类底图主题样式"
```

## Task 4: Template Loader Integration

**Files:**
- Create: `tests/test_template_background_integration.py`
- Modify: `renderers/template_loader.py`

- [ ] **Step 1: Write failing template-context tests**

Add a provider callback API to the wished-for tests:

```python
set_render_theme_resolver(
    lambda filename, command: RenderTheme(
        enabled=True,
        css=".wf-custom-background{--test:1}",
        scope="fissure",
    )
)
set_current_render_command("裂缝")
html = load_html_template(filename="status_list.html", context={"page": page})
assert "--test:1" in html
```

Also verify that caller-supplied `render_theme` is not overwritten, resolver exceptions return a disabled theme, and template selection/fallback still behaves as before.
Use `monkeypatch` to make `_template_file_candidates()` return a temporary template containing
`{{ render_theme.css }}`; do not require the built-in templates to opt in during this task.
Add an autouse fixture that calls `set_render_theme_resolver(None)`,
`set_current_render_command(None)`, and `set_current_render_template_name(None)` before and after
each test so resolver globals and ContextVars cannot leak between cases.

- [ ] **Step 2: Run and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_template_background_integration.py -q`

Expected: FAIL because `set_render_theme_resolver` is missing and templates do not consume the context.

- [ ] **Step 3: Implement resolver injection**

In `template_loader.py`:

```python
_RENDER_THEME_RESOLVER: Callable[[str, str], RenderTheme] | None = None

def set_render_theme_resolver(resolver): ...
```

Track the selected template path, copy the caller context, add `render_theme` with `setdefault`, and invoke the resolver with `selected_path.name` plus the normalized current command. On errors, inject a disabled theme instead of failing template rendering.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_template_background_integration.py -q`

Expected: all resolver and template-context tests PASS. Built-in template opt-in is tested separately in Task 5.

Run: `.\.venv\Scripts\python.exe -m pytest -q`

Expected: the complete suite PASS before committing.

- [ ] **Step 5: Commit the loader integration**

```powershell
git add renderers/template_loader.py tests/test_template_background_integration.py
git commit -m "重构：向模板注入渲染主题"
```

## Task 5: Built-in Template Opt-in and Visual Rules

**Files:**
- Modify: `assets/template/default/status_list.html`
- Modify: `assets/template/default/cycle_status.html`
- Modify: `assets/template/default/event.html`
- Modify: `assets/template/default/guide.html`
- Modify: `assets/template/default/lookup.html`
- Modify: `assets/template/default/subscription.html`
- Modify: `assets/template/default/crack.html`
- Modify: `assets/template/default/赏金.html`
- Modify: `assets/template/default/wm.html`
- Modify: `assets/template/default/wfp.html`
- Modify: `assets/template/default/wmr.html`
- Modify: `tests/test_template_background_integration.py`

- [ ] **Step 1: Add failing coverage for every built-in template**

Parameterize all filenames above and assert each rendered HTML contains the configured theme marker. Add a disabled-theme case asserting no `.wf-custom-background` marker is emitted.

- [ ] **Step 2: Run and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_template_background_integration.py -q`

Expected: FAIL for every template that lacks the theme insertion point.

- [ ] **Step 3: Add the shared opt-in block to every template**

Place after the existing base `<style>` block:

```jinja2
{% if render_theme and render_theme.enabled %}
<style>{{ render_theme.css | safe }}</style>
{% endif %}
```

Add the body class without removing existing classes:

```jinja2
<body{% if render_theme and render_theme.enabled %} class="wf-custom-background"{% endif %}>
```

- [ ] **Step 4: Run template and full unit tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_template_background_integration.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```powershell
git add assets/template/default tests/test_template_background_integration.py
git commit -m "新增：内置模板支持自定义底图"
```

## Task 6: Plugin Lifecycle and AstrBot Configuration Menu

**Files:**
- Create: `tests/test_background_schema.py`
- Create: `tests/test_background_runtime.py`
- Create: `tests/test_main_background_wiring.py`
- Create: `renderers/background_runtime.py`
- Modify: `_conf_schema.json`
- Modify: `main.py`

- [ ] **Step 1: Write failing schema tests**

Load `_conf_schema.json` and assert `render_background` is an object whose `items` contain every field in the design document with the exact defaults. Verify `glass_enabled` is a bool defaulting to true and `blur_px` is independently configurable.

- [ ] **Step 2: Run and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_background_schema.py -q`

Expected: FAIL because the schema object is absent.

- [ ] **Step 3: Add the configuration-menu schema**

Add Chinese `description` and `hint` text for every field. Hints must explain:

- classification override precedence;
- absolute and plugin-relative local paths;
- HTTP(S) startup download behavior;
- percentage/range limits;
- plugin reload requirement.

- [ ] **Step 4: Run schema tests and verify GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_background_schema.py -q`

Expected: schema tests PASS.

- [ ] **Step 5: Write failing runtime-composition tests**

In `tests/test_background_runtime.py`, specify a pure `BackgroundThemeRuntime` API:

```python
runtime = BackgroundThemeRuntime.from_config(
    plugin_config,
    plugin_root=tmp_path,
    fetcher=fake_fetcher,
    warning=fake_warning,
)
await runtime.initialize()
theme = runtime.resolve("crack.html", "裂缝")
assert isinstance(theme, RenderTheme)
assert theme.scope == "fissure"
```

Assert disabled configuration performs zero I/O, loaded category sources override the global source,
and failed category sources resolve through the global URI. Keep this module free of AstrBot imports.

In `tests/test_main_background_wiring.py`, parse `main.py` with `ast` and assert the plugin constructor
creates `BackgroundThemeRuntime.from_config`, installs `set_render_theme_resolver`, and
`initialize()` awaits `self._background_runtime.initialize()` before calling
`self._subscriptions.start()`. This is an AstrBot integration contract test that avoids importing
all framework handlers into the lightweight unit-test environment.

- [ ] **Step 6: Run and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_background_runtime.py tests/test_main_background_wiring.py -q
```

Expected: FAIL because the runtime module and lifecycle wiring are absent.

- [ ] **Step 7: Wire the background loader into the plugin**

Implement `BackgroundThemeRuntime` in `renderers/background_runtime.py` to own parsed settings,
`BackgroundAssetLoader`, and `resolve()`. In `WarframeHelperPlugin.__init__`:

```python
self._background_runtime = BackgroundThemeRuntime.from_config(
    self.config,
    plugin_root=Path(__file__).resolve().parent,
)
set_render_theme_resolver(self._background_runtime.resolve)
```

Await `self._background_runtime.initialize()` in `initialize()` before services start polling.
Disabled settings must return immediately without file or network access.

- [ ] **Step 8: Run tests and commit**

Run: `.\.venv\Scripts\python.exe -m pytest -q`

Expected: all tests PASS.

```powershell
git add _conf_schema.json main.py renderers/background_runtime.py tests/test_background_schema.py tests/test_background_runtime.py tests/test_main_background_wiring.py
git commit -m "新增：在配置菜单启用自定义底图"
```

## Task 7: Documentation and Changelog

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add user-facing configuration documentation**

Document:

- global and category override precedence;
- local absolute path examples for Windows and Docker;
- plugin-relative path example;
- HTTP(S) URL example;
- all visual controls and valid ranges;
- `cover`, `contain`, `width`, and `repeat-y` behavior;
- no upload button in this version;
- save and reload requirement;
- fallback and warning behavior.

- [ ] **Step 2: Add changelog entry**

Add an `Unreleased` section describing optional custom backgrounds, category overrides, and configurable glass effects.

- [ ] **Step 3: Verify docs and commit**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
```

Expected: all tests PASS and no whitespace errors.

```powershell
git add README.md CHANGELOG.md
git commit -m "文档：说明自定义底图配置"
```

## Task 8: Full Regression and Visual Verification

**Files:**
- Create: `scripts/render_background_preview.py`
- Create temporarily, then remove: `.test-output/fissure-background.png`
- Create temporarily, then remove: `.test-output/market-background.png`
- Create temporarily, then remove: `.test-output/worldstate-background.png`
- Modify only if verification reveals a defect: files covered by Tasks 1-7

- [ ] **Step 1: Run the complete automated suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q main.py renderers tests
git diff --check
```

Expected: all tests PASS, compileall exits 0, and no diff-check errors appear.

- [ ] **Step 2: Write the reproducible preview script**

Create `scripts/render_background_preview.py`. It must:

1. resolve the repository root from `Path(__file__)`, register a namespace module named
   `astrbot_plugin_warframe_helper` whose `__path__` points at that root, and only then import plugin
   modules; it must not depend on the worktree directory name or an AstrBot installation;
2. generate a temporary 980x720 gradient PNG with Pillow;
3. initialize `BackgroundThemeRuntime` with local global, fissure, market, and world-state settings
   so the lazily imported HTTP client is not needed;
4. render representative `crack.html`, `wm.html`, and `status_list.html` Jinja contexts;
5. use `playwright.async_api` directly with an installed Chromium or detected Edge/Chrome executable;
6. write exactly the three PNG files listed above;
7. exit nonzero if an output is missing or has zero dimensions.

Run:

```powershell
.\.venv\Scripts\python.exe scripts/render_background_preview.py --output-dir .test-output
```

If no system Chromium browser is detected, run
`.\.venv\Scripts\python.exe -m playwright install chromium` once and rerun the script.

Verify:

- no image distortion;
- background visible through panels;
- light text remains readable;
- glass off removes blur without removing the background;
- custom blur value changes emitted CSS;
- a long fissure list grows vertically without clipping.

- [ ] **Step 3: Inspect all preview images**

Open all three files with the image inspection tool. If any issue is found, first add a failing
regression test, then fix it and rerun Steps 1-2.

- [ ] **Step 4: Commit the preview tool after verification**

```powershell
git add scripts/render_background_preview.py
git commit -m "测试：增加底图视觉预览工具"
```

- [ ] **Step 5: Verify clean repository state**

Remove temporary previews, then run:

```powershell
git status --short
git log --oneline --decorate -10
```

Expected: no untracked preview files; only intentional committed changes remain.

- [ ] **Step 6: Final review**

Review the complete diff against `docs/plans/2026-07-10-custom-render-background-design.md`, ensuring every configurable field is implemented and documented, then prepare a Chinese PR summary.
