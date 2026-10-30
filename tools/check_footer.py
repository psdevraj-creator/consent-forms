"""Check the modal footer line is clean UTF-8 and reads as intended."""

from __future__ import annotations

import io
import pathlib

path = pathlib.Path(__file__).resolve().parent.parent / "homepage" / "index.html"
text = io.open(path, encoding="utf-8").read()
for line in text.splitlines():
    if 'class="mt-foot"' in line:
        print("line:", repr(line.strip()))
        bad = [ch for ch in line if ord(ch) > 127]
        print("non-ascii:", [f"U+{ord(ch):04X} {ch}" for ch in bad])
for marker in ("\u00c3", "\u00e2\u20ac", "\u00c2"):
    print(f"mojibake {marker!r}:", marker in text)
