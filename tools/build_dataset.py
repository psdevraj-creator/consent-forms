"""Merge hand-transcribed side-effect content with the PDF provenance manifest.

`sources/content.json` holds the wording (authored from the PDFs in `sources/pdf`).
`sources/manifest.json` holds what was downloaded and when. This script joins them into
`assets/consent_forms.json`, which is compiled into the wasm binary.

Usage:
    python tools/build_dataset.py
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONTENT = ROOT / "sources" / "content.json"
MANIFEST = ROOT / "sources" / "manifest.json"
OUTPUT = ROOT / "assets" / "consent_forms.json"

MONTHS = {
    "jan": "January",
    "feb": "February",
    "mar": "March",
    "apr": "April",
    "may": "May",
    "jun": "June",
    "jul": "July",
    "aug": "August",
    "sep": "September",
    "oct": "October",
    "nov": "November",
    "dec": "December",
}

# CRUK prints "Date of issue: June-25; Version 4; Review date: June-28".
CRUK_VERSION = re.compile(
    r"([A-Za-z]{3,9})-(\d{2});\s*Version\s*(\d+);\s*Review date:\s*([A-Za-z]{3,9})-(\d{2})"
)


def month_year(token: str, year: str) -> str:
    month = MONTHS.get(token[:3].lower(), token)
    return f"{month} 20{year}"


def clean_version(raw: str) -> str:
    """Turn the printed version string into one readable sentence."""
    text = raw.split("Page ")[0].strip().rstrip(".").strip()
    match = CRUK_VERSION.search(text)
    if match:
        issued_month, issued_year, version, review_month, review_year = match.groups()
        return (
            f"Version {version}, issued {month_year(issued_month, issued_year)}, "
            f"review due {month_year(review_month, review_year)}"
        )
    return text


def main() -> None:
    content = json.loads(CONTENT.read_text(encoding="utf-8"))
    manifest = {entry["id"]: entry for entry in json.loads(MANIFEST.read_text(encoding="utf-8"))}

    templates = []
    for form in content["forms"]:
        # Radiotherapy forms are parked: the app currently ships the SACT forms only.
        # Remove this filter to bring them back (the PDFs and coordinate files are still
        # in sources/pdf and assets/form_fields).
        if form["therapy"] != "sact":
            continue

        form_id = form["id"]
        if form_id not in manifest:
            raise SystemExit(f"{form_id}: no matching PDF in sources/manifest.json")

        source = manifest[form_id]
        version = clean_version(source.get("version_line", ""))
        if not version:
            raise SystemExit(f"{form_id}: could not read a version from the PDF footer")

        groups = [
            {"heading": group["heading"], "items": group["items"]} for group in form["groups"]
        ]
        side_effects = [item for group in groups for item in group["items"]]

        # The RCR forms genuinely repeat some side effects in both the early and the
        # late lists, so only a repeat *within one group* is a transcription error.
        for group in groups:
            seen: set[str] = set()
            for item in group["items"]:
                if item in seen:
                    raise SystemExit(f"{form_id}: duplicate in {group['heading']}: {item[:60]}")
                seen.add(item)

        templates.append(
            {
                "id": form_id,
                "therapy": form["therapy"],
                "tumour_site": form["tumour_site"],
                "regimen_name": form["regimen_name"],
                "side_effects": side_effects,
                "side_effect_groups": groups,
                "source": {
                    "organisation": source["organisation"],
                    "document_title": form["document_title"],
                    "source_url": source["source_url"],
                    "version": version,
                    "sha256": source["sha256"],
                    "fetched_on": source["fetched_on"],
                },
            }
        )

    dataset = {
        "version": content["_content_version"],
        "generated_on": dt.date.today().isoformat(),
        "templates": templates,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(dataset, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    total = sum(len(t["side_effects"]) for t in templates)
    print(f"wrote {OUTPUT.relative_to(ROOT)}: {len(templates)} forms, {total} side effects")
    for template in templates:
        print(
            f"  {template['id']:<26} {template['tumour_site']:<16} "
            f"{len(template['side_effects']):>2} items  v={template['source']['version']}"
        )


if __name__ == "__main__":
    main()
