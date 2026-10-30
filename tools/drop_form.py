"""Remove one form from the app.

Deletes the bundle, its PDF copy and the catalogue entry, and keeps the PDF in sources/ so
the decision can be reversed. Used for documents the app cannot express, such as a 143-page
booklet rather than a single-regimen consent form.

Usage:
    python tools/drop_form.py haematology-aml-aida-all-transretinoic-acid-and-idarubicin
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FORMS = ROOT / "forms"
CATALOGUE = ROOT / "assets" / "catalogue.json"


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python tools/drop_form.py <form id>")
        return 2

    form_id = sys.argv[1]
    removed = []
    for path in (FORMS / f"{form_id}.json", FORMS / f"{form_id}.pdf"):
        if path.exists():
            path.unlink()
            removed.append(path.name)

    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    before = len(catalogue["forms"])
    catalogue["forms"] = [form for form in catalogue["forms"] if form["id"] != form_id]
    after = len(catalogue["forms"])
    CATALOGUE.write_text(
        json.dumps(catalogue, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"removed {form_id}: {', '.join(removed) or 'no files'}")
    print(f"catalogue {before} -> {after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
