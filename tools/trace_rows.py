"""Trace how one PDF's side effects are extracted. (diagnostic)"""

from __future__ import annotations

import pathlib
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import pdfplumber

from import_all import clean_text, page_rows


def main() -> None:
    path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "forms/skin-chop-21.pdf")
    page_number = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[page_number - 1]
        for row in page_rows(page.extract_words(), page.width, page.rects):
            full = clean_text(" ".join(word["text"] for word in row["words"]))
            print(f"{'BOX' if row['bullet'] else '   '} top={row['top']:6.1f} {full[:88]}")


if __name__ == "__main__":
    main()
