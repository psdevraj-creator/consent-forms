"""Crop a region of a proof page so a tick can be inspected closely.

    python tools/crop_check.py <form id> <page> <left> <top> <right> <bottom> [scale]
"""

from __future__ import annotations

import pathlib
import sys

import pypdfium2 as pdfium

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROOFS = ROOT / "target" / "proofs"
OUT = ROOT / "target" / "look"


def main() -> int:
    form_id = sys.argv[1]
    page_number = int(sys.argv[2])
    left, top, right, bottom = (float(value) for value in sys.argv[3:7])
    scale = float(sys.argv[7]) if len(sys.argv) > 7 else 2.0

    image = pdfium.PdfDocument(str(PROOFS / f"{form_id}.pdf"))[page_number - 1]
    image = image.render(scale=scale).to_pil()
    crop = image.crop(
        (int(left * scale), int(top * scale), int(right * scale), int(bottom * scale))
    )
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{form_id}-p{page_number}-crop.png"
    crop.save(path)
    print(f"{path}  {crop.width}x{crop.height}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
