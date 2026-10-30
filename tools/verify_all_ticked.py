"""Every checkbox the form prints must be ticked in the proof.

`verify_boxes.py` proves each tick lands on a real box. This proves the reverse: each box the
form prints inside the side-effect section receives a tick. Together they show the app knows
about exactly the checkboxes the form offers — nothing invented, nothing left out.

The proofs are written by the `write_all_proofs` test, which ticks every side effect and every
declaration, so an empty box is a side effect the app is missing.

Usage:
    python tools/verify_all_ticked.py [--only <id fragment> ...]
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import re
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import numpy as np
import pdfplumber
import pypdfium2 as pdfium
from draft_form_fields import page_rows

ROOT = pathlib.Path(__file__).resolve().parent.parent
FORMS = ROOT / "forms"
PROOFS = ROOT / "target" / "proofs"
REPORTS = ROOT / "reports"
SCALE = 2.0
INK_WINDOW = 6  # points around the box centre

# Boxes that belong to the professional statement rather than the side-effect list.
NOT_A_SIDE_EFFECT = re.compile(
    r"^(yes|no|notavailable|otherpleasestate|cyes|cno|date|time|"
    r"patientidentifierlabel|tickifapplicable)"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", default=[])
    args = parser.parse_args()

    REPORTS.mkdir(exist_ok=True)
    paths = sorted(FORMS.glob("*.json"))
    if args.only:
        paths = [path for path in paths if any(f in path.stem for f in args.only)]

    rows = []
    for path in paths:
        bundle = json.loads(path.read_text(encoding="utf-8"))
        pages = sorted({tick["page"] for tick in bundle.get("side_effects", []) if tick.get("page")})
        proof = PROOFS / f"{path.stem}.pdf"
        pdf_path = FORMS / f"{path.stem}.pdf"
        if not proof.exists() or not pdf_path.exists():
            rows.append({"id": path.stem, "pass": False, "boxes": 0, "empty": "no proof"})
            continue

        empty: list[str] = []
        checked = 0
        images: dict[int, np.ndarray] = {}
        proof_doc = pdfium.PdfDocument(str(proof))

        with pdfplumber.open(pdf_path) as pdf:
            for page_number in pages:
                page = pdf.pages[page_number - 1]
                if page_number not in images:
                    rendered = proof_doc[page_number - 1].render(scale=SCALE).to_pil().convert("L")
                    images[page_number] = np.array(rendered)
                image = images[page_number]
                height_px = image.shape[0]

                for row in page_rows(page.extract_words(), page.width, page.rects):
                    bullet = row["bullet"]
                    if not bullet:
                        continue
                    if NOT_A_SIDE_EFFECT.match(row["squashed"]):
                        continue
                    cx = bullet["x0"] + (bullet["x1"] - bullet["x0"]) / 2.0
                    cy = page.height - (bullet["top"] + (bullet["bottom"] - bullet["top"]) / 2.0)
                    checked += 1
                    px = int(cx * SCALE)
                    py = int((height_px / SCALE - cy) * SCALE)
                    half = int(INK_WINDOW * SCALE)
                    window = image[max(0, py - half) : py + half, max(0, px - half) : px + half]
                    if window.size == 0 or (window < 160).sum() < 8:
                        empty.append(f"page {page_number}: {row['squashed'][:40]}")

        rows.append(
            {
                "id": path.stem,
                "pass": not empty,
                "boxes": checked,
                "empty": " | ".join(empty[:4]),
            }
        )

    with (REPORTS / "all_ticked.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "pass", "boxes", "empty"])
        writer.writeheader()
        writer.writerows(rows)

    failures = [row for row in rows if not row["pass"]]
    total_boxes = sum(row["boxes"] for row in rows)
    print(f"forms checked  : {len(rows)}")
    print(f"printed boxes  : {total_boxes}")
    print(f"forms passed   : {len(rows) - len(failures)}")
    print(f"forms failed   : {len(failures)}")
    for row in failures[:15]:
        print("  ", row["id"], "->", row["empty"].encode("ascii", "replace").decode()[:70])


if __name__ == "__main__":
    main()
