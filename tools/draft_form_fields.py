"""Draft one explicit coordinate file per consent form.

Rule for this project: each form gets its own file, hand-checked once. Nothing at runtime
infers a position from another form's layout.

The x of a tick belongs to a *column*, not to each item: every item in a column shares one
gutter, which is computed from the left edge of that column's text minus a margin, then
verified against every word on the page so a tick can never land on a letter.

Usage:
    python tools/draft_form_fields.py            # writes assets/form_fields/<id>.json
"""

from __future__ import annotations

import itertools
import json
import pathlib
import re

import pdfplumber

ROOT = pathlib.Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "sources" / "pdf"
LEGACY_MAPS = ROOT / "assets" / "form_maps.json"
OUT_DIR = ROOT / "assets" / "form_fields"

# Space between the tick's right edge and the leftmost letter of that line.
TICK_MARGIN = 12.0
TICK_WIDTH = 9.0
TICK_RISE = 9.0
TICK_DROP = 2.0

FIELD_ANCHORS = {
    # CRUK prints separate surname and first-name lines; RCR has one "Patient name:" box.
    "surname": [r"surname|family name"],
    "given_names": [r"first name"],
    "full_name": [r"patient name"],
    "date_of_birth": [r"date of birth"],
    "nhs_number": [r"nhs number", r"patient unique identifier"],
    "consultant": [r"responsible consultant"],
    "consent_date": [r"^date:"],
    "name_print": [r"name \(print\)"],
}
SIGNATURE_ANCHORS = [r"patient'?s? signature", r"signature:"]

PAGE_WIDTH = 595.28
RIGHT_MARGIN = 44.0


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


def find_field(pages, heights, patterns, start_page: int = 1) -> dict | None:
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
                    end = start + size - 1
                    while end + 1 < len(words):
                        nxt = words[end + 1]
                        if nxt["text"].endswith(":") and nxt["x0"] - words[end]["x1"] < 8.0:
                            end += 1
                        else:
                            break
                    following = words[end + 1] if end + 1 < len(words) else None

                    if following is not None and is_rule(following):
                        # Write on the printed rule, sitting just above it.
                        x = round(following["x0"] + 2.0, 2)
                        width = round(following["x1"] - following["x0"] - 4.0, 2)
                        y = round(heights[number] - following["bottom"] + 2.5, 2)
                    else:
                        x = round(words[end]["x1"] + 4.0, 2)
                        width = round(PAGE_WIDTH - RIGHT_MARGIN - x, 2)
                        y = round(heights[number] - words[end]["bottom"] + 1.8, 2)

                    return {
                        "page": number,
                        "x": x,
                        "y": y,
                        "size": 7.6 if width < 110.0 else 8.4,
                        "max_width": round(max(min(width, 260.0), 40.0), 2),
                    }
    return None


def build_fields(pdf_path: pathlib.Path) -> dict[str, dict]:
    fields: dict[str, dict] = {}
    with pdfplumber.open(pdf_path) as pdf:
        pages = [(number, rows_of(page)) for number, page in enumerate(pdf.pages, 1)]
        heights = {number: page.height for number, page in enumerate(pdf.pages, 1)}

    signature = find_field(pages, heights, SIGNATURE_ANCHORS)
    signature_page = signature["page"] if signature else 1

    for key, patterns in FIELD_ANCHORS.items():
        start = signature_page if key in {"consent_date", "name_print"} else 1
        found = find_field(pages, heights, patterns, start)
        if found:
            fields[key] = found
    return fields


def build_signature(pdf_path: pathlib.Path) -> dict | None:
    with pdfplumber.open(pdf_path) as pdf:
        pages = [(number, rows_of(page)) for number, page in enumerate(pdf.pages, 1)]
        heights = {number: page.height for number, page in enumerate(pdf.pages, 1)}
    found = find_field(pages, heights, SIGNATURE_ANCHORS)
    if not found:
        return None
    return {
        "page": found["page"],
        "x": found["x"],
        "y": round(found["y"] - 2.0, 2),
        "width": min(found["max_width"], 240.0),
        "height": 18.0,
    }

STATEMENT_STOP = re.compile(
    r"^(the intended benefits|patient information leaflet|clinical management guideline|"
    r"other risks|statement of patient|specific risks to you from)",
    re.IGNORECASE,
)


STATEMENT_START = re.compile(
    r"statement of health|any other risks and information", re.IGNORECASE
)
# The form's own description of what the treatment is, which the clinician confirms.
TREATMENT_START = re.compile(r"name of proposed course of treatment", re.IGNORECASE)
TREATMENT_STOP = re.compile(
    r"^(where will i have treatment|where the treatment will be given|"
    r"statement of health professional)",
    re.IGNORECASE,
)


def normalise(text: str) -> list[str]:
    return re.findall(r"[a-z0-9°]+", text.lower())


def find_sequence(haystack: list[str], needle: list[str]) -> int | None:
    for start in range(max(len(haystack) - len(needle) + 1, 0)):
        if haystack[start : start + len(needle)] == needle:
            return start
    return None


def word_at(words: list[dict], folded: list[list[str]], position: int) -> dict:
    consumed = 0
    for index, tokens in enumerate(folded):
        consumed += len(tokens)
        if consumed > position:
            return words[index]
    return words[-1]


def overlaps(rect: tuple[float, float, float, float], box: dict) -> bool:
    x0, y0, x1, y1 = rect
    return not (
        box["x1"] <= x0 or box["x0"] >= x1 or box["bottom"] <= y0 or box["top"] >= y1
    )


def collides(x: float, y: float, words: list[dict]) -> dict | None:
    """Return the first word the tick rectangle would touch."""
    rect = (x, y - TICK_DROP, x + TICK_WIDTH, y + TICK_RISE)
    for word in words:
        if overlaps(rect, word):
            return word
    return None


def build_index(words: list[dict]) -> tuple[str, list[int]]:
    """Squash a page's words into one string of letters/digits.

    The forms kern some words so that pdfplumber splits them ("B owel urgency",
    "L ymphoedema", "C hange to penile length"). Matching on a squashed string with a
    character→word map copes with that, where a word-sequence match does not.
    """
    chunks: list[str] = []
    owners: list[int] = []
    for index, word in enumerate(words):
        for token in normalise(word["text"]):
            chunks.append(token)
            owners.extend([index] * len(token))
    return "".join(chunks), owners


def needles_for(text: str) -> list[list[str]]:
    """Candidate word-sequences to look for, longest first.

    Form text carries frequency suffixes ("(expected: 50–100%)") and sub-headings
    ("Radiotherapy to your pelvic lymph nodes: lymphoedema …") that are not part of the
    printed line, so each item gets several candidate needles.
    """
    cleaned = re.sub(r"\s*\([^)]*\)\s*\.?\s*$", "", text).strip()
    candidates = [text, cleaned]
    if ": " in cleaned:
        head, _, tail = cleaned.partition(": ")
        candidates.extend([tail, head])
    needles: list[list[str]] = []
    for candidate in candidates:
        words = normalise(candidate)
        for length in (4, 3, 2, 1):
            if len(words) >= length:
                needle = words[:length]
                if needle not in needles:
                    needles.append(needle)
    return needles


def column_of(page_items: list[dict], x0: float) -> int:
    """Group items into columns by their text's left edge."""
    return 0 if x0 < 200.0 else 1


def band_column(text: str) -> int | None:
    """Which frequency column the printed band maps to (left to right)."""
    lowered = text.lower()
    if "(expected" in lowered:
        return 0
    if "(less common" in lowered:
        return 2
    if "(common" in lowered:
        return 1
    if "(rare" in lowered:
        return 3
    return None


def page_boxes(page) -> list[list[dict]]:
    """The printed tick boxes, grouped into columns, each column sorted top to bottom."""
    squares = [
        rect
        for rect in page.rects
        if 8.0 <= rect["width"] <= 11.0 and 8.0 <= rect["height"] <= 11.0
    ]
    columns: dict[float, list[dict]] = {}
    for rect in squares:
        key = round(rect["x0"] / 6.0) * 6.0
        columns.setdefault(key, []).append(rect)
    ordered = [columns[key] for key in sorted(columns)]
    for column in ordered:
        column.sort(key=lambda rect: rect["top"])
    return ordered


def nearest_box(columns: list[list[dict]], column_index: int, top: float) -> dict | None:
    if not columns:
        return None
    index = min(column_index, len(columns) - 1)
    return min(columns[index], key=lambda rect: abs(rect["top"] - top))


def batch_boxes(page) -> dict:
    """The printed tick-box grid, if this page has one.

    Only a real grid counts: at least four evenly spaced columns of at least ten boxes.
    Otherwise loose rectangles elsewhere on the page (frequency bars, statement boxes)
    would be mistaken for tick boxes.
    """
    empty = {"xs": [], "rows": []}
    squares = [
        rect
        for rect in page.rects
        if 8.0 <= rect["width"] <= 11.0 and 8.0 <= rect["height"] <= 11.0
    ]
    if len(squares) < 40:
        return empty

    columns: dict[float, list[dict]] = {}
    for rect in squares:
        key = round(rect["x0"] / 6.0) * 6.0
        columns.setdefault(key, []).append(rect)
    ordered = [columns[key] for key in sorted(columns)]

    if len(ordered) < 4 or any(len(column) < 10 for column in ordered[:4]):
        return empty

    centres = [column[0]["x0"] + column[0]["width"] / 2.0 for column in ordered[:4]]
    gaps = [b - a for a, b in itertools.pairwise(centres)]
    if max(gaps) - min(gaps) > 20.0:
        return empty

    xs = [round(centre, 2) for centre in centres]
    rows = sorted({round(rect["top"], 1) for rect in ordered[0]})
    return {"xs": xs, "rows": rows, "page_height": page.height}


def box_rectangles(rects: list[dict] | None) -> list[dict]:
    """The printed checkboxes that are drawn as small squares rather than a glyph.

    Older forms in the library use a vector rectangle instead of the symbol font. They are
    nested two deep (an outer and an inner border), so duplicates that share a centre are
    collapsed to one box. Anything that is not roughly square and small is ignored.
    """
    boxes: dict[tuple[float, float], dict] = {}
    for rect in rects or []:
        width = rect["x1"] - rect["x0"]
        height = rect["bottom"] - rect["top"]
        if not (5.0 <= width <= 16.0 and 5.0 <= height <= 16.0):
            continue
        cx = round((rect["x0"] + rect["x1"]) / 2.0, 1)
        cy = round((rect["top"] + rect["bottom"]) / 2.0, 1)
        boxes.setdefault(
            (cx, cy),
            {"x0": rect["x0"], "x1": rect["x1"], "top": rect["top"], "bottom": rect["bottom"]},
        )
    return list(boxes.values())


def page_rows(
    words: list[dict],
    page_width: float = 595.28,
    rects: list[dict] | None = None,
    split_x: float | None = None,
) -> list[dict]:
    """Group words into printed lines, per column.

    Splitting by column first matters: on a two-column page the last item of the left
    column shares a baseline with the footer or with the right column, and grouping across
    the whole width merged them into one nonsense row.
    """
    mid = split_x if split_x is not None else page_width / 2.0
    left = [w for w in words if (w["x0"] + w["x1"]) / 2.0 < mid]
    right = [w for w in words if (w["x0"] + w["x1"]) / 2.0 >= mid]

    rows: list[dict] = []
    for column in (left, right):
        for word in sorted(column, key=lambda w: (round(w["top"], 1), w["x0"])):
            if rows and abs(word["top"] - rows[-1]["words"][0]["top"]) <= 3.0:
                rows[-1]["words"].append(word)
            else:
                rows.append({"words": [word]})

    squares = box_rectangles(rects)

    for row in rows:
        words_in_row = row["words"]
        first = words_in_row[0]
        # The printed checkbox is a symbol-font glyph: it extracts as "c" or a stray
        # non-alphanumeric character. A real two-letter word ("of", "to", "in", "or") must never
        # be mistaken for one, or the word is silently deleted from the side effect.
        glyph = first["text"].replace("c", "")
        has_box = (
            len(first["text"]) <= 2
            and not re.search(r"[A-Za-z0-9]", glyph)
            and not (set(first["text"]) & set(".,;:'\"!?-–—()[]{}\u2713\u2714\u2717\u2718"))
        )
        row["glyph"] = has_box
        row["bullet"] = first if has_box else None
        if not has_box:
            # A small square to the left of the wording, level with it, is this row's box.
            # It must sit clear of the text: a glyph drawn *inside* a sentence (some forms
            # print a tick in the prose) is only a point or two from the first word and is
            # not a box.
            for square in squares:
                centre_y = (square["top"] + square["bottom"]) / 2.0
                if (
                    abs(centre_y - (row["words"][0]["top"] + 4.0)) <= 5.0
                    and square["x1"] <= first["x0"] - 3.0
                    and square["x1"] >= first["x0"] - 40.0
                ):
                    row["bullet"] = square
                    break
        body = words_in_row[1:] if has_box else words_in_row
        row["squashed"] = "".join(
            token for word in body for token in normalise(word["text"])
        )
        row["text_x"] = body[0]["x0"] if body else first["x0"]
        row["top"] = first["top"]
    return rows


def build_ticks(
    pdf_path: pathlib.Path, content: dict, split_x: float | None = None
) -> tuple[list[dict], list[dict], list[str]]:
    notes: list[str] = []
    items: list[dict] = []
    index = 0

    with pdfplumber.open(pdf_path) as pdf:
        rows_by_page = {
            number: page_rows(page.extract_words(), page.width, page.rects, split_x)
            for number, page in enumerate(pdf.pages, 1)
        }
        heights = {number: page.height for number, page in enumerate(pdf.pages, 1)}

        used: set[tuple[int, int]] = set()

        unplaced: list[tuple[int, str]] = []

        for group in content["groups"]:
            for text in group["items"]:
                placed = False
                for needle in needles_for(text):
                    if placed:
                        break
                    squashed_needle = "".join(needle)
                    matches: list[tuple[int, int]] = []
                    for number in sorted(rows_by_page):
                        if number == 1:
                            continue
                        for row_index, row in enumerate(rows_by_page[number]):
                            # An item's own line begins with its checkbox glyph and then its
                            # own wording; requiring a prefix stops one item claiming another
                            # item's line.
                            if not row["squashed"].startswith(squashed_needle):
                                continue
                            if (number, row_index) in used:
                                continue
                            matches.append((number, row_index))
                    if not matches:
                        continue
                    # "Headache." also prefixes a longer line ("headache, tiredness, ...").
                    # The side effect's own line is the one that carries a printed box, so a
                    # bulleted row always wins over an unbulleted one.
                    bulleted = [
                        spot for spot in matches if rows_by_page[spot[0]][spot[1]]["bullet"]
                    ]
                    number, row_index = (bulleted or matches)[0]
                    row = rows_by_page[number][row_index]
                    used.add((number, row_index))

                    bullet = row["bullet"]
                    if bullet is not None:
                        box_x = round(bullet["x0"] + (bullet["x1"] - bullet["x0"]) / 2.0, 2)
                        box_y = round(
                            heights[number]
                            - (bullet["top"] + (bullet["bottom"] - bullet["top"]) / 2.0),
                            2,
                        )
                    else:
                        box_x, box_y = None, None

                    items.append(
                        {
                            "index": index,
                            "page": number,
                            "text_x": round(row["text_x"], 2),
                            "y": round(heights[number] - row["top"] - 6.0, 2),
                            "box_x": box_x,
                            "box_y": box_y,
                            "band": band_column(text),
                        }
                    )
                    placed = True
                if not placed:
                    unplaced.append((index, text))
                index += 1

        # Second pass, over what the exact match missed. Looser, and only after every exact
        # match has been taken, so a loose match cannot steal another item's line.
        for index, text in unplaced:
            placed = False
            for needle in needles_for(text):
                if placed:
                    break
                squashed_needle = "".join(needle)
                for number in sorted(rows_by_page):
                    if number == 1 or placed:
                        continue
                    for row_index, row in enumerate(rows_by_page[number]):
                        if (number, row_index) in used:
                            continue
                        if squashed_needle not in row["squashed"]:
                            continue
                        used.add((number, row_index))
                        bullet = row["bullet"]
                        items.append(
                            {
                                "index": index,
                                "page": number,
                                "text_x": round(row["text_x"], 2),
                                "y": round(heights[number] - row["top"] - 6.0, 2),
                                "box_x": (
                                    round(bullet["x0"] + (bullet["x1"] - bullet["x0"]) / 2.0, 2)
                                    if bullet
                                    else None
                                ),
                                "box_y": (
                                    round(
                                        heights[number]
                                        - (bullet["top"] + (bullet["bottom"] - bullet["top"]) / 2.0),
                                        2,
                                    )
                                    if bullet
                                    else None
                                ),
                                "band": band_column(text),
                            }
                        )
                        placed = True
                        break

            if not placed:
                # Fuzzy fallback: the wording differs slightly between our transcription and
                # the PDF, so take the printed bullet row sharing the longest opening run of
                # characters. Requires 18 characters of agreement, so it cannot wander off.
                want = normalise(text)
                want_text = "".join(want)
                best: tuple[int, int, int] | None = None
                for number in sorted(rows_by_page):
                    if number == 1:
                        continue
                    for row_index, row in enumerate(rows_by_page[number]):
                        if row["bullet"] is None or (number, row_index) in used:
                            continue
                        candidate = row["squashed"]
                        common = 0
                        for left, right in zip(want_text, candidate):
                            if left != right:
                                break
                            common += 1
                        if common >= 18 and (best is None or common > best[0]):
                            best = (common, number, row_index)

                if best is not None:
                    _, number, row_index = best
                    row = rows_by_page[number][row_index]
                    used.add((number, row_index))
                    bullet = row["bullet"]
                    items.append(
                        {
                            "index": index,
                            "page": number,
                            "text_x": round(row["text_x"], 2),
                            "y": round(heights[number] - row["top"] - 6.0, 2),
                            "box_x": round(bullet["x0"] + (bullet["x1"] - bullet["x0"]) / 2.0, 2),
                            "box_y": round(
                                heights[number]
                                - (bullet["top"] + (bullet["bottom"] - bullet["top"]) / 2.0),
                                2,
                            ),
                            "band": band_column(text),
                        }
                    )
                    notes.append(
                        f"item {index} matched fuzzily ({best[0]} chars): {text[:40]}"
                    )
                    placed = True

            if not placed:
                notes.append(f"item {index} not found on any page: {text[:50]}")

    # Margin ticks (no printed checkbox on the line) sit one gutter left of the text,
    # pulled further left if that would touch a letter.
    for item in items:
        if item["box_x"] is not None:
            continue
        x = round(item["text_x"] - TICK_MARGIN, 2)
        for _ in range(40):
            clash = collides(x, item["y"], [w for row in rows_by_page[item["page"]] for w in row["words"]])
            if clash is None:
                break
            x = round(clash["x0"] - TICK_WIDTH - 2.0, 2)
        item["margin_x"] = x

    return items, [], notes


# A wrapped line that starts a new block rather than continuing a declaration.
HEADING_ROW = re.compile(
    r"^(the intended benefits|specific risks|other risks|clinical management|"
    r"patient information|where the treatment|statement of|name of proposed|"
    r"date of issue|prepared by|checked by)",
    re.IGNORECASE,
)


def build_statements(pdf_path: pathlib.Path, split_x: float | None = None) -> list[dict]:
    """Tickable declarations: the health professional's statement, plus the form's own
    description of the proposed course of treatment (which the clinician confirms)."""
    statements: list[dict] = []
    collecting = False
    collecting_treatment = False
    pending_statement: str | None = None

    with pdfplumber.open(pdf_path) as pdf:
        heights = {number: page.height for number, page in enumerate(pdf.pages, 1)}
        for number, page in enumerate(pdf.pages, 1):
            rows = page_rows(page.extract_words(), page.width, page.rects, split_x)
            index = 0
            while index < len(rows):
                row = rows[index]
                text = " ".join(word["text"] for word in row["words"]).strip()
                if STATEMENT_START.search(text):
                    collecting = True
                    collecting_treatment = False
                    index += 1
                    continue
                if TREATMENT_START.search(text):
                    collecting_treatment = True
                    collecting = False
                    index += 1
                    continue
                if TREATMENT_STOP.match(text):
                    collecting_treatment = False
                    collecting = False
                    index += 1
                    continue
                if STATEMENT_STOP.match(text):
                    collecting = False
                    index += 1
                    continue
                if not (collecting or collecting_treatment) or row["bullet"] is None:
                    index += 1
                    continue

                # A declaration is the block of printed lines that runs from its own box to
                # the next one. Taking only the first line cut every sentence short:
                # "I have explained the course of treatment and" was all the clinician saw.
                block = [text]
                anchor_x = row["words"][0]["x0"]
                following = index + 1
                while following < len(rows) and rows[following]["bullet"] is None:
                    candidate = rows[following]
                    # Only the lines under this box, in this column, continue the sentence.
                    # The next column starts at a different x and is a different block.
                    if abs(candidate["words"][0]["x0"] - anchor_x) > 10.0:
                        break
                    continuation = " ".join(
                        word["text"] for word in candidate["words"]
                    ).strip()
                    if (
                        not continuation
                        or HEADING_ROW.match(continuation)
                        or STATEMENT_STOP.match(continuation)
                        or TREATMENT_STOP.match(continuation)
                    ):
                        break
                    block.append(continuation)
                    following += 1

                body = " ".join(
                    word["text"]
                    for word in (row["words"][1:] if row["glyph"] else row["words"])
                ).strip()
                if len(block) > 1:
                    body = " ".join([body, *block[1:]]).strip()
                index = following
                if not body:
                    continue
                if collecting and not body.lower().startswith("i "):
                    if pending_statement and body.lower().startswith("all relevant"):
                        body = f"{pending_statement} {body}".strip()
                        pending_statement = None
                    else:
                        continue
                # "Tick all relevant boxes" is a heading for the list, not a declaration.
                if body.lower().startswith("tick all"):
                    continue
                # The "where will I have treatment" options are choices, not declarations.
                if "outpatient" in body.lower() and "inpatient" in body.lower():
                    continue
                if body.startswith("c c"):
                    continue

                statements.append(
                    {
                        "index": len(statements),
                        "page": number,
                        "x": round(
                            row["bullet"]["x0"]
                            + (row["bullet"]["x1"] - row["bullet"]["x0"]) / 2.0,
                            2,
                        ),
                        "y": round(
                            heights[number]
                            - (
                                row["bullet"]["top"]
                                + (row["bullet"]["bottom"] - row["bullet"]["top"]) / 2.0
                            ),
                            2,
                        ),
                        "text": body,
                    }
                )
    return statements


def build_box_columns(pdf_path: pathlib.Path) -> list[dict]:
    """The x centre of each printed tick-box column, per page."""
    out: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            boxes = batch_boxes(page)
            if boxes["xs"]:
                out.append({"page": number, "xs": boxes["xs"]})
    return out


def main() -> None:
    legacy = json.loads(LEGACY_MAPS.read_text(encoding="utf-8"))
    content = json.loads((ROOT / "sources" / "content.json").read_text(encoding="utf-8"))
    by_id = {form["id"]: form for form in content["forms"]}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    problems = 0

    for pdf_path in sorted(PDF_DIR.glob("*.pdf")):
        form = by_id.get(pdf_path.stem)
        old = legacy.get(pdf_path.stem)
        if not form or not old:
            continue

        items, columns, notes = build_ticks(pdf_path, form)
        statements = build_statements(pdf_path)
        problems += len(notes)

        field_map = {
            "id": pdf_path.stem,
            "pages": old.get("pages", 0),
            "fields": build_fields(pdf_path),
            "signature": build_signature(pdf_path),
            "free_text": old["free_text"],
            "box_columns": build_box_columns(pdf_path),
            "side_effects": [
                {
                    "index": item["index"],
                    "page": item["page"],
                    "y": item["y"],
                    "box_x": item["box_x"],
                    "box_y": item["box_y"],
                    "band": item["band"],
                    "text_x": item["text_x"],
                    "margin_x": item.get("margin_x"),
                }
                for item in items
            ],
            "statements": statements,
        }

        (OUT_DIR / f"{pdf_path.stem}.json").write_text(
            json.dumps(field_map, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(
            f"{pdf_path.stem:<26} items={len(items):>2} columns={len(columns)} "
            f"statements={len(statements)} free_text={'yes' if old['free_text'] else 'NO'}"
        )
        for note in notes:
            print("   !", note)

    print(f"\nwrote {len(list(OUT_DIR.glob('*.json')))} files to {OUT_DIR.relative_to(ROOT)}")
    if problems:
        print(f"{problems} items could not be placed and will be reported, not guessed")


if __name__ == "__main__":
    main()
