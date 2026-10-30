"""Build one self-contained HTML file that runs from a USB stick.

Browsers refuse to load a `.wasm` module from `file://`, so the normal Trunk output needs a
server. This bundles the wasm into the HTML as base64, uses the `no-modules` glue, and
inlines the CSS, so the result is a single file with no external requests of any kind.

Usage:
    python tools/bundle_single_file.py
    -> dist/DPSOncconsent.html
"""

from __future__ import annotations

import base64
import pathlib
import shutil
import subprocess
import sys
import textwrap

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD_DIR = ROOT / "build" / "single"
OUT = ROOT / "dist" / "consent.html"
STYLES = ROOT / "styles.css"
WASM_ARTEFACT = ROOT / "target" / "wasm32-unknown-unknown" / "release" / "consent-form.wasm"


def find_wasm_bindgen() -> pathlib.Path:
    """Prefer the copy Trunk already downloaded, so versions match the crate."""
    cache = pathlib.Path.home() / "AppData" / "Local" / "trunkrs" / "trunk" / "cache"
    candidates = sorted(cache.glob("wasm-bindgen-*/wasm-bindgen.exe"))
    if candidates:
        return candidates[-1]
    found = shutil.which("wasm-bindgen")
    if found:
        return pathlib.Path(found)
    raise SystemExit("wasm-bindgen not found: run `trunk build --release` once to fetch it")


def run(command: list[str]) -> None:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise SystemExit(f"{command[0]} failed:\n{result.stderr[-2000:]}")


def main() -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    print("building wasm ...", end=" ", flush=True)
    run(["cargo", "build", "--release", "--target", "wasm32-unknown-unknown"])
    print("ok")

    if not WASM_ARTEFACT.exists():
        raise SystemExit(f"missing {WASM_ARTEFACT}")

    print("generating glue ...", end=" ", flush=True)
    run(
        [
            str(find_wasm_bindgen()),
            "--target",
            "no-modules",
            "--no-typescript",
            "--out-dir",
            str(BUILD_DIR),
            str(WASM_ARTEFACT),
        ]
    )
    print("ok")

    glue = next(BUILD_DIR.glob("*.js")).read_text(encoding="utf-8")
    wasm = next(BUILD_DIR.glob("*.wasm")).read_bytes()
    css = STYLES.read_text(encoding="utf-8")
    encoded = base64.b64encode(wasm).decode("ascii")

    html = textwrap.dedent(
        """\
        <!doctype html>
        <html lang="en-GB">
          <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <meta name="referrer" content="no-referrer" />
            <!--
              Single-file build. Everything below is inline: there is no network request of
              any kind, so connect-src can stay 'none'. 'wasm-unsafe-eval' is required to
              instantiate the module, and 'unsafe-inline' because the code is inline by
              definition.
            -->
            <meta
              http-equiv="Content-Security-Policy"
              content="default-src 'none'; script-src 'unsafe-inline' 'wasm-unsafe-eval'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'"
            />
            <link
              rel="icon"
              href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Crect width='16' height='16' fill='%230f4c81'/%3E%3C/svg%3E"
            />
            <title>Consent form builder</title>
            <style>
        __CSS__
            </style>
          </head>
          <body>
            <div id="root"></div>
            <script>
        __GLUE__
            </script>
            <script>
              const WASM_B64 = "__WASM__";
              const binary = atob(WASM_B64);
              const bytes = new Uint8Array(binary.length);
              for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
              wasm_bindgen(bytes).catch(function (error) {
                document.body.innerHTML =
                  '<pre style="padding:2rem;font:14px monospace">Could not start: ' +
                  String(error) +
                  "</pre>";
              });
            </script>
          </body>
        </html>
        """
    )

    html = html.replace("__CSS__", css).replace("__GLUE__", glue).replace("__WASM__", encoded)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")

    size_mb = OUT.stat().st_size / (1024 * 1024)
    print(f"wrote {OUT.relative_to(ROOT)}  ({size_mb:.2f} MB)")


if __name__ == "__main__":
    sys.exit(main())
