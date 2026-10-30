"""Replicate extract_side_effects with per-row decisions printed. (diagnostic)"""

from __future__ import annotations

import pathlib
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import pdfplumber

from import_all import HEADINGS, SKIP_TEXT, STOP_TEXT, clean_text, page_rows


def main() -> int:
    path = pathlib.Path(sys.argv[1])
    groups: dict[str, list[str]] = {}
    current: str | None = None
    joined_previous: str | None = None

    with pdfplumber.open(path) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            for row in page_rows(page.extract_words(), page.width, page.rects):
                body = clean_text(
                    " ".join(
                        word["text"]
                        for word in (row["words"][1:] if row["glyph"] else row["words"])
                    )
                )
                full = clean_text(" ".join(word["text"] for word in row["words"]))
                heading = next((name for pattern, name in HEADINGS if pattern.match(full)), None)
                action = ""
                if heading:
                    current = heading
                    joined_previous = None
                    groups.setdefault(current, [])
                    action = f"HEADING->{heading}"
                elif current is None:
                    action = "skipped (no group)"
                elif STOP_TEXT.match(full):
                    current = None
                    joined_previous = None
                    action = "STOP"
                elif SKIP_TEXT.match(full):
                    joined_previous = None
                    action = "SKIP"
                elif row["bullet"] and body:
                    if body[:1].islower() and groups.get(current):
                        groups[current][-1] = f"{groups[current][-1]} {body}".strip()
                        joined_previous = groups[current][-1]
                        action = f"merged into {current}"
                    else:
                        groups[current].append(body)
                        joined_previous = body
                        action = f"NEW item in {current}"
                elif joined_previous and full:
                    groups[current][-1] = f"{groups[current][-1]} {full}".strip()
                    action = f"appended to {current}"
                if page_number == int(sys.argv[2]) if len(sys.argv) > 2 else False:
                    print(f"  x={row['words'][0]['x0']:6.1f} {action:26s} {full[:50]!r}")

    print({name: len(items) for name, items in groups.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
