"""Fetch the official CRUK SACT and RCR radiotherapy consent forms, then extract their text.

Provenance-first: every downloaded PDF records its source URL, sha256 and fetch date in
``sources/manifest.json`` so the printed copy can name the exact document version used.

Usage:
    python tools/fetch_forms.py            # download anything missing, then extract text
    python tools/fetch_forms.py --force    # re-download everything
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import pathlib
import re
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "sources" / "pdf"
TEXT_DIR = ROOT / "sources" / "text"
MANIFEST = ROOT / "sources" / "manifest.json"

UA = {"User-Agent": "Mozilla/5.0 (compatible; consent-form-fetcher/1.0)"}

CRUK_INDEX = (
    "https://www.cancerresearchuk.org/health-professional/"
    "treatment-and-other-post-diagnosis-issues/"
    "consent-forms-for-sact-systemic-anti-cancer-therapy"
)
RCR_INDEX = (
    "https://www.rcr.ac.uk/our-services/management-service-delivery/"
    "national-radiotherapy-consent-forms/"
)

# CRUK files are matched on their exact asset filename: titles repeat across tumour-site
# sections (several regimens are called just "Temozolomide"), so title matching is unsafe.
CRUK_FORMS = [
    ("sact-breast-ac-docetaxel", "Breast", "AC-Docetaxel", "breast_ac_-_docetaxel.pdf"),
    (
        "sact-breast-ec",
        "Breast",
        "EC (Epirubicin-Cyclophosphamide)",
        "breast_ec_epirubicin_-_cyclophosphamide.pdf",
    ),
    ("sact-breast-ec-paclitaxel", "Breast", "EC-Paclitaxel", "breast_ec-paclitaxel.pdf"),
    ("sact-cns-temozolomide", "Brain/CNS", "Temozolomide", "Brain_Temozolomide.pdf"),
    (
        "sact-cns-pcv",
        "Brain/CNS",
        "PCV (Procarbazine-Lomustine-Vincristine)",
        "Brain_PCV__Procarbazine-Lomustine-Vincristine_.pdf",
    ),
    (
        "sact-prostate-docetaxel",
        "Urology-Prostate",
        "Docetaxel with Prednisolone",
        "Urology_Prostate_Docetaxel_and_Prednisolone.pdf",
    ),
]

# RCR forms are matched on visible link text, excluding the Welsh-language duplicates.
RCR_FORMS = [
    ("rt-breast-ebrt", "Breast", "Breast Cancer Radiotherapy Consent Form", r"^RCR Breast Cancer Radiotherapy Consent Form$"),
    ("rt-prostate-ebrt", "Urology-Prostate", "Prostate Cancer Radiotherapy Consent Form", r"^RCR Prostate Cancer Radiotherapy Consent Form$"),
    (
        "rt-prostate-ldr-brachy",
        "Urology-Prostate",
        "Low Dose Rate Brachytherapy (with EBRT)",
        r"Low Dose Rate Brachytherapy.*Prostate",
    ),
    ("rt-cns-brain", "Brain/CNS", "Brain Tumours Radiotherapy", r"^RCR Radiotherapy Consent for Brain Tumours$"),
]


def http_get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as response:
        return response.read()


def http_text(url: str) -> str:
    return http_get(url).decode("utf-8", "replace")


def find_cruk_urls() -> dict[str, str]:
    """Map asset filename -> absolute URL for every CRUK consent-form PDF on the index page."""
    html = http_text(CRUK_INDEX)
    found: dict[str, str] = {}
    for match in re.finditer(r'href="(//assets\.ctfassets\.net/[^"]+\.pdf)"', html):
        url = "https:" + match.group(1)
        found[url.rsplit("/", 1)[-1]] = url
    return found


def find_rcr_urls() -> dict[str, str]:
    """Map visible anchor text -> absolute URL for every RCR consent-form PDF on the index page."""
    html = http_text(RCR_INDEX)
    found: dict[str, str] = {}
    for match in re.finditer(r'<a\b[^>]*href="([^"]+\.pdf)"[^>]*>([\s\S]*?)</a>', html):
        href = match.group(1)
        text = re.sub(r"<[^>]+>", " ", match.group(2))
        text = re.sub(r"\s+", " ", text.replace("&amp;", "&")).strip()
        url = href if href.startswith("http") else "https://www.rcr.ac.uk" + href
        found[text] = url
    return found


def extract_text(pdf_bytes: bytes) -> str:
    import pdfplumber  # imported late so --help works without the dependency

    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            pages.append(f"--- page {number} ---\n{page.extract_text() or ''}")
    return "\n".join(pages)


def common_metadata(text: str) -> dict[str, str]:
    """Pull the printed version/date-of-issue line that CRUK and RCR place in the footer."""
    version = ""
    match = re.search(
        r"Date of issue(?: and version)?:?\s*([^\n]{0,60})", text, re.IGNORECASE
    )
    if match:
        version = match.group(1).strip()
    if not version:
        match = re.search(r"\b(?:review(?:ed)?|version)\b[^\n]{0,40}?(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", text, re.IGNORECASE)
        if match:
            version = f"{match.group(1).capitalize()} {match.group(2)}"
    return {"version_line": version}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="re-download PDFs already present")
    args = parser.parse_args()

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    TEXT_DIR.mkdir(parents=True, exist_ok=True)

    print("INDEX  cancerresearchuk.org ...", end=" ", flush=True)
    cruk = find_cruk_urls()
    print(f"{len(cruk)} pdfs")
    print("INDEX  rcr.ac.uk ...", end=" ", flush=True)
    rcr = find_rcr_urls()
    print(f"{len(rcr)} pdfs")

    entries = []
    jobs = []

    # --- CRUK jobs are keyed by asset filename -------------------------------------------
    for key, site, regimen, filename in CRUK_FORMS:
        url = cruk.get(filename)
        if url is None:
            print(f"  MISS  {key}: {filename} not listed on the CRUK index", file=sys.stderr)
            continue
        jobs.append(("cruk", key, site, regimen, filename, "Cancer Research UK", url))

    # --- RCR jobs are keyed by anchor text ----------------------------------------------
    for key, site, regimen, pattern in RCR_FORMS:
        regex = re.compile(pattern, re.IGNORECASE)
        match = next((u for text, u in rcr.items() if regex.search(text) and "Welsh" not in text), None)
        if match is None:
            print(f"  MISS  {key}: no RCR link matched {pattern!r}", file=sys.stderr)
            continue
        jobs.append(("rcr", key, site, regimen, pattern, "The Royal College of Radiologists", match))

    for _kind, key, site, regimen, _name, org, url in jobs:
        pdf_path = PDF_DIR / f"{key}.pdf"
        text_path = TEXT_DIR / f"{key}.txt"
        if pdf_path.exists() and not args.force:
            data = pdf_path.read_bytes()
            print(f"  skip  {key}")
        else:
            print(f"  get   {key} ...", end=" ", flush=True)
            data = http_get(url)
            pdf_path.write_bytes(data)
            print(f"{len(data) // 1024} KB")

        if not text_path.exists() or args.force:
            text = extract_text(data)
            text_path.write_text(text, encoding="utf-8")
        else:
            text = text_path.read_text(encoding="utf-8")

        meta = common_metadata(text)
        entries.append(
            {
                "id": key,
                "organisation": org,
                "tumour_site": site,
                "regimen_name": regimen,
                "source_url": url,
                "sha256": sha256(data),
                "fetched_on": dt.date.today().isoformat(),
                "pages": text.count("--- page "),
                **meta,
            }
        )

    MANIFEST.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nmanifest: {MANIFEST.relative_to(ROOT)} ({len(entries)} forms)")
    for entry in entries:
        print(f"  {entry['id']:<28} {entry['pages']} pages  version={entry['version_line']!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
