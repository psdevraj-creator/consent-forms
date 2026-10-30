"""Column-aware extraction of side-effect lists from the downloaded consent-form PDFs.

`pdfplumber`'s default text extraction interleaves the two columns of a CRUK form, which
scrambles the bullet order. This script rebuilds each column separately using word
x-coordinates, splits the result into bullets, and writes a reviewable draft.

Outputs:
    sources/draft/<id>.json   structured draft, one file per form
    sources/draft/<id>.txt    cleaned column text, for eyeballing against the PDF

Nothing here is published automatically: `assets/consent_forms.json` is authored from
these drafts after a human reads them.
"""

from __future__ import annotations

import json
import pathlib
import re
import statistics

import pdfplumber

ROOT = pathlib.Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "sources" / "pdf"
DRAFT_DIR = ROOT / "sources" / "draft"

# Words closer together than this on the same baseline belong to the same line.
LINE_TOLERANCE = 3.5
# A horizontal gap wider than this means a new column/cell starts.
CELL_GAP = 18.0


def page_lines(page) -> list[dict]:
    """Rebuild visual lines, each split into cells separated by wide horizontal gaps."""
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False, extra_attrs=["size"])
    if not words:
        return []

    rows: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (round(w["top"], 1), w["x0"])):
        if rows and abs(word["top"] - rows[-1][0]["top"]) <= LINE_TOLERANCE:
            rows[-1].append(word)
        else:
            rows.append([word])

    lines = []
    for row in rows:
        row.sort(key=lambda w: w["x0"])
        cells: list[list[dict]] = [[row[0]]]
        for previous, word in zip(row, row[1:]):
            if word["x0"] - previous["x1"] > CELL_GAP:
                cells.append([word])
            else:
                cells[-1].append(word)
        lines.append(
            {
                "top": row[0]["top"],
                "cells": [
                    {
                        "x0": cell[0]["x0"],
                        "text": " ".join(w["text"] for w in cell).strip(),
                    }
                    for cell in cells
                ],
            }
        )
    return lines


def column_split(page, lines: list[dict]) -> float:
    """Guess the x boundary between the label column and the content column."""
    starts = sorted(cell["x0"] for line in lines for cell in line["cells"])
    if len(starts) < 4:
        return page.width / 2
    # The two most common left edges are the two column starts; the boundary sits
    # between the smaller one and the larger one.
    rounded = [round(x / 4) * 4 for x in starts]
    counts: dict[float, int] = {}
    for value in rounded:
        counts[value] = counts.get(value, 0) + 1
    top = sorted(counts, key=lambda k: -counts[k])[:4]
    left = min(top)
    right = max(top)
    if right - left < 40:
        return page.width / 2
    return (left + right) / 2


def read_column(lines: list[dict], low: float, high: float) -> list[str]:
    """Join the cells that fall inside [low, high) into text lines, in reading order."""
    out: list[str] = []
    for line in lines:
        text = " ".join(
            cell["text"] for cell in line["cells"] if low <= cell["x0"] < high
        ).strip()
        if text:
            out.append(text)
    return out


def is_bullet(line: str) -> bool:
    """CRUK bullets are drawn with a symbol font that extracts as a leading `c`."""
    return bool(re.match(r"^[cC•·]\s+\S", line))


def join_wrapped(lines: list[str]) -> list[str]:
    """Merge continuation lines into the bullet they belong to."""
    items: list[str] = []
    for line in lines:
        if is_bullet(line):
            items.append(re.sub(r"^[cC•·]\s+", "", line).strip())
        elif items:
            items[-1] = f"{items[-1]} {line}".strip()
        else:
            items.append(line.strip())
    return [re.sub(r"\s+", " ", item).strip() for item in items]


HEADING_PATTERNS = [
    (r"common side effects", "Common side effects"),
    (r"occasional side effects", "Occasional side effects"),
    (r"other risks", "Other risks"),
    (r"early[/ ]short[- ]term side[- ]effects", "Early / short-term side effects"),
    (r"late or long[- ]term side[- ]effects", "Late / long-term side effects"),
]


def split_sections(lines: list[str]) -> list[dict]:
    """Group content lines under the most recent recognised heading."""
    sections: list[dict] = []
    current = {"heading": "Side effects", "items": []}
    for line in lines:
        matched = next(
            (label for pattern, label in HEADING_PATTERNS if re.match(pattern, line, re.I)),
            None,
        )
        if matched:
            if current["items"]:
                sections.append(current)
            current = {"heading": matched, "items": []}
            continue
        current["items"].append(line)
    if current["items"]:
        sections.append(current)
    return sections


def main() -> None:
    DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    for pdf_path in sorted(PDF_DIR.glob("*.pdf")):
        form_id = pdf_path.stem
        column_lines: list[str] = []
        content_lines: list[str] = []

        with pdfplumber.open(pdf_path) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                lines = page_lines(page)
                boundary = column_split(page, lines)
                label_column = read_column(lines, 0, boundary)
                column_lines.append(f"--- page {page_number} | labels ---\n" + "\n".join(label_column))
                body = read_column(lines, boundary, page.width + 1)
                column_lines.append(f"--- page {page_number} | body ---\n" + "\n".join(body))
                content_lines.extend(body)

        (DRAFT_DIR / f"{form_id}.txt").write_text("\n".join(column_lines), encoding="utf-8")

        joined = join_wrapped(content_lines)
        sections = split_sections(joined)
        (DRAFT_DIR / f"{form_id}.json").write_text(
            json.dumps({"id": form_id, "sections": sections}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        total = sum(len(section["items"]) for section in sections)
        print(f"{form_id:<28} {len(sections)} sections, {total} candidate items")
        sizes = [len(item) for section in sections for item in section["items"]]
        if sizes:
            print(f"   median item length {statistics.median(sizes):.0f} chars, longest {max(sizes)}")


if __name__ == "__main__":
    main()
