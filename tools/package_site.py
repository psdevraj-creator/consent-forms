"""Arrange the built site as the web host expects it.

    site/
      consent.html          <- the page you link to
      consent/              <- everything else (js, wasm, css)

Trunk writes the page and its assets into `site/consent/`; this script lifts the page to
the root as `consent.html` and leaves the assets where they are.

Usage:
    trunk build --release
    python tools/package_site.py
"""

from __future__ import annotations

import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "site" / "consent"
PAGE = ROOT / "site" / "consent.html"


def main() -> None:
    built = ASSETS_DIR / "index.html"
    if built.exists():
        shutil.copyfile(built, PAGE)
        built.unlink()
    elif not PAGE.exists():
        raise SystemExit("site/consent/index.html missing - run: trunk build --release")

    # The per-form bundles live outside the build output, because `trunk build` wipes site/.
    forms_src = ROOT / "forms"
    forms_dst = ASSETS_DIR / "forms"
    if forms_src.exists():
        if forms_dst.exists():
            shutil.rmtree(forms_dst)
        shutil.copytree(forms_src, forms_dst)
        count = len(list(forms_dst.glob("*.json")))
        size_mb = sum(p.stat().st_size for p in forms_dst.iterdir()) / (1024 * 1024)
        print(f"forms: {count} bundles, {size_mb:.1f} MB")
    else:
        print("forms: none (run tools/import_all.py)")

    html = PAGE.read_text(encoding="utf-8")
    referenced = [chunk for chunk in html.split('"') if chunk.startswith("/consent/")]
    print(f"wrote {PAGE.relative_to(ROOT)}")
    print(f"assets in {ASSETS_DIR.relative_to(ROOT)}: "
          f"{', '.join(sorted(p.name for p in ASSETS_DIR.iterdir()))}")
    print(f"links into /consent/: {len(referenced)}")


if __name__ == "__main__":
    main()
