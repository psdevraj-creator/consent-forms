"""Count the CRUK SACT consent forms available to import."""

from __future__ import annotations

import re
import urllib.request

URL = (
    "https://www.cancerresearchuk.org/health-professional/"
    "treatment-and-other-post-diagnosis-issues/"
    "consent-forms-for-sact-systemic-anti-cancer-therapy"
)


def main() -> None:
    request = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(request, timeout=90).read().decode("utf-8", "replace")

    pdfs = set(re.findall(r'href="(//assets\.ctfassets\.net/[^"]+\.pdf)"', html))
    titles = {
        title.strip()
        for title in re.findall(r'<a[^>]*title="([^"]{2,90})"[^>]*href="//assets\.ctfassets\.net/', html)
    }

    print(f"unique PDF files: {len(pdfs)}")
    print(f"unique link titles: {len(titles)}")


if __name__ == "__main__":
    main()
