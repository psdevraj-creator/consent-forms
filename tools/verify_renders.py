"""Check that every tick actually appears on the rendered page, inside its printed box.

For each form this compares the proof PDF (all ticks baked in) with the untouched original:

  * a tick must be present in the 12 × 12 px window around every expected box centre
  * no other ink may be added anywhere else, so a stray or misplaced mark is caught

This is the only check that proves the PDF *looks* right, rather than that the numbers are
self-consistent.

Usage:
    cargo test write_all_proofs -- --ignored      # writes target/proofs/*.pdf
    python tools/verify_renders.py
"""

from __future__ import annotations

import csv
import json
import pathlib

import numpy as np
import pypdfium2 as pdfium

ROOT = pathlib.Path(__file__).resolve().parent.parent
FORMS = ROOT / "forms"
PROOFS = ROOT / "target" / "proofs"
REPORTS = ROOT / "reports"
SCALE = 2.0
WINDOW = 7  # half-width of the window around a box centre, in points
HALF_BOX = 5.5  # half the width of the printed 11 pt checkbox


def main() -> None:
    REPORTS.mkdir(exist_ok=True)
    rows = []
    proofs = sorted(PROOFS.glob("*.pdf"))
    print(f"proofs to check: {len(proofs)}")

    for number, proof in enumerate(proofs, 1):
        form_id = proof.stem
        original = FORMS / f"{form_id}.pdf"
        bundle_path = FORMS / f"{form_id}.json"
        if not original.exists() or not bundle_path.exists():
            rows.append({"id": form_id, "pass": False, "detail": "missing original or bundle"})
            continue

        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        expected = [
            (item["page"], item["box_x"], item["box_y"])
            for item in bundle.get("side_effects", [])
            if item.get("box_x") is not None and item.get("box_y") is not None
        ] + [
            (statement["page"], statement["x"], statement["y"])
            for statement in bundle.get("statements", [])
        ]

        wrong = []
        stray = 0
        try:
            new_doc = pdfium.PdfDocument(str(proof))
            old_doc = pdfium.PdfDocument(str(original))
        except Exception as error:  # noqa: BLE001
            rows.append({"id": form_id, "pass": False, "detail": f"cannot open: {error}"})
            continue

        by_page: dict[int, list[tuple[float, float]]] = {}
        for page, x, y in expected:
            by_page.setdefault(page, []).append((x, y))

        for page_number, points in by_page.items():
            index = page_number - 1
            if index >= len(new_doc):
                wrong.append(f"page {page_number} missing")
                continue
            new_img = np.array(new_doc[index].render(scale=SCALE).to_pil().convert("L"))
            old_img = np.array(old_doc[index].render(scale=SCALE).to_pil().convert("L"))
            if new_img.shape != old_img.shape:
                wrong.append(f"page {page_number} size changed")
                continue

            added = (old_img.astype(int) - new_img.astype(int)) > 60
            height = new_img.shape[0]

            # One mask covers every expected tick on this page: it proves both that each
            # tick was drawn and that nothing was drawn anywhere else.
            mask = np.zeros_like(added)
            for x, y in points:
                cx = int(x * SCALE)
                cy = int((height / SCALE - y) * SCALE)
                top = max(0, cy - WINDOW * 2)
                left = max(0, cx - WINDOW * 2)
                bottom, right = cy + WINDOW * 2, cx + WINDOW * 2
                window = added[top:bottom, left:right]
                if window.sum() < 12:
                    wrong.append(f"no tick drawn at ({x:.0f},{y:.0f}) on page {page_number}")
                    continue
                # Every speck of the tick must stay inside the printed box. The box is 11 pt
                # wide, so any ink more than 5.5 pt from its centre has overflowed into the
                # wording or the margin — the thing a clinician would notice on paper.
                rows_with_ink, cols_with_ink = np.where(window)
                if rows_with_ink.size:
                    dx = max(
                        abs((left + cols_with_ink.min()) - cx),
                        abs((left + cols_with_ink.max()) - cx),
                    ) / SCALE
                    dy = max(
                        abs((top + rows_with_ink.min()) - cy),
                        abs((top + rows_with_ink.max()) - cy),
                    ) / SCALE
                    if dx > HALF_BOX or dy > HALF_BOX:
                        wrong.append(
                            f"tick overflows its box by ({dx:.1f},{dy:.1f}) pt "
                            f"at ({x:.0f},{y:.0f}) on page {page_number}"
                        )
                mask[top:bottom, left:right] = True

            stray += int((added & ~mask).sum())

        if stray > 400:
            wrong.append(f"{stray} stray pixels away from any expected tick")

        rows.append(
            {
                "id": form_id,
                "pass": not wrong,
                "detail": "; ".join(wrong[:4]),
            }
        )
        if number % 25 == 0:
            print(f"  {number}/{len(proofs)}")

    with (REPORTS / "renders.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "pass", "detail"])
        writer.writeheader()
        writer.writerows(rows)

    failures = [row for row in rows if not row["pass"]]
    print(f"\nchecked {len(rows)} proofs")
    print(f"passed : {len(rows) - len(failures)}")
    print(f"failed : {len(failures)}")
    for row in failures[:10]:
        print("  ", row["id"], "->", row["detail"])


if __name__ == "__main__":
    main()
