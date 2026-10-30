"""Rebuild the embedded catalogue from the form bundles that were written.

CRUK lists a few regimens under more than one tumour section (hydroxycarbamide appears in
both AML and CML), which produced duplicate ids. This keeps one entry per id — the one with
the most side effects — so the dropdown never offers the same regimen twice.

Usage:
    python tools/rebuild_catalogue.py
"""

from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
FORMS = ROOT / "site" / "consent" / "forms"
OUT = ROOT / "assets" / "catalogue.json"


def main() -> None:
    best: dict[str, dict] = {}

    for path in sorted(FORMS.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        form_id = data.get("id") or path.stem
        count = sum(len(group.get("items", [])) for group in data.get("groups", []))
        entry = {
            "id": form_id,
            "tumour_site": data.get("tumour_site", "Other"),
            "regimen_name": data.get("regimen_name", form_id),
            "therapy": "sact",
            "side_effect_count": count,
            "statement_count": len(data.get("statements", [])),
        }
        current = best.get(form_id)
        if current is None or count > current["side_effect_count"]:
            if current is not None:
                print(f"duplicate id {form_id}: keeping {count} items over {current['side_effect_count']}")
            best[form_id] = entry

    forms = sorted(best.values(), key=lambda item: (item["tumour_site"], item["regimen_name"]))
    OUT.write_text(
        json.dumps({"version": "cr-brand-2026-10-28", "forms": forms}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    sites = sorted({form["tumour_site"] for form in forms})
    print(f"wrote {OUT.relative_to(ROOT)}: {len(forms)} forms across {len(sites)} tumour sites")


if __name__ == "__main__":
    main()
