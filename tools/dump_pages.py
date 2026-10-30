"""Dump the side-effect pages of each consent form as one-cell-per-line text.

The CRUK forms use two equal text columns; the RCR forms use a narrow frequency-band
column plus a wide content column. Both are flattened here into rows separated by `||`
so the reading order matches the printed page instead of the PDF's internal ordering.
"""

from __future__ import annotations

import pathlib
import re

import pdfplumber

ROOT = pathlib.Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "sources" / "pdf"
OUT_DIR = ROOT / "sources" / "clean"

LINE_TOLERANCE = 3.5
CELL_GAP = 18.0
# Left edge of the text columns: 62pt for the left of a CRUK page, 325pt for the
# right. RCR puts its frequency band in a 40-145pt strip.
CRUK_SPLIT = 300.0
RCR_SPLIT = 145.0

SIDE_EFFECT_MARKERS = re.compile(r"side[-\s]?effects?", re.IGNORECASE)


def rows_for_page(page) -> list[list[tuple[float, str]]]:
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    if not words:
        return []
    buckets: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (round(w["top"], 1), w["x0"])):
        if buckets and abs(word["top"] - buckets[-1][0]["top"]) <= LINE_TOLERANCE:
            buckets[-1].append(word)
        else:
            buckets.append([word])

    rows: list[list[tuple[float, str]]] = []
    for bucket in buckets:
        bucket.sort(key=lambda w: w["x0"])
        cells: list[list[dict]] = [[bucket[0]]]
        for previous, word in zip(bucket, bucket[1:]):
            if word["x0"] - previous["x1"] > CELL_GAP:
                cells.append([word])
            else:
                cells[-1].append(word)
        rows.append(
            [(cell[0]["x0"], " ".join(w["text"] for w in cell).strip()) for cell in cells]
        )
    return rows


def flatten(rows: list[list[tuple[float, str]]], split: float) -> list[str]:
    """Emit one line per page row: left cell, then right cell, joined by `||`."""
    out: list[str] = []
    for row in rows:
        left = " ".join(text for x0, text in row if x0 < split).strip()
        right = " ".join(text for x0, text in row if x0 >= split).strip()
        if left or right:
            out.append(f"{left} || {right}".strip(" |"))
    return out


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for pdf_path in sorted(PDF_DIR.glob("*.pdf")):
        split = CRUK_SPLIT if pdf_path.stem.startswith("sact") else RCR_SPLIT
        pages: list[list[str]] = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                pages.append(flatten(rows_for_page(page), split))

        # Keep from the first page that mentions side effects, and drop the boilerplate
        # footer that repeats on every page.
        start = next(
            (
                index
                for index, lines in enumerate(pages)
                if any(SIDE_EFFECT_MARKERS.search(line) for line in lines)
            ),
            len(pages) - 1,
        )
        kept: list[str] = []
        for index in range(start, len(pages)):
            kept.append(f"--- page {index + 1} ---")
            for line in pages[index]:
                if "TO BE RETAINED IN THE PATIENT" in line or "for latest version" in line:
                    continue
                kept.append(line)

        target = OUT_DIR / f"{pdf_path.stem}.txt"
        target.write_text("\n".join(kept) + "\n", encoding="utf-8")
        print(f"{pdf_path.stem:<28} {len(kept)} lines -> {target.name}")


if __name__ == "__main__":
    main()
