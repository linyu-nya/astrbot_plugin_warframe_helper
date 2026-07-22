from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_skip_reason():
    module_path = ROOT / "services" / "no_prefix_routing.py"
    assert module_path.exists(), "no-prefix routing policy is not implemented"
    spec = importlib.util.spec_from_file_location("wf_no_prefix_routing", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.no_prefix_skip_reason


def test_group_wake_flag_does_not_block_plain_no_prefix_command() -> None:
    no_prefix_skip_reason = _load_skip_reason()
    assert (
        no_prefix_skip_reason(
            "科研 深层",
            wake_or_command=True,
            has_explicit_at=False,
        )
        is None
    )


def test_real_command_flows_are_still_skipped() -> None:
    no_prefix_skip_reason = _load_skip_reason()
    assert (
        no_prefix_skip_reason(
            "/科研 深层",
            wake_or_command=True,
            has_explicit_at=False,
        )
        == "empty_or_slash"
    )
    assert (
        no_prefix_skip_reason(
            "科研 深层",
            wake_or_command=True,
            has_explicit_at=True,
        )
        == "explicit_at"
    )
