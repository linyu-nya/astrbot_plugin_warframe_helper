"""Export the reviewed topic pack as Markdown files for AstrBot upload."""
from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path


def export(output: Path) -> int:
    root = Path(__file__).resolve().parents[1]
    pack = json.loads((root / "assets" / "knowledge" / "starter_topics_zh.json").read_text(encoding="utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(pack, ensure_ascii=False, indent=2))
        for document in pack["documents"]:
            title = document["title"]
            filename = re.sub(r'[\\/:*?"<>|]', "_", title)
            content = f"# {title}\n\n{document['content']}\n\n来源：{document['source']}\n核验日期：{document.get('verified_at', pack['verified_at'])}\n适用范围：{document.get('applies_to', pack['applies_to'])}\n"
            archive.writestr(f"{document['id']}-{filename}.md", content)
    print(f"{output}: {len(pack['documents'])} Markdown documents")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    raise SystemExit(export(parser.parse_args().output))
