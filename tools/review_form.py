"""Render every side-effect page of one form at a size a person can actually read.

    python tools/review_form.py <form id> [scale]
"""

from __future__ import annotations

import json
import pathlib
import sys

import pypdfium2 as pdfium

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROOFS = ROOT / "target" / "proofs"
FORMS = ROOT / "forms"
OUT = ROOT / "target" / "review"


def main() -> int:
    form_id = sys.argv[1]
    scale = float(sys.argv[2]) if len(sys.argv) > 2 else 1.7

    bundle = json.loads((FORMS / f"{form_id}.json").read_text(encoding="utf-8"))
    pages = sorted({tick["page"] for tick in bundle["side_effects"] if tick.get("page")})
    items = sum(len(group["items"]) for group in bundle["groups"])

    OUT.mkdir(parents=True, exist_ok=True)
    doc = pdfium.PdfDocument(str(PROOFS / f"{form_id}.pdf"))
    written = []
    for page_number in pages:
        image = doc[page_number - 1].render(scale=scale).to_pil()
        path = OUT / f"{form_id}-p{page_number}.png"
        image.save(path)
        written.append(str(path))

    print(f"{form_id}: {items} items on pages {pages}")
    for path in written:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
