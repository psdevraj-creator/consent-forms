"""Compare every link on the live homepage with the patched copy.

Anything added, removed or altered shows up here, so a card insertion cannot silently break
a nav item, a video preview or an external link.

Usage:
    python tools/compare_homepage_links.py
"""

from __future__ import annotations

import pathlib
import re
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
PATCHED = ROOT / "homepage" / "index.html"
LIVE = "https://dpsoncology.com/"

LINK = re.compile(r'(?:href|src)="([^"]+)"')


def links(html: str) -> list[str]:
    return [value.strip() for value in LINK.findall(html)]


def main() -> None:
    live = urllib.request.urlopen(
        urllib.request.Request(LIVE, headers={"User-Agent": "Mozilla/5.0"}), timeout=90
    ).read().decode("utf-8")
    patched = PATCHED.read_text(encoding="utf-8")

    live_links = links(live)
    patched_links = links(patched)

    added = [l for l in patched_links if l not in live_links]
    removed = [l for l in live_links if l not in patched_links]

    print(f"live links:    {len(live_links)}")
    print(f"patched links: {len(patched_links)}")
    print(f"added:   {added}")
    print(f"removed: {removed}")

    if removed:
        raise SystemExit("a link from the live page is missing in the patched copy")

    # Anything that is not a full URL must resolve from the site root, where this file goes.
    relative = sorted({l for l in patched_links if not re.match(r"^(https?:|mailto:|#|data:)", l)})
    print(f"\nrelative links that must exist on the server ({len(relative)}):")
    for link in relative:
        print("  ", link)


if __name__ == "__main__":
    main()
