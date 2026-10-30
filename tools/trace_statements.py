"""Trace statement detection on one page. (diagnostic)"""

from __future__ import annotations

import pathlib
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import pdfplumber

from draft_form_fields import STATEMENT_START, TREATMENT_START, page_rows


def main() -> int:
    path = pathlib.Path(sys.argv[1])
    page_number = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[page_number - 1]
        for row in page_rows(page.extract_words(), page.width, page.rects):
            text = " ".join(word["text"] for word in row["words"]).strip()
            marks = []
            if row["bullet"]:
                marks.append("BOX")
            if STATEMENT_START.search(text):
                marks.append("START")
            if TREATMENT_START.search(text):
                marks.append("TREAT")
            print(f"{','.join(marks) or '   ':12s} x={row['words'][0]['x0']:6.1f} {text[:70]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
