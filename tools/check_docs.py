"""Check the docs are clean UTF-8 with no mojibake. (source of truth guard)"""

from __future__ import annotations

import pathlib

ALLOWED = set("—–’“”…°®™©§±×·→≈│├└─▲▼►•✓✔")


def main() -> None:
    root = pathlib.Path(__file__).resolve().parent.parent
    for name in ("README.md", "HANDOVER.md"):
        with (root / name).open(encoding="utf-8") as handle:
            text = handle.read()
        odd = sorted({ch for ch in text if ord(ch) > 127 and ch not in ALLOWED})
        mojibake = any(marker in text for marker in ("\u00c3", "\u00e2\u20ac", "\u00c2"))
        readable = ", ".join(f"U+{ord(ch):04X}" for ch in odd) or "none"
        print(f"{name}: {len(text)} chars, unexpected {readable}, mojibake {mojibake}")


if __name__ == "__main__":
    main()
