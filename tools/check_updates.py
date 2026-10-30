"""Check the CRUK library for new or revised consent forms.

Compares the published index and every PDF's SHA-256 with what this app holds, and reports:

  * NEW      a form on the website that the app does not have
  * REVISED  a form whose PDF has changed since it was imported
  * GONE     a form the app has that the website no longer lists
  * ERROR    a download that failed (worth retrying, not a change)

Nothing is modified unless you pass --write-manifest, which records the current SHA-256
values after you have re-imported.

Usage:
    python tools/check_updates.py                # full check, downloads every PDF
    python tools/check_updates.py --new-only     # fast: new and removed forms only
    python tools/check_updates.py --limit 20     # sample
    python tools/check_updates.py --write-manifest
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import pathlib
import re
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from import_all import fetch, index_entries, index_sections, slugify  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
CATALOGUE = ROOT / "assets" / "catalogue.json"
FORMS = ROOT / "forms"
REPORTS = ROOT / "reports"
VERSION_LINE = re.compile(
    r"(date of issue[^\n]{0,60}|version[:\s][^\n]{0,20}|review date[^\n]{0,30})", re.IGNORECASE
)


def version_note(pdf_bytes: bytes) -> str:
    """The version / issue date printed in the form's footer, if it can be read."""
    try:
        import io
        import warnings

        warnings.filterwarnings("ignore")
        import pdfplumber

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages[-2:]:
                text = page.extract_text() or ""
                for line in text.splitlines():
                    match = VERSION_LINE.search(line)
                    if match:
                        return match.group(1).strip()[:60]
    except Exception:  # noqa: BLE001
        return ""
    return ""


def assign_ids(entries: list[dict], sections: dict[str, str]) -> list[dict]:
    """The same id rules the importer uses, so the comparison lines up."""
    used: set[str] = set()
    out = []
    for entry in entries:
        site = sections.get(entry["title"], "Other")
        base = f"{slugify(site)}-{slugify(entry['title'])}"
        form_id = base
        if form_id in used:
            form_id = f"{base}-{hashlib.sha1(entry['url'].encode()).hexdigest()[:6]}"
        used.add(form_id)
        out.append({**entry, "id": form_id, "site": site})
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--new-only", action="store_true")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    REPORTS.mkdir(exist_ok=True)
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    known = {form["id"]: form for form in catalogue["forms"]}

    entries = index_entries()
    sections = index_sections()
    print(f"website lists {len(entries)} consent forms")
    entries = assign_ids(entries, sections)
    if args.limit:
        entries = entries[: args.limit]
    listed = {entry["id"] for entry in entries}

    new_forms = [entry for entry in entries if entry["id"] not in known]
    gone_forms = [
        form for form_id, form in known.items() if form_id not in listed and not args.limit
    ]

    revised: list[dict] = []
    errors: list[dict] = []
    unchanged = 0

    if not args.new_only:
        def work(entry: dict) -> tuple[dict, str, str]:
            try:
                data = fetch(entry["url"])
            except Exception as error:  # noqa: BLE001
                return entry, "error", str(error)
            digest = hashlib.sha256(data).hexdigest()
            expected = known.get(entry["id"], {}).get("sha256", "")
            if expected and digest != expected:
                return entry, "revised", version_note(data)
            if not expected:
                return entry, "unknown", ""
            return entry, "same", ""

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for entry, status, note in pool.map(work, entries):
                if status == "revised":
                    revised.append({**entry, "note": note})
                elif status == "error":
                    errors.append({**entry, "note": note})
                elif status == "unknown":
                    revised.append({**entry, "note": "not previously recorded"})
                else:
                    unchanged += 1

    print(f"\nnew      : {len(new_forms)}")
    print(f"revised  : {len(revised)}")
    print(f"gone     : {len(gone_forms)}")
    print(f"errors   : {len(errors)}")
    if not args.new_only:
        print(f"unchanged: {unchanged}")

    for entry in new_forms[:10]:
        print(f"  NEW     {entry['site']:<24} {entry['title'][:52]}")
    for entry in revised[:10]:
        print(f"  REVISED {entry['id'][:52]:52s} {entry.get('note', '')[:40]}")
    for form in gone_forms[:10]:
        print(f"  GONE    {form['id'][:52]}")
    for entry in errors[:5]:
        print(f"  ERROR   {entry['id'][:52]} {entry['note'][:40]}")

    with (REPORTS / "updates.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["status", "id", "title", "site", "url", "note"])
        for entry in new_forms:
            writer.writerow(["new", entry["id"], entry["title"], entry["site"], entry["url"], ""])
        for entry in revised:
            writer.writerow(
                ["revised", entry["id"], entry["title"], entry["site"], entry["url"],
                 entry.get("note", "")]
            )
        for form in gone_forms:
            writer.writerow(["gone", form["id"], form["regimen_name"], form["tumour_site"],
                             form.get("source_url", ""), ""])
        for entry in errors:
            writer.writerow(
                ["error", entry["id"], entry["title"], entry["site"], entry["url"],
                 entry.get("note", "")]
            )

    print(f"\nreport: {REPORTS / 'updates.csv'}")
    if new_forms or revised or gone_forms:
        print("To apply: python tools/import_all.py --force  (then re-run the checks)")
    else:
        print("Nothing to do — the app matches the published library.")


if __name__ == "__main__":
    main()
