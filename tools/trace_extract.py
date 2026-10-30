"""Trace extraction decisions for one page. (diagnostic)

    python tools/trace_extract.py <pdf> <page>
"""

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
    page_number = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[page_number - 1]
        rows = page_rows(page.extract_words(), page.width, page.rects)
        print(f"page width {page.width} mid {page.width / 2:.2f} rows {len(rows)}")
        for row in rows:
            full = clean_text(" ".join(word["text"] for word in row["words"]))
            heading = next((name for pattern, name in HEADINGS if pattern.match(full)), None)
            decisions = []
            if heading:
                decisions.append(f"HEADING {heading}")
            if STOP_TEXT.match(full):
                decisions.append("STOP")
            if SKIP_TEXT.match(full):
                decisions.append("SKIP")
            decisions.append("BULLET" if row["bullet"] else "no-box")
            print(f"  x={row['words'][0]['x0']:6.1f} top={row['top']:6.1f} "
                  f"{','.join(decisions):22s} {full[:60]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
