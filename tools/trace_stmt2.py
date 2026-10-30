"""Trace the statement-collection decisions. (diagnostic)"""

from __future__ import annotations

import pathlib
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import pdfplumber

from draft_form_fields import (
    STATEMENT_START,
    STATEMENT_STOP,
    page_rows,
)


def main() -> int:
    path = pathlib.Path(sys.argv[1])
    collecting = False
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages[:1], 1):
            for row in page_rows(page.extract_words(), page.width, page.rects):
                text = " ".join(word["text"] for word in row["words"]).strip()
                if STATEMENT_START.search(text):
                    collecting = True
                    print(f"START at {text[:40]!r}")
                if STATEMENT_STOP.match(text):
                    collecting = False
                    print(f"STOP  at {text[:40]!r}")
                if collecting:
                    print(
                        f"   {'BOX' if row['bullet'] else '   '} x={row['words'][0]['x0']:6.1f}"
                        f" {text[:64]!r}"
                    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
