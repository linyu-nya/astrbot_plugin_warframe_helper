from __future__ import annotations

from pathlib import Path

import pytest

from astrbot_plugin_warframe_helper.renderers import template_loader
from astrbot_plugin_warframe_helper.renderers.render_theme import RenderTheme
from astrbot_plugin_warframe_helper.renderers.template_loader import (
    load_html_template,
    set_current_render_command,
    set_current_render_template_name,
    set_render_theme_resolver,
)


@pytest.fixture(autouse=True)
def _reset_template_render_state():
    set_render_theme_resolver(None)
    set_current_render_command(None)
    set_current_render_template_name(None)
    yield
    set_render_theme_resolver(None)
    set_current_render_command(None)
    set_current_render_template_name(None)


def _set_temporary_template(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    content: str,
    *,
    filename: str = "custom.html",
) -> Path:
    template_path = tmp_path / filename
    template_path.write_text(content, encoding="utf-8")
    monkeypatch.setattr(
        template_loader,
        "_template_file_candidates",
        lambda *_args, **_kwargs: [template_path],
    )
    return template_path


def test_injects_resolved_theme_into_jinja_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    selected = _set_temporary_template(
        monkeypatch,
        tmp_path,
        "<style>{{ render_theme.css | safe }}</style>{{ render_theme.scope }}",
        filename="selected.html",
    )
    calls: list[tuple[str, str]] = []

    def resolver(filename: str, command: str) -> RenderTheme:
        calls.append((filename, command))
        return RenderTheme(
            enabled=True,
            css=".wf-custom-background{--test:1}",
            scope="fissure",
        )

    set_render_theme_resolver(resolver)
    set_current_render_command("/裂缝")

    html = load_html_template(filename="status_list.html", context={})

    assert ".wf-custom-background{--test:1}" in html
    assert "fissure" in html
    assert calls == [(selected.name, "裂缝")]


def test_caller_supplied_theme_is_not_overwritten_or_resolved(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    _set_temporary_template(
        monkeypatch,
        tmp_path,
        "{{ render_theme.css }}|{{ render_theme.scope }}",
    )
    calls: list[tuple[str, str]] = []

    def unexpected_resolver(filename: str, command: str) -> RenderTheme:
        calls.append((filename, command))
        return RenderTheme(enabled=False, css="", scope="default")

    set_render_theme_resolver(unexpected_resolver)
    supplied = RenderTheme(enabled=True, css="caller-css", scope="market")

    html = load_html_template(
        filename="wm.html",
        context={"render_theme": supplied},
    )

    assert html == "caller-css|market"
    assert calls == []


def test_resolver_exception_injects_disabled_theme(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    _set_temporary_template(
        monkeypatch,
        tmp_path,
        "{{ render_theme.enabled }}|{{ render_theme.css }}|{{ render_theme.scope }}",
    )

    def broken_resolver(_filename: str, _command: str) -> RenderTheme:
        raise RuntimeError("resolver failed")

    set_render_theme_resolver(broken_resolver)
    set_current_render_command("仲裁")

    html = load_html_template(filename="status_list.html", context={})

    assert html == "False||default"


def test_missing_resolver_injects_disabled_theme(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    _set_temporary_template(
        monkeypatch,
        tmp_path,
        "{{ render_theme.enabled }}|{{ render_theme.css }}|{{ render_theme.scope }}",
    )

    html = load_html_template(filename="guide.html", context={})

    assert html == "False||default"


def test_template_candidate_fallback_still_selects_first_existing_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    missing = tmp_path / "missing.html"
    fallback = tmp_path / "fallback.html"
    fallback.write_text("fallback-ok|{{ value }}", encoding="utf-8")
    monkeypatch.setattr(
        template_loader,
        "_template_file_candidates",
        lambda *_args, **_kwargs: [missing, fallback],
    )

    html = load_html_template(
        filename="status_list.html",
        context={"value": "preserved"},
    )

    assert html == "fallback-ok|preserved"
