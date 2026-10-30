"""Check the 'More tools' wiring in the patched homepage."""

from __future__ import annotations

import pathlib

html = (pathlib.Path(__file__).resolve().parent.parent / "homepage" / "index.html").read_text(
    encoding="utf-8"
)

probes = [
    "card-more",
    'id="tools-grid"',
    "more-tools",
    "show-more",
    "repeat(4,",
    "@media (max-width: 640px)",
]
for probe in probes:
    print(f"{probe!r:<26} {html.count(probe)}")

# Which cards carry the card-more class?
import re

for match in re.finditer(r'<a href="([^"]+)" class="tool-card([^"]*)"', html):
    if "card-more" in match.group(2):
        print("behind More tools:", match.group(1))
