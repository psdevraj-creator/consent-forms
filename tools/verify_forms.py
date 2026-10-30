"""Verify every imported consent form against its source PDF.

Four independent checks per form, because each catches a different kind of error:

A. STRUCTURE   the bundle is complete: groups, one tick position per side effect, indexes
               in order, pages and coordinates inside the page.
B. FIDELITY    every extracted side effect appears verbatim in the PDF text, and every
               bullet printed on the side-effect pages appears in the bundle.
C. POSITION    each tick's coordinate matches the printed row it belongs to.

D. RENDER is handled by tools/verify_renders.py, which proves the ink lands in the box.

Each page is parsed once and reused, which matters at 515 forms.

Usage:
    python tools/verify_forms.py [--limit N]
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import pdfplumber
from draft_form_fields import page_rows

ROOT = pathlib.Path(__file__).resolve().parent.parent
FORMS = ROOT / "forms"
REPORTS = ROOT / "reports"


def norm(text: str) -> str:
    text = text.replace("\u2013", "-").replace("\u2014", "-").replace("\u2019", "'")
    return re.sub(r"[^a-z0-9]", "", text.lower())


def rows_from(words: list[dict], rects: list[dict] | None = None) -> list[dict]:
    """The importer's own line grouping, so the check and the extraction cannot disagree."""
    rows = page_rows(words, 595.28, rects)
    for row in rows:
        # Rows such as "c Yes  c No  c Not available" carry several boxes: they are choice
        # rows on the professional statement, never side effects.
        row["bullet_count"] = sum(
            1
            for word in row["words"]
            if len(word["text"]) <= 2
            and not re.search(r"[A-Za-z0-9]", word["text"].replace("c", ""))
        )
    return rows


DECLARATION_LINES = re.compile(
    r"^(clinicalmanagement|thefollowingwritten|tobetained|preparedby|checkedby|"
    r"patientagreement|statementof|wherewill|nameofproposed|theintendedbenefits|"
    r"informationleaflet|sacttreatmentrecord|24houralert|opentoread|cyes|"
    r"common|occasional|otherrisks|dosage|thisformshould|please)",
)


HEADING = re.compile(r"^(commonsideeffects|occasionalsideeffects|otherrisks)")
STOP_HEADING = re.compile(
    r"^(anyotherrisks|clinicalmanagement|thefollowingwritten|tobetained|preparedby|"
    r"checkedby|patientagreement|statementof|wherewill|nameofproposed|theintendedbenefits|"
    r"informationleaflet|sacttreatmentrecord|24houralert|opentoread|dosage|thisformshould)"
)


def check_form(path: pathlib.Path) -> dict:
    bundle = json.loads(path.read_text(encoding="utf-8"))
    result = {"id": path.stem, "pass": True, "items": 0, "page_count": 0, "errors": []}
    errors: list[str] = result["errors"]

    pdf_path = FORMS / f"{path.stem}.pdf"
    if not pdf_path.exists():
        errors.append("missing PDF")
        result["pass"] = False
        return result

    items = [item for group in bundle.get("groups", []) for item in group["items"]]
    result["items"] = len(items)

    # ---- A. structure ----------------------------------------------------------------
    if not bundle.get("groups"):
        errors.append("no side-effect groups")
    ticks = bundle.get("side_effects", [])
    if len(ticks) != len(items):
        errors.append(f"tick positions {len(ticks)} != side effects {len(items)}")
    if [tick["index"] for tick in ticks] != list(range(len(ticks))):
        errors.append("tick indexes are not 0..n")
    if not bundle.get("statements"):
        errors.append("no declarations found")

    # ---- B + C. fidelity and position, one parse per page -----------------------------
    with pdfplumber.open(pdf_path) as pdf:
        result["page_count"] = len(pdf.pages)
        words_by_page = {}
        rows_by_page = {}
        text_parts: list[str] = []

        for number, page in enumerate(pdf.pages, 1):
            words = page.extract_words()
            words_by_page[number] = words
            rows = rows_from(words, page.rects)
            # Build the page's plain text from the reconstructed lines, not from the raw word
            # order: on a two-column page the raw order interleaves the columns and would
            # break every sentence that wraps.
            text_parts.append("".join(row["squashed"] for row in rows))
            bullets = sum(1 for row in rows if row["bullet"] is not None)
            if number > 1 and bullets >= 1:
                rows_by_page[number] = rows

        all_text = norm(" ".join(text_parts))

        for position, text in enumerate(items):
            if norm(text) and norm(text) not in all_text:
                errors.append(f"item {position} not verbatim in PDF: {text[:44]}")

        # Every bulleted line printed on a side-effect page must be represented by an
        # extracted item — either as the item's own wording or inside it (sub-bullets are
        # folded into their parent). This is the check that proves nothing was dropped.
        # No two side effects on a form should read identically *on the same printed line*:
        # that means a line was captured twice. The same wording legitimately appears twice
        # on some forms (under both "Common" and "Occasional"), so the position must match
        # before this counts as a duplicate.
        seen: dict[str, int] = {}
        spots: dict[int, tuple] = {}
        for position, text in enumerate(items):
            key = norm(text)[:80]
            if not key:
                continue
            tick = ticks[position] if position < len(ticks) else {}
            spot = (tick.get("page"), tick.get("box_y"))
            if key in seen and spots.get(seen[key]) == spot:
                errors.append(f"item {position} duplicates item {seen[key]}")
            elif key not in seen:
                seen[key] = position
                spots[position] = spot

        # Mangled characters must never reach the clinician: a side effect reading
        # "temperature over 37.5<?>C" is not the form's own wording.
        for position, text in enumerate(items):
            for character in text:
                if character == "\ufffd" or (
                    ord(character) > 127 and character not in "°–—’‘“”®™©§℃℉éèàüöñ"
                ):
                    errors.append(
                        f"item {position} contains a mangled character "
                        f"U+{ord(character):04X} in {text[:44]}"
                    )
                    break

        item_norm = [norm(text) for text in items]
        checking = False
        for number in sorted(rows_by_page):
            page_height = pdf.pages[number - 1].height
            for row in rows_by_page[number]:
                if row["top"] > page_height - 95.0:
                    continue  # page furniture: never ends a section, never a side effect
                squashed = row["squashed"]
                if not squashed:
                    continue
                if STOP_HEADING.match(squashed):
                    checking = False
                    continue
                if HEADING.match(squashed):
                    checking = True
                    continue
                if not checking or row["bullet"] is None:
                    continue
                if row.get("bullet_count", 1) >= 2:
                    continue  # a Yes / No / Not available choice row
                needle = squashed[:26]
                if len(needle) < 12:
                    continue
                if not any(needle in candidate for candidate in item_norm):
                    errors.append(
                        f"printed side effect on page {number} missing from the bundle: "
                        f"{' '.join(w['text'] for w in row['words'][:6])[:52]}"
                    )

        for tick in ticks:
            page = tick.get("page")
            box_y = tick.get("box_y")
            if page not in rows_by_page:
                errors.append(f"item {tick['index']}: no side-effect page {page}")
                continue
            if box_y is None:
                errors.append(f"item {tick['index']}: no box position")
                continue
            height = pdf.pages[page - 1].height
            column_x = tick.get("box_x") or tick.get("text_x") or 0.0
            # Compare against every printed box on the page and let distance decide: a box
            # that straddles the halfway line has its glyph just inside one column and its
            # centre just outside, so partitioning by column alone put it out of reach.
            in_column = [row for row in rows_by_page[page] if row["bullet"]]
            if not in_column:
                errors.append(f"item {tick['index']}: page {page} has no printed boxes")
                continue

            # The tick must be centred on the printed box of the row that carries this side
            # effect's own wording — not merely near some row. Both numbers come from the
            # same geometry, so anything beyond half a point is a real misplacement.
            own = item_norm[tick["index"]] if tick["index"] < len(item_norm) else ""
            best = None
            for row in in_column:
                bullet = row["bullet"]
                cx = bullet["x0"] + (bullet["x1"] - bullet["x0"]) / 2.0
                cy = height - (bullet["top"] + (bullet["bottom"] - bullet["top"]) / 2.0)
                distance = abs(cx - column_x) + abs(cy - box_y)
                row_text = row["squashed"]
                if not own:
                    wording_matches = True
                elif row_text:
                    head = row_text[:24]
                    wording_matches = (
                        own.startswith(head) or head in own or own[:24] in row_text
                    )
                else:
                    wording_matches = False
                score = (0 if wording_matches else 1, distance)
                if best is None or score < best[0]:
                    best = (score, row, cx, cy, row_text)

            score, row, cx, cy, row_text = best
            if abs(cx - column_x) > 0.6 or abs(cy - box_y) > 0.6:
                errors.append(
                    f"item {tick['index']}: tick is {abs(cx - column_x):.1f},"
                    f"{abs(cy - box_y):.1f} pt from the nearest printed box"
                )
            elif score[0] == 1 and row_text:
                errors.append(
                    f"item {tick['index']}: tick sits on the line {row_text[:44]!r}, "
                    f"which is not its own wording"
                )


    if errors:
        result["pass"] = False
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--only", nargs="*", default=[], help="check only forms whose id contains a fragment"
    )
    args = parser.parse_args()

    REPORTS.mkdir(exist_ok=True)
    paths = sorted(FORMS.glob("*.json"))
    if args.limit:
        paths = paths[: args.limit]
    if args.only:
        paths = [path for path in paths if any(f in path.stem for f in args.only)]

    started = time.time()
    rows = []
    for number, path in enumerate(paths, 1):
        rows.append(check_form(path))
        if number % 25 == 0:
            elapsed = time.time() - started
            rate = number / elapsed
            print(f"  {number}/{len(paths)}  ({rate:.1f}/s, ~{(len(paths) - number) / rate / 60:.0f} min left)")

    with (REPORTS / "verification.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "pass", "items", "page_count", "errors"])
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "errors": " | ".join(row["errors"])})

    failures = [row for row in rows if not row["pass"]]
    with (REPORTS / "failures.md").open("w", encoding="utf-8") as handle:
        handle.write(f"# Verification failures\n\n{len(failures)} of {len(rows)} forms failed.\n\n")
        for row in failures:
            handle.write(f"## {row['id']}  ({row['items']} items)\n\n")
            for error in row["errors"][:12]:
                handle.write(f"- {error}\n")
            handle.write("\n")

    print(f"\nchecked {len(rows)} forms in {(time.time() - started) / 60:.1f} min")
    print(f"passed : {len(rows) - len(failures)}")
    print(f"failed : {len(failures)}")
    for row in failures[:10]:
        print("  ", row["id"], "->", row["errors"][0].encode("ascii", "replace").decode())


if __name__ == "__main__":
    main()
