"""Re-key the earlier title-named PDF cache to URL-keyed names, so a re-extraction does not
have to download everything again.

Titles that appear more than once on the index are skipped: their cached file could belong
to either entry, so those are fetched fresh.

Usage:
    python tools/migrate_cache.py
"""

from __future__ import annotations

import collections
import hashlib
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from import_all import FORMS, index_entries, slugify  # noqa: E402


def main() -> None:
    entries = index_entries()
    counts = collections.Counter(entry["title"] for entry in entries)

    migrated = 0
    skipped = 0
    for entry in entries:
        if counts[entry["title"]] > 1:
            skipped += 1
            continue
        target = FORMS / ("url-" + hashlib.sha1(entry["url"].encode("utf-8")).hexdigest()[:16] + ".pdf")
        if target.exists():
            continue
        source = FORMS / f"{slugify(entry['title'])}.pdf"
        if source.exists():
            shutil.copyfile(source, target)
            migrated += 1

    print(f"migrated {migrated} cached PDFs; {skipped} entries with duplicate titles left to fetch")


if __name__ == "__main__":
    main()
