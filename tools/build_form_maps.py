"""Locate the fill-in positions on each official consent form.

The PDFs are flat (no AcroForm fields), so the app overlays text at fixed coordinates.
Those coordinates are found here rather than guessed: each label is located by its printed
text, and the writing position is taken to the right of it on the same baseline. Each side
effect is located by matching the first few words of its printed wording.

Output: assets/form_maps.json (coordinates in PDF space: origin bottom-left).

    {
      "sact-breast-ac-docetaxel": {
        "fields": {"full_name": {"page": 1, "x": 210, "y": 690, "size": 8, "max_width": 240}},
        "signature": {"page": 5, "x": 48, "y": 210, "width": 250, "height": 34},
        "ticks": [{"index": 3, "page": 2, "x": 60, "y": 705}],
        "free_text": {"page": 4, "x": 48, "y": 640, "width": 500}
      }
    }
"""

from __future__ import annotations

import json
import pathlib
import re

import pdfplumber

ROOT = pathlib.Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "sources" / "pdf"
CONTENT = ROOT / "sources" / "content.json"
OUTPUT = ROOT / "assets" / "form_maps.json"

PAGE_WIDTH = 595.28

# Matched anywhere in the printed row, because the forms put two labels on one line.
FIELD_ANCHORS = {
    # CRUK prints a narrow "surname" cell and a wide "first name(s)" rule, so the wider
    # line is used for the full name; RCR has a single "Patient name:" box.
    "full_name": [r"first name", r"surname|family name", r"patient name"],
    "date_of_birth": [r"date of birth"],
    "nhs_number": [r"nhs number", r"patient unique identifier"],
    "consultant": [r"responsible consultant"],
    "consent_date": [r"^date:"],
}
SIGNATURE_ANCHORS = [r"patient'?s? signature", r"signature:"]
FREE_TEXT_ANCHORS = [r"any other risks", r"specific risks to you from"]

# Statement blocks the health professional ticks, and where each block ends.
STATEMENT_START = re.compile(
    r"statement of health professional|any other risks and information", re.IGNORECASE
)
STATEMENT_STOP = re.compile(
    r"^(the intended benefits|patient information leaflet|clinical management guideline|"
    r"any other risks|statement of patient|specific risks to you from)",
    re.IGNORECASE,
)

MIN_WIDTH = {"full_name": 120.0, "consultant": 120.0}

# Where a tick goes: just left of a CRUK bullet, or in the gutter of an RCR frequency table.
RCR_TICK_X = 147.0



def rows_of(page) -> list[dict]:
    words = page.extract_words()
    rows: list[dict] = []
    for word in sorted(words, key=lambda w: (round(w["top"], 1), w["x0"])):
        if rows and abs(word["top"] - rows[-1]["top"]) <= 3.0:
            rows[-1]["words"].append(word)
        else:
            rows.append({"top": word["top"], "words": [word]})
    return rows


def is_rule(word: dict) -> bool:
    return set(word["text"]) == {"_"} and len(word["text"]) >= 3


def find_label(pages, patterns, start_page: int = 1) -> dict | None:
    """Find the printed label and work out where writing starts and how much room there is."""
    for number, rows in pages:
        if number < start_page:
            continue
        for row in rows:
            words = row["words"]
            for size in range(1, 6):
                for start in range(len(words) - size + 1):
                    text = " ".join(word["text"] for word in words[start : start + size]).lower()
                    if not any(re.search(pattern, text) for pattern in patterns):
                        continue

                    after = start + size
                    # The label often finishes with a word ending in ':' ("... family name:").
                    end = after - 1
                    while end + 1 < len(words):
                        nxt = words[end + 1]
                        if nxt["text"].endswith(":") and nxt["x0"] - words[end]["x1"] < 8.0:
                            end += 1
                        else:
                            break
                    following = words[end + 1] if end + 1 < len(words) else None
                    label_end = words[end]["x1"]
                    if following is not None and is_rule(following):
                        # Write on the printed rule, from its left end.
                        x = following["x0"] + 2.0
                        available = following["x1"] - x - 2.0
                    else:
                        x = label_end + 4.0
                        if following is None:
                            available = PAGE_WIDTH - 40.0 - x
                        elif following["x0"] - label_end > 120.0:
                            # The next word is in the other column; do not run into it.
                            available = min(PAGE_WIDTH - 40.0 - x, 260.0)
                        else:
                            available = following["x0"] - 4.0 - x

                    available = max(available, MIN_WIDTH.get(key_hint(patterns), 60.0))
                    available = min(available, PAGE_WIDTH - 40.0 - x)
                    # Narrow cells get smaller writing so a name or a date still fits.
                    size = 6.8 if available < 110.0 else 8.0
                    return {
                        "page": number,
                        "row": row,
                        "x": round(x, 2),
                        "max_width": round(max(available, 30.0), 2),
                        "size": size,
                    }
    return None


def key_hint(patterns: list[str]) -> str:
    for key, candidates in FIELD_ANCHORS.items():
        if candidates == patterns:
            return key
    return ""


def normalise(text: str) -> list[str]:
    return re.findall(r"[a-z0-9°]+", text.lower())


def find_sequence(haystack: list[str], needle: list[str]) -> int | None:
    if not needle:
        return None
    for start in range(max(len(haystack) - len(needle) + 1, 0)):
        if haystack[start : start + len(needle)] == needle:
            return start
    return None


def locate_ticks(page_words, content: dict, margin_x: float | None) -> list[dict]:
    ticks: list[dict] = []
    index = 0
    for group in content["groups"]:
        for item in group["items"]:
            needle = normalise(" ".join(item.split()[:4]))[:4]
            for number, (page, words) in page_words.items():
                if number == 1:
                    continue
                folded = [normalise(word["text"]) for word in words]
                flat = [token for tokens in folded for token in tokens]
                position = find_sequence(flat, needle)
                if position is None:
                    continue
                consumed = 0
                word_index = 0
                for local, tokens in enumerate(folded):
                    consumed += len(tokens)
                    if consumed > position:
                        word_index = local
                        break
                word = words[word_index]

                # Anchor on the printed bullet that precedes the item, not on the item's
                # own text: anchoring on the text put the tick on top of the first word.
                anchor = word["x0"]
                if word_index > 0:
                    previous = words[word_index - 1]
                    same_line = abs(previous["top"] - word["top"]) <= 3.0
                    is_bullet = len(previous["text"]) <= 2 and not previous["text"].isalnum()
                    if same_line and is_bullet:
                        anchor = previous["x0"]

                x = margin_x if margin_x is not None else anchor
                ticks.append(
                    {
                        "index": index,
                        "page": number,
                        "x": round(x, 2),
                        # Baseline, not the bottom of the glyph box: 'bottom' moves with
                        # descenders, which made neighbouring ticks sit at different heights.
                        "y": round(page.height - word["top"] - 6.0, 2),
                    }
                )
                break
            index += 1
    return ticks


def locate_statements(pages, heights) -> list[dict]:
    """Find the health professional's declaration lines and the bullet beside each."""
    statements: list[dict] = []
    collecting = False

    for number, rows in pages:
        for row in rows:
            words = row["words"]
            text = " ".join(word["text"] for word in words).strip()
            if not text:
                continue
            if STATEMENT_START.search(text):
                collecting = True
                continue
            if not collecting:
                continue
            if STATEMENT_STOP.match(text):
                collecting = False
                continue

            first = words[0]["text"]
            rest = " ".join(word["text"] for word in words[1:]).strip()
            is_bullet = first.lower() in {"c", "–", "-", "•"} or (
                len(first) == 1 and not first.isalnum()
            )
            if not is_bullet or not rest.lower().startswith("i "):
                continue

            statements.append(
                {
                    "index": len(statements),
                    "page": number,
                    "x": round(words[0]["x0"], 2),
                    "y": round(heights[number] - words[0]["top"] - 6.0, 2),
                    "text": rest,
                }
            )
    return statements


def snap_to_columns(marks: list[dict], page_heights: dict[int, float], margin: float = 0.0) -> None:
    """Put every mark on a page into the same gutter as the rest of its column.

    The forms use bullets that sit at slightly different x on each line; drawing at
    `x0 - 9` for each one produces a ragged edge. Clustering the x values per page and
    snapping to the column's left edge makes a single straight column of ticks.
    """
    by_page: dict[int, list[dict]] = {}
    for mark in marks:
        by_page.setdefault(mark["page"], []).append(mark)

    for _page, group in by_page.items():
        values = sorted(mark["x"] for mark in group)
        clusters: list[list[float]] = []
        for value in values:
            if clusters and value - clusters[-1][-1] <= 40.0:
                clusters[-1].append(value)
            else:
                clusters.append([value])

        for cluster in clusters:
            gutter = round(min(cluster) - margin, 2)
            for mark in group:
                if min(cluster) - 0.01 <= mark["x"] <= max(cluster) + 0.01:
                    mark["x"] = gutter


def build(pdf_path: pathlib.Path, content: dict) -> dict:
    is_sact = content["therapy"] == "sact"
    field_map: dict = {
        "fields": {},
        "ticks": [],
        "statements": [],
        "signature": None,
        "free_text": None,
        "id": pdf_path.stem,
    }

    with pdfplumber.open(pdf_path) as pdf:
        pages = [(number, rows_of(page)) for number, page in enumerate(pdf.pages, start=1)]
        heights = {number: page.height for number, page in enumerate(pdf.pages, start=1)}
        page_words = {
            number: (page, page.extract_words())
            for number, page in enumerate(pdf.pages, start=1)
        }
        field_map["pages"] = len(pdf.pages)

    signature = find_label(pages, SIGNATURE_ANCHORS)
    if signature:
        number = signature["page"]
        bottom = max(word["bottom"] for word in signature["row"]["words"])
        field_map["signature"] = {
            "page": number,
            "x": signature["x"],
            "y": round(heights[number] - bottom + 1.0, 2),
            "width": signature["max_width"],
            "height": 30.0,
        }

    signature_page = signature["page"] if signature else 1

    for key, patterns in FIELD_ANCHORS.items():
        # The date is signed on the same page as the signature, not in the header block.
        start_page = signature_page if key == "consent_date" else 1
        found = find_label(pages, patterns, start_page)
        if not found:
            continue
        number = found["page"]
        bottom = max(word["bottom"] for word in found["row"]["words"])
        field_map["fields"][key] = {
            "page": number,
            "x": found["x"],
            "y": round(heights[number] - bottom + 1.5, 2),
            "size": found["size"],
            "max_width": found["max_width"],
        }

    free_text = find_label(pages, FREE_TEXT_ANCHORS)
    if free_text:
        number = free_text["page"]
        bottom = max(word["bottom"] for word in free_text["row"]["words"])
        field_map["free_text"] = {
            "page": number,
            "x": 50.0,
            "y": round(heights[number] - bottom - 14.0, 2),
            "width": round(PAGE_WIDTH - 100.0, 2),
        }

    field_map["ticks"] = locate_ticks(
        page_words, content, None if is_sact else RCR_TICK_X
    )
    field_map["statements"] = locate_statements(pages, heights)
    snap_to_columns(field_map["ticks"] + field_map["statements"], heights)
    return field_map


def main() -> None:
    content = json.loads(CONTENT.read_text(encoding="utf-8"))
    by_id = {form["id"]: form for form in content["forms"]}

    maps = {}
    for pdf_path in sorted(PDF_DIR.glob("*.pdf")):
        form = by_id.get(pdf_path.stem)
        if not form:
            continue
        entry = build(pdf_path, form)
        maps[pdf_path.stem] = entry
        missing = [key for key in FIELD_ANCHORS if key not in entry["fields"]]
        unplaced = len(form["groups"][0]["items"]) and sum(
            len(group["items"]) for group in form["groups"]
        ) - len(entry["ticks"])
        print(
            f"{pdf_path.stem:<26} fields={len(entry['fields'])} ticks={len(entry['ticks']):>2} "
            f"unplaced={unplaced:<2} signature={'yes' if entry['signature'] else 'NO'} "
            f"free_text={'yes' if entry['free_text'] else 'NO'} "
            f"{'MISSING:' + ','.join(missing) if missing else ''}"
        )

    OUTPUT.write_text(json.dumps(maps, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nwrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
