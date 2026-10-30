"""Show why one cached PDF yields no side effects. (diagnostic)"""

from __future__ import annotations

import hashlib
import pathlib
import re
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import pdfplumber
from import_all import FORMS, index_entries, index_sections, slugify

TARGET = sys.argv[1] if len(sys.argv) > 1 else "melanoma-skin-ipilimumab"


def main() -> None:
    entries = index_entries()
    sections = index_sections()
    used: set[str] = set()
    for entry in entries:
        site = sections.get(entry["title"], "Other")
        base = f"{slugify(site)}-{slugify(entry['title'])}"
        form_id = base
        if form_id in used:
            form_id = f"{base}-{hashlib.sha1(entry['url'].encode()).hexdigest()[:6]}"
        used.add(form_id)
        if not form_id.startswith(TARGET):
            continue
        cache = FORMS / f"url-{hashlib.sha1(entry['url'].encode()).hexdigest()[:16]}.pdf"
        if not cache.exists():
            print(form_id, "no cache")
            continue
        with pdfplumber.open(cache) as pdf:
            print(f"== {form_id}  {len(pdf.pages)} pages  {cache.name}")
            for number, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                shapes = f"rects={len(page.rects)} words={len(page.extract_words())}"
                heads = [
                    line.strip()[:50]
                    for line in text.split("\n")
                    if re.match(r"(?i)^(common|occasional|other risks|side effects)", line.strip())
                ]
                print(f"   p{number} {shapes} heads={heads[:3]}")


if __name__ == "__main__":
    main()
