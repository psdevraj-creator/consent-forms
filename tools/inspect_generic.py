"""Inspect the generic consent forms. (diagnostic)"""

from __future__ import annotations

import io
import pathlib
import re
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import pdfplumber

from import_all import fetch

URLS = {
    "generic-sact": "https://assets.ctfassets.net/u7vsjnoopqo5/6nnZGGjyzjR30z6S9vlX9t/"
    "070fbdb14645740f065370775071ac4e/Generic_SACT.pdf",
    "generic-immunotherapy": "https://assets.ctfassets.net/u7vsjnoopqo5/41z5mZ8wJomS4Cyfr0K1Yx/"
    "d418ee1b1462a86236a97e33e32104ec/generic_checkpoint_inhibitor_immunotherapy_consent_v03-november.pdf",
}

for name, url in URLS.items():
    data = fetch(url)
    path = pathlib.Path("sources") / "forms" / f"{name}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print(f"== {name}: {len(data) / 1024:.0f} KB")
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        print(f"   pages {len(pdf.pages)}")
        for number, page in enumerate(pdf.pages, 1):
            words = page.extract_words()
            boxes = sum(
                1
                for w in words
                if len(w["text"]) <= 2 and not re.search(r"[A-Za-z0-9]", w["text"].replace("c", ""))
            )
            text = page.extract_text() or ""
            heads = [
                line.strip()[:46]
                for line in text.splitlines()
                if re.match(r"(?i)^(common|occasional|other risks|side effect)", line.strip())
            ]
            print(f"   p{number}: words={len(words)} glyphboxes={boxes} heads={heads[:2]}")
