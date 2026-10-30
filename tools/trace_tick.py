"""Print the verifier's view of one tick. (diagnostic)

    python tools/trace_tick.py <form id> <item index>
"""

from __future__ import annotations

import json
import pathlib
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import pdfplumber

from verify_forms import FORMS, rows_from


def main() -> int:
    form_id = sys.argv[1]
    index = int(sys.argv[2]) if len(sys.argv) > 2 else 0

    bundle = json.loads((FORMS / f"{form_id}.json").read_text(encoding="utf-8"))
    items = [item for group in bundle["groups"] for item in group["items"]]
    tick = bundle["side_effects"][index]
    print(f"item {index}: page={tick['page']} box=({tick['box_x']},{tick['box_y']})")
    print(f"   text: {items[index][:70]}")

    with pdfplumber.open(FORMS / f"{form_id}.pdf") as pdf:
        page = pdf.pages[tick["page"] - 1]
        height = page.height
        rows = rows_from(page.extract_words(), page.rects)
        print(f"   page height {height}, {len(rows)} rows")
        for row in rows:
            bullet = row["bullet"]
            if not bullet:
                continue
            cy = height - (bullet["top"] + (bullet["bottom"] - bullet["top"]) / 2.0)
            cx = bullet["x0"] + (bullet["x1"] - bullet["x0"]) / 2.0
            delta = abs(cy - tick["box_y"])
            if delta < 300:
                print(
                    f"     box at ({cx:6.1f},{cy:6.1f}) delta={delta:6.1f} "
                    f"col={'L' if row['words'][0]['x0'] < 595.28 / 2 else 'R'} "
                    f"{row['squashed'][:44]!r}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
