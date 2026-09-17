"""Build the AstrBot-installable plugin archive.

AstrBot extracts an uploaded archive into `data/plugins/<name>/`, so `main.py`
and `metadata.yaml` have to sit at the archive root — the archive is flat and
named after the plugin. Development-only files are left out.

Archives are named after the existing releases sitting next to the plugin
directory, so a folder of builds stays sortable at a glance:

    astrbot_plugin_warframe_helper-v0.5.0-wm-resolve-wiki-suffix-20260913.zip
    astrbot_plugin_warframe_helper-v0.4.0-auto-push-20260721.zip
    astrbot_plugin_warframe_helper-v0.3.2-fissure-sort-20260711.zip

Usage:

    python scripts/package_plugin.py --theme wm-resolve-wiki-suffix
    python scripts/package_plugin.py --theme hotfix --output D:/somewhere/plugin.zip
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
import zipfile
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "astrbot_plugin_warframe_helper"
OUTPUT_DIR = PLUGIN_ROOT.parent

# Files that must exist at the archive root for AstrBot to load the plugin.
REQUIRED_ROOT_FILES = ("main.py", "metadata.yaml", "_conf_schema.json", "requirements.txt")

# Directories that are only useful while developing.
EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".venv",
        ".pytest_cache",
        ".worktrees",
        ".package-staging",
        "__pycache__",
        "docs",
        "scripts",
        "tests",
    }
)

EXCLUDED_SUFFIXES = (".pyc", ".pyo")

# Development-only files that live at the archive root.
EXCLUDED_ROOT_FILES = frozenset({"pytest.ini", "requirements-test.txt"})


def _is_excluded(relative: Path) -> bool:
    if any(part in EXCLUDED_DIRS for part in relative.parts):
        return True
    if len(relative.parts) == 1 and relative.name in EXCLUDED_ROOT_FILES:
        return True
    return relative.name.endswith(EXCLUDED_SUFFIXES)


def _collect() -> list[Path]:
    files: list[Path] = []
    for path in sorted(PLUGIN_ROOT.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(PLUGIN_ROOT)
        if _is_excluded(relative):
            continue
        files.append(relative)
    return files


def _read_version() -> str:
    text = (PLUGIN_ROOT / "metadata.yaml").read_text(encoding="utf-8")
    match = re.search(r"^version:\s*(\S+)", text, re.MULTILINE)
    return match.group(1) if match else "unknown"


def _slugify_theme(theme: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(theme or "").strip().lower())
    return slug.strip("-")


def _default_output(version: str, theme: str) -> Path:
    stamp = datetime.date.today().strftime("%Y%m%d")
    slug = _slugify_theme(theme)
    return OUTPUT_DIR / f"{PLUGIN_NAME}-{version}-{slug}-{stamp}.zip"


def build(output: Path) -> int:
    missing = [name for name in REQUIRED_ROOT_FILES if not (PLUGIN_ROOT / name).is_file()]
    if missing:
        print(f"missing required root files: {', '.join(missing)}", file=sys.stderr)
        return 1

    files = _collect()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative in files:
            archive.write(PLUGIN_ROOT / relative, relative.as_posix())

    size_mb = output.stat().st_size / (1024 * 1024)
    print(f"{output}")
    print(f"version {_read_version()}, {len(files)} files, {size_mb:.1f} MiB")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--theme",
        required=True,
        help="short slug describing the change, e.g. wm-resolve-wiki-suffix",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="archive path (default: <plugin>-<version>-<theme>-<date>.zip next to the plugin)",
    )
    args = parser.parse_args()

    output = args.output or _default_output(_read_version(), args.theme)
    return build(output)


if __name__ == "__main__":
    raise SystemExit(main())
