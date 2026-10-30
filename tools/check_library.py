"""Check the imported library: coverage, parse quality, and catalogue consistency."""

from __future__ import annotations

import collections
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
FORMS = ROOT / "forms"
CATALOGUE = ROOT / "assets" / "catalogue.json"


def main() -> None:
    catalogue = json.loads(CATALOGUE.read_text(encoding="utf-8"))["forms"]
    ids = [form["id"] for form in catalogue]
    duplicates = [key for key, count in collections.Counter(ids).items() if count > 1]

    bundles = {path.stem for path in FORMS.glob("*.json")}
    pdfs = {path.stem for path in FORMS.glob("*.pdf")}

    missing_json = [key for key in ids if key not in bundles]
    missing_pdf = [key for key in ids if key not in pdfs]
    orphan = [key for key in bundles if key not in set(ids)]

    sites = collections.Counter(form["tumour_site"] for form in catalogue)
    empty = [key for key, count in ((f["id"], f["side_effect_count"]) for f in catalogue) if count == 0]
    few = sorted(((f["side_effect_count"], f["id"]) for f in catalogue))[:5]

    in_box = 0
    in_margin = 0
    no_statements: list[str] = []
    for path in FORMS.glob("*.json"):
        bundle = json.loads(path.read_text(encoding="utf-8"))
        if not bundle.get("statements"):
            no_statements.append(path.stem)
        for item in bundle.get("side_effects", []):
            if item.get("box_x") is not None:
                in_box += 1
            else:
                in_margin += 1

    size_mb = sum(path.stat().st_size for path in FORMS.iterdir()) / (1024 * 1024)

    print(f"catalogue forms : {len(catalogue)}")
    print(f"bundles on disk : {len(bundles)}  ({size_mb:.1f} MB)")
    print(f"pdfs on disk    : {len(pdfs)}")
    print(f"duplicate ids   : {duplicates or 'none'}")
    print(f"missing json    : {missing_json[:5] or 'none'}")
    print(f"missing pdf     : {missing_pdf[:5] or 'none'}")
    print(f"orphan bundles  : {orphan[:5] or 'none'}")
    print(f"zero side effects: {empty[:5] or 'none'}")
    print(f"\nticks inside a printed box : {in_box}")
    print(f"ticks in the margin        : {in_margin}")
    print(f"forms with no declarations : {len(no_statements)} {no_statements[:5]}")
    print(f"\nfewest side effects: {few}")
    print(f"\ntumour sites ({len(sites)}):")
    for site, count in sites.most_common():
        print(f"  {site:<34} {count}")


if __name__ == "__main__":
    main()
