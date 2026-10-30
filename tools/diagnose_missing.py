"""Which of the forms that produced no side effects now work? (diagnostic)"""

from __future__ import annotations

import hashlib
import pathlib
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from import_all import (
    FORMS,
    extract_side_effects,
    index_entries,
    index_sections,
    slugify,
)

TARGETS = [
    "children-and-young-people-all-in-children-and-young-people",
    "head-and-neck-nivolumab",
    "colorectal-pembrolizumab",
    "melanoma-skin-ipilimumab",
    "skin-bexarotene",
    "skin-interferon-alfa-2a-roferon-a",
    "open-to-read-faqs-in-this-document",
]


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
        if not any(target in form_id for target in TARGETS):
            continue
        cache = FORMS / f"url-{hashlib.sha1(entry['url'].encode()).hexdigest()[:16]}.pdf"
        if not cache.exists():
            print(f"{form_id:52s} NO CACHED PDF")
            continue
        groups = extract_side_effects(cache)
        counts = [(group["heading"][:10], len(group["items"])) for group in groups]
        print(f"{form_id:52s} {counts}")


if __name__ == "__main__":
    main()
