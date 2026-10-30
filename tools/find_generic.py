"""Find how the generic consent forms are marked up on the CRUK index. (diagnostic)"""

from __future__ import annotations

import pathlib
import re
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from import_all import INDEX, fetch

HTML = fetch(INDEX).decode("utf-8", "replace")

for match in re.finditer(r'href="([^"]*\.pdf[^"]*)"', HTML):
    url = match.group(1)
    if "generic" in url.lower():
        print("PDF:", url)

index = HTML.find("Generic SACT form")
print("title at", index)
if index > 0:
    print(HTML[max(0, index - 600) : index + 200].replace("><", ">\n<"))
