"""Repair side effects that were given a tick position without a printed box.

The extractor's loose pass can match a wrapped continuation line, leaving an item with no
checkbox glyph to tick. This re-runs the match for those items only, preferring printed
bulleted rows, and writes the corrected position back into the bundle.

It also reports anything it cannot place, rather than inventing a position.

Usage:
    python tools/repair_positions.py
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import pdfplumber
from draft_form_fields import normalise, page_rows

ROOT = pathlib.Path(__file__).resolve().parent.parent
FORMS = ROOT / "forms"


def main() -> None:
    repaired = 0
    unfixable: list[str] = []

    for path in sorted(FORMS.glob("*.json")):
        bundle = json.loads(path.read_text(encoding="utf-8"))
        broken = [item for item in bundle.get("side_effects", []) if item.get("box_x") is None]
        if not broken:
            continue

        items = [text for group in bundle.get("groups", []) for text in group["items"]]
        pdf_path = FORMS / f"{path.stem}.pdf"
        if not pdf_path.exists():
            unfixable.append(f"{path.stem}: missing PDF")
            continue

        with pdfplumber.open(pdf_path) as pdf:
            heights = {number: page.height for number, page in enumerate(pdf.pages, 1)}
            rows_by_page = {
                number: page_rows(page.extract_words())
                for number, page in enumerate(pdf.pages, 1)
                if number > 1
            }

        used = {(item["page"], round(item.get("box_y") or -1)) for item in bundle["side_effects"]}

        for tick in broken:
            text = items[tick["index"]] if tick["index"] < len(items) else ""
            want = "".join(normalise(text))
            best: tuple[int, int, int] | None = None

            for number, rows in rows_by_page.items():
                for row_index, row in enumerate(rows):
                    if row["bullet"] is None:
                        continue
                    if (number, round(heights[number] - row["top"] - 4.7)) in used:
                        continue
                    candidate = row["squashed"]
                    common = 0
                    for left, right in zip(want, candidate):
                        if left != right:
                            break
                        common += 1
                    if common >= 14 and (best is None or common > best[0]):
                        best = (common, number, row_index)

            if best is None:
                unfixable.append(f"{path.stem}: item {tick['index']} ({text[:40]})")
                continue

            _, number, row_index = best
            row = rows_by_page[number][row_index]
            bullet = row["bullet"]
            tick["page"] = number
            tick["box_x"] = round(bullet["x0"] + (bullet["x1"] - bullet["x0"]) / 2.0, 2)
            tick["box_y"] = round(
                heights[number] - (bullet["top"] + (bullet["bottom"] - bullet["top"]) / 2.0), 2
            )
            tick["y"] = round(heights[number] - row["top"] - 6.0, 2)
            tick["text_x"] = round(row["text_x"], 2)
            used.add((number, round(heights[number] - row["top"] - 4.7)))
            repaired += 1

        path.write_text(json.dumps(bundle, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"repaired {repaired} tick positions")
    if unfixable:
        print(f"could not repair {len(unfixable)}:")
        for line in unfixable[:20]:
            print("  ", line)


if __name__ == "__main__":
    main()
