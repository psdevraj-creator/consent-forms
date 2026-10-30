"""Check the graphics-state balance of the pages we produce.

CRUK's own content leaves more `q` than `Q`. A lenient renderer tolerates that; Adobe can
discard everything drawn after it. This counts q and Q across each page's content streams for
a proof and for its original, so an imbalance shows up as a number rather than a surprise on
paper.

    python tools/check_gstate.py <form id> [...]
"""

from __future__ import annotations

import pathlib
import re
import sys

from pypdf import PdfReader

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROOFS = ROOT / "target" / "proofs"
FORMS = ROOT / "forms"

TOKEN = re.compile(rb"(?<![A-Za-z0-9])(q|Q)(?![A-Za-z0-9])")


def balance(path: pathlib.Path, page_index: int) -> tuple[int, int]:
    reader = PdfReader(str(path))
    page = reader.pages[page_index]
    data = page.get_contents().get_data()
    opens = len(TOKEN.findall(data))
    saves = len(re.findall(rb"(?<![A-Za-z0-9])q(?![A-Za-z0-9])", data))
    restores = len(re.findall(rb"(?<![A-Za-z0-9])Q(?![A-Za-z0-9])", data))
    return saves, restores


def main() -> int:
    names = sys.argv[1:] or ["breast-ac-docetaxel", "skin-chop-21"]
    for name in names:
        proof = PROOFS / f"{name}.pdf"
        original = FORMS / f"{name}.pdf"
        if not proof.exists() or not original.exists():
            print(f"{name}: missing")
            continue
        for label, path in (("original", original), ("proof", proof)):
            s, r = balance(path, 1)
            verdict = "balanced" if s == r else f"{'extra q' if s > r else 'extra Q'} x{abs(s - r)}"
            print(f"{name:34s} {label:9s} q={s:4d} Q={r:4d}  {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
