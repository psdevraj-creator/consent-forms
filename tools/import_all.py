"""Import every SACT consent form from the CRUK library.

For each form this:
  1. downloads the PDF (cached by URL in sources/forms/),
  2. reads the tumour-site section heading from the index page,
  3. extracts the side-effect bullets and the tickable declarations,
  4. drafts the per-form coordinate file (tick positions from the printed checkbox glyph),
  5. writes a QA report so failures are visible rather than silent.

Outputs:
    sources/forms/<slug>.pdf          the downloaded forms
    assets/catalogue.json             one record per form (no PDF text)
   assets/form_fields/<slug>.json     coordinates, same shape as the pilot forms
    sources/import_report.txt          per-form counts and problems

Usage:
    python tools/import_all.py            # everything
    python tools/import_all.py --limit 20 # a sample
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import shutil
import sys
import urllib.request

import pdfplumber

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from draft_form_fields import (
    build_fields,
    build_signature,
    build_statements,
    build_ticks,
    page_rows,
)
from fix_sites import index_sections

ROOT = pathlib.Path(__file__).resolve().parent.parent
FORMS = ROOT / "sources" / "forms"
# Written outside the build output: `trunk build` wipes site/, which would delete them.
BUNDLES = ROOT / "forms"
FIELDS = ROOT / "assets" / "form_fields"
INDEX = (
    "https://www.cancerresearchuk.org/health-professional/"
    "treatment-and-other-post-diagnosis-issues/"
    "consent-forms-for-sact-systemic-anti-cancer-therapy"
)
UA = {"User-Agent": "Mozilla/5.0 (compatible; consent-importer/1.0)"}

HEADINGS = [
    (re.compile(r"^common side effects", re.IGNORECASE), "Common side effects"),
    (re.compile(r"^occasional side effects", re.IGNORECASE), "Occasional side effects"),
    (re.compile(r"^other risks", re.IGNORECASE), "Other risks"),
]
SKIP_TEXT = re.compile(
    r"^(tick all|continue on to|please read|you may have|affecting more|affecting between)",
    re.IGNORECASE,
)
# Lines that genuinely end a section (page furniture or the next heading).
STOP_TEXT = re.compile(
    r"^(to be retained|prepared by|checked by|patient agreement|statement of|any other risks|"
    r"where will|name of proposed|the intended benefits|clinical management|"
    r"the following written|health professional details|statement of interpreter|"
    r"information leaflet|sact treatment record|24 hour alert|open to read)",
    re.IGNORECASE,
)
# Running headers repeat on every page and are not part of any side effect.
HEADER_TEXT = re.compile(
    r"^(statementofhealth|professional|continued|patientidentifierlabel|listed|"
    r"peoplehaveoneormore|thesideeffectslisted)"
)


SKIP_TITLE = re.compile(
    r"guidance|bilingual|welsh|"
    r"summary letter|project acknowledg|implementation of|development of",
    re.IGNORECASE,
)


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug)[:70]


def fetch(url: str) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90).read()


def index_entries() -> list[dict]:
    """Every consent form on the index page, with the section it sits under."""
    html = fetch(INDEX).decode("utf-8", "replace")
    entries: list[dict] = []
    section = "Other"
    pattern = re.compile(
        r'<h2[^>]*>([^<]{2,80})</h2>|<a[^>]*title="([^"]{2,90})"[^>]*href="(//assets\.ctfassets\.net/[^"]+\.pdf)"',
        re.IGNORECASE,
    )
    seen: set[str] = set()
    for match in pattern.finditer(html):
        heading, title, url = match.groups()
        if heading:
            section = re.sub(r"\s*\(.*\)\s*$", "", heading).strip()
            continue
        if not title or not url:
            continue
        key = url.lower()
        if key in seen or SKIP_TITLE.search(title):
            continue
        seen.add(key)
        title_text = title.strip()
        # The generic (blank) forms sit under their own heading, which the <h2> scan cannot
        # see because the heading wraps a button.
        entry_section = "Generic forms" if re.search(r"generic", title_text, re.IGNORECASE) else section
        entries.append(
            {
                "title": title_text,
                "url": "https:" + url,
                "section": entry_section,
            }
        )
    return entries


BULLET_CHARS = "\u2022\u00b7\u25aa\u25cf\u2023\u2043\u00a7"


def _squash(text: str) -> str:
    """Lower case, letters and digits only — for matching headings and furniture."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _undouble(text: str) -> str:
    """Collapse a fake-bold run: some forms draw each letter twice ("PPaattiieenntt")."""
    if (
        len(text) % 2 == 0
        and len(text) >= 4
        and all(text[i] == text[i + 1] for i in range(0, len(text), 2))
    ):
        return text[::2]
    return text


def clean_text(text: str) -> str:
    """Join the words of a printed line, dropping list markers.

    The glyphs that mark a bullet inside a wrapped line extract as a character such as
    "•" and would otherwise land in the middle of a sentence: "unwell (even with a •
    normal temperature)".
    """
    for character in BULLET_CHARS:
        text = text.replace(character, " ")
    return re.sub(r"\s+", " ", text).strip()


def extract_side_effects(pdf_path: pathlib.Path, split_x: float | None = None) -> list[dict]:
    """Side effects under the form's own headings."""
    groups: dict[str, list[str]] = {}
    current: str | None = None
    joined_previous: str | None = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            footer_band = page.height - 95.0
            for row in page_rows(page.extract_words(), page.width, page.rects):
                # Rows are read column by column, so the left column's footer arrives before
                # the right column's side effects. Treating it as an end-of-section marker
                # silently threw away everything printed to its right.
                if row["top"] > footer_band:
                    continue
                # A symbol-font box is the first word of the line; a drawn square is not a
                # word at all, so the wording starts at the first word either way.
                body = clean_text(
                    " ".join(
                        word["text"]
                        for word in (row["words"][1:] if row["glyph"] else row["words"])
                    )
                )
                full = clean_text(" ".join(word["text"] for word in row["words"]))

                heading = next((name for pattern, name in HEADINGS if pattern.match(full)), None)
                if heading:
                    current = heading
                    joined_previous = None
                    groups.setdefault(current, [])
                    continue
                if HEADER_TEXT.match(_undouble(_squash(full))):
                    # "Statement of health professional", "Patient identifier/label" and the
                    # like repeat at the top of every page. They are not side effects and must
                    # not be glued onto the one above them.
                    joined_previous = None
                    continue
                if current is None:
                    continue
                if STOP_TEXT.match(full):
                    current = None
                    joined_previous = None
                    continue
                if SKIP_TEXT.match(full):
                    # A frequency sub-heading or page furniture: skip the line, keep going.
                    joined_previous = None
                    continue

                if row["bullet"] and body:
                    if body[:1].islower() and groups.get(current):
                        # A wrapped line that happened to start with a glyph: it belongs to
                        # the previous side effect, it is not one of its own.
                        groups[current][-1] = f"{groups[current][-1]} {body}".strip()
                        joined_previous = groups[current][-1]
                        continue
                    if len(groups.setdefault(current, [])) >= 60:
                        current = None
                        joined_previous = None
                        continue
                    groups[current].append(body)
                    joined_previous = body
                elif joined_previous and full and not SKIP_TEXT.match(full):
                    groups[current][-1] = f"{groups[current][-1]} {full}".strip()

    if not any(groups.values()):
        return fallback_side_effects(pdf_path)

    return [
        {"heading": name, "items": items}
        for name, items in groups.items()
        if items
    ]


LEAD_IN = re.compile(r"^youmayhaveoneormoreofthesideeffects", re.IGNORECASE)
FALLBACK_STOP = re.compile(
    r"^(otherinformation|patientagreement|clinicalmanagement|tobetained|statementofinterpreter|"
    r"preparedby|checkedby|wherewill|nameofproposed|informationleaflet|sacttreatmentrecord)",
    re.IGNORECASE,
)


def fallback_side_effects(pdf_path: pathlib.Path) -> list[dict]:
    """Read a form that lists its side effects without the usual three headings.

    A few immunotherapy forms (Ipilimumab, Ipilimumab with Nivolumab) print one lead-in,
    "You may have one or more of the side effects listed", then a nested bullet list: a
    bullet such as "Commonly, inflammation of:" followed by unbulleted lines naming the
    organs. Each unbulleted line is folded into the bullet above it, so an item reads the way
    the form reads. This only runs when no standard heading was found, so it cannot disturb
    the 500 forms that use the usual layout.
    """
    items: list[str] = []
    started = False
    previous: str | None = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for row in page_rows(page.extract_words(), page.width, page.rects):
                full = clean_text(" ".join(word["text"] for word in row["words"]))
                squashed = row["squashed"]
                if not started:
                    if LEAD_IN.match(squashed):
                        started = True
                    continue
                if FALLBACK_STOP.match(squashed) or STOP_TEXT.match(full):
                    return [{"heading": "Side effects", "items": items}] if items else []
                body = clean_text(
                    " ".join(
                        word["text"]
                        for word in (row["words"][1:] if row["glyph"] else row["words"])
                    )
                )
                if not body:
                    continue
                if row["bullet"]:
                    items.append(body)
                    previous = body
                elif previous is not None:
                    items[-1] = f"{items[-1]} {body}".strip()

    return [{"heading": "Side effects", "items": items}] if items else []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--only",
        nargs="*",
        default=[],
        help="re-import only forms whose id contains one of these fragments",
    )
    args = parser.parse_args()
    if args.only:
        args.force = True

    FORMS.mkdir(parents=True, exist_ok=True)
    FIELDS.mkdir(parents=True, exist_ok=True)

    entries = index_entries()
    print(f"index: {len(entries)} consent forms")
    sections = index_sections()
    print(f"sections: {len(sections)} titles mapped to a tumour site")
    if args.limit:
        entries = entries[: args.limit]

    catalogue = []
    report: list[str] = []
    used_ids: set[str] = set()

    for number, entry in enumerate(entries, 1):
        # Ids must be unique: CRUK lists a few regimens twice inside the same section
        # (monotherapy and combination versions share a title), so a repeat gets a suffix
        # derived from its URL.
        site = sections.get(entry["title"], "Other")
        base_id = f"{slugify(site)}-{slugify(entry['title'])}"
        form_id = base_id
        if form_id in used_ids:
            suffix = hashlib.sha1(entry["url"].encode("utf-8")).hexdigest()[:6]
            form_id = f"{base_id}-{suffix}"
        used_ids.add(form_id)

        if args.only and not any(fragment in form_id for fragment in args.only):
            continue


        # Resume: bundles already on disk are kept unless --force.
        bundle_path = BUNDLES / f"{form_id}.json"
        if bundle_path.exists() and not args.force:
            existing = json.loads(bundle_path.read_text(encoding="utf-8"))
            catalogue.append(
                {
                    "id": form_id,
                    "tumour_site": existing.get("tumour_site", site),
                    "regimen_name": existing.get("regimen_name", entry["title"]),
                    "therapy": "sact",
                    "side_effect_count": sum(
                        len(group.get("items", [])) for group in existing.get("groups", [])
                    ),
                    "statement_count": len(existing.get("statements", [])),
                    "source_url": entry["url"],
                    "sha256": "",
                }
            )
            continue

        # Cache by URL, so a title that appears twice cannot overwrite the other's PDF.
        cache_slug = "url-" + hashlib.sha1(entry["url"].encode("utf-8")).hexdigest()[:16]
        pdf_path = FORMS / f"{cache_slug}.pdf"

        if not pdf_path.exists() or args.force:
            try:
                data = fetch(entry["url"])
            except Exception as error:  # noqa: BLE001
                report.append(f"FETCH FAIL {form_id}: {error}")
                continue
            pdf_path.write_bytes(data)
        else:
            data = pdf_path.read_bytes()

        content = {
            "id": form_id,
            "therapy": "sact",
            "tumour_site": site,
            "regimen_name": entry["title"],
            "groups": extract_side_effects(pdf_path),
        }

        if not content["groups"]:
            report.append(f"NO SIDE EFFECTS {form_id}")
            continue
        # A book that swallows the whole document produces hundreds of items and cannot be
        # ticked as one regimen; it is reported instead of shipped as nonsense.
        if any(len(group["items"]) >= 60 for group in content["groups"]):
            report.append(
                f"TOO MANY SIDE EFFECTS {form_id}: "
                + ", ".join(f"{g['heading']}={len(g['items'])}" for g in content["groups"])
            )
            continue

        items, _, notes = build_ticks(pdf_path, content)
        statements = build_statements(pdf_path)
        fields = {
            "id": form_id,
            "fields": build_fields(pdf_path),
            "signature": build_signature(pdf_path),
            "free_text": None,
            "box_columns": [],
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
        (FIELDS / f"{form_id}.json").write_text(
            json.dumps(fields, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        total_items = sum(len(group["items"]) for group in content["groups"])
        in_box = sum(1 for item in items if item["box_x"] is not None)

        # The bundle the app fetches: wording plus tick coordinates.
        bundle = {
            "id": form_id,
            "tumour_site": site,
            "regimen_name": entry["title"],
            "groups": content["groups"],
            "fields": fields["fields"],
            "box_columns": fields["box_columns"],
            "side_effects": fields["side_effects"],
            "statements": fields["statements"],
            "signature": fields["signature"],
            "free_text": fields["free_text"],
        }
        BUNDLES.mkdir(parents=True, exist_ok=True)
        (BUNDLES / f"{form_id}.json").write_text(
            json.dumps(bundle, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        shutil.copyfile(pdf_path, BUNDLES / f"{form_id}.pdf")
        catalogue.append(
            {
                "id": form_id,
                "tumour_site": site,
                "regimen_name": entry["title"],
                "therapy": "sact",
                "side_effect_count": total_items,
                "statement_count": len(statements),
                "source_url": entry["url"],
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
        report.append(
            f"{form_id:<60} site={site[:22]:<22} items={total_items:>3} "
            f"ticks={len(items):>3} inbox={in_box:>3} statements={len(statements)} "
            f"{' | ' + '; '.join(notes) if notes else ''}"
        )
        if number % 25 == 0:
            print(f"  {number}/{len(entries)}")

    catalogue_path = ROOT / "assets" / "catalogue.json"
    if args.only and catalogue_path.exists():
        # A targeted run must not shrink the catalogue to the handful of forms it touched.
        previous = json.loads(catalogue_path.read_text(encoding="utf-8"))["forms"]
        updated = {entry["id"]: entry for entry in catalogue}
        merged: list[dict] = []
        for entry in previous:
            merged.append(updated.pop(entry["id"], entry))
        merged.extend(sorted(updated.values(), key=lambda entry: entry["id"]))
        catalogue = merged

    catalogue_path.write_text(
        json.dumps(
            {"version": "cr-brand-2026-10-28", "forms": catalogue},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (ROOT / "sources" / "import_report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")

    problems = [line for line in report if line.startswith(("FETCH FAIL", "NO SIDE EFFECTS"))]
    print(f"\nimported {len(catalogue)} forms")
    print(f"problems: {len(problems)}")
    for line in problems[:10]:
        print("  ", line)


if __name__ == "__main__":
    main()
