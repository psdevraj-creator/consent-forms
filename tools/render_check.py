"""Render one page of a proof PDF to PNG so a human (or a vision model) can look at it.

    python tools/render_check.py <form id> <page> [scale]
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
    page_number = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    scale = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0

    OUT.mkdir(parents=True, exist_ok=True)
    doc = pdfium.PdfDocument(str(PROOFS / f"{form_id}.pdf"))
    image = doc[page_number - 1].render(scale=scale).to_pil()
    path = OUT / f"{form_id}-p{page_number}.png"
    image.save(path)
    print(f"{path}  {image.width}x{image.height}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
