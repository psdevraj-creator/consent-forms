"""Look at the table structure of the generic consent forms. (diagnostic)"""

from __future__ import annotations

import pathlib
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import pdfplumber

for name in ("generic-sact", "generic-immunotherapy"):
    path = pathlib.Path("sources") / "forms" / f"{name}.pdf"
    with pdfplumber.open(path) as pdf:
        print(f"== {name}")
        for number, page in enumerate(pdf.pages[:3], 1):
            tables = page.extract_tables()
            print(f"   p{number}: {len(tables)} tables")
            for table in tables[:1]:
                for row in table[:6]:
                    cleaned = [(cell or "").replace("\n", " ")[:38] for cell in row]
                    print("      ", cleaned)
