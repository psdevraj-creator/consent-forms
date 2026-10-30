"""Remove list-marker characters that leaked into a side effect's text.

A bullet glyph inside a wrapped line extracts as a character such as "•" and lands mid
sentence: "unwell (even with a • normal temperature)". The importer strips them now, but
this cleans bundles written before that fix without re-parsing 517 PDFs.

Only text fields are touched; coordinates are left exactly as they are.

Usage:
    python tools/clean_bundles.py
"""

from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
FORMS = ROOT / "forms"

BULLET_CHARS = "\u2022\u00b7\u25aa\u25cf\u2023\u2043"


def clean(value: object) -> object:
    if isinstance(value, str):
        for character in BULLET_CHARS:
            value = value.replace(character, " ")
        return re.sub(r"\s+", " ", value).strip()
    if isinstance(value, list):
        return [clean(item) for item in value]
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items()}
    return value


def main() -> None:
    changed = 0
    for path in sorted(FORMS.glob("*.json")):
        original = path.read_text(encoding="utf-8")
        bundle = json.loads(original)
        cleaned = clean(bundle)
        if cleaned == bundle:
            continue
        path.write_text(json.dumps(cleaned, ensure_ascii=False) + "\n", encoding="utf-8")
        changed += 1
    print(f"cleaned {changed} bundles")


if __name__ == "__main__":
    main()
