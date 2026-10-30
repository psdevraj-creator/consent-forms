"""Word-for-word coverage: is anything printed on the form missing from the app?

`verify_forms.py` proves the app's wording appears on the form. This proves the reverse for
every printed word inside the side-effect section: if the form prints 400 words of side
effects and the app holds 260 of them, something was dropped even though every item checked
out.

Headings, frequency notes and page furniture are excluded, so the ratio reflects the actual
clinical wording.

Usage:
    python tools/verify_coverage.py [--only <id fragment> ...] [--threshold 0.9]
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import re
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import pdfplumber
from import_all import clean_text, page_rows

ROOT = pathlib.Path(__file__).resolve().parent.parent
FORMS = ROOT / "forms"
REPORTS = ROOT / "reports"

HEADER_BAND = 115.0
FOOTER_BAND = 95.0
FURNITURE = re.compile(
    r"^(statementofhealth|professional|continued|patientidentifierlabel|commonsideeffects|"
    r"occasionalsideeffects|otherrisks|affectingmorethan|affectingbetween|youmayhave|"
    r"thesideeffectslisted|tobetained|preparedby|checkedby|dateofissue|approvedby|"
    r"checkcruk|version|page\d|thefollowingwritten|clinicalmanagement|patientagreement|"
    r"informationleaflet|sacttreatmentrecord|anyotherrisks|wherewill|nameofproposed|"
    r"theintendedbenefits|opentoread|otherinformation|importantnotes|dosage)",
    re.IGNORECASE,
)
WORD = re.compile(r"[a-z0-9]{3,}")


def tokens(text: str) -> set[str]:
    return set(WORD.findall(text.lower().replace("’", "'")))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*", default=[])
    parser.add_argument("--threshold", type=float, default=0.90)
    args = parser.parse_args()

    REPORTS.mkdir(exist_ok=True)
    paths = sorted(FORMS.glob("*.json"))
    if args.only:
        paths = [path for path in paths if any(f in path.stem for f in args.only)]

    rows = []
    for path in paths:
        bundle = json.loads(path.read_text(encoding="utf-8"))
        items = [item for group in bundle.get("groups", []) for item in group["items"]]
        have = tokens(" ".join(items))

        pages = sorted({tick["page"] for tick in bundle.get("side_effects", []) if tick.get("page")})
        if not pages:
            pages = [2]

        printed: set[str] = set()
        pdf_path = FORMS / f"{path.stem}.pdf"
        if not pdf_path.exists():
            rows.append(
                {
                    "id": path.stem,
                    "coverage": 0.0,
                    "printed": 0,
                    "captured": 0,
                    "missing": -1,
                    "examples": "missing PDF",
                }
            )
            continue

        with pdfplumber.open(pdf_path) as pdf:
            for page_number in pages:
                page = pdf.pages[page_number - 1]
                top_limit = HEADER_BAND
                bottom_limit = page.height - FOOTER_BAND
                chunk: list[str] = []
                for row in page_rows(page.extract_words(), page.width, page.rects):
                    if not (top_limit <= row["top"] <= bottom_limit):
                        continue
                    squashed = row["squashed"]
                    if squashed and FURNITURE.match(squashed):
                        continue
                    text = clean_text(" ".join(w["text"] for w in row["words"]))
                    if row["bullet"]:
                        # A boxed row starts a new side effect; whatever is printed under it
                        # until the next box belongs to the same side effect.
                        if chunk:
                            printed |= tokens(" ".join(chunk))
                        chunk = [text]
                    elif chunk:
                        chunk.append(text)
                    # Prose before the first box is an explanation, not a side effect.
                if chunk:
                    printed |= tokens(" ".join(chunk))

        if not printed:
            continue
        missing = printed - have
        coverage = len(printed & have) / len(printed)
        rows.append(
            {
                "id": path.stem,
                "coverage": round(coverage, 3),
                "printed": len(printed),
                "captured": len(printed & have),
                "missing": len(missing),
                "examples": " ".join(sorted(missing)[:12]),
            }
        )

    with (REPORTS / "coverage.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["id", "coverage", "printed", "captured", "missing", "examples"]
        )
        writer.writeheader()
        writer.writerows(rows)

    below = [row for row in rows if row["coverage"] < args.threshold]
    below.sort(key=lambda row: row["coverage"])
    total = sum(row["printed"] for row in rows)
    kept = sum(row["captured"] for row in rows)
    print(f"forms          : {len(rows)}")
    print(f"printed words  : {total}")
    print(f"captured       : {kept}  ({kept / total * 100 if total else 0:.1f}%)")
    print(f"below {args.threshold:.0%}      : {len(below)}")
    for row in below[:15]:
        print(
            f"   {row['id'][:52]:52s} {row['coverage']:.2f}  missing {row['missing']:3d}"
            f"  e.g. {row['examples'][:60]}"
        )


if __name__ == "__main__":
    main()
