"""Print the DevStat card anchor and the More tools button, to confirm the wiring."""

from __future__ import annotations

import pathlib

html = (pathlib.Path(__file__).resolve().parent.parent / "homepage" / "index.html").read_text(
    encoding="utf-8"
)

heading = html.find("<h3>DevStat Statistics App</h3>")
anchor = html.rfind("<a ", 0, heading)
print("DevStat card:", html[anchor : anchor + 180])

button = html.find('id="more-tools"')
print("\nbutton:", html[max(0, button - 80) : button + 120])

print("\nscript present:", "classList.toggle" in html)
print("css present:   ", ".tools-grid.show-more" in html)
