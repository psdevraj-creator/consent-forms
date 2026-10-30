"""Render the parts of a filled form that need looking at.

Vision QA, per form: crop the patient block, the side-effect tick columns, the declaration
block and the signature so each can be inspected at 3x instead of squinting at a whole page.

Usage:
    python tools/qa_render.py <filled.pdf> <form_id> [--out sources/qa]
"""

from __future__ import annotations

import argparse
import json
import pathlib

import pypdfium2 as pdfium

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIELDS = ROOT / "assets" / "form_fields"
SCALE = 3.0
PAD = 26.0


def crop_box(page_height: float, top: float, bottom: float, width: float) -> tuple[float, float, float, float]:
    """PDF coordinates (y up) to image box (y down), with padding."""
    return (
        max(0.0, -PAD),
        max(0.0, page_height - top - PAD),
        width + PAD,
        min(page_height, page_height - bottom + PAD),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    parser.add_argument("form_id")
    parser.add_argument("--out", default="sources/qa")
    args = parser.parse_args()

    fields = json.loads((FIELDS / f"{args.form_id}.json").read_text(encoding="utf-8"))
    out_dir = ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    document = pdfium.PdfDocument(args.pdf)
    heights = {i + 1: page.get_height() for i, page in enumerate(document)}

    regions: list[tuple[str, int, float, float]] = []

    # Patient block: the page holding the name field.
    name = fields["fields"].get("full_name") or fields["fields"].get("surname")
    if name:
        regions.append(("patient", name["page"], name["y"] + 120.0, name["y"] - 70.0))

    # Tick columns: from the first to the last side effect on each page.
    pages = sorted({item["page"] for item in fields["side_effects"]})
    for page in pages[:3]:
        ys = [item["y"] for item in fields["side_effects"] if item["page"] == page]
        if ys:
            regions.append((f"ticks-p{page}", page, max(ys) + 30.0, min(ys) - 12.0))

    # Declarations.
    pages = sorted({item["page"] for item in fields["statements"]})
    for page in pages:
        ys = [item["y"] for item in fields["statements"] if item["page"] == page]
        if ys:
            regions.append((f"declarations-p{page}", page, max(ys) + 26.0, min(ys) - 14.0))

    # Signature.
    signature = fields.get("signature")
    if signature:
        regions.append(
            (
                "signature",
                signature["page"],
                signature["y"] + signature["height"] + 20.0,
                signature["y"] - 24.0,
            )
        )

    for label, page_number, top, bottom in regions:
        page = document[page_number - 1]
        width = page.get_width()
        image = page.render(scale=SCALE).to_pil()
        box = crop_box(heights[page_number], top, bottom, width)
        left, upper = int(box[0] * SCALE), int(box[1] * SCALE)
        right, lower = int(box[2] * SCALE), int(box[3] * SCALE)
        crop = image.crop((left, upper, right, lower))
        target = out_dir / f"{args.form_id}-{label}.png"
        crop.save(target)
        print(f"{target.relative_to(ROOT)}  {crop.size[0]}x{crop.size[1]}")


if __name__ == "__main__":
    main()
