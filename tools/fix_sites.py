"""Assign each form to its tumour site from the CRUK index page.

The index lists regimens inside accordions; the section name sits in
`<span class="css-1eziwv">…</span>` immediately before that section's PDF links. This reads
the index once, maps each link title to its section, then rewrites the tumour site in every
form bundle and rebuilds the catalogue.

Usage:
    python tools/fix_sites.py
"""

from __future__ import annotations

import json
import pathlib
import re
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
FORMS = ROOT / "site" / "consent" / "forms"
OUT = ROOT / "assets" / "catalogue.json"
INDEX = (
    "https://www.cancerresearchuk.org/health-professional/"
    "treatment-and-other-post-diagnosis-issues/"
    "consent-forms-for-sact-systemic-anti-cancer-therapy"
)

ALIASES = {
    "Breast cancers": "Breast",
    "Central Nervous System (CNS) tumours": "Brain/CNS",
    "Brain tumours": "Brain/CNS",
    "Urology-Bladder cancer": "Urology-Bladder",
    "Urology-Prostate cancer": "Urology-Prostate",
    "Urology-Kidney cancer": "Urology-Kidney",
    "Urology-Testicular cancer": "Urology-Testicular",
    "Upper Gastro-intestinal cancers": "Upper GI",
    "Lower Gastro-intestinal cancers": "Colorectal",
    "Gynaecological cancers": "Gynaecological",
    "Head and neck cancers": "Head and Neck",
    "Lung cancers": "Lung",
    "Skin cancers": "Skin",
    "Sarcoma": "Sarcoma",
    "Lymphomas": "Lymphoma",
    "Acute Lymphoblastic Leukaemia (ALL)": "Haematology-ALL",
    "Acute Myeloid Leukaemia (AML)": "Haematology-AML",
    "Chronic Lymphocytic Leukaemia (CLL)": "Haematology-CLL",
    "Chronic Myeloid Leukaemia (CML)": "Haematology-CML",
    "Myeloma": "Haematology-Myeloma",
    "Myeloproliferative neoplasms": "Haematology-MPN",
    "Children and young people": "Children and Young People",
}


def tidy(label: str) -> str:
    label = label.strip()
    if label in ALIASES:
        return ALIASES[label]
    label = re.sub(r"\s*\((.*?)\)\s*$", "", label)
    label = re.sub(r"\s+(cancers?|tumours?)$", "", label, flags=re.I)
    return label.strip() or "Other"


def index_sections() -> dict[str, str]:
    """Map every link title on the index to the accordion section it sits under."""
    html = urllib.request.urlopen(
        urllib.request.Request(INDEX, headers={"User-Agent": "Mozilla/5.0"}), timeout=90
    ).read().decode("utf-8", "replace")

    pattern = re.compile(
        r'<span class="css-1eziwv">([^<]{3,90})</span>'
        r'|<a[^>]*title="([^"]{2,90})"[^>]*href="(//assets\.ctfassets\.net/[^"]+\.pdf)"',
    )

    section = "Other"
    titles: dict[str, str] = {}
    for match in pattern.finditer(html):
        label, title, _url = match.groups()
        if label:
            section = tidy(label)
            continue
        if title and title not in titles:
            titles[title.strip()] = section
    return titles


def main() -> None:
    sections = index_sections()
    print(f"index sections mapped: {len(sections)} titles")

    catalogue: dict[str, dict] = {}
    changed = 0

    for path in sorted(FORMS.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        title = data.get("regimen_name", "")
        site = sections.get(title, data.get("tumour_site", "Other"))
        if site != data.get("tumour_site"):
            data["tumour_site"] = site
            path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
            changed += 1

        count = sum(len(group.get("items", [])) for group in data.get("groups", []))
        entry = {
            "id": data.get("id", path.stem),
            "tumour_site": site,
            "regimen_name": title,
            "therapy": "sact",
            "side_effect_count": count,
            "statement_count": len(data.get("statements", [])),
        }
        best = catalogue.get(entry["id"])
        if best is None or count > best["side_effect_count"]:
            catalogue[entry["id"]] = entry

    forms = sorted(catalogue.values(), key=lambda item: (item["tumour_site"], item["regimen_name"]))
    OUT.write_text(
        json.dumps({"version": "cr-brand-2026-10-28", "forms": forms}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    sites = sorted({form["tumour_site"] for form in forms})
    print(f"updated {changed} bundles")
    print(f"catalogue: {len(forms)} forms across {len(sites)} sites")
    for site in sites:
        count = sum(1 for form in forms if form["tumour_site"] == site)
        print(f"  {site:<28} {count}")


if __name__ == "__main__":
    main()
