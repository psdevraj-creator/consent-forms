"""Prove that every tick sits on a checkbox the form actually prints.

`verify_renders.py` proves ink lands inside a small window; it cannot tell whether a box is
printed there at all — a tick in blank paper passes. This walks every form, every tick, and
requires a real printed checkbox (symbol-font glyph or drawn square) within a fraction of a
point of the tick's centre.

Usage:
    python tools/verify_boxes.py [--only <id fragment> ...]
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import pdfplumber
from draft_form_fields import box_rectangles, page_rows

ROOT = pathlib.Path(__file__).resolve().parent.parent
FORMS = ROOT / "forms"
REPORTS = ROOT / "reports"
TOLERANCE = 0.6  # points


def printed_boxes(page: pdfplumber.page.Page) -> list[tuple[float, float]]:
    """Centres of every checkbox the page prints."""
    centres: list[tuple[float, float]] = []
    for row in page_rows(page.extract_words(), page.width, page.rects):
        bullet = row["bullet"]
        if not bullet:
            continue
        centres.append(
            (
                bullet["x0"] + (bullet["x1"] - bullet["x0"]) / 2.0,
                page.height - (bullet["top"] + (bullet["bottom"] - bullet["top"]) / 2.0),
            )
        )
    for square in box_rectangles(page.rects):
        centres.append(
            (
                square["x0"] + (square["x1"] - square["x0"]) / 2.0,
                page.height - (square["top"] + (square["bottom"] - square["top"]) / 2.0),
            )
        )
    return centres


def check(path: pathlib.Path) -> dict:
    bundle = json.loads(path.read_text(encoding="utf-8"))
    pdf_path = FORMS / f"{path.stem}.pdf"
    result = {"id": path.stem, "pass": True, "ticks": 0, "errors": []}
    if not pdf_path.exists():
        result["pass"] = False
        result["errors"].append("missing PDF")
        return result

    with pdfplumber.open(pdf_path) as pdf:
        cache: dict[int, list[tuple[float, float]]] = {}
        for tick in bundle.get("side_effects", []) + bundle.get("statements", []):
            x = tick.get("box_x", tick.get("x"))
            y = tick.get("box_y", tick.get("y"))
            page_number = tick.get("page")
            if x is None or y is None:
                result["pass"] = False
                result["errors"].append(f"item {tick.get('index')}: no position")
                continue
            result["ticks"] += 1
            if page_number not in cache:
                cache[page_number] = printed_boxes(pdf.pages[page_number - 1])
            centres = cache[page_number]
            if not centres:
                result["pass"] = False
                result["errors"].append(f"item {tick.get('index')}: page {page_number} prints no boxes")
                continue
            nearest = min(abs(cx - x) + abs(cy - y) for cx, cy in centres)
            if nearest > TOLERANCE:
                result["pass"] = False
                result["errors"].append(
                    f"item {tick.get('index')}: {nearest:.1f} pt from a printed box "
                    f"on page {page_number}"
                )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", default=[])
    args = parser.parse_args()

    REPORTS.mkdir(exist_ok=True)
    paths = sorted(FORMS.glob("*.json"))
    if args.only:
        paths = [path for path in paths if any(f in path.stem for f in args.only)]

    rows = [check(path) for path in paths]
    with (REPORTS / "boxes.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "pass", "ticks", "errors"])
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "errors": " | ".join(row["errors"])})

    failures = [row for row in rows if not row["pass"]]
    total_ticks = sum(row["ticks"] for row in rows)
    print(f"forms checked : {len(rows)}")
    print(f"ticks checked : {total_ticks}")
    print(f"forms passed  : {len(rows) - len(failures)}")
    print(f"forms failed  : {len(failures)}")
    for row in failures[:15]:
        print("  ", row["id"], "->", row["errors"][0].encode("ascii", "replace").decode())


if __name__ == "__main__":
    main()
