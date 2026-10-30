"""Serve the built site exactly as it will be uploaded.

    site/consent.html   ->  http://127.0.0.1:8080/consent.html
    site/consent/*      ->  http://127.0.0.1:8080/consent/*

Usage:
    trunk build --release
    python tools/package_site.py
    python tools/serve_site.py
"""

from __future__ import annotations

import argparse
import functools
import http.server
import mimetypes
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE = ROOT / "site"


class Handler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        # During development the bundles are not copied into site/ (trunk build wipes that
        # folder), so serve consent/forms/* straight from the project's forms/ directory.
        # A real copy in site/ still wins, so the final packaged layout can be checked too.
        resolved = pathlib.Path(super().translate_path(path))
        if not resolved.exists() and path.startswith("/consent/forms/"):
            name = path.rsplit("/", 1)[-1]
            candidate = ROOT / "forms" / name
            if candidate.exists():
                return str(candidate)
        return str(resolved)

    def end_headers(self) -> None:
        # Revalidate every time: a stale wasm bundle with fresh HTML is the classic
        # "deploy didn't work" bug.
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--address", default="127.0.0.1")
    args = parser.parse_args()

    mimetypes.add_type("application/wasm", ".wasm")
    mimetypes.add_type("text/javascript", ".js")

    if not (SITE / "consent.html").exists():
        raise SystemExit("site/consent.html missing - run: trunk build --release && "
                         "python tools/package_site.py")

    handler = functools.partial(Handler, directory=str(SITE))
    with http.server.ThreadingHTTPServer((args.address, args.port), handler) as httpd:
        print(f"serving {SITE} at http://{args.address}:{args.port}/consent.html")
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
