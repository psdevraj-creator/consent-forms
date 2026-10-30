"""Render a proof with a second PDF engine (MuPDF) to check the ticks really draw.

Chrome, Edge and my pixel checks all use PDFium. If a hospital viewer is built on something
else, a content stream that PDFium tolerates could vanish there. This renders the same page
with MuPDF and with PDFium and compares the ink, so a difference shows up here rather than on
paper.

    python tools/verify_second_engine.py [form id ...]
"""

from __future__ import annotations

import pathlib
import sys
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pymupdf

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROOFS = ROOT / "target" / "proofs"
OUT = ROOT / "target" / "engine"
SCALE = 2.0


def ink(image: np.ndarray) -> int:
    return int((image < 160).sum())


def main() -> int:
    names = sys.argv[1:] or ["breast-ac-docetaxel", "skin-chop-21", "melanoma-skin-ipilimumab"]
    OUT.mkdir(parents=True, exist_ok=True)
    worst = 0.0
    for name in names:
        path = PROOFS / f"{name}.pdf"
        original_path = ROOT / "forms" / f"{name}.pdf"
        if not path.exists() or not original_path.exists():
            print(f"{name}: missing proof or original")
            continue

        import json

        bundle = json.loads((ROOT / "forms" / f"{name}.json").read_text(encoding="utf-8"))
        pages = sorted({t["page"] for t in bundle["side_effects"] if t.get("page")})
        drawn = 0
        missing = 0
        for page_number in pages:
            doc = pymupdf.open(path)
            page = doc[page_number - 1]
            pix = page.get_pixmap(matrix=pymupdf.Matrix(SCALE, SCALE), colorspace=pymupdf.csGRAY)
            new = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)

            old_doc = pymupdf.open(original_path)
            old_page = old_doc[page_number - 1]
            old_pix = old_page.get_pixmap(
                matrix=pymupdf.Matrix(SCALE, SCALE), colorspace=pymupdf.csGRAY
            )
            old = np.frombuffer(old_pix.samples, dtype=np.uint8).reshape(
                old_pix.height, old_pix.width
            )
            if new.shape != old.shape:
                continue
            added = (old.astype(int) - new.astype(int)) > 60
            height = new.shape[0]
            for tick in bundle["side_effects"]:
                if tick.get("page") != page_number:
                    continue
                x, y = tick.get("box_x"), tick.get("box_y")
                if x is None or y is None:
                    continue
                cx = int(x * SCALE)
                cy = int((height / SCALE - y) * SCALE)
                window = added[max(0, cy - 14) : cy + 14, max(0, cx - 14) : cx + 14]
                if window.sum() >= 8:
                    drawn += 1
                else:
                    missing += 1
        print(f"{name:34s} ticks drawn in MuPDF: {drawn}, missing: {missing}")
        if missing:
            worst = 1.0
    print("\nMuPDF renders every tick." if not worst else "\nSOME TICKS DO NOT RENDER")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
