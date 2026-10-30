"""Serve the release bundle from dist/ with the correct wasm MIME type.

`python -m http.server` does not know `.wasm` (it sends application/octet-stream), and
browsers refuse to instantiate a streaming wasm module with the wrong type. This is also a
decent stand-in for a clinic intranet file server.

Usage:
    trunk build --release
    python tools/serve_dist.py --port 8080
"""

from __future__ import annotations

import argparse
import functools
import http.server
import mimetypes
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        # Revalidate every time: a stale wasm bundle with fresh HTML is the classic
        # "deploy didn't work" bug.
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--address", default="127.0.0.1")
    args = parser.parse_args()

    mimetypes.add_type("application/wasm", ".wasm")
    mimetypes.add_type("text/javascript", ".js")

    if not (DIST / "index.html").exists():
        raise SystemExit("dist/index.html missing - run: trunk build --release")

    handler = functools.partial(Handler, directory=str(DIST))
    with http.server.ThreadingHTTPServer((args.address, args.port), handler) as httpd:
        print(f"serving {DIST} at http://{args.address}:{args.port}")
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
