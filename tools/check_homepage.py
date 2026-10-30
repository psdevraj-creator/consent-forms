"""Verify the patched homepage: card count, card titles, and the grid setting."""

from __future__ import annotations

import pathlib
import re

html = (pathlib.Path(__file__).resolve().parent.parent / "homepage" / "index.html").read_text(
    encoding="utf-8"
)

cards = re.findall(r'class="tool-card card-[a-z]+"', html)
titles = re.findall(r"<h3>([^<]+)</h3>", html)
grid = re.search(r"\.tools-grid\s*\{[^}]*\}", html)

print(f"cards: {len(cards)}")
for title in titles:
    print("  -", title.strip())
print("grid:", " ".join(grid.group(0).split()) if grid else "not found")

index = html.find("Consent Forms")
print("\ncontext:")
print(" ".join(html[index - 300 : index + 260].split()))
