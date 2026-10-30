"""Build contact sheets so every form can be looked at, not just sampled.

Each sheet shows twelve forms' side-effect pages side by side, small but large enough to see
whether a tick sits in its printed box or floats in the text. Sheets are numbered so a review
can be recorded per sheet.

Usage:
    python tools/contact_sheets.py [--per-sheet 12] [--scale 0.62]
"""

from __future__ import annotations

import argparse
import json
import pathlib

import pypdfium2 as pdfium
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
FORMS = ROOT / "forms"
PROOFS = ROOT / "target" / "proofs"
OUT = ROOT / "target" / "sheets"


def side_effect_pages(bundle: dict) -> list[int]:
    pages = sorted({tick["page"] for tick in bundle.get("side_effects", []) if tick.get("page")})
    return pages or [2]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-sheet", type=int, default=12)
    parser.add_argument("--scale", type=float, default=0.62)
    parser.add_argument("--only", nargs="*", default=[])
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("sheet-*.png"):
        old.unlink()

    forms = sorted(FORMS.glob("*.json"))
    if args.only:
        forms = [path for path in forms if any(f in path.stem for f in args.only)]

    cells = []
    for path in forms:
        bundle = json.loads(path.read_text(encoding="utf-8"))
        proof = PROOFS / f"{path.stem}.pdf"
        if not proof.exists():
            continue
        doc = pdfium.PdfDocument(str(proof))
        page_number = side_effect_pages(bundle)[0]
        image = doc[page_number - 1].render(scale=args.scale).to_pil().convert("RGB")
        cells.append((path.stem, image))

    columns = 4
    per_sheet = args.per_sheet
    width = max(image.width for _, image in cells)
    height = max(image.height for _, image in cells)

    sheet_index = 0
    for start in range(0, len(cells), per_sheet):
        chunk = cells[start : start + per_sheet]
        rows = (len(chunk) + columns - 1) // columns
        sheet = Image.new("RGB", (columns * width, rows * height), "white")
        for position, (_, image) in enumerate(chunk):
            x = (position % columns) * width
            y = (position // columns) * height
            sheet.paste(image, (x, y))
        sheet_index += 1
        sheet.save(OUT / f"sheet-{sheet_index:03d}.png")
        print(f"sheet-{sheet_index:03d}.png  {len(chunk)} forms  first: {chunk[0][0]}")

    print(f"\n{len(cells)} forms on {sheet_index} sheets in {OUT}")


if __name__ == "__main__":
    raise SystemExit(main())
